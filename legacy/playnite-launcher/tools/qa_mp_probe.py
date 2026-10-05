"""Probe which DoomNite entries actually load and host under Zandronum.

Zandronum's `-host 4` goes straight into a hosted deathmatch, so a UDP bind on
the game port means "the mod loaded and the server is live".  A mod that is
single-player-only, or that Zandronum cannot parse, never reaches that state.

  python tools/qa_mp_probe.py            # probe everything
  python tools/qa_mp_probe.py 6 14 27    # probe a few entries by number

Writes  data/mp_verified.json  — the MP-capable list build_doomnite.py reads.
"""
import json
import os
import re
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


def probe(idx, label, cwd, exe, args, note, settle=14):
    """Launch one entry under Zandronum and see whether it reaches a hosted game."""
    kill_stray()
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

    if hosted:
        try:
            proc.terminate()
        except Exception:
            pass
        kill_stray()
        return {"index": idx, "label": label, "mp": True,
                "reason": f"hosted on UDP {GAME_PORT} with: {args.strip()}"}

    died = proc.poll() is not None
    kill_stray()
    return {"index": idx, "label": label, "mp": False,
            "reason": ("exited immediately (Zandronum could not load it)"
                       if died else
                       f"ran but never opened UDP {GAME_PORT} — not hostable")}


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
        print(f"  [{idx:2d}] {'HOST' if r['mp'] else ' NO '}  {label} — {r['reason']}",
              flush=True)

    out = os.path.join(REPO, "data", "mp_verified.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)
    ok = sum(1 for r in results if r["mp"])
    print(f"\n{ok}/{len(results)} entries host under Zandronum -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())