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
from io import BytesIO

try:
    from PIL import Image
except ImportError:                        # optional
    Image = None

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
    index = {}
    for i in range(min(num, 50000)):
        e = data[off + i * 16: off + i * 16 + 16]
        if len(e) < 16:
            break
        lo, sz = struct.unpack("<II", e[:8])
        name = e[8:16].rstrip(b"\x00").decode("ascii", "ignore").upper()
        index.setdefault(name, (lo, sz))
        if name not in WANT or sz < 1000:
            continue
        body = data[lo:lo + sz]
        pl = payload(body)
        if pl:
            out.append((name, pl))
            continue
        # No image signature: a Doom WAD TITLEPIC is a flat 8-bit paletted
        # picture needing PLAYPAL from the same WAD, not an encoded file.
        pic = flat_picture(body, index, data)
        if pic is not None:
            out.append((name, pic))
    return out


def flat_picture(body, index, data):
    """Decode a flat unscaled WAD picture lump (TITLEPIC, INTERPIC).

    These are width*height palette indices, not PNG/JPEG, so signature sniffing
    finds nothing and they were previously skipped entirely. PLAYPAL holds 14
    bytes per entry, but only the first 3 are RGB.
    """
    if Image is None:
        return None
    if "PLAYPAL" not in index:
        return None
    plo, psz = index["PLAYPAL"]
    pal = data[plo:plo + psz]
    need = 256 * 3
    if len(pal) < need:
        return None
    rgb = bytearray()
    for c in range(256):
        p = pal[c * 14:c * 14 + 3]
        rgb += bytes((p[0], p[1], p[2]))
    # Unscaled flats are 320x200; anything else is a scaled/custom resolution we
    # cannot infer, so decline rather than emit a scrambled image.
    for w, h in ((320, 200), (640, 400), (1280, 800), (256, 224), (512, 448)):
        if len(body) >= w * h:
            im = Image.frombytes("P", (w, h), body[:w * h])
            im.putpalette(bytes(rgb))
            buf = BytesIO()
            im.convert("RGB").save(buf, format="PNG")
            return buf.getvalue()
    return None


def from_pk3(path):
    out = []
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            pname = pathlib.PurePosixPath(n).name
            # Title art is often nested -- MoonMan and MyHouse both keep theirs
            # at graphics/TITLEPIC with no file extension at all. Match on the
            # stem anywhere in the path and let signature detection decide.
            if pathlib.PurePosixPath(pname).stem.upper() not in WANT:
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