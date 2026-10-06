"""Inspect a candidate mod and work out what build.py's GAMES table would need.

Section 5's blocker for an "add a mod" flow is that a new mod's IWAD and launcher
config are hand-authored in tools/build.py, "not derived from any file
metadata". This is the evidence half of that: it reads the file and reports what
the file itself actually says, so the amount that has to be asked for is a
measured number instead of a guess.

  python tools/add_mod.py <file-or-folder> ...

Read-only. It writes nothing, changes nothing and downloads nothing -- a mod
that only exists on ModDB stays a `source: "browser"` entry (see todo.md
section 6), and this only ever looks at a file already on disk.

What it can decide, and why:

* **the IWAD**, from the map lumps. `E1M1`..`E4M9` is Doom 1, `MAP01`..`MAP32`
  is Doom 2 -- that is the format of the maps themselves, not a guess about the
  mod. A mod that ships NO maps (Brutal Doom 22 is one) plays on whichever IWAD
  it is handed, and this says so rather than picking one.
* **whether it is an IWAD or a mod**, from the WAD header magic (`IWAD` vs
  `PWAD`) and from a pk3 carrying the IWAD's own lump set.
* **whether the pack already has it**, by name and by sha256 against
  sources.json -- so adding a mod does not silently duplicate 200 MB.
"""
import argparse
import hashlib
import json
import os
import re
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)

# Doom 1 episodes and Doom 2 maps, as they appear in a WAD directory or as a
# pk3's map lump filenames.
DOOM1_MAPS = re.compile(r"^E[1-4]M[1-9]$")
DOOM2_MAPS = re.compile(r"^MAP(0[1-9]|[12]\d|3[0-2])$")

# A WAD's directory entries are 16 bytes: filepos, size, then an 8-byte name
# that is NUL-padded, not NUL-terminated.
LUMP = struct.Struct("<ii8s")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def wad_lumps(path):
    """(magic, [lump names]) for a WAD, or (None, []) if it is not one.

    Only the 12-byte header and the directory are read -- a 200 MB PWAD is not
    loaded to find out what its maps are called.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(12)
            if len(head) < 12:
                return None, []
            magic, numlumps, infotableofs = struct.unpack("<4sii", head)
            magic = magic.decode("ascii", "replace").strip("\0")
            if magic not in ("IWAD", "PWAD"):
                return None, []
            # Sanity bound: a bogus count would otherwise read for ever.
            if not (0 <= numlumps <= 1_000_000) or infotableofs < 12:
                return magic, []
            f.seek(infotableofs)
            raw = f.read(numlumps * LUMP.size)
    except OSError:
        return None, []
    names = []
    for i in range(len(raw) // LUMP.size):
        _pos, _size, name = LUMP.unpack_from(raw, i * LUMP.size)
        names.append(name.split(b"\0")[0].decode("ascii", "replace"))
    return magic, names


def pk3_lumps(path):
    """The map lumps inside a PK3 (a zip), by filename.

    ZDoom reads maps out of a pk3 as `maps/<name>.wad`, but plenty of released
    mods also drop `MAP01.wad` at the root, so both are accepted.
    """
    names = []
    try:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                base = os.path.basename(info.filename)
                stem = os.path.splitext(base)[0]
                if DOOM1_MAPS.match(stem) or DOOM2_MAPS.match(stem):
                    names.append(stem)
    except (zipfile.BadZipFile, OSError):
        return []
    return sorted(set(names))


def classify(path):
    """Everything this can honestly say about one file."""
    out = {"path": path, "name": os.path.basename(path),
           "size": os.path.getsize(path), "container": "?",
           "iwad": None, "why": "", "maps": [], "already": None,
           "is_iwad": False}
    ext = os.path.splitext(path)[1].lower()

    if ext in (".pk3", ".pk7", ".ipk3", ".zip"):
        out["container"] = "pk3 (zip)"
        out["maps"] = pk3_lumps(path)
    else:
        magic, lumps = wad_lumps(path)
        if magic:
            out["container"] = f"{magic} (wad)"
            out["maps"] = sorted({n for n in lumps if DOOM1_MAPS.match(n) or DOOM2_MAPS.match(n)})
            if magic == "IWAD":
                out["iwad"] = "THIS FILE IS AN IWAD"
                out["is_iwad"] = True
                out["why"] = "its WAD header says IWAD, so it is a game, not a mod"
                return out
        else:
            out["container"] = "not a WAD or PK3"
            out["why"] = "no IWAD/PWAD header and not a zip -- nothing to derive"
            return out

    d1 = [m for m in out["maps"] if DOOM1_MAPS.match(m)]
    d2 = [m for m in out["maps"] if DOOM2_MAPS.match(m)]
    if d1 and not d2:
        out["iwad"] = "DOOM.WAD"
        out["why"] = f"{len(d1)} Doom 1 map lump(s) ({d1[0]}..{d1[-1]}) and no MAPxx"
    elif d2 and not d1:
        out["iwad"] = "DOOM2.WAD"
        out["why"] = f"{len(d2)} Doom 2 map lump(s) ({d2[0]}..{d2[-1]}) and no ExMx"
    elif d1 and d2:
        out["iwad"] = None
        out["why"] = ("ships BOTH Doom 1 and Doom 2 maps -- pick the IWAD per "
                      "variant, or list both like Brutal Doom does")
    else:
        out["iwad"] = None
        out["why"] = ("ships no maps of its own, so it plays on whichever IWAD "
                      "it is handed -- the IWAD is a content decision (which "
                      "music/sprites the mod targets), not a derivable one")
    return out


def already_in_pack(path, digest):
    """What the pack already knows about this file: name, and sha256."""
    hits = []
    man_p = os.path.join(PACK, "pack-manifest.json")
    if os.path.isfile(man_p):
        try:
            man = json.load(open(man_p, encoding="utf-8"))
        except ValueError:
            man = {}
        for g in man.get("games", []):
            for a in g.get("actions", []):
                for m in a.get("mods", []):
                    if os.path.basename(m.replace("\\", "/")) == os.path.basename(path):
                        hits.append(f"{g.get('name')} (in pack)")
    src_p = os.path.join(PACK, "sources.json")
    if os.path.isfile(src_p):
        try:
            files = json.load(open(src_p, encoding="utf-8")).get("files") or {}
        except ValueError:
            files = {}
        for rel, rec in files.items():
            if os.path.basename(rel.replace("\\", "/")) == os.path.basename(path):
                hits.append(f"hosted at sources.json:{rel}")
            if rec.get("sha256") == digest:
                hits.append(f"SAME BYTES as sources.json:{rel}")
    return sorted(set(hits))


def slugify(s):
    """The same slug rule tools/build.py uses, so the skeleton names the folder
    the build will actually create."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


def skeleton(info, source_prefix="BD"):
    stem = os.path.splitext(info["name"])[0]
    iwad = info["iwad"] or "<IWAD?>"
    return "\n".join([
        f'    ("{stem}",',
        '     "TODO: what it is, and why it loads where it does",',
        f'     [("{iwad}", {source_prefix} + r"\\{info["name"]}")]),',
    ])


def report(path, source_prefix="BD"):
    digest = sha256(path)
    info = classify(path)
    print(f"\n{info['name']}  ({info['size'] / 1e6:.1f} MB)")
    print(f"  container : {info['container']}")
    print(f"  sha256    : {digest[:16]}...")
    print(f"  maps      : {len(info['maps'])} found"
          + (f" ({info['maps'][0]}..{info['maps'][-1]})" if info["maps"] else ""))
    print(f"  IWAD      : {info['iwad'] or 'cannot be derived'}")
    print(f"              {info['why']}")
    hits = already_in_pack(path, digest)
    print(f"  in pack   : {'; '.join(hits) if hits else 'not referenced anywhere yet'}")
    if info.get("is_iwad"):
        # An IWAD is not a GAMES entry: it is a game. build.py handles iwads/
        # separately, so printing a mod skeleton here would be actively wrong.
        print("  -> this belongs in iwads/, not in GAMES. Nothing to add here.")
        return info
    print(f"  slug      : mods\\{slugify(os.path.splitext(info['name'])[0])}\\")
    print("  GAMES entry for tools/build.py:")
    print(skeleton(info, source_prefix))
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="files or folders to inspect")
    ap.add_argument("--src", default="BD",
                    help="the build.py path variable the file lives under (default BD)")
    args = ap.parse_args()

    targets = []
    for p in args.paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for fn in sorted(files):
                    if os.path.splitext(fn)[1].lower() in (".pk3", ".pk7", ".wad", ".ipk3", ".zip"):
                        targets.append(os.path.join(root, fn))
        elif os.path.isfile(p):
            targets.append(p)
        else:
            print(f"not found: {p}")
            return 1
    if not targets:
        print("nothing to inspect (no .pk3/.pk7/.wad/.ipk3/.zip found)")
        return 1

    infos = []
    for t in targets:
        infos.append(report(t, args.src))

    derivable = sum(1 for i in infos if i["iwad"])
    print(f"\n{derivable}/{len(infos)} file(s): the IWAD could be derived from the file itself.")
    if derivable < len(infos):
        print("The rest need the IWAD chosen -- a mod with no maps of its own")
        print("plays on any IWAD, so which one is a content decision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
