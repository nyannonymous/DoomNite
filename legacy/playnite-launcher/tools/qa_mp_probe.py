"""Probe which DoomNite entries actually load and host under Zandronum.

Zandronum's `-host 4` goes straight into a hosted deathmatch, so a UDP bind on
the game port means "the mod loaded and the server is live".  A mod that is
single-player-only, or that Zandronum cannot parse, never reaches that state.

  python tools/qa_mp_probe.py            # probe everything
  python tools/qa_mp_probe.py 6 14 27    # probe a few entries by number

Writes  data/mp_verified.json  — the MP-capable list build_doomnite.py reads.

NOTE: this launches real games on the desktop, one per entry, each for the
length of its settle window.  Do not run it unattended.
"""
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ZN_DIR = r"Z:\GAMES\Zandronum"
ZN_EXE = os.path.join(ZN_DIR, "zandronum.exe")
# Zandronum's stock game port.  A bind here == "it got into a hosted game".
GAME_PORT = 10666

# How long to wait for the engine to load the entry's files and bind the port.
#
# This used to be a flat 14 s for every entry, which is a false negative for
# anything large: a 200 MB PK3 is still being read off disk when the window
# closes, so a perfectly hostable mod was recorded as "not hostable" -- which is
# exactly how Doom III (a plain PK3 that loads fine) got classified wrong.
# The window now scales with the bytes the entry actually asks the engine to
# load.  A small mod still gets the base 14 s, so nothing gets slower for the
# common case.
BASE_SETTLE = 14.0
# Seconds added per MB of assets.  ~0.2 s/MB puts a 200 MB entry at ~54 s, well
# inside the cap below, and leaves the 14 s base as the floor for tiny mods.
SETTLE_PER_MB = 0.2
# Hard ceiling, so one pathological entry cannot hang the whole run.
MAX_SETTLE = 90.0

# Extensions the engine reads as content.  A token that is not one of these and
# does not follow -iwad is a flag or a flag's value, not a file to size.
ASSET_EXT = (".pk3", ".pk7", ".pkz", ".ipk3", ".iwad", ".wad", ".zip")

# Entries whose exe is NOT the GZDoom/Zandronum family, so the port cannot host
# them no matter what.  Kept explicit (rather than inferred) because these are
# exactly the ones a naive "it's all Doom, it'll work" guess gets wrong.
NON_ZANDRONUM = {
    28: "hl2doom.exe — standalone Half-Life port, not a ZDoom engine",
    29: "srb2win.exe — Sonic Robo Blast 2, standalone engine",
}


def port_is_open():
    """True if anything is bound to the Zandronum game port."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", GAME_PORT)) == 0


def kill_stray():
    subprocess.run(["taskkill", "/F", "/IM", "zandronum.exe"],
                   capture_output=True, shell=False)
    time.sleep(1.5)


def asset_names(args):
    """The content filenames an entry's args tell the engine to load.

    `args` is the raw command-line tail recorded in doomnite.json, e.g.
        brutal22test6.pk3 -iwad DOOM2.WAD -file DoomMetalVol5_44100.wad
        "The Bikini Bottom Massacre 1,3.wad" -iwad DOOM2.WAD
        DoomRPG\\DoomRPG.pk3 DoomRPG\\DoomRPG-Extras.pk3 -iwad DOOM2.WAD

    Split with posix=False: POSIX mode eats the backslash in `DoomRPG\\x.pk3`
    and silently turns two different files into one nonsense name, which is
    precisely the kind of quiet wrong answer this function exists to avoid.
    Quotes are then stripped by hand, since posix=False keeps them.
    """
    try:
        toks = shlex.split(args or "", posix=False)
    except ValueError:      # unbalanced quote in hand-written data
        toks = (args or "").split()
    toks = [t.strip().strip('"') for t in toks]
    names = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.lower() == "-iwad" and i + 1 < len(toks):
            # The IWAD is a real asset the engine reads too -- ~11-40 MB, and
            # it is the first thing loaded, so it belongs in the window. Its
            # value is consumed here so it is not also counted as a bare
            # filename on the next pass.
            names.append(toks[i + 1])
            i += 2
            continue
        if not t.startswith("-") and t.lower().endswith(ASSET_EXT):
            names.append(t)
        i += 1
    return names


def asset_bytes(args, cwd):
    """Total bytes of the files in `args` that actually exist under `cwd`.

    A name that is not on disk contributes 0 rather than raising: an entry
    pointing at a missing file should still get a probe attempt, and its own
    reason string is what reports the problem.
    """
    total = 0
    for n in asset_names(args):
        for cand in (os.path.join(cwd, n), os.path.join(cwd, os.path.basename(n))):
            try:
                total += os.path.getsize(cand)
                break
            except OSError:
                continue
    return total


def settle_for(args, cwd):
    """Seconds to wait for this entry to reach a hosted game.

    Scales with the bytes to load, floored at BASE_SETTLE and capped at
    MAX_SETTLE.  Pure function of the entry's args and the files on disk, so
    selftest_settle.py can check it without launching anything.
    """
    mb = asset_bytes(args, cwd) / 1e6
    return min(MAX_SETTLE, BASE_SETTLE + mb * SETTLE_PER_MB)


def probe(idx, label, cwd, exe, args, note, settle=None):
    """Launch one entry under Zandronum and see whether it reaches a hosted game."""
    kill_stray()
    if settle is None:
        settle = settle_for(args, cwd)
    argv = [ZN_EXE, "-host", "4", "-nomusic"] + (args.split() if args else [])
    # Zandronum needs a resolvable IWAD; doomnite.json already passes -iwad.
    if "-iwad" not in argv:
        return {"index": idx, "label": label, "mp": False,
                "reason": "no -iwad in the entry's args; cannot resolve an IWAD"}

    before = port_is_open()
    proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    deadline = time.time() + settle
    hosted = False
    while time.time() < deadline:
        if proc.poll() is not None:
            break            # died: bad mod, or a fatal parse error
        if not before and port_is_open():
            hosted = True
            break
        time.sleep(0.5)

    window = f"{settle:.0f}s window"
    if hosted:
        try:
            proc.terminate()
        except Exception:
            pass
        kill_stray()
        return {"index": idx, "label": label, "mp": True,
                "reason": f"hosted on UDP {GAME_PORT} with: {args.strip()}",
                "settle": round(settle, 1)}

    died = proc.poll() is not None
    kill_stray()
    return {"index": idx, "label": label, "mp": False,
            "reason": ("exited immediately (Zandronum could not load it)"
                       if died else
                       f"ran but never opened UDP {GAME_PORT} in its {window} "
                       f"— not hostable"),
            "settle": round(settle, 1)}


def main():
    if not os.path.exists(ZN_EXE):
        print("zandronum.exe not found at", ZN_EXE)
        return 1
    with open(os.path.join(REPO, "data", "doomnite.json"), encoding="utf-8") as fh:
        games = json.load(fh)

    wanted = [int(a) for a in sys.argv[1:]]
    results = []
    for idx, (label, cwd, exe, args, note) in enumerate(games, start=1):
        if wanted and idx not in wanted:
            continue
        if idx in NON_ZANDRONUM:
            results.append({"index": idx, "label": label, "mp": False,
                            "reason": NON_ZANDRONUM[idx]})
            print(f"  [{idx:2d}] SKIP  {label} — {NON_ZANDRONUM[idx]}", flush=True)
            continue
        # the mod files have to actually exist or the probe proves nothing
        if not os.path.exists(os.path.join(cwd, exe)):
            results.append({"index": idx, "label": label, "mp": False,
                            "reason": f"exe missing: {exe}"})
            print(f"  [{idx:2d}] MISS  {label} — exe missing", flush=True)
            continue
        r = probe(idx, label, cwd, exe, args, note)
        results.append(r)
        print(f"  [{idx:2d}] {'HOST' if r['mp'] else ' NO '}  "
              f"{label} — {r['reason']}  (waited {r.get('settle')}s)",
              flush=True)

    out = os.path.join(REPO, "data", "mp_verified.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)
    ok = sum(1 for r in results if r["mp"])
    print(f"\n{ok}/{len(results)} entries host under Zandronum -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())