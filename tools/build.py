#!/usr/bin/env python3
"""
Doom Knight - build the portable Doom pack.

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
import shutil
import sys

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BD = r"Z:\GAMES\BRUTAL_DOOM (uwu)"
GZ = r"Z:\GAMES\GZDOOM"
HD = r"Z:\GAMES\HEXEN HD"
HO = r"Z:\GAMES\Hocus Doom"
HL = r"Z:\GAMES\DOOM HALF LIFE"

# Files that must exist and be copied. These are the IWADs and the runtime.
IWADS = ["DOOM.WAD", "DOOM2.WAD"]
RUNTIME = ["uzdoom.exe", "game_support.pk3", "zmusic.dll"]

# (name, note, [(subfolder, source path, iwad)])
# subfolder is where it lands under mods\. "extra" is a raw -file fragment.
GAMES = [
    ("Brutal Doom v22 test 6", "Brutal Doom 22. Loads first, so combos list it first.",
     [("DOOM2.WAD", BD + r"\brutal22test6.pk3"),
      ("DOOM.WAD", BD + r"\brutal22test6.pk3")]),
    ("Brutal Doom + Doom Metal vol 5", "Adds the heavy-metal sound pack.",
     [("DOOM2.WAD", BD + r"\brutal22test6.pk3", BD + r"\DoomMetalVol5_44100.wad")]),
    ("Beautiful Doom", "HD 16:9 retexture of the original sprites.",
     [("DOOM2.WAD", BD + r"\Beautiful_Doom_716.pk3")]),
    ("DSD Remake", "Dave's Doom Done remake. Author's recommended edition.",
     [("DOOM2.WAD", BD + r"\DSD remake.pk3")]),
    ("DSD Remake (mp edition)", "Multiplayer maps included.",
     [("DOOM2.WAD", BD + r"\DSD remake mp edition.pk3")]),
    ("DSD Remake (gore edition)", "Extra gore.",
     [("DOOM2.WAD", BD + r"\DSD remake gore edittion.pk3")]),
    ("ULSimpDM", "Simpler, punchier hitscan weapons. Plays well with Brutal.",
     [("DOOM2.WAD", BD + r"\ulsimpdm.wad")]),
    ("Aliens: Eradication TC", "Full 8-level Aliens-style campaign.",
     [("DOOM2.WAD", BD + r"\ALIENS_ERADICATION_TC_2_0.pk3")]),
    ("Aliens: Eradication TC + Brutal", "Eradication on top of Brutal Doom.",
     [("DOOM2.WAD", BD + r"\brutal22test6.pk3", BD + r"\ALIENS_ERADICATION_TC_2_0.pk3")]),
    ("The Bikini Bottom Massacre", "SpongeBob, but in Doom.",
     [("DOOM2.WAD", BD + r"\The Bikini Bottom Massacre 1,3.wad")]),
    ("Doom III: Dusk 'til Dawn", "Doom 3's Rogue-like gameplay in Doom II.",
     [("DOOM2.WAD", BD + r"\D3.pk3"),
      ("DOOM2.WAD", BD + r"\D3.pk3", BD + r"\D3_UltraWide.pk3")]),
    ("DukeBoomem", "Duke Nukem with the Boomstick.",
     [("DOOM2.WAD", BD + r"\Duke-Boomem-2.5D.wad"),
      ("DOOM2.WAD", BD + r"\Duke-Boomem-Aliens-Only.wad"),
      ("DOOM2.WAD", BD + r"\Duke-Boomem-2.5D.wad", BD + r"\Duke-Textures.pk3")]),
    ("QuakinDoom: Total 3-D Edition", "Quake's guns and monsters, Doom's maps.",
     [("DOOM2.WAD", BD + r"\QuakinDoomT3DE.pk3"),
      ("DOOM2.WAD", BD + r"\QuakinDoomT3DE.pk3", BD + r"\QuakinMobs.pk3")]),
    ("Shadow Warrior", "Full conversion with the music pack.",
     [("DOOM2.WAD", BD + r"\SWMapPack.pk3", BD + r"\ShadowWarriorMusic.pk3"),
      ("DOOM2.WAD", BD + r"\SWMapPack.pk3")]),
    ("Call of Doom: Black Warfare", "Modern military campaign.",
     [("DOOM2.WAD", BD + r"\Cod1-11.wad")]),
    ("DBP37: Auger;Zenith", "2023 community hit. Maps only.",
     [("DOOM2.WAD", BD + r"\DBP37_AUGZEN.wad")]),
    ("MoonMan", "Vanilla-friendly. Uses the pk3: ZDoom cannot load the zip.",
     [("DOOM2.WAD", BD + r"\moon_man_v1_3_1.pk3"),
      ("DOOM.WAD", BD + r"\moon_man_v1_3_1.pk3")]),
    ("MyHouse.pk3", "A recreation of a childhood home.",
     [("DOOM2.WAD", BD + r"\myhouse.pk3")]),
    ("Hocus Pocus 3D", "Hocus Pocus, but 3D. Runs on the Doom II IWAD.",
     [("DOOM2.WAD", HO + r"\HOCUS.pk3")]),
    ("Hexen Remade", "The cancelled Hexen 1.5, finished.",
     [("DOOM2.WAD", GZ + r"\HEXENREMADE.wad")]),
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
    """The engine invocation. Relative to the pack root, so it stays portable."""
    parts = ['start "" "runtime\\uzdoom.exe"']
    for sub, fname in mods:
        parts.append(f'"mods\\{sub}\\{fname}"')
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
        "rem DOOM_KNIGHT_DRYRUN=1 prints the command instead of running it, so",
        "rem 'PLAY DOOM KNIGHT.cmd --dryrun N' can check every entry without",
        "rem launching anything. The menu sets it.",
        'if /I "%DOOM_KNIGHT_DRYRUN%"=="1" (',
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

    for n in RUNTIME:
        src = os.path.join(GZ, n)
        if not os.path.isfile(src):
            sys.exit(f"missing runtime file: {src}")
        shutil.copy2(src, os.path.join(PACK, "runtime", n))
        manifest["runtime"].append(n)

    for n in IWADS:
        src = os.path.join(GZ, n)
        if not os.path.isfile(src):
            manifest["missing"].append(f"iwad {n} not found at {src}")
            continue
        shutil.copy2(src, os.path.join(PACK, "iwads", n))
        manifest["iwads"].append(n)

    for name, note, actions in GAMES:
        entry = {"name": name, "note": note, "actions": []}
        for i, (iwad, *modsrcs) in enumerate(actions):
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
            # One launcher per action. Mod order matters: GZDoom loads -file
            # entries in sequence, so a combo lists its base mod first.
            suffix = "" if i == 0 else f"-d{i}"
            bat = f"{slugify(name)}{suffix}.bat"
            write_bat(bat, name, iwad, mods, note)
            entry["actions"].append({
                "bat": bat, "iwad": iwad, "hd": False,
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

    nbat = sum(len(g["actions"]) for g in manifest["games"])
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


def check():
    """Verify the built pack against GAMES, without writing anything."""
    problems = []
    man_p = os.path.join(PACK, "pack-manifest.json")
    if not os.path.exists(man_p):
        sys.exit("no pack-manifest.json - run: python tools\\build.py")
    man = json.load(open(man_p, encoding="utf-8"))
    for n in RUNTIME + IWADS:
        sub = "runtime" if n in RUNTIME else "iwads"
        p = os.path.join(PACK, sub, n)
        if not os.path.isfile(p):
            problems.append(f"missing {sub}\\{n}")
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