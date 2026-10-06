"""Check tools/nn_preset.py against a throwaway NukemNet layout.

The writer edits a config another program owns, so the checks that matter are:
the shape it writes is NN's own shape (not an approximation of it), the rest of
the document survives untouched, a backup exists before anything is written,
and it REFUSES when NN could not open the files it is about to name -- a preset
naming a file NN cannot see silently drops the mod from the game.

  python tools/selftest_nn_preset.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import nn_preset as nn  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}"
          + ("" if ok else f"\n        got  {got!r}\n        want {want!r}"))


# A LaunchDefaults.json in the exact shape of the real one on this machine,
# trimmed to the parts that matter: a per-game `file` param plus the other
# params and top-level keys that must come out the other side unchanged.
FIXTURE = {
    "games": {
        "doom": {"executables": {"zandronum": {
            "params": {"gamemode": {"value": 4, "htmlProp": "selectedIndex",
                                    "for": "host-only-shared",
                                    "args": ["+Cooperative", "1"],
                                    "valueLabel": "Cooperative"}},
            "maxPlayers": 8, "mode": "multiplayer"}}},
        "doom2": {"executables": {"zandronum": {
            "params": {
                "file": {"value": "Z:\\ZAN\\DOOM2.WAD\nZ:\\ZAN\\brutalv22test4.pk3",
                         "htmlProp": "value", "for": "shared",
                         "args": ["-file", "Z:\\ZAN\\DOOM2.WAD",
                                  "-file", "Z:\\ZAN\\brutalv22test4.pk3"],
                         "valueLabel": "DOOM2.WAD, brutalv22test4.pk3"},
                "skill": {"value": "4", "htmlProp": "value",
                          "args": ["+skill", "4"], "valueLabel": "4"},
            },
            "maxPlayers": 8, "mode": "multiplayer"}}},
    },
    "roomName": "", "roomPass": "", "hideRoom": False,
    "defaultGameAndExec": {"gameId": "doom", "execId": "zandronum"},
}

SETTINGS = {"gamePort": 23513, "games": {"doom2": {"zandronum": {"path": "Z:\\ZAN"}}}}


def build_layout(root, zan_mods=(), zan_flat=()):
    """A temp NN folder + its Zandronum folder. Returns (nn_user, zan)."""
    nn_user = os.path.join(root, "NN", "user")
    os.makedirs(nn_user)
    zan = os.path.join(root, "ZAN")
    os.makedirs(os.path.join(zan, "mods"), exist_ok=True)
    for n in zan_mods:
        with open(os.path.join(zan, "mods", n), "wb") as f:
            f.write(b"x")
    for n in zan_flat:
        with open(os.path.join(zan, n), "wb") as f:
            f.write(b"x")
    with open(os.path.join(nn_user, "LaunchDefaults.json"), "w", encoding="utf-8") as f:
        json.dump(FIXTURE, f, indent=2)
    with open(os.path.join(nn_user, "Settings.json"), "w", encoding="utf-8") as f:
        # zan is spelled out here so nn_zandronum_dir() is read, not guessed.
        json.dump({"games": {"doom2": {"zandronum": {"path": zan}}}}, f)
    return nn_user, zan


def run_cli(nn_user, *args):
    env = dict(os.environ, DOOMNITE_NN_DIR=nn_user)
    p = subprocess.run([sys.executable, os.path.join(HERE, "nn_preset.py"), *args],
                       capture_output=True, text=True, env=env, cwd=PACK)
    return p.returncode, p.stdout + p.stderr


print("discovery")
with tempfile.TemporaryDirectory() as root:
    nn_user, zan = build_layout(root, zan_mods=["mod.pk3"], zan_flat=["DOOM2.WAD"])
    saved_env = os.environ.get("DOOMNITE_NN_DIR")
    os.environ["DOOMNITE_NN_DIR"] = nn_user
    try:
        check("$DOOMNITE_NN_DIR is honoured", nn.find_nn(), nn_user)
    finally:
        if saved_env is None:
            os.environ.pop("DOOMNITE_NN_DIR", None)
        else:
            os.environ["DOOMNITE_NN_DIR"] = saved_env
    check("NN's Zandronum folder comes from Settings.json", nn.nn_zandronum_dir(nn_user), zan)

    print("\nthe `file` param is NN's own shape, not an approximation")
    got = nn.file_param([r"C:\Z\DOOM2.WAD", r"C:\Z\mod.pk3"])
    check("value is newline-joined (NN's textarea binding)", got["value"],
          "C:\\Z\\DOOM2.WAD\nC:\\Z\\mod.pk3")
    check("args repeat -file, the way NN passes the IWAD too", got["args"],
          ["-file", "C:\\Z\\DOOM2.WAD", "-file", "C:\\Z\\mod.pk3"])
    check("for is 'shared' (host and joiners need the same list)", got["for"], "shared")
    check("htmlProp is NN's binding", got["htmlProp"], "value")
    check("valueLabel is the comma-joined basenames", got["valueLabel"],
          "DOOM2.WAD, mod.pk3")

    print("\nseeing the files NN can see")
    check("a file flat in the Zandronum folder", nn.nn_visible(r"C:\pack\mods\a\DOOM2.WAD", zan),
          os.path.join(zan, "DOOM2.WAD"))
    check("a file behind the mods link", nn.nn_visible(r"C:\pack\mods\a\mod.pk3", zan),
          os.path.join(zan, "mods", "mod.pk3"))
    # The pack's own layout is mods\<slug>\<file>, one level deeper than the
    # legacy flat folder, so the mods link has to be searched a level down.
    mods_link = os.path.join(zan, nn.LINKS[0][0])
    iwads_link = os.path.join(zan, nn.LINKS[1][0])
    os.makedirs(os.path.join(mods_link, "hocus"), exist_ok=True)
    with open(os.path.join(mods_link, "hocus", "HOCUS.pk3"), "wb") as f:
        f.write(b"x")
    check("a file behind the mods link (one slug folder down)",
          nn.nn_visible(r"C:\pack\mods\hocus\HOCUS.pk3", zan),
          os.path.join(mods_link, "hocus", "HOCUS.pk3"))
    # The IWADs link is flat: the pack cannot host Hexen.wad, so without this
    # the Hexen entries are unusable from NN no matter what the preset says.
    os.makedirs(iwads_link, exist_ok=True)
    with open(os.path.join(iwads_link, "Hexen.wad"), "wb") as f:
        f.write(b"x")
    check("a file behind the iwads link (flat)",
          nn.nn_visible(r"C:\pack\iwads\Hexen.wad", zan),
          os.path.join(iwads_link, "Hexen.wad"))
    check("a file NN cannot reach is None", nn.nn_visible(r"C:\pack\mods\a\nope.pk3", zan), None)
    check("a path already inside the Zandronum folder is passed through",
          nn.nn_visible(os.path.join(zan, "mods", "mod.pk3"), zan),
          os.path.join(zan, "mods", "mod.pk3"))

print("\nthe CLI, end to end (dry run writes nothing)")
with tempfile.TemporaryDirectory() as root:
    nn_user, zan = build_layout(root, zan_mods=["myhouse.wad", "myhouse.pk3"],
                                zan_flat=["DOOM2.WAD"])
    before_bytes = open(os.path.join(nn_user, "LaunchDefaults.json"), "rb").read()
    rc, out = run_cli(nn_user, "--game", "MyHouse.pk3")
    check("dry run exits 0", rc, 0)
    check("dry run says so", "DRY RUN" in out, True)
    check("dry run names the game id", "NN game id     : doom2" in out, True)
    check("dry run puts the IWAD first, as NN does", "after : DOOM2.WAD, myhouse.wad, myhouse.pk3" in out, True)
    check("dry run wrote nothing",
          open(os.path.join(nn_user, "LaunchDefaults.json"), "rb").read(), before_bytes)
    check("dry run made no backup",
          [f for f in os.listdir(nn_user) if ".bak-" in f], [])

    print("\n--write: backup first, rest of the document untouched")
    rc, out = run_cli(nn_user, "--game", "MyHouse.pk3", "--write")
    check("write exits 0", rc, 0)
    baks = [f for f in os.listdir(nn_user) if ".bak-" in f]
    check("exactly one backup was made", len(baks), 1)
    check("the backup is the original", open(os.path.join(nn_user, baks[0]), "rb").read(),
          before_bytes)
    doc = json.load(open(os.path.join(nn_user, "LaunchDefaults.json"), encoding="utf-8"))
    fp = doc["games"]["doom2"]["executables"]["zandronum"]["params"]["file"]
    check("the file param now names the entry's mods, IWAD first",
          fp["valueLabel"], "DOOM2.WAD, myhouse.wad, myhouse.pk3")
    check("and its paths are the ones NN can open",
          all(os.path.isfile(p) for p in fp["value"].splitlines()), True)
    check("everything else in the document survived",
          {k: v for k, v in doc.items() if k != "games"},
          {k: v for k, v in FIXTURE.items() if k != "games"})
    check("the other game id is untouched", doc["games"]["doom"], FIXTURE["games"]["doom"])
    check("the other params are untouched",
          doc["games"]["doom2"]["executables"]["zandronum"]["params"]["skill"],
          FIXTURE["games"]["doom2"]["executables"]["zandronum"]["params"]["skill"])
    check("no .tmp file was left behind",
          [f for f in os.listdir(nn_user) if f.endswith(".tmp")], [])

    print("\na mod NN cannot see is refused, not silently dropped")
    # Hocus Pocus 3D's HOCUS.pk3 is not in this temp Zandronum folder.
    rc, out = run_cli(nn_user, "--game", "Hocus Pocus 3D", "--write")
    check("write exits non-zero", rc, 1)
    check("it says why", "NN cannot see" in out or "cannot see" in out, True)
    check("it did not write", json.load(open(os.path.join(nn_user, "LaunchDefaults.json"),
                                             encoding="utf-8"))["games"]["doom2"]
          ["executables"]["zandronum"]["params"]["file"]["valueLabel"],
          "DOOM2.WAD, myhouse.wad, myhouse.pk3")
    check("and made no second backup",
          len([f for f in os.listdir(nn_user) if ".bak-" in f]), 1)

print("\nthe pack links")
with tempfile.TemporaryDirectory() as root:
    nn_user, zan = build_layout(root)
    check("dry run creates nothing", nn.make_link(zan, False), 0)
    check("and really created nothing",
          [d for _l, _t, d in nn.link_state(zan)], [False, False])
    # A junction reads as a plain directory, so a REAL folder with content in
    # the way must be refused rather than shadowed.
    real = os.path.join(zan, nn.LINKS[0][0])
    os.makedirs(real)
    with open(os.path.join(real, "someone-elses.pk3"), "wb") as f:
        f.write(b"x")
    check("a non-empty real folder is refused", nn.make_link(zan, True), 1)
    check("and its contents are untouched",
          os.listdir(real), ["someone-elses.pk3"])

    # And a link it made itself must be recognised on the next run, or the tool
    # refuses to touch its own work. os.stat hides the reparse flag (it follows
    # the link); os.lstat is the one that shows it.
    with tempfile.TemporaryDirectory() as t2:
        nn_user2, zan2 = build_layout(t2)
        link2 = os.path.join(zan2, nn.LINKS[0][0])
        subprocess.run(["cmd", "/c", "mklink", "/J", link2,
                        os.path.join(PACK, "mods")], capture_output=True)
        if os.path.isdir(link2):
            check("a junction it created is recognised as a junction",
                  nn.is_junction(link2), True)
            check("a real folder is not", nn.is_junction(real), False)
            check("so a second run is a no-op, not a refusal",
                  nn.make_link(zan2, True), 0)
        else:
            print("  SKIP  could not create a junction to test against "
                  "(mklink refused in this environment)")

print()
if FAILED:
    print(f"FAILED ({len(FAILED)}): " + "; ".join(FAILED))
    sys.exit(1)
print("all NN preset checks passed")
