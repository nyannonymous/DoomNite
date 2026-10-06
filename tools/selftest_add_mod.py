"""Check tools/add_mod.py's reading of a candidate mod.

The tool's whole claim is that it reports what the FILE says rather than
guessing, so the checks are about the two things that can be derived (the IWAD,
from the map lumps) and the things that must NOT be invented (an IWAD for a mod
that ships no maps; a GAMES entry for something that is actually an IWAD).

  python tools/selftest_add_mod.py
"""
import os
import struct
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import add_mod as am  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}"
          + ("" if ok else f"\n        got  {got!r}\n        want {want!r}"))


def make_wad(path, magic, lump_names):
    """A WAD with a real header and directory, and no lump data.

    Only the header and the directory are ever read by add_mod.py, so the data
    can be zero bytes -- which is what keeps this test instant instead of
    writing a real 200 MB PWAD.
    """
    body = b""
    directory = b""
    for n in lump_names:
        directory += struct.pack("<ii8s", 12 + len(body), 0, n.encode()[:8].ljust(8, b"\0"))
    with open(path, "wb") as f:
        f.write(struct.pack("<4sii", magic.encode(), len(lump_names), 12 + len(body)))
        f.write(body)
        f.write(directory)
    return path


def make_pk3(path, member_names):
    with zipfile.ZipFile(path, "w") as z:
        for n in member_names:
            z.writestr(n, b"")
    return path


with tempfile.TemporaryDirectory() as tmp:
    p = lambda n: os.path.join(tmp, n)

    print("the IWAD is read off the map lumps")
    check("E1M1..E1M3 -> Doom 1",
          am.classify(make_wad(p("d1.wad"), "PWAD", ["E1M1", "E1M2", "E1M3"]))["iwad"],
          "DOOM.WAD")
    check("MAP01..MAP05 -> Doom 2",
          am.classify(make_wad(p("d2.wad"), "PWAD", ["MAP01", "MAP05"]))["iwad"],
          "DOOM2.WAD")
    check("MAP22 counts too",
          am.classify(make_wad(p("m22.wad"), "PWAD", ["MAP22"]))["iwad"], "DOOM2.WAD")
    check("MAP33 does not (it is not a real Doom 2 map slot)",
          am.classify(make_wad(p("m33.wad"), "PWAD", ["MAP33"]))["iwad"], None)
    check("E5M1 does not (no Doom 1 episode 5)",
          am.classify(make_wad(p("e5.wad"), "PWAD", ["E5M1"]))["iwad"], None)

    print("\nboth formats in one file is reported, not guessed at")
    both = am.classify(make_wad(p("both.wad"), "PWAD", ["E1M1", "MAP01"]))
    check("no IWAD is picked", both["iwad"], None)
    check("and it says why", "BOTH" in both["why"], True)

    print("\na mod with no maps of its own gets no invented IWAD")
    # Brutal Doom 22 is exactly this: 159 MB, no maps, plays on any IWAD.
    nomaps = am.classify(make_wad(p("nomaps.wad"), "PWAD", ["PLAYPAL", "COLORMAP", "DECORATE"]))
    check("no IWAD", nomaps["iwad"], None)
    check("and it says the choice is a content decision, not a derivable one",
          "content decision" in nomaps["why"], True)

    print("\na PK3's maps are read out of the zip")
    check("maps/MAP01.wad -> Doom 2",
          am.classify(make_pk3(p("m.pk3"), ["maps/MAP01.wad", "graphics/title.png"]))["iwad"],
          "DOOM2.WAD")
    check("a bare E1M1.wad at the root works too",
          am.classify(make_pk3(p("e.pk3"), ["E1M1.wad"]))["iwad"], "DOOM.WAD")
    check("a pk3 with no maps gets none",
          am.classify(make_pk3(p("n.pk3"), ["sprites/SARG.png"]))["iwad"], None)

    print("\nan IWAD is not a mod")
    iwad = am.classify(make_wad(p("DOOM2.WAD"), "IWAD", ["MAP01", "PLAYPAL"]))
    check("the IWAD header is noticed", iwad["is_iwad"], True)
    check("so it reports itself as an IWAD, not a mod with an IWAD",
          iwad["iwad"], "THIS FILE IS AN IWAD")

    print("\nnot an archive at all")
    with open(p("notes.txt"), "wb") as f:
        f.write(b"just text")
    txt = am.classify(p("notes.txt"))
    check("container says so", txt["container"], "not a WAD or PK3")
    check("no IWAD claimed", txt["iwad"], None)

    print("\na truncated/corrupt file does not raise")
    # A complete 12-byte header whose directory is missing entirely.
    with open(p("cut.wad"), "wb") as f:
        f.write(struct.pack("<4sii", b"PWAD", 5, 12))
    cut = am.classify(p("cut.wad"))
    check("it survives a header with no directory", cut["container"], "PWAD (wad)")
    check("and claims nothing", cut["iwad"], None)
    # And a file too short to even be a header.
    with open(p("tiny.wad"), "wb") as f:
        f.write(b"PWAD\x05\x00\x00\x00")
    check("a file shorter than a header is not called a WAD",
          am.classify(p("tiny.wad"))["container"], "not a WAD or PK3")

    print("\nthe GAMES skeleton")
    skel = am.skeleton({"name": "My Mod.pk3", "iwad": "DOOM2.WAD"})
    check("names the file", 'BD + r"\\My Mod.pk3"' in skel, True)
    check("carries the derived IWAD", '[("DOOM2.WAD", ' in skel, True)
    check("leaves the note as a TODO rather than inventing one",
          "TODO" in skel, True)
    check("unknown IWAD is an explicit placeholder",
          "<IWAD?>" in am.skeleton({"name": "x.wad", "iwad": None}), True)
    check("the slug rule matches tools/build.py's",
          am.slugify("DBP37: Auger;Zenith"), "dbp37-auger-zenith")

print("\nagainst the real pack (the heuristics, on files that shipped)")
check("DBP37_AUGZEN.wad -> DOOM2.WAD (22 maps, matches the manifest)",
      am.classify(os.path.join(PACK, "mods", "dbp37-augzen", "DBP37_AUGZEN.wad"))["iwad"],
      "DOOM2.WAD")
check("brutal22test6.pk3 ships no maps, so no IWAD is claimed",
      am.classify(os.path.join(PACK, "mods", "brutal22test6", "brutal22test6.pk3"))["iwad"],
      None)
check("the pack's DOOM2.WAD is recognised as an IWAD",
      am.classify(os.path.join(PACK, "iwads", "DOOM2.WAD"))["is_iwad"], True)
check("and a file the pack already hosts is reported as such",
      bool(am.already_in_pack(os.path.join(PACK, "mods", "myhouse", "myhouse.pk3"),
                              am.sha256(os.path.join(PACK, "mods", "myhouse", "myhouse.pk3")))),
      True)

print()
if FAILED:
    print(f"FAILED ({len(FAILED)}): " + "; ".join(FAILED))
    sys.exit(1)
print("all add-mod inspection checks passed")
