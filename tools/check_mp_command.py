"""Build-time guard: the multiplayer command line must be launchable.

Run as part of desktop/build/stage-pack.js, i.e. on every packaged build. A
build that regresses this FAILS instead of shipping an installer whose
Multiplayer button opens Zandronum's "Welcome to Zandronum! / point us to your
Doom directory" dialog.

What it asserts, and why each one shipped broken once:

* the IWAD is a single, ABSOLUTE -iwad argument. It was a bare basename
  (`-iwad DOOM.WAD`), which only resolves when the engine's own IWAD search
  list names the folder holding the WAD -- and the bundled engine's folder
  does not, so every multiplayer launch asked the user for the folder, and
  kept asking (the pack strips runtime\\zandronum\\*.ini, so there was nothing
  to remember the choice in).

* the base WAD is passed exactly ONCE. files_for_entry() reads the pack's own
  launcher .bat, which names its IWAD too, so the WAD used to come back out of
  that list as a second -file and the engine loaded the base game stacked on
  itself.

* $DOOMWADDIR is set and absolute. It is one of the engine's OWN default search
  directories, so it makes a first run with no config find the pack's WADs by
  itself -- the belt-and-braces half of the fix.

Zandronum-friendly: nothing here launches the engine or touches the network.

It also needs NO pack content. Paths are stubbed to the pack's own conventions
before the command is built, so this passes on a build machine that has only
the manifest, launchers and the pack's python files -- the same set staging
requires.

  python tools/check_mp_command.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, PACK)
sys.path.insert(0, HERE)

import iwadfinder as _iwadfinder          # noqa: E402
import mp_session as M                    # noqa: E402
import serve as _serve                    # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    tag = "PASS  " if ok else "FAIL  "
    print(tag + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(name)


def main():
    try:
        _serve.load_sources()
        _serve.load_entries()
    except Exception as e:
        print(f"cannot check: the pack's own data did not load ({e})")
        return 1
    if not _serve.ENTRIES:
        print("cannot check: the entry list is empty. Was pack-manifest.json "
              "generated? Run  python tools/build.py  first.")
        return 1

    playable = [(i, e) for i, e in enumerate(_serve.ENTRIES)
                if e.get("kind") == "pack" and e.get("iwad")
                and e.get("bat")]
    if not playable:
        print("cannot check: no entry is both a pack game with an IWAD and a "
              "launcher .bat. The launchers/ staging item is missing or stale.")
        return 1
    idx, entry = playable[0]

    # Stub ONLY the two outside facts: where the engine exe is and where the
    # IWAD resolves. Both stubs use the pack's own layout, so the built command
    # line is the shape the real one takes on an installed pack. Pack CONTENT
    # (the files the entry loads) is never opened below.
    _iwadfinder.available = lambda name: os.path.join(PACK, "iwads", name)
    M.zandronum_exe = lambda: os.path.join(PACK, "runtime", "zandronum",
                                           "zandronum.exe")

    # ---- the IWAD reaches the engine as a path ---------------------------
    iwads = {}
    try:
        argv = M.host_argv(idx, 23513)
        join_argv = M.join_argv(idx, "1.2.3.4:%d" % 23513)
    except ValueError as e:
        print(f"cannot check: host_argv refused ({e})")
        return 1

    for i, a in enumerate(argv):
        if a == "-iwad":
            iwads.setdefault(argv[i + 1], len(iwads))
    check("the engine is handed exactly one -iwad", len(iwads) == 1,
          f"{len(iwads)}: {sorted(iwads)}")
    check("the IWAD is an absolute path, not a bare name",
          bool(iwads) and all(os.path.isabs(p) for p in iwads),
          next(iter(iwads), "(none)"))
    check("it is the entry's own IWAD",
          bool(iwads)
          and os.path.basename(next(iter(iwads))).upper()
          == (entry.get("iwad") or "").upper(),
          entry.get("iwad", ""))

    # ---- and it is not ALSO in the -file list ----------------------------
    files = M.files_for_entry(idx)
    base = M.iwad_path_for_entry(idx)
    files_cmd = [argv[i + 1] for i, a in enumerate(argv) if a == "-file"]
    dupes = [f for f in files_cmd
             if base and os.path.normcase(os.path.abspath(f))
             == os.path.normcase(os.path.abspath(base))]
    check("the base WAD is not also passed as -file", not dupes,
          ", ".join(os.path.basename(d) for d in dupes) or "clean")
    check("the base WAD appears once in the whole command line",
          len(iwads) == 1 and not dupes)

    # ---- the rest of the shape stays intact ------------------------------
    check("every other file keeps the entry's own order",
          files_cmd == [f for f in files
                        if not (base and os.path.normcase(os.path.abspath(f))
                                 == os.path.normcase(os.path.abspath(base)))],
          " -> ".join(os.path.basename(f) for f in files_cmd))
    check("hosting carries -host", "-host" in argv, "host mode")
    check("joining carries +Connect and the address",
          "+Connect" in join_argv and "1.2.3.4:23513" in join_argv)

    # ---- DOOMWADDIR ------------------------------------------------------
    env = M.launch_env()
    dd = env.get("DOOMWADDIR") or ""
    check("DOOMWADDIR is set to an absolute iwads directory",
          os.path.isabs(dd) and os.path.basename(dd).lower() == "iwads", dd)
    check("launch_env keeps the rest of the environment",
          "PATH" in env or "Path" in env)

    print()
    if FAILS:
        print(f"{len(FAILS)} of {7} multiplayer command-line checks FAILED.")
        return 1
    print("multiplayer command-line shape: OK "
          "(absolute -iwad, base WAD once, DOOMWADDIR set)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
