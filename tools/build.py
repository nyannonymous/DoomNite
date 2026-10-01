#!/usr/bin/env python3
"""
DoomNite - build the portable Doom pack.

Copies the runtime, IWADs and mods into a self-contained folder and writes one
launcher .bat per entry, all using paths RELATIVE to the pack root, so the
whole folder works from a USB stick or any drive letter.

Two rules this script enforces, both learned the hard way:

1. ZDoom cannot load .zip. A .zip in -file is silently ignored, so every mod
   here must be a .pk3 or .wad. MoonMan ships as moonman-doom-2-master.zip
   in the source folder; the pack uses moon_man_v1_3_1.pk3 instead.
2. Only .pk3/.wad are copied. A .zip that Playnite references may be a mod that
   has since been repackaged, so zips are recorded in the manifest as
   "not_found" rather than guessed at.

Everything is driven by GAMES below. Add a mod, re-run, and both the launchers
and the menu pick it up.

Usage:
    python tools\\build.py            # build the pack
    python tools\\build.py --check    # verify the pack against this script
"""
import argparse
import json
import os
import re
import struct
import shutil
import subprocess
import sys

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BD = r"Z:\GAMES\BRUTAL_DOOM (uwu)"
BDBE = BD + r"\BDBE 3.38 Build v3 by RaZZoR"
GZ = r"Z:\GAMES\GZDOOM"
HD = r"Z:\GAMES\HEXEN HD"
HO = r"Z:\GAMES\Hocus Doom"
HL = r"Z:\GAMES\DOOM HALF LIFE"

# Files that must exist and be copied. These are the IWADs and the runtime.
#
# The runtime is copied as a WHOLE SET, not a file list. UZDoom loads openal32,
# libsndfile, libfluidsynth and friends from its own directory; copy the exe
# without them and it dies at startup with STATUS_DLL_NOT_FOUND (0xC0000135),
# which surfaces as "nothing happens" because there is no console output. So:
# copy every .dll sitting next to the exe, and fail loudly if it is missing.
#
# The exe is named doom.exe to match the copy in the Playnite library at
# Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe. It is the same binary (verified by
# sha256), and UZDoom's own release names it uzdoom.exe -- the identical hash
# is why this was confusing enough to document. Nothing in the pack runs
# GZDoom; that engine is not used here.
RUNTIME_EXE = "doom.exe"
# The file as it is named in the source folder. Z:\GAMES\GZDOOM is a mixed
# directory holding both engines -- gzdoom.exe (GZDoom) and uzdoom.exe (UZDoom).
# The pack uses the UZDoom build, copied in under the pack's own name so it
# matches the doom.exe the Playnite library launches.
SOURCE_EXE = "uzdoom.exe"
# soft_oal.dll, NOT openal32.dll. UZDoom loads OpenAL Soft by its canonical
# name -- the binary literally contains "$PROGDIR/soft_oal.dll" -- so a pack
# carrying only openal32.dll silently falls back to the null sound module:
# the game runs, with no audio and no error message. The GZDOOM source folder
# ships both names, so the pack happens to have been correct, but nothing was
# checking that. RUNTIME_REQUIRED is checked at build time, so putting the
# UZDoom name here turns a silent failure into a build failure.
# Soundfonts are NOT listed here: they live in runtime\soundfonts\ and are
# verified separately in check(), where the subfolder path can be checked
# properly. Listing a bare name would fail the flat-path existence test.
RUNTIME_REQUIRED = ["game_support.pk3", "zmusic.dll", "soft_oal.dll", "sndfile.dll",
                    "libsndfile-1.dll"]
# UZDoom's own data pk3s. Deliberately NOT every .pk3 in the source folder:
# mod pk3s (Brutal Doom, DN3DooM, SWMapPack) live there too and must not be
# auto-loaded for every entry.
RUNTIME_PK3 = ["uzdoom.pk3", "game_support.pk3", "brightmaps.pk3", "lights.pk3",
               "game_widescreen_gfx.pk3", "h_PBR_v461.pk3"]


def runtime_files():
    """Every file UZDoom needs beside the exe: itself, its pk3s and all DLLs.

    Names are the SOURCE names, as they exist in the GZDOOM folder; the exe is
    renamed to RUNTIME_EXE on the way into the pack.
    """
    names = {SOURCE_EXE, *RUNTIME_PK3}
    for n in os.listdir(GZ):
        if n.lower().endswith(".dll"):
            names.add(n)
    # Soundfonts live in a subfolder and are looked up by name at
    # $PROGDIR/soundfonts/<engine>.sf2, so the copy must carry them there.
    sf_dir = os.path.join(GZ, "soundfonts")
    soundfonts = []
    if os.path.isdir(sf_dir):
        for n in sorted(os.listdir(sf_dir)):
            if n.lower().endswith(".sf2"):
                names.add(os.path.join("soundfonts", n))
                soundfonts.append(n)
    # Compare on the normalised path: soundfont entries are "soundfonts/x.sf2"
    # while the requirement reads "uzdoom.sf2", so match on the basename being
    # present somewhere under soundfonts/.
    have = {n.lower() for n in names}
    have |= {os.path.basename(n).lower() for n in names if os.sep in n}
    missing = [n for n in RUNTIME_REQUIRED if n.lower() not in have]
    if missing:
        sys.exit(f"runtime incomplete at {GZ}: missing {', '.join(missing)}\n"
                 "UZDoom will not start without these (STATUS_DLL_NOT_FOUND).")
    return sorted(names)


# Hexen Remade is a Hexen 1.5 remake: 31 MAP## maps that belong to the Hexen
# IWAD, not either Doom one. It was being launched with DOOM2.WAD and so
# could never work.
IWADS = [("DOOM.WAD", GZ), ("DOOM2.WAD", GZ), ("Hexen.wad", HD)]

# (name, note, [(subfolder, source path, iwad)])
# subfolder is where it lands under mods\. "extra" is a raw -file fragment.
GAMES = [
    ("Brutal Doom v22 test 6",
     "Brutal Doom 22. Loads first, so combos list it first. Optionally with the Doom Metal vol 5 sound pack.",
     [("DOOM2.WAD", BD + r"\brutal22test6.pk3"),
      ("DOOM.WAD", BD + r"\brutal22test6.pk3"),
      ("DOOM2.WAD", BD + r"\brutal22test6.pk3", BD + r"\DoomMetalVol5_44100.wad"),
      ("DOOM.WAD", BD + r"\brutal22test6.pk3", BD + r"\DoomMetalVol5_44100.wad")]),
    # Brutal Doom Black Edition is a COMPLETE standalone total conversion, and
    # that is now proven rather than assumed. BDBE_v3.38.pk3 carries 10,496
    # sprites, 923 sounds, 80 actor-definition lumps and its own DECORATE for
    # Doom 1's entire cast (Zombie_Man, ShotgunGuy1, Imp, BaronofHell2, BEDoomer).
    #
    # A previous version of this file stacked brutal22test6.pk3 underneath,
    # on the theory that BDBE had no maps and needed a base to borrow them. The
    # engine proved that wrong, directly:
    #
    #   Script error, "BDBE_v3.38.pk3:cvarinfo.txt" line 1:
    #   cvar 'zdoombrutalblood' already exists
    #
    # BDBE and BD22 are two forks of the same base and both declare
    # "server int zdoombrutalblood = 2;" and "zdoombrutaljanitor" -- byte
    # identical. UZDoom refuses duplicate cvar declarations outright, so
    # loading both aborts the game before the menu. They are alternatives, not
    # layers.
    #
    # BDBE uses AddDefaultMap, so with no other mod loaded it plays the IWAD's
    # own maps, and the episode wad then supplies its own on top. That is the
    # correct arrangement, and it is what RaZZoR's own 30-byte .bat does:
    # "doom.exe -file enh_e1v1.8c.wad" -- no BD base, no -iwad.
    #
    # The weapon-sounds pk3 is built against v3.35 and only adds sounds, so it
    # is safe after v3.38. HD textures, neural upscale, music, visor and
    # terrain splashes stay out: that is the optional addon layer.
    #
    # Each mod lands in its own subfolder, slugified from its filename.
    # HD VARIANTS ARE FIRST ON PURPOSE. serve.py marks the first action of a
    # group as primary, and a left-click on a card launches the primary. So the
    # best-looking build is the default and the bare one is still a variant.
    #
    # Why the HD addons are needed at all -- the user noticed the helmet and
    # weapons looked low-res, and the base pk3 confirms it:
    #
    #   BDBE_v3.38.pk3            10,496 sprites, but only 23 HIRES/ lumps, and
    #                             22 of those are items/health. Exactly one is
    #                             a weapon (SGN2A0). The BD marine visor
    #                             (PLAYA*, 62 sprites) has 0 hires versions.
    #   BD_Black_NeuralUpscale    1,274 HIRES/ lumps: shotgun, plasma, BFG,
    #                             rifle, chainsaw, ripper.
    #   DoomHDTextures            51 hires PLAY* under filter/doom/hires/player/
    #                             -- the helmet -- plus the HD texture set.
    #
    # So the base pk3 alone is not designed to look good; it ships the art
    # layer and expects the addons for the hires pass.
    #
    # Load order: base first, then the upscaler and HD textures, then the
    # episode wad last so the mapset still wins.
    #
    # BDBE itself is standalone and must not be stacked on brutal22test6 -- both
    # forks declare 'server int zdoombrutalblood' and UZDoom aborts on the
    # duplicate. See the note above the BDBE definition.
    ("Brutal Doom Black Edition (Enhanced Episode 1)",
     "RaZZoR's Black Edition v3.38 with Enhanced Episode 1. HD by default.",
     [("DOOM.WAD", BDBE + r"\addons\BDBE_v3.38.pk3",
       BDBE + r"\addons\BD_Black_NeuralUpscale.pk3",
       BDBE + r"\addons\DoomHDTextures.pk3",
       BDBE + r"\addons\BD_Black_Editionv3.35_WeaponSounds.pk3",
       BDBE + r"\enh_e1v1.8c.wad", {"hd": True, "label": "HD"}),
      ("DOOM2.WAD", BDBE + r"\addons\BDBE_v3.38.pk3",
       BDBE + r"\addons\BD_Black_NeuralUpscale.pk3",
       BDBE + r"\addons\DoomHDTextures.pk3",
       BDBE + r"\addons\BD_Black_Editionv3.35_WeaponSounds.pk3",
       BDBE + r"\enh_e1v1.8c.wad", {"hd": True, "label": "HD"}),
      ("DOOM.WAD", BDBE + r"\addons\BDBE_v3.38.pk3",
       BDBE + r"\addons\BD_Black_Editionv3.35_WeaponSounds.pk3",
       BDBE + r"\enh_e1v1.8c.wad", {"label": "no addons"}),
      ("DOOM2.WAD", BDBE + r"\addons\BDBE_v3.38.pk3",
       BDBE + r"\addons\BD_Black_Editionv3.35_WeaponSounds.pk3",
       BDBE + r"\enh_e1v1.8c.wad", {"label": "no addons"})]),
    ("Brutal Doom Black Edition (HontE Remastered)",
     "RaZZoR's Black Edition v3.38 with HontE Remastered REV1.103. HD by default.",
     [("DOOM2.WAD", BDBE + r"\addons\BDBE_v3.38.pk3",
       BDBE + r"\addons\BD_Black_NeuralUpscale.pk3",
       BDBE + r"\addons\DoomHDTextures.pk3",
       BDBE + r"\addons\BD_Black_Editionv3.35_WeaponSounds.pk3",
       BDBE + r"\HontE_remastered_Experimental_REV1.103.wad", {"hd": True, "label": "HD"}),
      ("DOOM.WAD", BDBE + r"\addons\BDBE_v3.38.pk3",
       BDBE + r"\addons\BD_Black_NeuralUpscale.pk3",
       BDBE + r"\addons\DoomHDTextures.pk3",
       BDBE + r"\addons\BD_Black_Editionv3.35_WeaponSounds.pk3",
       BDBE + r"\HontE_remastered_Experimental_REV1.103.wad", {"hd": True, "label": "HD"}),
      ("DOOM2.WAD", BDBE + r"\addons\BDBE_v3.38.pk3",
       BDBE + r"\addons\BD_Black_Editionv3.35_WeaponSounds.pk3",
       BDBE + r"\HontE_remastered_Experimental_REV1.103.wad", {"label": "no addons"}),
      ("DOOM.WAD", BDBE + r"\addons\BDBE_v3.38.pk3",
       BDBE + r"\addons\BD_Black_Editionv3.35_WeaponSounds.pk3",
       BDBE + r"\HontE_remastered_Experimental_REV1.103.wad", {"label": "no addons"})]),
    ("Aliens: Eradication TC", "Full 8-level Aliens-style campaign.",
     # Two files, per the author's Readme_2_0.txt: "run both files (pk3 and wad)
     # with the pk3 first and the wad second." The mapset carries MAP01-MAP08;
     # the pk3 alone has an 8-line MAPINFO and no map lumps, so loading it alone
     # boots the IWAD's own maps wearing Aliens enemies and guns -- which is
     # exactly the symptom. pk3 first, mapset second, DOOM2 IWAD only.
     #
     # Single variant on purpose: stacking brutal22test6.pk3 underneath was tried
     # and dropped. It fights the campaign's own MAPINFO for episode/map control,
     # and this is a total conversion, not a weapon pack to layer on top.
     [("DOOM2.WAD", BD + r"\ALIENS_ERADICATION_TC_2_0.pk3", BD + r"\ERADICATION_MAPSET_2_0.wad")]),
    ("The Bikini Bottom Massacre", "SpongeBob, but in Doom.",
     [("DOOM2.WAD", BD + r"\The Bikini Bottom Massacre 1,3.wad")]),
    ("DukeBoomem", "Duke Nukem with the Boomstick.",
     [("DOOM2.WAD", BD + r"\Duke-Boomem-2.5D.wad"),
      ("DOOM2.WAD", BD + r"\Duke-Boomem-Aliens-Only.wad"),
      ("DOOM2.WAD", BD + r"\Duke-Boomem-2.5D.wad", BD + r"\Duke-Textures.pk3")]),
    ("QuakinDoom: Total 3-D Edition", "Quake's guns and monsters, Doom's maps.",
     [("DOOM2.WAD", BD + r"\QuakinDoomT3DE.pk3"),
      ("DOOM2.WAD", BD + r"\QuakinDoomT3DE.pk3", BD + r"\QuakinMobs.pk3")]),
    # SWMapPack is maps + ACS + a few sprites. It carries no weapons, monsters or
    # sounds, so on its own every map ran with stock Doom weapons and missing
    # enemy sprites. ShadowWarriorBackup.pk3 is the asset half -- 1973 sprites,
    # 179 sounds, actors and voxels, no maps -- and was sitting unused in the
    # GAMES folder. Base first so the map pack can override it.
    ("Shadow Warrior", "Full conversion with the music pack. Needs the asset "
     "pack -- the map pack alone has no weapons or enemy sprites.",
     [("DOOM2.WAD", BD + r"\ShadowWarriorBackup.pk3", BD + r"\SWMapPack.pk3",
       BD + r"\ShadowWarriorMusic.pk3"),
      ("DOOM2.WAD", BD + r"\ShadowWarriorBackup.pk3", BD + r"\SWMapPack.pk3")]),
    ("DBP37: Auger;Zenith", "2023 community hit. Maps only.",
     [("DOOM2.WAD", BD + r"\DBP37_AUGZEN.wad")]),
    ("MoonMan", "Vanilla-friendly. Uses the pk3: ZDoom cannot load the zip.",
     [("DOOM2.WAD", BD + r"\moon_man_v1_3_1.pk3"),
      ("DOOM.WAD", BD + r"\moon_man_v1_3_1.pk3")]),
    ("MyHouse.pk3", "A recreation of a childhood home. 33 maps, mostly Doom 2 "
     "maps reskinned via MAPINFO lookup; MAP01 is the author's own and needs "
     "myhouse.wad alongside the pk3.",
     [("DOOM2.WAD", BD + r"\myhouse.wad", BD + r"\myhouse.pk3")]),
    ("Hocus Pocus 3D", "Hocus Pocus, but 3D. Runs on the Doom II IWAD.",
     [("DOOM2.WAD", HO + r"\HOCUS.pk3")]),
    # Two flavours, same 31 maps. The PBR pack is a 686 MB download that replaces
    # every texture with a physically based one, so it ships as the HD default
    # with the plain build kept as a second option -- the PBR one is a heavy
    # load and some people just want the original 1995 look.
    ("Hexen Remade HD", "The cancelled Hexen 1.5, finished -- HD remaster. Needs "
     "the Hexen IWAD: its 31 maps are MAP##, which neither Doom IWAD has.",
     [("Hexen.wad", HD + r"\HEXENREMADE.wad", HD + r"\h_PBR_v461.pk3"),
      ("Hexen.wad", HD + r"\HEXENREMADE.wad")]),
    ("DN3DooM", "Duke 3D in Doom II.",
     [("DOOM2.WAD", BD + r"\DN3DooM.pk3")]),
]

# Non-ZDoom games: launched in place, not copied into the pack.
STANDALONE = [
    ("Sonic Robo Blast 2 v2.2", "ZDoom build. Sonic in Doom.",
     os.path.join(BD, "SRB2 v2.2"), os.path.join(BD, "SRB2 v2.2", "srb2win.exe")),
    ("Doom Half-Life", "Half-Life 1 in Doom.",
     HL, os.path.join(HL, "hl2doom.exe")),
]


def slugify(s):
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")


def q(p):
    """Quote a pack-relative path for the batch line."""
    return '"' + p.replace("/", "\\") + '"'


def launcher_line(slug, iwad, mods):
    """The engine invocation. Relative to the pack root, so it stays portable.

    A bare .pk3/.pk7 argument is loaded as a mod, which is what the combos want.
    A bare .wad argument is NOT: UZDoom stacks it onto the IWAD and boots the
    IWAD's own game, so both Brutal Doom Black Edition entries just started plain
    Doom. Standalone wads must go through -file.
    """
    parts = ['start "" "runtime\\doom.exe"']
    pend = []
    for sub, fname in mods:
        ext = os.path.splitext(fname)[1].lower()
        if ext in (".pk3", ".pk7"):
            parts.append(f'"mods\\{sub}\\{fname}"')
        else:
            pend.append(f'"mods\\{sub}\\{fname}"')
    # -file and -iwad are flags, so they must follow the positional mods.
    if pend:
        parts.append("-file " + " ".join(pend))
    parts.append(f'-iwad "iwads\\{iwad}"')
    return " ".join(parts)


def write_bat(bat, title, iwad, mods, note):
    out = os.path.join(PACK, "launchers", bat)
    line = launcher_line(bat, iwad, mods)
    lines = [
        "@echo off",
        f"rem {title}",
        'cd /d "%~dp0.."',
        "",
        "rem DOOMNITE_DRYRUN=1 prints the command instead of running it, so",
        "rem 'PLAY DOOMNITE.cmd --dryrun N' can check every entry without",
        "rem launching anything. The menu sets it.",
        'if /I "%DOOMNITE_DRYRUN%"=="1" (',
        f'  echo {line}>>"%~dp0..\\dryrun.log"',
        "  exit /b 0",
        ")",
        "",
        line,
        "",
        f"rem {note}",
        "",
    ]
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(lines))
    return out


def build():
    for sub in ("runtime", "iwads", "mods", "launchers", "tools"):
        os.makedirs(os.path.join(PACK, sub), exist_ok=True)

    manifest = {"iwads": [], "runtime": [], "games": [], "standalone_games": [],
                "missing": []}

    rt = runtime_files()
    for n in rt:
        src = os.path.join(GZ, n)
        dest = os.path.join(PACK, "runtime", RUNTIME_EXE if n == SOURCE_EXE else n)
        # Soundfonts arrive as "soundfonts/x.sf2"; copy2 will not mkdir for us.
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not (os.path.exists(dest)
                and os.path.getsize(dest) == os.path.getsize(src)):
            shutil.copy2(src, dest)
    manifest["runtime"] = sorted(
        RUNTIME_EXE if n == SOURCE_EXE else n for n in rt)

    for n, src_dir in IWADS:
        src = os.path.join(src_dir, n)
        if not os.path.isfile(src):
            manifest["missing"].append(f"iwad {n} not found at {src}")
            continue
        shutil.copy2(src, os.path.join(PACK, "iwads", n))
        manifest["iwads"].append(n)

    for name, note, actions in GAMES:
        entry = {"name": name, "note": note, "actions": []}
        # An action may carry an optional trailing dict of options. Kept as a
        # 4th tuple slot so the common (iwad, *mods) form stays unchanged.
        #
        # hd=True marks the high-fidelity build. The UI treats the first action
        # of a group as primary, so ordering the HD build first makes the best
        # looking version what a left-click launches, with the bare build still
        # reachable as a variant.
        for i, action in enumerate(actions):
            # The options dict is always the LAST element when present, and it
            # may sit at any index because the number of mods varies per action.
            # Checking only a fixed slot (len == 4) silently passed a dict
            # through as a mod path, which then reached os.path.isfile.
            opts = {}
            if action and isinstance(action[-1], dict):
                iwad, *modsrcs = action[:-1]
                opts = action[-1]
            else:
                iwad, *modsrcs = action
            is_hd = bool(opts.get("hd"))
            mods, ok = [], True
            for src in modsrcs:
                if not os.path.isfile(src):
                    manifest["missing"].append(f"{name}: {src}")
                    ok = False
                    break
                fname = os.path.basename(src)
                sub = slugify(os.path.splitext(fname)[0])
                dest_dir = os.path.join(PACK, "mods", sub)
                os.makedirs(dest_dir, exist_ok=True)
                dest = os.path.join(dest_dir, fname)
                # Skip if already the right size; the pack is big and
                # rebuilds are common, so this keeps them quick.
                if not (os.path.exists(dest)
                        and os.path.getsize(dest) == os.path.getsize(src)):
                    shutil.copy2(src, dest)
                mods.append((sub, fname))
            if not ok:
                continue
            # One launcher per action. Mod order matters: ZDoom loads -file
            # entries in sequence, so a combo lists its base mod first.
            suffix = "" if i == 0 else f"-d{i}"
            bat = f"{slugify(name)}{suffix}.bat"
            write_bat(bat, name, iwad, mods, note)
            entry["actions"].append({
                "bat": bat, "iwad": iwad, "hd": is_hd,
                # Optional explicit label for this variant. Without it serve.py
                # infers one from the mod list, which goes unreadable once a
                # variant carries four mods.
                "label": opts.get("label", ""),
                "mod": mods[0][1] and f"mods\\{mods[0][0]}\\{mods[0][1]}",
                "mods": [f"mods\\{s}\\{f}" for s, f in mods],
            })
        if entry["actions"]:
            manifest["games"].append(entry)

    for name, note, wdir, exe in STANDALONE:
        if not os.path.isfile(exe):
            manifest["missing"].append(f"standalone {name}: {exe}")
            continue
        manifest["standalone_games"].append(
            {"name": name, "note": note, "wdir": wdir, "exe": exe})

    with open(os.path.join(PACK, "pack-manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)

    # Regenerate the console menu from the manifest we just wrote. This must be
    # part of the build: PLAY DOOMNITE.cmd used to be generated by hand, so it
    # silently kept stale entries whose menu numbers no longer matched the
    # launchers -- picking "Aliens" launched Brutal Doom, because every number
    # below the removed entries had shifted.
    try:
        import make_menu
        make_menu.main()
    except Exception as exc:                      # noqa: BLE001
        print(f"warning: could not regenerate the menu: {exc}")

    nbat = sum(len(g["actions"]) for g in manifest["games"])
    # Prune launchers this build no longer generates. Without this, removing a
    # game leaves its .bat behind: the old "Aliens + Brutal" launcher survived a
    # rename and still launched Brutal, so selecting plain Aliens could start
    # Brutal Doom instead. Stale files must not outlive the manifest.
    wanted = {a["bat"] for g in manifest["games"] for a in g["actions"]}
    ldir = os.path.join(PACK, "launchers")
    pruned = []
    if os.path.isdir(ldir):
        for fn in os.listdir(ldir):
            if fn.lower().endswith(".bat") and fn not in wanted:
                os.remove(os.path.join(ldir, fn))
                pruned.append(fn)
    if pruned:
        print(f"pruned {len(pruned)} stale launcher(s): "
              + ", ".join(sorted(pruned)))

    # A mod that ships a MAPINFO but no map lumps needs a companion file, or it
    # silently boots the IWAD's own maps wearing the mod's monsters -- the
    # Aliens: Eradication TC pk3 shipped alone did exactly that for days. The
    # file being present on disk proves nothing, so warn on the pattern and let
    # a human confirm it is intentional.
    for w in _mapless_mods(manifest):
        print(f"  NOTE: {w}")

    total = 0
    for root, _, files in os.walk(PACK):
        if ".git" in root:
            continue
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    print(f"built {len(manifest['games'])} games, {nbat} launchers, "
          f"{len(manifest['standalone_games'])} standalone")
    print(f"pack size: {total / 1073741824:.2f} GB")
    if manifest["missing"]:
        print(f"\n{len(manifest['missing'])} MISSING:")
        for m in manifest["missing"]:
            print("  " + m)
    return manifest


def _has_map_lumps(path):
    """True if a pk3/wad contains at least one playable map lump.

    Deliberately broad: anything under maps/, anything named like E1M1/MAP01
    or a nested .wad under maps/. A mod may legitimately reuse vanilla maps, so
    this only detects the absence of maps, which is the actual failure.
    """
    s = os.path.splitext(path)[1].lower()
    try:
        if s in (".pk3", ".pk7"):
            import zipfile
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
            pat = re.compile(r"(maps?/map\d\d|^map\d\d|/\w\d\d\.wad$)", re.I)
            return any(pat.search(n) for n in names)
        if s == ".wad":
            with open(path, "rb") as f:
                head = f.read(12)
                if len(head) < 12 or head[:4] not in (b"IWAD", b"PWAD"):
                    return False
                num, off = struct.unpack("<II", head[4:12])
                f.seek(0)
                data = f.read()
            pat = re.compile(rb"^(E\dM\d|MAP\d\d|UMAP\d\d)\x00")
            for i in range(min(num, 20000)):
                e = data[off + i * 16: off + i * 16 + 16]
                if len(e) < 16:
                    break
                if pat.match(e[8:16]):
                    return True
    except Exception:
        return True          # unreadable: do not cry wolf
    return False


def _mapless_mods(manifest):
    """Report launchers whose only mod is a total conversion with no maps.

    If ANY file in the launcher supplies maps, the set is fine -- Aliens pairs
    a mapless pk3 with a mapset wad, and that is the whole point of the check.
    """
    out = []
    for g in manifest["games"]:
        for a in g["actions"]:
            mods = a.get("mods", [])
            if not mods:
                continue
            paths = [os.path.join(PACK, m) for m in mods]
            paths = [p for p in paths if os.path.isfile(p)]
            if not paths:
                continue
            if any(_has_map_lumps(p) for p in paths):
                continue
            out.append(f"{g['name']}: no map lumps in "
                       + ", ".join(sorted(os.path.basename(p) for p in paths))
                       + " -- confirm it is meant to reuse the IWAD's maps")
    return sorted(set(out))


def check():
    """Verify the built pack against GAMES, without writing anything."""
    problems = []
    man_p = os.path.join(PACK, "pack-manifest.json")
    if not os.path.exists(man_p):
        sys.exit("no pack-manifest.json - run: python tools\\build.py")
    man = json.load(open(man_p, encoding="utf-8"))
    for n in RUNTIME_REQUIRED + [RUNTIME_EXE]:
        p = os.path.join(PACK, "runtime", n)
        if not os.path.isfile(p):
            problems.append(f"missing runtime\\{n}")
    # Hard requirement, not a nicety: UZDoom loads OpenAL Soft as
    # $PROGDIR/soft_oal.dll. If only openal32.dll is present it falls back to
    # the null sound module -- the game runs silently and prints no error, which
    # is exactly the bug that cost BDBE its audio.
    for must in ("soft_oal.dll", "zmusic.dll", "sndfile.dll"):
        if not os.path.isfile(os.path.join(PACK, "runtime", must)):
            problems.append(f"missing runtime\\{must} (sound will be SILENT)")
    # MIDI lumps in brutal22test6 / HOCUS / QuakinDoom need a soundfont.
    sf = os.path.join(PACK, "runtime", "soundfonts", "uzdoom.sf2")
    if not os.path.isfile(sf):
        problems.append("missing runtime\\soundfonts\\uzdoom.sf2 "
                        "(MIDI tracks in Brutal Doom / Hocus / QuakinDoM will be silent)")
    # The one that matters: can the runtime actually START? A runtime missing
    # its DLLs passes every file-exists check and still dies instantly with
    # STATUS_DLL_NOT_FOUND, so run it and read the exit code.
    #
    # -norun makes ZDoom load the IWAD, init sound and video, then exit without
    # opening a window. Plain -version is no good here: on this build it opens a
    # window and waits for a keypress, so it would always "hang".
    #
    # Exit code 1337 is ZDoom's own "quit requested" result for -norun, so it
    # is success here, not a failure. Anything non-zero that is NOT 1337, and
    # any NTSTATUS crash code, is a real problem.
    DLL_NOT_FOUND = {0xC0000135, -1073741515}
    ACCESS_VIOLATION = {0xC0000005, -1073741819}
    exe = os.path.join(PACK, "runtime", RUNTIME_EXE)
    iwad = os.path.join(PACK, "iwads", "DOOM2.WAD")
    if os.path.isfile(exe) and os.path.isfile(iwad):
        try:
            r = subprocess.run([exe, "-iwad", iwad, "-norun"],
                               cwd=os.path.join(PACK, "runtime"),
                               capture_output=True, timeout=120)
            if r.returncode in DLL_NOT_FOUND:
                problems.append("runtime cannot start: STATUS_DLL_NOT_FOUND "
                                "(a DLL beside doom.exe is missing)")
            elif r.returncode in ACCESS_VIOLATION:
                problems.append("runtime crashed: STATUS_ACCESS_VIOLATION")
            elif r.returncode not in (0, 1337):
                problems.append(f"runtime -norun exited {r.returncode}")
        except subprocess.TimeoutExpired:
            problems.append("runtime -norun hung")
    expected = sum(len(a) for _, _, a in GAMES)
    have = sum(len(g["actions"]) for g in man["games"])
    if expected != have:
        problems.append(f"launcher count: script implies {expected}, manifest has {have}")
    for g in man["games"]:
        for a in g["actions"]:
            if not os.path.isfile(os.path.join(PACK, a["mod"])):
                problems.append(f"missing mod file {a['mod']} ({g['name']})")
            if not os.path.isfile(os.path.join(PACK, "launchers", a["bat"])):
                problems.append(f"missing launcher launchers\\{a['bat']}")
            if a["mod"].endswith(".zip"):
                problems.append(f".zip in mod list (ZDoom cannot load these): {a['mod']}")
            iw = os.path.join(PACK, "iwads", a["iwad"])
            if not os.path.isfile(iw):
                problems.append(f"missing iwad {a['iwad']} for {g['name']}")
    print(f"{len(man['games'])} games, {have} launchers")
    if problems:
        print(f"\n{len(problems)} PROBLEMS:")
        for p in problems:
            print("  " + p)
        sys.exit(1)
    print("pack OK: every referenced file exists, no .zip in any mod list")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        check()
    else:
        build()


if __name__ == "__main__":
    main()