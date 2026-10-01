"""Extract each mod's own title screen from its WAD/PK3 as cover art.

Doom mods almost always ship a TITLEPIC (Doom) or TITLE (Heretic/Hexen) lump.
It is often PNG, sometimes JPEG despite the .png extension, and sometimes
wrapped in ZDoom's 13-byte lump header -- or not. Detect every case by
signature rather than trusting the filename or extension, and prefer TITLEPIC
over the INTERPIC interstitial.

The art is authored by the mod authors and already sits on disk as part of the
mods; this only copies it out. No downloads, no third-party artwork.

Usage:  python tools/extract_art.py
"""
import pathlib
import struct
import zipfile

PACK = pathlib.Path(__file__).resolve().parent.parent
MODS = PACK / "mods"
ART = PACK / "art"

WANT = {"TITLEPIC", "TITLE", "INTERPIC"}
RANK = {"TITLEPIC": 3, "TITLE": 3, "INTERPIC": 1}

# (magic bytes, extension, PIL mode hint)
SIGS = [
    (b"\x89PNG\r\n\x1a\n", "png", None),
    (b"\xff\xd8\xff", "jpg", None),
    (b"GIF8", "gif", None),
]

# ZDoom wraps some lumps in an 8-byte name + 4-byte length header.
LUMP_HEADER = 13


def payload(blob):
    """Return the image payload, tolerating an optional ZDoom lump header."""
    for sig, _, _ in SIGS:
        if blob.startswith(sig):
            return blob
    for sig, _, _ in SIGS:
        if blob[LUMP_HEADER:].startswith(sig):
            return blob[LUMP_HEADER:]
    return None


def extension(blob):
    for sig, ext, _ in SIGS:
        if blob.startswith(sig):
            return ext
    for sig, ext, _ in SIGS:
        if blob[LUMP_HEADER:].startswith(sig):
            return ext
    return None


def from_wad(path):
    out = []
    data = path.read_bytes()
    if len(data) < 12 or data[:4] not in (b"IWAD", b"PWAD"):
        return out
    num, off = struct.unpack("<II", data[4:12])
    for i in range(min(num, 50000)):
        e = data[off + i * 16: off + i * 16 + 16]
        if len(e) < 16:
            break
        lo, sz = struct.unpack("<II", e[:8])
        name = e[8:16].rstrip(b"\x00").decode("ascii", "ignore").upper()
        if name not in WANT or sz < 1000:
            continue
        pl = payload(data[lo:lo + sz])
        if pl:
            out.append((name, pl))
    return out


def from_pk3(path):
    out = []
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            pname = pathlib.PurePosixPath(n).name
            if pathlib.PurePosixPath(pname).stem.upper() not in WANT:
                continue
            if not pname.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                continue
            pl = payload(z.read(n))
            if pl:
                out.append((pathlib.PurePosixPath(pname).stem.upper(), pl))
    return out


def main():
    ART.mkdir(exist_ok=True)
    for old in ART.iterdir():
        if old.is_file() and old.name != ".gitkeep":
            old.unlink()

    donors = {}
    for p in sorted(MODS.rglob("*")):
        if not p.is_file():
            continue
        s = p.suffix.lower()
        if s in (".pk3", ".pk7"):
            got = from_pk3(p)
        elif s == ".wad":
            got = from_wad(p)
        else:
            continue
        for name, blob in got:
            if RANK[name] > donors.get(p.stem, (0,))[0]:
                donors[p.stem] = (RANK[name], name, blob)

    for key, (_, name, blob) in sorted(donors.items()):
        ext = extension(blob)
        dest = ART / f"{key}.{ext}"
        dest.write_bytes(blob)
        print(f"  {key:46} {name:9} .{ext} {len(blob) // 1024:5} KB")

    print(f"\n{len(donors)} title screens extracted to {ART}")


if __name__ == "__main__":
    main()