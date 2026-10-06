"""Check the hand-placed ("browser" source) mod path in serve.py.

A mod the pack has no URL for can only arrive by hand -- ModDB answers 403 to
scripted requests, so there is no download button to offer. Two things then
have to hold, and both are checked here against a throwaway pack so the real
one is never touched:

  1. the server must say WHERE the file goes (entry["manual"]), because that is
     the one thing the UI cannot work out for itself; and
  2. the entry must flip to present the moment the file appears, which is what
     App.jsx's folder watch polls /api/entries for.

  python tools/selftest_watch.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)      # serve.py lives in the pack root
sys.path.insert(0, PACK)

import serve  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}"
          + ("" if ok else f"   got {got!r}, want {want!r}"))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def launcher(slug, pk3, iwad="DOOM2.WAD"):
    """A launcher .bat in the same shape tools/build.py writes.

    Deliberately includes the DOOMNITE_DRYRUN echo line: every real launcher
    repeats its whole command line there, so each path appears TWICE in the
    file. That is what made the hint read "put HOCUS.pk3, HOCUS.pk3 in
    mods\\hocus", so the fake launcher has to reproduce it.
    """
    cmd = (f'start "" "%~dp0..\\runtime\\doom.exe" -file '
           f'"%~dp0..\\mods\\{slug}\\{pk3}" -iwad "%~dp0..\\iwads\\{iwad}"')
    return (
        "@echo off\r\n"
        "cd /d \"%~dp0..\"\r\n"
        "if /I \"%DOOMNITE_DRYRUN%\"==\"1\" (\r\n"
        f"  echo {cmd}>>\"%~dp0..\\dryrun.log\"\r\n"
        "  exit /b 0\r\n"
        ")\r\n"
        f"{cmd}\r\n"
    )


def build_pack(root, sources=None):
    """A one-game pack. `hand` is the only entry, and its mod is not on disk."""
    write(os.path.join(root, "pack-manifest.json"), json.dumps({
        "games": [{
            "name": "Hand Placed Game",
            "note": "a mod the pack cannot fetch",
            "actions": [{
                "bat": "hand.bat", "iwad": "DOOM2.WAD", "hd": False,
                "label": "", "art": "",
                "mod": "mods\\hand\\hand.pk3",
                "mods": ["mods\\hand\\hand.pk3"],
            }],
        }],
        "standalone_games": [], "missing": [],
    }))
    write(os.path.join(root, "launchers", "hand.bat"), launcher("hand", "hand.pk3"))
    write(os.path.join(root, "iwads", "DOOM2.WAD"), "iwad")
    write(os.path.join(root, "sources.json"),
          json.dumps(sources if sources is not None
                     else {"base_url": "", "files": {}}))


def entry():
    serve.load_sources()
    serve.load_entries()
    return serve.ENTRIES[0]


def with_pack(fn):
    """Run fn(tmpdir) with serve pointed at a throwaway pack, then restore."""
    saved = (serve.PACK, serve.MANIFEST, serve.SOURCES, serve.ENTRIES)
    tmp = tempfile.mkdtemp(prefix="doomnite-watch-")
    try:
        serve.PACK = tmp
        serve.MANIFEST = os.path.join(tmp, "pack-manifest.json")
        build_pack(tmp)
        return fn(tmp)
    finally:
        serve.PACK, serve.MANIFEST, serve.SOURCES, serve.ENTRIES = saved
        shutil.rmtree(tmp, ignore_errors=True)


print("a mod with nowhere to fetch it from")


def case_unfetchable(tmp):
    e = entry()
    hint = {"folder": os.path.join("mods", "hand"), "files": ["hand.pk3"],
            "hosted": False}
    check("content is reported missing", e["exists"], False)
    check("no fetch path", e["fetchable"], False)
    check("the server says where to put the file", e["manual"], hint)
    check("the variant carries the hint too", e["variants"][0]["manual"], hint)
    check("each file is named once, not once per dryrun echo", e["manual"]["files"],
          ["hand.pk3"])
    check("no absolute path leaks into the hint",
          os.path.isabs(e["manual"]["folder"]), False)

    # 2. THE FLIP. This is the whole point of the folder watch: the same call
    #    the UI polls must change its answer once the file is on disk.
    write(os.path.join(tmp, "mods", "hand", "hand.pk3"), "pk3 bytes")
    e2 = entry()
    check("dropping the file in flips the entry to present", e2["exists"], True)
    check("and the hint goes away", e2["manual"], None)
    check("nothing is missing any more", e2["variants"][0]["exists"], True)


with_pack(case_unfetchable)

print("\na missing IWAD is not a hand-placed mod")
# The IWAD has its own flow (iwadfinder.py, /api/setup). Telling the user to
# drop DOOM2.WAD into the mods folder would be wrong advice, so a missing IWAD
# must NOT produce a manual hint.
saved_iwad = None


def case_missing_iwad(tmp):
    # The mod itself is present; only the IWAD is gone. That is the Setup
    # flow's problem, and the entry must not be told to hand-place anything.
    write(os.path.join(tmp, "mods", "hand", "hand.pk3"), "pk3 bytes")
    os.remove(os.path.join(tmp, "iwads", "DOOM2.WAD"))
    e = entry()
    check("entry is missing", e["exists"], False)
    check("but there is no hand-place hint for an IWAD", e["manual"], None)


with_pack(case_missing_iwad)

print("\na missing mod the pack CAN host")
# Hosted + missing is still a dead end in the UI today: there is no fetch
# button for a pack mod (only installer.py's two on-demand entries get one).
# So it gets the same hint, flagged `hosted` so the panel can also name the
# rebuild path.
HOSTED = {"base_url": "https://example.invalid/",
          "files": {"mods/hand/hand.pk3": {"size": 12345}}}


def case_hosted(tmp):
    build_pack(tmp, sources=HOSTED)
    e = entry()
    check("entry is missing", e["exists"], False)
    check("it is reported fetchable", e["fetchable"], True)
    check("it still gets the hint", e["manual"],
          {"folder": os.path.join("mods", "hand"), "files": ["hand.pk3"],
           "hosted": True})


with_pack(case_hosted)

print("\nan on-demand entry is not a hand-place job")
# Adventures of Square / Requiem have a real INSTALL button, so they must never
# be told to go and find the file themselves.


def case_needs_install(tmp):
    write(os.path.join(tmp, "pack-manifest.json"), json.dumps({
        "games": [{
            "name": "On Demand Game", "note": "",
            "actions": [{"bat": "hand.bat", "iwad": "DOOM2.WAD", "hd": False,
                         "label": "", "art": "",
                         "mod": "mods\\hand\\hand.pk3",
                         "mods": ["mods\\hand\\hand.pk3"],
                         "needs_install": "hand"}],
        }],
        "standalone_games": [], "missing": [],
    }))
    e = entry()
    check("entry is missing", e["exists"], False)
    check("but it has an INSTALL button, so no hint", e["manual"], None)


with_pack(case_needs_install)

print("\npath safety")
# <slug> comes out of the .bat, which the server wrote -- but the guard is
# cheap and this is the kind of thing a later edit gets subtly wrong.


def case_escape(tmp):
    write(os.path.join(tmp, "launchers", "hand.bat"),
          '@echo off\r\nstart "" "%~dp0..\\..\\outside\\x.pk3" -iwad "%~dp0..\\iwads\\DOOM2.WAD"\r\n')
    e = entry()
    check("a ref outside the pack gets no hint", e["manual"], None)


with_pack(case_escape)

print()
if FAILED:
    print(f"FAILED ({len(FAILED)}): " + "; ".join(FAILED))
    sys.exit(1)
print("all hand-placed-mod checks passed")
