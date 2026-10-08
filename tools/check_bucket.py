"""Is every file in sources.json actually on the bucket?

    python tools/check_bucket.py            # report
    python tools/check_bucket.py --workers 16

One HEAD request per file -- nothing is downloaded, only headers -- run through
a thread pool so all 68 finish in seconds. Exits non-zero if any file is
missing or its size disagrees with the manifest, so it can gate a release.

WHY THIS IS PYTHON AND NOT THE SHELL SCRIPT IT REPLACED
------------------------------------------------------
The bash version (tools/check_bucket.sh, kept for reference) went through six
failures in a row, every one of them a shell-quoting or path-translation
problem rather than a networking one -- on Windows under MSYS, with a pack path
containing both a space and a middle dot:

  1. `while read` on the key list consumed the loop's own stdin, so every file
     was reported unreachable against a bucket that was serving HTTP 200.
  2. `mktemp -d` returns a native Windows path while the shell passes an MSYS
     one to python; python could not find the file the shell had just written.
  3. Deriving sources.json's path from `sys.argv[0]` resolved wrongly, because
     argv[0] is "-" for a heredoc.
  4. python writes CRLF on Windows, so every size arrived as "11159840\\r" and
     failed the integer test.
  5. A path built from `$PWD` translated differently inside each xargs child
     (/Z/... vs /mnt/z/... vs C:\\...), so probes appended to "" or nowhere.
  6. bash DISCARDS NUL bytes inside $(...), so a NUL-separated list can never
     pass through a variable -- it has to be piped, which then needed
     `xargs -0`, which in turn cannot handle a real filename containing a
     space and a comma: "The Bikini Bottom Massacre 1,3.wad".

That last one is the real reason this is Python. Splitting on a separator is
fine when you control the data; here a legitimate filename defeats every shell
splitter. In Python the manifest keys are already a dict, so the filename never
needs to survive a round trip through a command line at all.
"""
import concurrent.futures as futures
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
SOURCES = os.path.join(PACK, "sources.json")

sys.path.insert(0, PACK)
import fetcher as _fetcher  # noqa: E402

UA = getattr(_fetcher, "UA", "DoomNite/2.0")
CTX = getattr(_fetcher, "CTX", None)
unverified_ctx = getattr(_fetcher, "unverified_ctx", None)
is_cert_failure = getattr(_fetcher, "is_cert_failure", None)
if CTX is None or unverified_ctx is None or is_cert_failure is None:
    # Older fetcher without the fallback: degrade to the default context rather
    # than refusing to run.
    import ssl as _ssl
    CTX = _ssl.create_default_context()
    unverified_ctx = lambda: _ssl.create_default_context()  # noqa: E731
    is_cert_failure = lambda e: False                        # noqa: E731

# The bucket rejects bursts; 12 concurrent HEADs is well inside what it and the
# network between tolerate, and finishes 68 files in a couple of seconds.
DEFAULT_WORKERS = 12
TIMEOUT = 45


def head(url):
    """(status, content_length) for a HEAD request. Never raises.

    Goes through fetcher.py's own SSL path, verified first and unverified on a
    certificate failure. Do not "simplify" this to a bare urlopen: on a machine
    whose Python has no CA bundle -- which is the case on the owner's box, where
    ssl.get_default_verify_paths() reports cafile=None -- every verified request
    fails and the whole bucket looks empty. fetcher.py documents why the
    fallback is acceptable (the manifest's sha256 is what protects integrity).
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
    for ctx in (CTX, unverified_ctx()):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
                return r.status, int(r.headers.get("Content-Length") or -1)
        except urllib.error.HTTPError as e:
            return e.code, -1
        except Exception as e:
            if ctx is CTX and is_cert_failure(e):
                continue        # retry without verification, exactly as the app does
            return 0, -1
    return 0, -1


def main():
    workers = DEFAULT_WORKERS
    if "--workers" in sys.argv:
        try:
            workers = int(sys.argv[sys.argv.index("--workers") + 1])
        except (IndexError, ValueError):
            pass

    with open(SOURCES, encoding="utf-8") as f:
        doc = json.load(f)
    base = (doc.get("base_url") or "").strip()
    files = doc.get("files") or {}
    if not base:
        print("sources.json has no base_url; nothing to check")
        return 2

    results = {}
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        # Each future is keyed by its own manifest path, so the result cannot be
        # misattributed when two entries happen to share a basename.
        # Percent-encode, exactly as fetcher.urls_for() does. One real file is
        # named "The Bikini Bottom Massacre 1,3.wad": unencoded, the space ends
        # the URL and the request comes back with no response, which this script
        # reported as the file being absent from the bucket.
        pending = {pool.submit(head, base + quote(rel)): rel for rel in files}
        for fut in futures.as_completed(pending):
            results[pending[fut]] = fut.result()

    ok = missing = mismatch = 0
    problems = []
    for rel, rec in sorted(files.items()):
        status, length = results.get(rel, (0, -1))
        want = rec.get("size") or -1
        if status != 200:
            missing += 1
            problems.append(("MISSING", rel, f"http={status or 'no response'}"))
            continue
        if want > 0 and length != want:
            mismatch += 1
            problems.append(
                ("SIZE", rel, f"remote={length} manifest={want}"))
            continue
        ok += 1

    total = len(files)
    print(f"bucket    : {base}")
    print(f"files     : {total}")
    print(f"reachable : {ok}/{total}")
    print(f"missing   : {missing}")
    print(f"size drift: {mismatch}")
    if problems:
        print("\n--- problems ---")
        for kind, rel, detail in problems:
            print(f"  {kind:8} {rel}  {detail}")
    else:
        print("\nevery file is present and the right size.")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())