"""Write NukemNet's LaunchDefaults.json from a DoomNite entry.

The gap this closes: NN stores ONE `file` list per game id, hand-edited JSON in
its user folder, so "play this mod online" means editing AppData by hand every
time. DoomNite already knows the mod, its load order and its IWAD -- this puts
that into NN's preset instead.

  python tools/nn_preset.py --list              # NN's folder, games, current file list
  python tools/nn_preset.py --entry 1           # DRY RUN: show what would be written
  python tools/nn_preset.py --entry 1 --write   # apply (backs the file up first)
  python tools/nn_preset.py --game "MyHouse.pk3" --write

Two facts this gets right that the old plan got wrong:

* NN here is a PORTABLE Electron build: `user/` sits next to NukemNet.exe, not
  in %LOCALAPPDATA%\\NukemNet. A writer aimed at the AppData path would create a
  config NN never reads. find_nn() checks the portable layout first.
* NN passes EVERY file, the IWAD included, as `-file <path>`; it does not use
  `-iwad`. The preset has to mirror NN's own shape or NN ignores it.

Nothing here is written without --write, and --write backs the original up
first, because this is the user's config and NN owns the rest of it.
"""
import argparse
import glob
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, PACK)

# The junctions this creates inside NN's Zandronum folder: (link name, pack
# subfolder). Named for the pack, so they sit beside whatever else is there
# instead of replacing it. Two, not one, because the pack's mods are at
# mods\<slug>\<file> and its IWADs at iwads\<file> -- and the Hexen IWAD only
# exists in the pack, so without the second link the Hexen entries stay
# unusable from NN.
LINKS = (
    ("doomnite-mods", "mods"),
    ("doomnite-iwads", "iwads"),
)

# How NN is allowed to name each game id. Only these two exist in NN's own game
# list, and the mapping is by IWAD, which is the only signal DoomNite has.
GAME_FOR_IWAD = {"DOOM.WAD": "doom", "DOOM2.WAD": "doom2"}


def mask(path):
    """Hide the real home directory. Standing rule: it never goes in output."""
    home = os.path.expanduser("~")
    try:
        if os.path.normcase(path).startswith(os.path.normcase(home)):
            return "~" + path[len(home):]
    except Exception:
        pass
    return path


def find_nn():
    """NukemNet's user folder, or None.

    $DOOMNITE_NN_DIR wins, then the portable layouts (user/ next to a
    NukemNet.exe), then the Electron default under %LOCALAPPDATA%.
    """
    env = os.environ.get("DOOMNITE_NN_DIR")
    if env and os.path.isfile(os.path.join(env, "LaunchDefaults.json")):
        return env
    if env and os.path.isfile(os.path.join(env, "user", "LaunchDefaults.json")):
        return os.path.join(env, "user")

    roots = [
        os.path.join(os.path.expanduser("~"), "Desktop", "NUKEMNET"),
        os.path.join(os.path.expanduser("~"), "Desktop", "NukemNet"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "NukemNet"),
    ]
    for root in roots:
        if not root:
            continue
        if os.path.isfile(os.path.join(root, "NukemNet.exe")):
            for cand in (os.path.join(root, "user"), root):
                if os.path.isfile(os.path.join(cand, "LaunchDefaults.json")):
                    return cand
        if os.path.isfile(os.path.join(root, "user", "LaunchDefaults.json")):
            return os.path.join(root, "user")
    # Last resort: any NukemNet.exe under the desktop.
    for exe in glob.glob(os.path.join(os.path.expanduser("~"), "Desktop", "*", "NukemNet.exe")):
        cand = os.path.join(os.path.dirname(exe), "user")
        if os.path.isfile(os.path.join(cand, "LaunchDefaults.json")):
            return cand
    return None


def nn_zandronum_dir(nn_user):
    """Where NN launches Zandronum from -- its Settings.json `games.*.zandronum.path`.

    That folder is what every path in the preset has to be reachable from, and
    it is not the NN folder: NN keeps its own config next to the exe and the
    engine's files wherever Zandronum was installed.
    """
    p = os.path.join(nn_user, "Settings.json")
    try:
        doc = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for _game, exes in (doc.get("games") or {}).items():
        if isinstance(exes, dict) and isinstance(exes.get("zandronum"), dict):
            path = exes["zandronum"].get("path")
            if path:
                return path
    return None


def entry_files(bat_path):
    """The mod/IWAD files an entry's launcher loads, in load order, absolute.

    Reads the .bat rather than pack-manifest.json for the same reason serve.py
    does: the manifest's `mods` list is basenames with the mods\\<slug>\\ part
    stripped off, so it cannot be turned back into a path. Each path appears
    twice in the file (the DOOMNITE_DRYRUN echo repeats the command line), so
    dedupe while keeping order.
    """
    base = os.path.dirname(bat_path)
    try:
        txt = open(bat_path, "r", encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    txt = txt.replace("%~dp0..\\", PACK + "\\").replace("%~dp0", base + "\\")
    seen, out = set(), []
    for r in re.findall(r'"([^"]+\.(?:pk3|pk7|wad|WAD))"', txt):
        key = os.path.normcase(r)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def nn_visible(path, zan_dir):
    """The path NN should be told to load, or None if NN cannot see the file.

    NN loads from its own Zandronum folder, so a path inside the DoomNite pack
    is no use to it. The same filename reachable from that folder -- flat, or
    through the `mods` junction, or through the pack's own LINK_NAME junction --
    is what goes in the preset. Nothing is copied: a copy would drift from the
    pack and double the disk.
    """
    if os.path.normcase(os.path.dirname(path)).startswith(os.path.normcase(zan_dir)):
        return path if os.path.isfile(path) else None
    name = os.path.basename(path)
    for cand in (os.path.join(zan_dir, name),
                 os.path.join(zan_dir, "mods", name)):
        if os.path.isfile(cand):
            return cand
    # The pack keeps its files one level deeper (mods\<slug>\<file>) than the
    # flat legacy folder, so each link is searched both ways.
    for link, _sub in LINKS:
        for cand in (glob.glob(os.path.join(zan_dir, link, "*", name))
                     + glob.glob(os.path.join(zan_dir, link, name))):
            if os.path.isfile(cand):
                return cand
    return None


def link_state(zan_dir):
    """[(link, target, exists)] for the junctions inside NN's folder."""
    return [(os.path.join(zan_dir, name),
             os.path.join(PACK, sub),
             os.path.isdir(os.path.join(zan_dir, name)))
            for name, sub in LINKS]


def is_junction(path):
    """True for a junction or symlink.

    A junction is invisible to os.path.islink() -- Python reports it as a plain
    directory -- so the only way to tell one from a real folder is the reparse
    point attribute, and it has to be read with os.lstat: os.stat FOLLOWS the
    junction and reports a plain directory (0x10) where lstat reports 0x410.
    Reading it with os.stat made this function say "not a junction" about the
    link it had just created, and the next run then refused to touch it.
    """
    try:
        return bool(os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, AttributeError):
        return False


def make_link(zan_dir, apply_it):
    """Point NN's folder at the pack's files, so NN can open what a preset names.

    Additive and reversible on purpose: NEW junctions beside whatever is already
    there, never a replacement, never a copy, and never over a real folder -- if
    that name is already a non-empty real directory this refuses rather than
    shadowing somebody's files. `rmdir` on a junction removes the link and
    leaves the pack alone.
    """
    rc = 0
    for link, target, exists in link_state(zan_dir):
        if exists and is_junction(link):
            print(f"junction : {mask(link)}  already linked, nothing to do.")
            continue
        if os.path.isdir(link) and os.listdir(link):
            print(f"{mask(link)} already exists and is not empty, and is not a link.")
            print("Refusing to touch it. Remove it by hand if it is a stale link.")
            rc = 1
            continue
        print(f"junction : {mask(link)}  ->  {mask(target)}")
        if not apply_it:
            continue
        if not os.path.isdir(target):
            print(f"  {mask(target)} does not exist, so there is nothing to link.")
            rc = 1
            continue
        p = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                           capture_output=True, text=True)
        print("  " + (p.stdout + p.stderr).strip())
        if not os.path.isdir(link):
            print("  the link was not created.")
            rc = 1
        else:
            print(f"  linked. NN can now open files under {mask(link)}")
    if not apply_it:
        print("DRY RUN. Nothing created. Add --write to create these.")
    return rc


def file_param(paths):
    """NN's own `file` param shape, mirrored exactly.

    value    newline-joined paths (NN's textarea binding)
    args     -file <path> repeated, which is how NN passes the IWAD too
    for      "shared" -- both host and joiners need the same list
    """
    label = ", ".join(os.path.basename(p) for p in paths)
    args = []
    for p in paths:
        args += ["-file", p]
    return {"value": "\n".join(paths), "htmlProp": "value", "for": "shared",
            "args": args, "valueLabel": label}


def load_defaults(nn_user):
    with open(os.path.join(nn_user, "LaunchDefaults.json"), encoding="utf-8") as f:
        return json.load(f)


def backup(nn_user):
    """One timestamped copy, before the first write. Returns the backup path."""
    src = os.path.join(nn_user, "LaunchDefaults.json")
    dst = src + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(src, dst)
    return dst


def plan(doc, game_id, files):
    """What would change, as a list of (game_id, param, before, after)."""
    exe = (doc.get("games", {}).get(game_id, {}).get("executables", {})
           .get("zandronum"))
    if exe is None:
        raise KeyError(f"NN has no game id {game_id!r}")
    before = (exe.get("params", {}).get("file") or {}).get("valueLabel")
    exe.setdefault("params", {})["file"] = file_param(files)
    after = exe["params"]["file"]["valueLabel"]
    return game_id, "file", before, after


def resolve_entry(arg):
    """A DoomNite entry by index or by game name, from the live pack."""
    import serve  # local import: only needed for --entry
    serve.load_sources()
    serve.load_entries()
    entries = serve.ENTRIES
    if arg.isdigit():
        idx = int(arg)
        if not (0 <= idx < len(entries)):
            raise SystemExit(f"no entry {idx}; the pack has {len(entries)}")
        return entries[idx]
    hits = [e for e in entries if e["label"].lower() == arg.lower()]
    if not hits:
        hits = [e for e in entries if arg.lower() in e["label"].lower()]
    if len(hits) != 1:
        raise SystemExit(f"{arg!r} matches {len(hits)} entries; be more specific")
    return hits[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="show NN's games and current file lists")
    ap.add_argument("--entry", help="DoomNite entry: an index, or (part of) a game name")
    ap.add_argument("--game", help="same as --entry, named for readability")
    ap.add_argument("--link", action="store_true",
                    help="create/refresh the junction that lets NN see the pack's mods")
    ap.add_argument("--write", action="store_true",
                    help="apply the change (a timestamped backup is made first)")
    args = ap.parse_args()

    nn_user = find_nn()
    if not nn_user:
        print("NukemNet's user folder was not found.")
        print("Set DOOMNITE_NN_DIR to the folder holding LaunchDefaults.json and retry.")
        return 2
    print(f"NN user folder : {mask(nn_user)}")
    zan = nn_zandronum_dir(nn_user)
    print(f"NN runs from   : {mask(zan) if zan else '(unknown - no Settings.json path)'}")

    if args.link:
        if not zan:
            print("NN's Zandronum folder is unknown, so there is nowhere to link.")
            return 1
        return make_link(zan, args.write)

    doc = load_defaults(nn_user)
    games = doc.get("games") or {}
    print(f"NN game ids    : {', '.join(sorted(games))}")

    if args.list or not (args.entry or args.game):
        for gid in sorted(games):
            exe = games[gid].get("executables", {}).get("zandronum", {})
            fp = (exe.get("params") or {}).get("file") or {}
            print(f"\n  {gid}: {fp.get('valueLabel') or '(no file list)'}")
            for p in (fp.get("value") or "").splitlines():
                print(f"      {mask(p)}{'' if os.path.isfile(p) else '   <- MISSING'}")
        if zan:
            link, ok = link_state(zan)
            print(f"\npack link      : {mask(link)}"
                  + ("  present" if ok else "  MISSING -- run --link --write"))
        if not args.list:
            print("\nPass --entry <index|name> to see the change it would make.")
        return 0

    want = args.entry or args.game
    entry = resolve_entry(want)
    bat = os.path.join(PACK, "launchers", entry["bat"])
    files = entry_files(bat)
    if not files:
        print(f"entry {entry['label']!r}: its launcher names no mod files.")
        return 1

    game_id = GAME_FOR_IWAD.get((entry["iwad"] or "").upper())
    if not game_id:
        print(f"entry {entry['label']!r}: IWAD {entry['iwad']!r} maps to no NN game id "
              f"({', '.join(sorted(GAME_FOR_IWAD))}).")
        return 1

    # One list of (source, NN-visible path or None), kept in step with `files`.
    # Two parallel lists (visible/blind) drift: a print that zips them pairs one
    # file's name with another file's path -- Requiem showed its IWAD where its
    # mod belonged.
    resolved = [(p, nn_visible(p, zan) if zan else None) for p in files]
    visible = [dst for _src, dst in resolved if dst]
    blind = [src for src, dst in resolved if not dst]

    # NN's own preset lists the IWAD first (`-file DOOM2.WAD -file mod.pk3`), so
    # mirror that: Zandronum reads the first valid IWAD it is given, and a list
    # that happens to put a mod first is a silent way to change which game runs.
    iwads = [p for p in visible if os.path.basename(p).upper() == (entry["iwad"] or "").upper()]
    order = iwads + [p for p in visible if p not in iwads]

    print(f"\nentry          : {entry['label']}")
    print(f"NN game id     : {game_id}")
    print("load order     :")
    for src, dst in resolved:
        if dst:
            mark = "" if dst == src else f"  ->  {mask(dst)}"
            print(f"    {os.path.basename(src)}{mark}")
        else:
            print(f"    {os.path.basename(src)}   <- NN cannot see this one")
    if blind:
        print("\nNN loads from its own Zandronum folder, and these are not there:")
        for p in blind:
            print(f"    {mask(p)}")
        print("  Link or place them there first (section 6 of todo.md). A preset that")
        print("  names a file NN cannot open silently drops the mod from the game.")

    if blind:
        print(f"\n{game_id}.file would be written WITHOUT {len(blind)} of "
              f"{len(files)} file(s). Not a valid preset.")
        if args.write:
            print("Refusing to write it.")
            return 1
        print("DRY RUN. Nothing written.")
        return 0

    _gid, _param, before, after = plan(doc, game_id, order)
    print(f"\n{game_id}.file")
    print(f"  before: {before or '(none)'}")
    print(f"  after : {after}")

    if not args.write:
        print("\nDRY RUN. Nothing written. Add --write to apply.")
        return 0

    bak = backup(nn_user)
    print(f"\nbacked up to {mask(bak)}")
    tmp = os.path.join(nn_user, "LaunchDefaults.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    os.replace(tmp, os.path.join(nn_user, "LaunchDefaults.json"))
    print(f"wrote {mask(os.path.join(nn_user, 'LaunchDefaults.json'))}")
    print("Close NN and reopen it (or reload its presets) to pick this up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
