"""Locate the player's own DOOM.WAD / DOOM2.WAD on first run.

Doomnite does not distribute IWADs. DOOM.WAD and DOOM2.WAD are commercial id
Software / Bethesda content with no free redistribution, so this module only
ever *finds* a copy the player already owns -- it never downloads one, and it
never copies one from anywhere.

Two strategies, in order:

1. scan the places Steam, GOG and the standalone installers actually put them;
2. ask the player to browse, if the scan comes up empty or finds the wrong thing.

Results are written to config.json next to the pack, and build.py reads that
instead of the hardcoded paths it used to rely on.
"""

import json
import os

PACK = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(PACK, "config.json")

# WADs we know how to use, by the filename build.py refers to.
WANTED = ("DOOM.WAD", "DOOM2.WAD", "Hexen.wad")

# Steam/GOG appids for the games that ship a usable WAD, plus the folder name
# under the library. Freeware Steam appids are deliberately absent: DOOM and
# DOOM2 complete are the paid ones, and those are the ones a player has.
#   Doom (classic) 228440 -> "Ultimate Doom"
#   Doom II 228440-era -> "DOOM2" ships as doom2 via "Doom Classic 1994"
_APP_DIRS = (
    "steamapps/common/Ultimate Doom",
    "steamapps/common/DOOM2",
    "steamapps/common/Doom Classic 1994",
    "GOG Games/DOOM 2",
    "GOG Games/DOOM",
    "GOG Games/Ultimate Doom",
    "Hexen",
)

# Steam library roots. Steam allows several per machine, and they are recorded
# in libraryfolders.vdf -- this reads it rather than guessing drive letters.
_STEAM_ROOTS = (
    r"C:\Program Files (x86)\Steam",
    r"C:\Program Files\Steam",
    r"D:\Steam", r"D:\SteamLibrary", r"D:\Games\Steam",
    r"E:\Steam", r"E:\SteamLibrary",
)


def _wad_score(path):
    """Is this a real IWAD, or a mod/level file that happens to share the name?

    A DOOM2.WAD from a total conversion is 11 MB; the real one is ~12 MB and
    starts with a known IWAD header. Size alone is a decent filter, but the
    definitive test is the IWAD identification string in the header.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return 0
    name = os.path.basename(path).lower()
    # Real IWADs are large. Anything under ~4 MB is a mod or a PWAD.
    if size < 4_000_000:
        return 0
    try:
        with open(path, "rb") as f:
            head = f.read(4)
    except OSError:
        return 0
    return size if _iwad_magic(head) else 0


def _iwad_magic(head):
    """True if this file declares itself an IWAD rather than a PWAD.

    The 4-byte magic at offset 0 is IWAD for a base game and PWAD for a level
    pack, and a PWAD must never be offered as an IWAD -- Doom II total
    conversions ship their own DOOM2.WAD that would pass a size check and boot
    the wrong game.
    """
    return head[:4] == b"IWAD"


def _steam_libraries():
    """Every Steam library root, from libraryfolders.vdf where readable."""
    roots = list(_STEAM_ROOTS)   # plain list[str]; vdf paths are appended
    for base in _STEAM_ROOTS:
        vdf = os.path.join(base, "steamapps", "libraryfolders.vdf")
        if not os.path.isfile(vdf):
            continue
        try:
            txt = open(vdf, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        # The file is VDF, but the path lines are quoted Windows paths, so a
        # regex is enough and avoids a parser dependency.
        import re
        for m in re.finditer(r'"path"\s*"([A-Za-z]:\\\\[^"]+)"', txt):
            p = m.group(1).encode().decode("unicode_escape")
            if os.path.isdir(p) and p not in roots:
                roots.append(p)
    return roots


def scan():
    """Search the usual install locations. Returns {WADNAME: [paths]}."""
    found = {}
    searched = []

    # 1. Steam and GOG library roots.
    for lib in _steam_libraries():
        for sub in _APP_DIRS:
            d = os.path.join(lib, sub)
            if not os.path.isdir(d):
                continue
            searched.append(d)
            for w in WANTED:
                p = os.path.join(d, w)
                if os.path.isfile(p) and _wad_score(p):
                    found.setdefault(w, []).append(p)

    # 2. Doomnite's own pack, in case the player already put them there.
    iwad_dir = os.path.join(PACK, "iwads")
    if os.path.isdir(iwad_dir):
        searched.append(iwad_dir)
        for w in WANTED:
            p = os.path.join(iwad_dir, w)
            if os.path.isfile(p) and _wad_score(p):
                found.setdefault(w, []).append(p)

    return found, searched


def load_config():
    if not os.path.isfile(CONFIG):
        return {}
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        # A corrupt config must not stop the app; treat it as "not set up yet"
        # so the first-run prompt shows again rather than the app dying.
        return {}


def save_config(cfg):
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, sort_keys=True)
    os.replace(tmp, CONFIG)   # atomic, so a crash mid-write cannot corrupt it


def iwads():
    """Resolved {WADNAME: path}, from config only. Never scans implicitly.

    Scanning is a first-run action; doing it on every start would be slow and
    would silently change where the game launches from.
    """
    return load_config().get("iwads", {})


def needs_setup():
    """True when the required WADs are not all accounted for."""
    have = iwads()
    return [w for w in ("DOOM.WAD", "DOOM2.WAD") if not have.get(w)]


def record(found):
    """Persist a scan result or a manual choice into config.json."""
    cfg = load_config()
    cur = cfg.setdefault("iwads", {})
    for w, p in found.items():
        cur[w] = os.path.abspath(p)
    save_config(cfg)
    return cur