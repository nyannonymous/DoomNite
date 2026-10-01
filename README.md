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

**Mod order matters in combos.** GZDoom loads `-file` entries in sequence, so a
combo lists its base mod first and the patch second. Swapping them usually
works but changes which version of a definition wins.

**Hocus Pocus 3D runs on the Doom II IWAD.** It does not run on `DOOM.WAD`, even
though it is a Doom 1 style game.

## Layout

```
PLAY DOOMNITE.cmd   the menu
launchers\*.bat        one per entry, usable standalone
runtime\               uzdoom.exe, game_support.pk3, zmusic.dll
iwads\                 DOOM.WAD, DOOM2.WAD
mods\                  one folder per mod
tools\build.py         the mod table; build and verify the pack
tools\make_menu.py     generate the menu from pack-manifest.json
pack-manifest.json     generated; what the menu reads
```

The pack is about 5 GB. It is not in git: the runtime, IWADs and mods are
copyrighted and far too big. The scripts are the project.

## Credits

Mods are by their respective authors. Doom, GZDoom and the IWADs are by id
Software and contributors. Nothing here is mine to license; check each mod's
own terms before redistributing the pack.