"""DoomNite mod installer — installs catalog entries from GitHub release assets.

Every entry in data/catalog.json with "source": "direct" has a real, verified
release asset URL, so Install is a true one-click: fetch, verify size, extract
if needed, drop into the mods folder, done.

ModDB is deliberately absent from the auto path. It sits behind a Cloudflare
challenge that returns 403 to scripted requests and never clears in a browser
either, so a "download from ModDB" button would silently no-op for real users.
Entries that can only be had from ModDB use source "browser" instead.

  python tools/install_mod.py                  # list
  python tools/install_mod.py --install <id>   # install one
  python tools/install_mod.py --status         # what is present
"""
import argparse
import json
import os
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CATALOG = os.path.join(REPO, "data", "catalog.json")
# Where mods live.  NukemNet launches Zandronum out of
# %LOCALAPPDATA%\\Zandronum, and DoomNite's existing entries run out of
# Z:\\GAMES\\BRUTAL_DOOM (uwu) -- so this is the one folder both can use.
MODS_DIR = os.environ.get("DOOMNITE_MODS_DIR", r"Z:\GAMES\BRUTAL_DOOM (uwu)")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def human(n):
    return f"{n/1e6:.1f} MB" if n >= 1e6 else f"{n/1e3:.0f} kB"


def load():
    with open(CATALOG, encoding="utf-8") as fh:
        return json.load(fh)


def is_installed(entry):
    """A mod counts as installed when its payload file is in the mods folder."""
    name = entry["install"]["filename"]
    return os.path.exists(os.path.join(MODS_DIR, name))


def status(entries):
    print(f"mods folder: {MODS_DIR}\n")
    for e in entries:
        mark = "HAVE" if is_installed(e) else ("ghost" if not e.get("installed_locally") else "-")
        print(f"  {mark:>5}  {e['title']:32s} {human(e['asset']['bytes']):>10}")
        if e.get("note"):
            print(f"         note: {e['note']}")


def download(url, dest, expect_bytes):
    """Fetch to dest, showing progress. Verifies the size we were promised."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = dest + ".part"
    got = 0
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as fh:
        total = int(r.headers.get("Content-Length") or expect_bytes)
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            fh.write(chunk)
            got += len(chunk)
            pct = got * 100 // total if total else 0
            sys.stdout.write(f"\r    {pct:3d}%  {human(got)} / {human(total)}")
            sys.stdout.flush()
    print()
    if got != expect_bytes:
        os.remove(tmp)
        raise RuntimeError(f"size mismatch: got {got}, catalog says {expect_bytes}")
    os.replace(tmp, dest)
    return dest


def install(entry):
    if entry.get("source") != "direct":
        print(f"  {entry['title']}: source is '{entry.get('source')}' - not auto-installable.")
        print(f"    open: {entry.get('download_page') or entry['url']}")
        return False
    a = entry["asset"]
    dest = os.path.join(MODS_DIR, a["name"])
    if os.path.exists(dest):
        print(f"  {entry['title']}: already present, nothing to do.")
        return True
    os.makedirs(MODS_DIR, exist_ok=True)
    print(f"  {entry['title']}  ({human(a['bytes'])})")
    print(f"    from {entry['repo']} @ {entry['release_tag']}")
    download(a["url"], dest, a["bytes"])
    print(f"    saved {dest}")

    # .zip payloads (DOOM64 EX+ builds) contain a folder of engine files; the
    # port runs out of its own directory, so unpack next to the archive.
    if a["name"].lower().endswith(".zip"):
        with zipfile.ZipFile(dest) as z:
            z.extractall(MODS_DIR)
        print(f"    extracted to {MODS_DIR}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    entries = load()

    if args.status:
        status(entries)
        return 0
    if args.install:
        for e in entries:
            if e["id"] == args.install:
                return 0 if install(e) else 1
        print("no such mod:", args.install)
        return 1
    # default: list
    for e in entries:
        ghost = "ghost" if not is_installed(e) else "HAVE "
        print(f"  {ghost}  [{e['id']}] {e['title']}  ({human(e['asset']['bytes'])})")
        print(f"           {e['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())