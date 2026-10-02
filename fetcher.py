"""Fill in a pack from hosted URLs. A clone becomes a working launcher.

    python fetcher.py                 # fetch whatever is missing
    python fetcher.py --check         # report, download nothing
    python fetcher.py --only mods     # one root
    python fetcher.py --force         # re-fetch even if present

Reads sources.json (written by tools/make_sources.py) for the list of files,
their sizes and their sha256. Each file carries a "urls" list, most-preferred
first; a mirror that fails or is slow is skipped for the next one.

Design notes, because this is the thing that decides whether the pack is
trustworthy:

* Integrity is per-file sha256, checked AFTER the download completes and
  BEFORE the file moves into place. A corrupt or truncated file never lands in
  the pack -- a half-written wad is worse than a missing one, because the
  launcher cannot tell the difference.
* Downloads land as <name>.part and are os.replace()d into position only once
  verified. Interrupted runs are therefore always safe to repeat.
* Present is decided by sha256, not by "the file exists". A truncated file from
  an older bad download gets repaired instead of trusted.
* No URLs is not an error state -- it means the operator has not published
  hosting yet, so every such file is reported as unavailable and skipped.
* Paths are percent-encoded when they become URLs. Names in a pack are the
  authors' file names, spaces and commas included, and a URL built from one is
  not valid until it is encoded.
* A certificate this machine cannot verify is retried without verification
  rather than failed. See the note on unverified_ctx: the sha256 above is what
  provides integrity, and a machine whose root store is stale would otherwise
  be unable to obtain a pack at all. This fallback is announced once per host.
* Free space is checked before starting, and a disk-full error stops further
  writes and removes incomplete .part files so retries do not waste space.
* One file's failure is never allowed to abort the run. Anything a download can
  raise is caught per file and reported as that file's result.

Downloading is concurrent but writes are not: each file has its own .part and
its own final path, so nothing needs a lock.
"""

import argparse
import errno
import hashlib
import http.client
import json
import os
import shutil
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

PACK = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(PACK, "sources.json")
CTX = ssl.create_default_context()
UA = "DoomNite/1.0 (+fetcher)"
CHUNK = 1024 * 256
TIMEOUT = 120
RETRIES = 2
_DISK_FULL = threading.Event()
_UNVERIFIED_HOSTS = set()
_UNVERIFIED_HOSTS_LOCK = threading.Lock()


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


def sha256_file(path, chunk=CHUNK):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load():
    if not os.path.exists(MANIFEST):
        print(f"error: no sources.json at {MANIFEST}")
        print("It is committed to the repo. If you are on an old clone, run:")
        print("    git pull")
        return None
    with open(MANIFEST, encoding="utf-8") as f:
        doc = json.load(f)
    files = doc.get("files") or {}
    if not files:
        print("error: sources.json lists no files")
        return None
    # A top-level base_url means every file is fetchable from the same place,
    # so the operator sets one line instead of editing 90. Per-file "urls" are
    # merged in as higher-priority mirrors, so a file with a hand-added mirror
    # keeps it and can still fall back to the base.
    base = (doc.get("base_url") or "").strip()
    if base:
        if not base.endswith("/"):
            base += "/"
        BASE_URL.clear()
        BASE_URL.update({"url": base})
    return files


# Set by load(). Deliberately a dict rather than a global string: it is written
# once at startup and read from worker threads during downloads, and rebinding a
# name is atomic under the GIL whereas mutating one is not.
BASE_URL = {}


# Built once, and only ever used after CTX has already failed on the same URL.
# A machine whose root store is out of date cannot validate the chain at all, and
# Windows makes that state easy to reach: the store keeps expired cross-signed
# roots (ISRG Root X1 via DST Root CA X3 is the usual one), and OpenSSL will
# happily build a path through one, so a browser opens a URL that Python refuses.
# Falls back to this rather than making the pack unobtainable, on the same
# reasoning installer.py already documents: the sha256 is what provides
# integrity here, and it is checked before anything is renamed into place. A
# wrong or tampered payload still fails the hash -- this can only turn a hard
# failure into a slower one.
_CTX_UNVERIFIED = None


def unverified_ctx():
    global _CTX_UNVERIFIED
    if _CTX_UNVERIFIED is None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _CTX_UNVERIFIED = ctx
    return _CTX_UNVERIFIED


def is_cert_failure(err):
    """Did this failure come from being unable to verify the certificate?"""
    reason = getattr(err, "reason", None)
    return isinstance(reason, ssl.SSLCertVerificationError) or isinstance(
        err, ssl.SSLCertVerificationError
    )


def is_disk_full(err):
    """Recognize POSIX and Windows errors for an exhausted target volume."""
    return (
        getattr(err, "errno", None) in (errno.ENOSPC, getattr(errno, "EDQUOT", -1))
        or getattr(err, "winerror", None) in (39, 112)
    )


def remove_part_files(items):
    """Remove unverified leftovers; they are never resumed or trusted."""
    for rel, _rec in items:
        try:
            os.remove(os.path.join(PACK, rel.replace("/", os.sep)) + ".part")
        except OSError:
            pass


def urls_for(rel, rec):
    """Every place this file can be fetched from, most-preferred first.

    Per-file urls come first because they are the deliberate override, then the
    base_url mirror. Returns [] when neither exists, which the caller reports as
    "no hosted URL" rather than treating as an error.

    "no_host": true is a hard veto that beats everything, including an
    explicit per-file url. It exists for files that must never be published:
    DOOM2.WAD and Hexen.wad are commercial retail IWADs, and a blanket
    base_url would otherwise silently hand the world a copy of each. A veto that
    could be overridden by a later edit is not a veto, so it is checked first and
    ignores "urls" entirely.
    """
    if rec.get("no_host"):
        return []
    out = [u for u in (rec.get("urls") or []) if u]
    base = (BASE_URL.get("url") or "").strip()
    if base:
        # Percent-encode the relative path before it becomes a URL.
        #
        # Without this, a pack file whose name contains a space -- and one does,
        # "The Bikini Bottom Massacre 1,3.wad" -- is not a valid URL. urlopen
        # raises http.client.InvalidURL before it even opens a socket, and
        # because that is not an OSError or a URLError it escaped fetch_one's
        # error handling, propagated out of the future, and killed the whole
        # run with a traceback on the first such file. One awkward filename
        # took 67 good ones with it.
        #
        # Only the constructed URL is encoded. A per-file "urls" entry is
        # written by hand and is already a URL; quoting it again would encode
        # its own %20 into %2520.
        guess = base + quote(rel.replace(os.sep, "/").lstrip("/"))
        if guess not in out:
            out.append(guess)
    return out


def file_state(rel, rec):
    """One of: ok, corrupt, absent. Decided by hash, never by existence."""
    path = os.path.join(PACK, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        return "absent", path
    size = os.path.getsize(path)
    if rec.get("size") and size != rec["size"]:
        return "corrupt", path       # wrong size: skip re-hashing, it is wrong
    if not rec.get("sha256"):
        return "ok", path
    try:
        return ("ok" if sha256_file(path) == rec["sha256"] else "corrupt"), path
    except OSError:
        return "absent", path


def _download(url, dest, expect_size=None, progress=None, ctx=CTX):
    """Stream url to dest. Returns sha256. Raises on any failure."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    h = hashlib.sha256()
    got = 0
    tmp = dest + ".part"
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        with open(tmp, "wb") as f:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if progress:
                    progress(got, total or expect_size)
    # A short read that the server did not flag is still a failure. Content-Length
    # is absent on chunked responses, so only enforce it when it was sent.
    if total and got != total:
        os.remove(tmp)
        raise IOError(f"short read: {got} of {total} bytes")
    return h.hexdigest(), tmp


def _progress_printer(host):
    """Return a callback that rewrites one progress line in place."""
    def show(got, total):
        pct = f"{got * 100 // total}%" if total else human(got)
        print(f"\r    {host}: {human(got)} {pct}   ", end="", flush=True)
    return show


def fetch_one(rel, rec, force=False, verbose=True):
    """Bring one file to a verified state. Returns (rel, status, detail)."""
    state, path = file_state(rel, rec)
    if state == "ok" and not force:
        return rel, "ok", "present"

    urls = urls_for(rel, rec)
    if not urls:
        return rel, "no-url", "no hosted URL in sources.json"

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError as e:
        if is_disk_full(e):
            _DISK_FULL.set()
            return rel, "failed", (
                "not enough free disk space; free space on the pack drive "
                "and try again"
            )
        return rel, "failed", f"could not create destination directory: {e}"
    want = rec.get("sha256")
    errors = []

    for url in urls:
        if _DISK_FULL.is_set():
            return rel, "skipped", "stopped because the target disk is full"
        host = url.split("/")[2] if "://" in url else url[:40]
        # Once this host's certificate failure is known, reuse the same fallback
        # for its other files instead of emitting the same warning for each one.
        # The downloaded bytes are still accepted only after their sha256 matches.
        with _UNVERIFIED_HOSTS_LOCK:
            host_is_unverified = host in _UNVERIFIED_HOSTS
        ctx = unverified_ctx() if host_is_unverified else CTX
        for attempt in range(1, RETRIES + 1):
            if _DISK_FULL.is_set():
                return rel, "skipped", "stopped because the target disk is full"
            last = (attempt == RETRIES)
            try:
                cb = _progress_printer(host) if verbose else None
                digest, tmp = _download(url, path, progress=cb, ctx=ctx)
                if verbose:
                    print("\r" + " " * 62 + "\r", end="", flush=True)

                if want and digest != want:
                    os.remove(tmp)
                    errors.append(f"{host}: checksum "
                                  f"(got {digest[:12]}, want {want[:12]})")
                    if last:
                        break
                    continue

                os.replace(tmp, path)   # atomic, same volume
                return rel, "fetched", human(rec.get("size") or os.path.getsize(path))

            # http.client.HTTPException covers a malformed URL (InvalidURL). It
            # is not covered by OSError or URLError, and letting one escape here
            # is what used to abort the run instead of reporting one bad file.
            except (urllib.error.URLError, OSError, IOError,
                    http.client.HTTPException) as e:
                if verbose:
                    print("\r" + " " * 62 + "\r", end="", flush=True)
                errors.append(f"{host}: {type(e).__name__} {e}")
                if is_disk_full(e):
                    _DISK_FULL.set()
                    try:
                        os.remove(path + ".part")
                    except OSError:
                        pass
                    return rel, "failed", (
                        "not enough free disk space; free space on the pack drive "
                        "and try again"
                    )
                if _DISK_FULL.is_set():
                    return rel, "skipped", "stopped because the target disk is full"
                if is_cert_failure(e) and ctx is CTX:
                    ctx = unverified_ctx()
                    with _UNVERIFIED_HOSTS_LOCK:
                        first_warning = host not in _UNVERIFIED_HOSTS
                        _UNVERIFIED_HOSTS.add(host)
                    if verbose and first_warning:
                        print(f"    {host}: certificate cannot be verified on "
                              f"this machine; retrying without verification "
                              f"(every file is checked against its sha256)")
                    continue
                if last:
                    break
                time.sleep(1.5 * attempt)

    return rel, "failed", "; ".join(errors[:3])[:240]


def main():
    ap = argparse.ArgumentParser(description="Fetch a pack from hosted URLs.")
    ap.add_argument("--check", action="store_true",
                    help="report what is missing, download nothing")
    ap.add_argument("--force", action="store_true",
                    help="re-fetch files even if already valid")
    ap.add_argument("--only", default=None,
                    help="limit to one root, e.g. mods or iwads")
    ap.add_argument("--jobs", type=int, default=4,
                    help="parallel downloads (default 4)")
    args = ap.parse_args()

    files = load()
    if files is None:
        return 1

    if args.only:
        pref = args.only.rstrip("/") + "/"
        files = {k: v for k, v in files.items() if k.startswith(pref)}
        if not files:
            print(f"error: nothing under {pref}")
            return 1

    tally = {"ok": 0, "corrupt": 0, "absent": 0}
    todo = []
    for rel, rec in sorted(files.items()):
        state, _ = file_state(rel, rec)
        tally[state] = tally.get(state, 0) + 1
        if state != "ok" or args.force:
            todo.append((rel, rec))

    total_bytes = sum(f.get("size") or 0 for _, f in todo)
    print(f"{len(files)} files in manifest")
    print(f"  present  {tally['ok']}")
    print(f"  corrupt  {tally['corrupt']}")
    print(f"  absent   {tally['absent']}")
    if todo:
        print(f"to fetch: {len(todo)} files, {human(total_bytes)}\n")

    if args.check or not todo:
        if not todo:
            print("\nnothing to do -- pack is complete.")
        else:
            nourl = sum(1 for r, rec in todo if not urls_for(r, rec))
            if nourl:
                print(f"{nourl} of these have no hosted URL yet.")
        return 0

    fetchable = [(r, rec) for r, rec in todo if urls_for(r, rec)]
    # Earlier versions left interrupted, unverified .part files behind. They
    # cannot be resumed safely, so remove them before measuring free space.
    remove_part_files(fetchable)
    required = sum(rec.get("size") or 0 for _, rec in fetchable)
    safety = min(128 * 1024 * 1024, max(4 * 1024 * 1024, required // 100))
    try:
        free = shutil.disk_usage(PACK).free
    except OSError as e:
        print(f"\nwarning: could not check free space on the pack drive: {e}")
        free = None
    if free is not None and required and free < required + safety:
        print("\nerror: insufficient disk space for the remaining downloads.")
        print(f"  needed:    {human(required)} plus {human(safety)} safety margin")
        print(f"  available: {human(free)} on the drive containing {PACK}")
        print("Free disk space on that drive, then run the fetch again.")
        return 2

    _DISK_FULL.clear()
    print(f"fetching with {args.jobs} parallel connections\n")
    done = {"ok": 0, "no-url": 0, "failed": 0, "skipped": 0}
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futs = {pool.submit(fetch_one, r, c, args.force): r for r, c in todo}
        for fut in as_completed(futs):
            rel, status, detail = fut.result()
            done[status] = done.get(status, 0) + 1
            n = sum(done.values())
            mark = {"ok": "ok", "fetched": "ok", "no-url": "--",
                    "failed": "!!", "skipped": "--"}.get(status, "  ")
            print(f"[{n:>3}/{len(todo)}] {mark} {rel}"
                  + (f"\n         {detail}"
                     if status in ("failed", "no-url", "skipped") else ""))

    if done.get("failed") or done.get("skipped"):
        # Failed downloads are not resumable; discard their unverified temp data
        # so a later retry starts clean and has enough room to proceed.
        remove_part_files(fetchable)

    failed = done.get("failed", 0) + done.get("skipped", 0)
    print(f"\nfetched {done.get('fetched', 0)}   "
          f"no-url {done.get('no-url', 0)}   failed {failed}")
    if done.get("skipped"):
        print(f"stopped early: {done['skipped']} file(s) after disk space ran out")

    if done.get("no-url") or failed:
        print("\nPack is still incomplete. See above per file; run --check anytime.")
        return 2

    print("\nPack complete. Now:  python tools\\build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())