# DoomNite

A portable Doom mod launcher. One folder holds the GZDoom runtime, the IWADs and
the mods; every path is relative, so the whole thing works from a USB stick or
any drive letter.

Double-click `PLAY DOOMNITE.cmd`, type a number, type it again to confirm.
`0` exits.

## What it does

- 21 Doom games, 28 launchers, plus Sonic Robo Blast 2 and Doom Half-Life
  launched in place.
- Brutal Doom 22, Beautiful Doom, DSD Remake, ULSimpDM, Aliens: Eradication TC,
  The Bikini Bottom Massacre, Doom III, DukeBoomem, QuakinDoom, Shadow Warrior,
  Call of Doom, DBP37, MoonMan, MyHouse, Hocus Pocus 3D, Hexen Remade, DN3DooM,
  and six multi-mod combos.
- Vanilla Doom and Doom II IWADs only. Nothing here is a total conversion that
  needs its own game data.

## Run it

Two ways, both from the pack root.

**Web UI (the main one)**

```
python serve.py
```

Opens a browser at `http://127.0.0.1:8765/`. Search and filter 30 entries, arrow
keys and Enter to launch, `d` to show the exact command an entry runs. `python
serve.py --no-open` if you don't want the browser popping up.

No dependencies, no npm install, no build step. It is one HTML file and one
Python file using only the standard library.

**Batch menu**

```
PLAY DOOMNITE.cmd
```

Still there and still works. It is the fallback if the browser is not an option,
and it is what the CI-style checks below drive.

## Build it

```
python tools\build.py         # copy runtime, iwads, mods; write launchers
python tools\make_menu.py     # write PLAY DOOMNITE.cmd from the manifest
python tools\build.py --check # verify every referenced file exists
```

`tools\build.py` is the only file you edit to change the game list. Its `GAMES`
table maps each entry to its mod files and IWAD; `make_menu.py` reads the
manifest that build produces and knows nothing about the games itself.

## Verify it without launching anything

This is the part worth keeping. `--dryrun` makes each launcher log the command
line it *would* run to `dryrun.log` instead of running it:

```
python tools\make_menu.py --dryrun 15          # show what entry 15 does
"PLAY DOOMNITE.cmd" --dryrun 15             # log it, launch nothing
for /L %%n in (1,1,30) do @"PLAY DOOMNITE.cmd" --dryrun %%n
```

Then check every logged line resolves against the pack. All 30 currently pass:
each has an engine, an IWAD, at least one mod, and no file is missing.

Use this rather than clicking through the menu. Launching all 28 entries at once
will start 28 copies of ZDoom, and that is genuinely unpleasant to clean up.

## Things that bite

**ZDoom cannot load `.zip`.** A zip in `-file` is ignored silently, so the game
just starts as vanilla Doom with no error. Playnite's library lists MoonMan as
`moonman-doom-2-master.zip`; the pack uses `moon_man_v1_3_1.pk3` instead. Every
mod here is a `.pk3` or `.wad` and `--check` fails the build if a `.zip` ever
reaches a mod list.

**GZDoom is copied as a whole set, DLLs and all.** This is not optional. Copy
just `uzdoom.exe` and it dies instantly with `STATUS_DLL_NOT_FOUND`
(`0xC0000135`), because `openal32.dll`, `libsndfile-1.dll`,
`libfluidsynth64.dll` and friends must sit beside it. It fails *silently* — no
console output, no window, and `start` reports success — so a file-exists check
passes happily on a pack that cannot start a single game. `build.py --check`
therefore runs `uzdoom.exe -iwad ... -norun` and reads the exit code, treating
only `0` and GZDoom's own quit code `1337` as success. Copy the `RUNTIME_PK3`
list rather than every `.pk3` in the folder, or loose mod pk3s (Brutal Doom,
DN3DooM, SWMapPack) get loaded into every entry.

**Mod order matters in combos.** GZDoom loads `-file` entries in sequence, so a
combo lists its base mod first and the patch second. Swapping them usually
works but changes which version of a definition wins.

**Hocus Pocus 3D runs on the Doom II IWAD.** It does not run on `DOOM.WAD`, even
though it is a Doom 1 style game.

## Layout

```
PLAY DOOMNITE.cmd   the batch menu
launchers\*.bat        one per entry, usable standalone
serve.py               local web server (stdlib only)
index.html             the web UI
runtime\               uzdoom.exe, its DLLs, and GZDoom's own pk3s
iwads\                 DOOM.WAD, DOOM2.WAD
mods\                  one folder per mod
tools\build.py         the mod table; build and verify the pack
tools\make_menu.py     generate the batch menu from pack-manifest.json
pack-manifest.json     generated; what both UIs read
```

`serve.py` binds to `127.0.0.1` only and its `/api/launch` endpoint accepts an
integer index into the manifest, never a path or command string. The index is
resolved to a known launcher server-side, so the worst a hostile page on
localhost can do is start a game that was already in the menu. It is a
single-user local tool, not something to expose to a network.

The pack is about 5 GB. It is not in git: the runtime, IWADs and mods are
copyrighted and far too big. The scripts are the project.

## Credits

Mods are by their respective authors. Doom, GZDoom and the IWADs are by id
Software and contributors. Nothing here is mine to license; check each mod's
own terms before redistributing the pack.