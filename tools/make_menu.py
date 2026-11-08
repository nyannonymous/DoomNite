#!/usr/bin/env python3
"""
DoomNite menu generator - writes PLAY DOOMNITE.cmd, a numbered menu for
every entry in pack-manifest.json.

The menu holds no game knowledge of its own: it reads the manifest that
tools\\build.py produced and CALLS the launchers\\*.bat it finds there. So the
build script stays the single source of truth - add a mod to its GAMES table,
re-run both, and it appears in the menu with no edit here.

Batch details that are deliberate, each fixing a real bug:

* Input is validated against an explicit whitelist of numbers rather than a
  range check, so a typo can never run the wrong game.
* findstr gets one /c: per number. It treats "|" literally, so a single
  /c:"1|2|3" matches nothing.
* "for /f" over a variable loops once per LINE, so leftover piped input could
  overwrite the choice. Only the first line is read.
* Empty input means stdin hit EOF. A real console never does that, and looping
  on it would spin forever, so it exits.
* The number is confirmed a second time before anything launches.
* DOOMNITE_DRYRUN=1 is exported to the launchers, which log their command
  line to dryrun.log instead of running. That is how every entry gets verified
  without launching 28 games at once.

Usage:
    python tools\\make_menu.py            # write PLAY DOOMNITE.cmd
    python tools\\make_menu.py --check    # verify it matches the manifest
    python tools\\make_menu.py --dryrun N # print the command entry N runs
"""
import argparse
import json
import os
import sys

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(PACK, "pack-manifest.json")
OUT_NAME = "PLAY DOOMNITE.cmd"
TITLE = "D O O M N I T E"
RULE = "=" * 59


def entries(manifest):
    """Flatten the manifest into numbered rows.

    Returns [(n, label, launcher_batname_or_None, note)].
    """
    rows = []
    n = 0
    for g in manifest.get("games", []):
        acts = g.get("actions", [])
        # Only spell out the IWAD when there is an actual choice.
        variants = {a["iwad"] for a in acts}
        for a in acts:
            # A pending (browser-source) card has no launcher until its file is
            # dropped in and build.py runs again. Numbering it would shift every
            # entry below and point a menu pick at a batch file that is not
            # there.
            if a.get("pending"):
                continue
            n += 1
            label = g["name"]
            if len(acts) > 1 and len(variants) > 1:
                label += " [Doom 1]" if a["iwad"] == "DOOM.WAD" else " [Doom 2]"
            rows.append((n, label, a["bat"], g.get("note", "")))
    for s in manifest.get("standalone_games", []):
        n += 1
        rows.append((n, s["name"], None, s.get("note", "")))
    return rows


def standalone_base(manifest):
    """How many menu rows come before the first standalone game.

    Pending (browser-source) cards are skipped by entries() because they have
    no launcher yet, so they must not be counted here either. Counting every
    action made this number too high by the number of pending cards -- seven
    at the time of writing -- so run_standalone.cmd waited for 54 while the
    menu dispatched 47, and picking any Duke game or SRB2 from the console did
    nothing at all. Clicks in the UI were unaffected (they go through
    serve.py), which is why it went unnoticed.
    """
    return sum(1 for g in manifest.get("games", [])
               for a in g.get("actions", []) if not a.get("pending"))


def standalone_launcher(manifest):
    """Emit tools\\run_standalone.cmd, used for the non-ZDoom entries.

    Those are launched in place rather than copied, since each is a whole game
    with its own data tree rather than a mod. Under DOOMNITE_DRYRUN it logs
    the real start line to dryrun.log instead, so a verification pass can
    resolve every entry's files, not just the pack launchers.
    """
    base = standalone_base(manifest)
    L = []
    a = L.append
    a("@echo off")
    a("setlocal")
    a('set "n=%~1"')
    a("")
    for i, s in enumerate(manifest.get("standalone_games", []), start=1):
        n = base + i
        # Extra args are part of the launch, not decoration. Duke Nukem Forever
        # is an EDuke32 total conversion: without -gDNF.GRP and -xDNFGAME.con
        # the engine boots plain Duke3D from duke3d.grp and the mod never
        # appears, and SRB2 needs -window plus an explicit size because SDL
        # otherwise falls back to a silent no-display mode. Dropping them here
        # meant the console menu launched a different game than the .bat/
        # serve.py path did.
        extra = " ".join(s.get("args") or ())
        cmd = f'start "" /D "{s["wdir"]}" "{s["exe"]}"' + (f" {extra}" if extra else "")
        a(f'if "%n%"=="{n}" (')
        a('  if /I "%DOOMNITE_DRYRUN%"=="1" (')
        a(f'    echo {cmd}>>"%~dp0..\\dryrun.log"')
        a("    exit /b 0")
        a("  )")
        a(f"  {cmd}")
        a("  exit /b 0")
        a(")")
        a("")
    a("exit /b 0")
    a("")
    out = os.path.join(PACK, "tools", "run_standalone.cmd")
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(L))
    return out


def build_cmd(rows):
    total = rows[-1][0] if rows else 0
    t = []
    a = t.append
    a("@echo off")
    a("setlocal enabledelayedexpansion")
    a(f"title {TITLE}")
    a("rem Generated by tools\\make_menu.py. To change the list, edit the mod")
    a("rem table in tools\\build.py and re-run it - do not edit this file.")
    a("set DOOMNITE_DRYRUN=0")
    a('if /I "%~1"=="--dryrun" set DOOMNITE_DRYRUN=1')
    a('set "pick=%~2"')
    a('set "oneshot=0"')
    a("if not defined pick goto :top")
    a('set "oneshot=1"')
    a("goto dispatch")
    a(":top")
    a("cls")
    a(f"echo {RULE}")
    a(f"echo {TITLE}")
    a(f"echo {RULE}")
    a("echo.")
    for n, label, bat, note in rows:
        a(f"echo  {n:2}. {label}")
        if note:
            # A note may be a paragraph now (the Ashes cards list their whole
            # saga so their order is visible). The menu is one line per entry,
            # so fold to the headline -- otherwise the remaining lines land as
            # stray text between rows and the numbering reads as broken.
            a(f"echo        {note.splitlines()[0]}")
    a("echo.")
    a("echo   0. Exit")
    a("echo.")
    a('set "pick="')
    a('set /p "pick=Number, then Enter: "')
    a("rem " + "-" * 56)
    a("rem Only the FIRST line is read: piped stdin can leave several lines in")
    a("rem the variable and 'for /f' loops over all of them.")
    a('set "first="')
    a('for /f "tokens=1" %%a in ("!pick!") do if not defined first set "first=%%a"')
    a('set "pick=%first%"')
    a("rem " + "-" * 56)
    opts = " ".join(f'/c:"{i}"' for i in range(total + 1))
    a(f"echo !pick!|findstr /x {opts} >nul")
    a("if errorlevel 1 goto bad")
    a('if "!pick!"=="0" exit /b 0')
    a("rem Empty means stdin hit EOF; looping would spin forever.")
    a('if not defined pick exit /b 0')
    a('if "!DOOMNITE_DRYRUN!"=="1" goto dispatch')
    a("echo.")
    a("echo Type the number again to launch it, anything else to go back.")
    a('set "confirm="')
    a('set /p "confirm=Launch? (number again): "')
    a('set "cfirst="')
    a('for /f "tokens=1" %%a in ("!confirm!") do if not defined cfirst set "cfirst=%%a"')
    a("if not defined cfirst goto top")
    a('if "!cfirst!"=="!pick!" goto dispatch')
    a("goto top")
    a(":bad")
    a("echo Not one of the numbers above.")
    a("pause")
    a("goto top")
    a(":dispatch")
    for n, label, bat, note in rows:
        if bat:
            a(f'if "!pick!"=="{n}" call "%~dp0launchers\\{bat}"')
        else:
            a(f'if "!pick!"=="{n}" call "%~dp0tools\\run_standalone.cmd" {n}')
    a('if "!oneshot!"=="1" exit /b 0')
    a("goto top")
    a("")
    return "\r\n".join(t), total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dryrun", type=int, metavar="N")
    args = ap.parse_args()

    if not os.path.exists(MANIFEST):
        sys.exit(f"no {MANIFEST}\nrun: python tools\\build.py")
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    standalone_launcher(manifest)
    rows = entries(manifest)
    cmd, total = build_cmd(rows)
    out = os.path.join(PACK, OUT_NAME)

    if args.dryrun is not None:
        for n, label, bat, note in rows:
            if n == args.dryrun:
                if bat:
                    print(f"{n}. {label}\n   call launchers\\{bat}")
                else:
                    base = standalone_base(manifest)
                    s = manifest["standalone_games"][args.dryrun - base - 1]
                    extra = " ".join(s.get("args") or ())
                    print(f"{n}. {label}\n   start \"\" /D \"{s['wdir']}\" "
                          f"\"{s['exe']}\"" + (f" {extra}" if extra else ""))
                return
        sys.exit(f"no entry numbered {args.dryrun}")

    if args.check:
        if not os.path.exists(out):
            sys.exit(f"missing {out} - run: python tools\\make_menu.py")
        cur = open(out, encoding="utf-8", newline="").read()
        if cur != cmd:
            sys.exit("menu is stale vs the manifest - run: python tools\\make_menu.py")
        print(f"menu is up to date: {total} entries")
        return

    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write(cmd)
    bats = sum(1 for r in rows if r[2])
    print(f"wrote {out}")
    print(f"  {total} entries ({bats} pack launchers, {total - bats} standalone)")


if __name__ == "__main__":
    main()