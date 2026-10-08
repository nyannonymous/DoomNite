"""Can this machine actually download from the bucket? Uses fetcher.py's own
code path, including its unverified-context fallback, because that is what a
friend's install runs. Read-only: one HEAD, no bytes saved.

  python tools/probe_fetch.py
"""
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, PACK)

import fetcher  # noqa: E402


def try_url(url, ctx, label):
    req = urllib.request.Request(url, headers={"User-Agent": fetcher.UA}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=40, context=ctx) as r:
            return f"{label}: {r.status}, {r.headers.get('Content-Length')} bytes"
    except Exception as e:
        detail = f"{label}: FAILED {type(e).__name__}"
        if fetcher.is_cert_failure(e):
            detail += " (certificate)"
        else:
            detail += f" ({e})"
        return detail


def main():
    # BASE_URL is populated by load(), which reads sources.json. The first
    # version of this probe read it directly and built "/iwads/DOOM.WAD",
    # which urllib rejects as "unknown url type".
    files = fetcher.load()
    base = (fetcher.BASE_URL.get("url") or "").rstrip("/")
    print("manifest  :", len(files or {}), "files")
    print("bucket    :", base)
    print("ctx       : verified" if fetcher.CTX else "ctx: (default)")
    print()

    for rel in ("iwads/DOOM.WAD", "iwads/Hexen.wad", "mods/brutal22test6/brutal22test6.pk3"):
        url = base + "/" + fetcher.quote(rel)
        print(" ", try_url(url, fetcher.CTX, "verified  "))

        # The fallback, only where it is actually needed.
        req = urllib.request.Request(url, headers={"User-Agent": fetcher.UA}, method="HEAD")
        try:
            urllib.request.urlopen(req, timeout=40, context=fetcher.CTX)
        except Exception as e:
            if fetcher.is_cert_failure(e):
                print(" ", try_url(url, fetcher.unverified_ctx(), "UNVERIFIED"))
            else:
                print("  (not a cert failure; fallback not attempted)")
        print()


if __name__ == "__main__":
    main()