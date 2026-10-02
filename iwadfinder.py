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


def resolve_wad_path(wad, path):
    """Resolve a selected IWAD file or install folder to the expected WAD."""
    if wad not in WANTED or not isinstance(path, str) or not path.strip():
        return None
    candidate = os.path.abspath(os.path.expanduser(path.strip()))
    if os.path.isdir(candidate):
        try:
            match = next(
                name for name in os.listdir(candidate)
                if name.casefold() == wad.casefold()
            )
        except (OSError, StopIteration):
            return None
        candidate = os.path.join(candidate, match)
    if (os.path.isfile(candidate)
            and os.path.basename(candidate).casefold() == wad.casefold()
            and _wad_score(candidate)):
        return candidate
    return None


def install(rel_name, src):
    """Make src available to the launchers as pack\\iwads\\<name>.

    The generated .bat files are %~dp0-relative and hardcode
    -iwad "%~dp0..\\iwads\\DOOM2.WAD", so the pack's own iwads\\ folder is the
    ONLY location a launch can read from. Recording a path in config.json is
    not enough: build.py copies IWADs in at build time, so a pack built before
    the player pointed at their Steam copy never gets one, and every Doom II
    launcher then fails on a file that is not there.

    A copy, deliberately, matching what build.py already does -- not a
    hardlink. A hardlink makes pack\\iwads\\DOOM2.WAD and the player's retail
    copy the SAME file, so anything that writes to one corrupts the other, and
    "is the pack copy still valid?" becomes unanswerable: they are always
    identical. Three IWADs is under 50 MB; correctness is worth more than
    that. The copy is staged as .tmp and moved into place, so an interrupted
    install never leaves a half WAD where a launch expects a whole one.
    """
    dest = os.path.join(PACK, "iwads", rel_name)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    src = os.path.abspath(src)
    if os.path.abspath(dest) == src:
        return dest
    if not _wad_score(src):
        raise OSError(f"{os.path.basename(src)} is not a usable IWAD")
    try:
        if (os.path.isfile(dest) and os.path.getsize(dest) == os.path.getsize(src)
                and sha256(dest) == sha256(src)):
            return dest
    except OSError:
        pass
    tmp = dest + ".tmp"
    try:
        os.remove(tmp)
    except OSError:
        pass
    try:
        import shutil
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise OSError(f"could not place {rel_name} in the pack: {e}")
    # The launcher will read whatever landed here, so confirm it rather than
    # reporting success on a file that cannot boot.
    if not _wad_score(dest):
        raise OSError(f"the copy of {rel_name} in the pack is not a usable IWAD")
    return dest


def sha256(path, chunk=1024 * 256):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def resolved(w):
    """The configured path for `w` only if it is still a real IWAD on disk.

    config.json is a record of a past decision, not a fact about the machine:
    the WAD can be moved, renamed, or deleted after it was written, and the
    launcher would then fail on a file that is not there. needs_setup() reads
    through this, so a stale entry re-opens setup instead of reporting
    "All set" over a WAD that does not exist.
    """
    p = iwads().get(w)
    if not p:
        return None
    r = resolve_wad_path(w, p)
    return r or None


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


def available(w):
    """Is `w` launchable right now, from either the recorded path or the pack?

    Both are checked because either one alone lies. config.json alone ignores
    a WAD that was moved or deleted after it was recorded; the pack folder
    alone ignores a pack that was built before the player ever pointed the
    finder at their own copy. A launch reads pack\\iwads\\<name> and nothing
    else, so that file being a valid IWAD is the condition that matters.
    """
    p = resolved(w)
    if p:
        return p
    return resolve_wad_path(w, os.path.join(PACK, "iwads", w))


def needs_setup():
    """True when the required WADs are not all accounted for."""
    return [w for w in ("DOOM.WAD", "DOOM2.WAD") if not available(w)]


def record(found):
    """Persist a scan result or a manual choice into config.json.

    Also installs each WAD into the pack's iwads\\ folder, because that is the
    only path the generated launchers use. Recording without installing left
    every Doom II entry reporting "missing content" forever: the finder said
    All set, config.json was correct, and the game still had nothing to boot.
    """
    cfg = load_config()
    cur = cfg.setdefault("iwads", {})
    problems = []
    for w, p in found.items():
        ap = os.path.abspath(p)
        cur[w] = ap
        try:
            install(w, ap)
        except OSError as e:
            # Kept in config.json either way: it is still the player's stated
            # preference, and needs_setup() reads through to what is on disk,
            # so setup stays open rather than reporting a WAD that cannot boot.
            problems.append(f"{w}: {e}")
    save_config(cfg)
    if problems:
        raise OSError("; ".join(problems))
    return cur