"""Generate sources.json: every file the pack ships, with size and sha256.

This is the input to fetcher.py. Run it on a machine that already HAS a
working pack; commit the result. fetcher.py then needs no knowledge of the
GAMES table -- it just fills in what the manifest says is missing.

    python tools\\make_sources.py            # write sources.json
    python tools\\make_sources.py --verify   # re-hash, report drift only

Deliberately separate from build.py. build.py knows where files came from on
the author's machine; this knows only what must exist in the finished pack, so
the two can disagree without either lying about the other.

sources.json is committed (it is small -- a few hundred lines of hashes), while
the files it describes are not. That is the whole point: a clone gets the list
of what it needs and can go get it.
"""

import hashlib
import json
import os
import sys

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(PACK, "sources.json")

# Directories the pack ships. runtime/ is engine + support files, mods/ and
# iwads/ are the content, and both are gitignored -- which is exactly why this
# manifest has to exist.
ROOTS = ("runtime", "iwads", "mods")

# Downloads/ is a cache the on-demand installer owns, not part of the pack.
# `app` is the built launcher UI. It is served from the local install, never
# downloaded, and dist/ is the Cloudflare Pages download page -- neither belongs
# in the R2 object store.
SKIP_DIRS = {".git", "__pycache__", "downloads", ".staging", "node_modules",
              "dist", "app", "ui", "playnite-data", "art"}

# Never publish these, whatever else is true of them. Hexen.wad is a
# commercial retail IWAD: freely redistributing it is not ours to decide, so
# it is excluded from hosting at the source rather than by remembering to
# leave a URL off it.
#
# DOOM2.WAD was on this list and is not any more. The operator owns the
# bucket hosting the pack and has taken that decision deliberately, so the
# veto is lifted here rather than only in sources.json -- otherwise the next
# `make_sources.py` run would re-arm it silently, which is the whole reason
# the carry-forward below exists. DOOM.WAD is v1.9 shareware and was never
# on this list.
VETOED = {
    "iwads/Hexen.wad",
}


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


def sha256(path, chunk=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def collect():
    """Every file under ROOTS, keyed by its pack-relative posix path."""
    out = {}
    for root in ROOTS:
        base = os.path.join(PACK, root)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in sorted(dirnames) if d not in SKIP_DIRS]
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                if os.path.islink(full) or not os.path.isfile(full):
                    continue
                rel = os.path.relpath(full, PACK).replace("\\", "/")
                out[rel] = {"size": os.path.getsize(full), "sha256": None}
    return out


def main():
    verify_only = "--verify" in sys.argv

    # Absent file is normal on a fresh clone: everything is treated as new.
    existing = {}
    if os.path.exists(OUT):
        existing = json.load(open(OUT, encoding="utf-8"))["files"]
    else:
        print(f"no {OUT} yet -- creating from the pack on disk")

    files = collect()
    if not files:
        print("nothing to hash -- are runtime/ iwads/ mods/ present?")
        return 1

    # Carry forward the per-file settings this generator must not invent.
    # "no_host" is a legal decision, not a measurement: it marks the commercial
    # IWADs that must never be published. Regenerating without preserving it
    # would quietly re-arm them for publication the next time anyone ran this --
    # the exact opposite of what the flag is for. An operator who removes one
    # by hand gets it stripped back out here, loudly.
    #
    # "publish" is the operator overriding that decision for one file: it is
    # how the DOOM2.WAD veto was lifted. Without it the carry-forward would
    # undo the override on the very next run, silently.
    PUBLISH = {"iwads/DOOM2.WAD"}
    for rel, rec in files.items():
        old = existing.get(rel) or {}
        if rel in PUBLISH:
            rec.pop("no_host", None)
            print(f"  note: {rel} is explicitly published; veto lifted")
        elif old.get("no_host"):
            rec["no_host"] = True
        elif rec.get("no_host") is None and rel in VETOED:
            print(f"  note: {rel} is commercial; keeping it out of hosting")
            rec["no_host"] = True

    total = sum(f["size"] for f in files.values())
    print(f"{len(files)} files, {human(total)}")

    drift = []
    for rel, rec in sorted(files.items()):
        old = existing.get(rel)
        if verify_only and old and old.get("sha256"):
            rec["sha256"] = old["sha256"]
            continue
        rec["sha256"] = sha256(os.path.join(PACK, rel.replace("/", os.sep)))
        if old and old.get("sha256") and old["sha256"] != rec["sha256"]:
            drift.append((rel, old["size"], rec["size"]))
        print(f"  {human(rec['size']):>9}  {rec['sha256'][:12]}  {rel}")

    if drift:
        print(f"\n!! {len(drift)} file(s) changed on disk since sources.json:")
        for rel, o, n in drift:
            print(f"   {rel}: {o} -> {n}")

    if verify_only:
        return 0

    doc = {
        "_comment": [
            "Generated by tools/make_sources.py. Committed; describes files that",
            "are NOT (they are gitignored). fetcher.py reads this to fill in a",
            "clone. 'urls' is empty by design -- hosting is the operator's",
            "choice. Add mirrors there, one per line, most-preferred first.",
        ],
        "version": 1,
        "files": files,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    print(f"\nwrote {OUT} ({human(os.path.getsize(OUT))})")
    print("next: add hosted URLs to each file's \"urls\" list, then run fetcher.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())