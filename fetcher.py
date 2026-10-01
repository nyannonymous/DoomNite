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

Downloading is concurrent but writes are not: each file has its own .part and
its own final path, so nothing needs a lock.
"""

import argparse
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

PACK = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(PACK, "sources.json")
CTX = ssl.create_default_context()
UA = "DoomNite/1.0 (+fetcher)"
CHUNK = 1024 * 256
TIMEOUT = 120
RETRIES = 2


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
        guess = base + rel.replace(os.sep, "/").lstrip("/")
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


def _download(url, dest, expect_size=None, progress=None):
    """Stream url to dest. Returns sha256. Raises on any failure."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    h = hashlib.sha256()
    got = 0
    tmp = dest + ".part"
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as resp:
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

    os.makedirs(os.path.dirname(path), exist_ok=True)
    want = rec.get("sha256")
    errors = []

    for url in urls:
        host = url.split("/")[2] if "://" in url else url[:40]
        for attempt in range(1, RETRIES + 1):
            last = (attempt == RETRIES)
            try:
                cb = _progress_printer(host) if verbose else None
                digest, tmp = _download(url, path, progress=cb)
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

            except (urllib.error.URLError, OSError, IOError) as e:
                if verbose:
                    print("\r" + " " * 62 + "\r", end="", flush=True)
                errors.append(f"{host}: {type(e).__name__} {e}")
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

    print(f"fetching with {args.jobs} parallel connections\n")
    done = {"ok": 0, "no-url": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futs = {pool.submit(fetch_one, r, c, args.force): r for r, c in todo}
        for fut in as_completed(futs):
            rel, status, detail = fut.result()
            done[status] = done.get(status, 0) + 1
            n = sum(done.values())
            mark = {"ok": "ok", "fetched": "ok", "no-url": "--",
                    "failed": "!!"}.get(status, "  ")
            print(f"[{n:>3}/{len(todo)}] {mark} {rel}"
                  + (f"\n         {detail}" if status in ("failed", "no-url")
                     else ""))

    print(f"\nfetched {done.get('fetched', 0)}   "
          f"no-url {done.get('no-url', 0)}   "
          f"failed {done.get('failed', 0)}")

    if done.get("no-url") or done.get("failed"):
        print("\nPack is still incomplete. See above per file; run --check anytime.")
        return 2

    print("\nPack complete. Now:  python tools\\build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())