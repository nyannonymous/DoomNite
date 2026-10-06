#!/usr/bin/env python3
"""
DoomNite web launcher.

    python serve.py            # start the server and print the URL
    python serve.py --port 8123
    python serve.py --no-open  # do not open a browser

A local web UI over pack-manifest.json. Serves the page, exposes the manifest
as JSON, and starts games on request.

Security model, deliberate and narrow:

* Binds to 127.0.0.1 only. Not reachable from the network.
* /api/launch takes an INTEGER index into the manifest. It never accepts a
  path, a command line, or any string that gets executed. The index is
  resolved to a known launcher .bat (or a known standalone exe) server-side,
  so the worst a malicious page on localhost can do is start a game that was
  already going to be in the menu.
* The launcher .bat files are what actually start UZDoom; the server shells out
  to cmd /c on a path it built itself, never one supplied by a request.
* /api/dryrun does the same resolution but only prints the command, so the UI
  can show what an entry runs without launching anything.

This is a launcher for one person on one machine. It is not hardened for
exposure to anything else.
"""
import argparse
import json
import re

import installer as _inst
import iwadfinder as _iwad
import os
import posixpath
import subprocess
import sys
import threading
import webbrowser

PACK = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(PACK, "pack-manifest.json")
INDEX = os.path.join(PACK, "app", "index.html")

# Resolved once at startup: a flat, ordered list of runnable entries. The UI and
# the launch endpoint both work off this, so a number always means the same game.
ENTRIES = []
# Rebound, never mutated in place, by load_entries(). See the comment there:
# in-place mutation raced with concurrent /api/entries requests.


def _variant_label(mods, shared_base, other_iwad, explicit=""):
    """A short human label for one variant of a game.

    When every variant of a game shares the same leading mod, that mod is the
    base and the rest are optional extras -- label it "base" or "+ extra". When
    the leading mods differ the variants are genuinely different games wearing
    one name (DukeBoomem ships 2.5D, Aliens-Only and 2.5D+Textures), so fall
    back to naming the mods rather than pretending one is a superset.

    other_iwad is the OTHER iwad this game offers, or None when every variant
    uses the same one -- so only the differing half gets an IWAD tag.
    """
    # An explicit label from the manifest wins. The inferred form reads like
    # "with BD_Black_NeuralUpscale.pk3, DoomHDTextures.pk3" once a variant
    # carries four mods, which is no use to anyone on a card.
    if explicit:
        label = explicit
        if other_iwad:
            label += "  [Doom 1]" if other_iwad == "DOOM.WAD" else "  [Doom 2]"
        return label
    base = mods[0] if mods else ""
    if shared_base and base:
        extras = mods[1:]
        label = "base" if not extras else "with " + ", ".join(extras)
    else:
        label = ", ".join(mods) or "no mod"
    if other_iwad:
        label += "  [Doom 1]" if other_iwad == "DOOM.WAD" else "  [Doom 2]"
    return label


def art_map():
    """Map each mod file's stem to its extracted title-screen filename.

    Matched against a launcher's mods so a tile can show the mod's own art
    when it ships a title screen, and the generated poster otherwise.
    """
    d = os.path.join(PACK, "art")
    if not os.path.isdir(d):
        return {}
    return {os.path.splitext(f)[0]: f for f in os.listdir(d)
            if os.path.isfile(os.path.join(d, f))}


def _sources_files():
    """The files map from sources.json, or {} if it is absent or unreadable."""
    p = os.path.join(PACK, "sources.json")
    if not os.path.isfile(p):
        return {}
    try:
        doc = json.load(open(p, encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return {k.replace("\\", "/"): (v or {})
            for k, v in (doc.get("files") or {}).items()}


def _has_host(rec):
    """True when sources.json gives this file somewhere to fetch it from.

    A per-file "urls" list wins. Failing that, a top-level "base_url" means
    every file is fetchable, so the operator sets one line instead of 90.

    "no_host" is the veto from fetcher.py, honoured identically here: if the two
    disagreed, the UI would offer to fetch a file the fetcher then refuses,
    which is the worst possible combination -- a button that always fails.
    """
    if rec.get("no_host"):
        return False
    if [u for u in (rec.get("urls") or []) if u]:
        return True
    return bool((SOURCES.get("_base_url") or "").strip())


# Top-level manifest config, read once. fetcher.py understands the same keys.
SOURCES = {}


def load_sources():
    global SOURCES
    p = os.path.join(PACK, "sources.json")
    SOURCES = {}
    if not os.path.isfile(p):
        return
    try:
        doc = json.load(open(p, encoding="utf-8"))
    except (ValueError, OSError):
        return
    SOURCES["_base_url"] = doc.get("base_url") or ""
    SOURCES["_files"] = doc.get("files") or {}


def _fetchable():
    """Which pack files are BOTH hosted AND not already here.

    Two conditions, and the second one is the one that was missing. Before any
    URL existed the set was always empty, so "fetchable" was really "has a URL"
    and every card read IN PACK for the wrong reason -- by luck. The moment a
    base_url appeared, all 90 files would have flipped to ON DEMAND even though
    every one of them is sitting on disk, which is a lie the UI would tell on
    every tile.

    ON DEMAND means "we can get this if it goes missing". A file that is
    present is IN PACK regardless of whether a URL exists. Presence is decided
    by size, not by hashing: this runs on every /api/entries request and
    re-hashing 3.7 GB of IWADs to label a tile would hang the UI.
    """
    out = set()
    for rel, rec in _sources_files().items():
        if not _has_host(rec):
            continue
        fp = os.path.join(PACK, rel.replace("/", os.sep))
        try:
            if os.path.getsize(fp) == (rec.get("size") or -1):
                continue        # present at the right size -> in pack
        except OSError:
            pass                # absent -> fetchable
        out.add(rel)
    return out


def _missing_mod_refs(action):
    """The files an entry's launcher wants, that are not on disk, under mods\\.

    Reads the same launcher .bat _content_present() parses, for the same
    reason: the manifest's `mods` list is basenames only, with the
    mods\\<slug>\\ folder component stripped off, so it cannot say WHERE a
    missing file has to go. The .bat is the one record that still has the real
    path, and it is a file this server wrote at build time.

    Deliberately limited to paths under mods\\. A missing IWAD is a different
    problem with its own flow (/api/setup, iwadfinder.py), and offering to
    hand-place DOOM2.WAD in the mods folder would be wrong advice.
    """
    bat = action.get("bat")
    if not bat:
        return []
    bp = os.path.join(PACK, "launchers", bat)
    try:
        txt = open(bp, "r", encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    base = os.path.dirname(bp)
    txt = txt.replace("%~dp0..\\", PACK + "\\").replace("%~dp0", base + "\\")
    mods_prefix = os.path.normcase(os.path.join(PACK, "mods") + os.sep)
    # Every launcher repeats its whole command line inside the DOOMNITE_DRYRUN
    # branch, so each path appears twice in the file. Report each file once:
    # "put HOCUS.pk3, HOCUS.pk3 in mods\hocus" reads like a broken hint.
    seen, out = set(), []
    for r in re.findall(r'"([^"]+\.(?:pk3|pk7|wad|WAD))"', txt):
        key = os.path.normcase(r)
        if not key.startswith(mods_prefix) or key in seen:
            continue
        seen.add(key)
        if not os.path.isfile(r):
            out.append(r)
    return out


def manual_hint(action, hosted=False):
    """Where a missing mod file has to go, or None.

    Any pack entry whose content is not on disk and is not one of
    installer.py's two on-demand downloads has a dead end in the UI: PLAY is
    disabled, there is no INSTALL button, and the card just says the files are
    missing. There are two ways out and the UI cannot name either of them by
    itself, so this is that answer:

      * a "browser" source mod (sources.json has no host for it -- ModDB
        answers 403 to scripted requests, so there is no download button to
        offer) can only ever arrive by hand;
      * a hosted one can be put back by hand *or* restored by rebuilding, which
        is what `hosted` lets the caller say.

    Either way the folder comes out of the launcher .bat, which the server
    itself wrote at build time -- the manifest's `mods` list is basenames only
    and cannot say where anything belongs.

    Returns {"folder": "mods\\<slug>", "files": [...], "hosted": bool} with
    folder relative to the pack, so nothing here is an absolute path the UI
    could turn into a traversal.
    """
    missing = _missing_mod_refs(action)
    if not missing:
        return None
    folder = os.path.dirname(missing[0])
    try:
        rel = os.path.relpath(folder, PACK)
    except ValueError:      # different drive: not a path inside the pack
        return None
    if rel.startswith(".."):
        return None
    return {"folder": rel,
            "files": sorted(os.path.basename(r) for r in missing),
            "hosted": bool(hosted)}


def load_entries():
    """Build the flat entry list from the manifest.

    A game with several launch configurations (Brutal Doom on either IWAD,
    QuakinDoom with or without QuakinMobs) becomes ONE entry per configuration
    still -- the index has to stay stable for /api/launch -- but they carry a
    shared group id so the UI can show a single card and offer the
    configurations as options instead of three near-identical cards.
    """
    global ENTRIES
    # Build into a local list and publish it in one assignment at the end.
    #
    # This used to mutate the module-global ENTRIES in place: ENTRIES.clear()
    # followed by refills. load_entries() is called on every /api/entries
    # request, so with the UI polling and a Vite dev server proxying on top,
    # one thread's clear() landed in the middle of another thread's iteration
    # over ENTRIES. Symptom: KeyError 'variant' at the variants comprehension,
    # printed as a traceback from load_entries, and the client saw
    # "RemoteDisconnected" because the handler thread died mid-response.
    # Measured 143 failures out of 200 concurrent requests before this.
    #
    # Assigning once is atomic under the GIL, so a reader either sees the whole
    # previous list or the whole new one -- never a partial one.
    built = []
    art = art_map()
    man = json.load(open(MANIFEST, encoding="utf-8"))
    fetchable = _fetchable()
    for g in man.get("games", []):
        acts = g.get("actions", [])
        iwads = {a["iwad"] for a in acts}
        # Shared base = every variant starts with the same mod.
        firsts = {tuple(a.get("mods", []))[:1] for a in acts}
        shared_base = len(firsts) == 1
        start = len(built)
        # Per-variant IWAD tag: None where every variant shares one IWAD, so the
        # label stops saying "[Doom 1]" on two identical rows. The tag names the
        # entry's OWN iwad, matching the card label in the manifest.
        def _own(a):
            return a["iwad"] if len(iwads) > 1 else None
        for a in acts:
            mods = [os.path.basename(m) for m in a.get("mods", [])]
            label = g["name"]
            if len(acts) > 1 and len(iwads) > 1:
                label += " [Doom 1]" if a["iwad"] == "DOOM.WAD" else " [Doom 2]"
            # exists means "the launcher AND its content are present". A total
            # conversion that has not been downloaded yet must report False, or
            # clicking PLAY silently does nothing.
            exists = (
                os.path.isfile(os.path.join(PACK, "launchers", a["bat"]))
                and _content_present(a)
            )
            # True when every mod this action loads has a hosted URL in
            # sources.json. The UI offers INSTALL for these and labels the rest
            # "in pack", instead of hardcoding which games those are.
            is_fetchable = bool(
                a.get("mods")
                and all(m.replace("\\", "/") in fetchable for m in a["mods"]))
            # A pack entry whose content is missing has no button to press:
            # PLAY is disabled, there is no INSTALL, and "ON DEMAND" is a
            # label, not an action. Say where the file goes and let the UI
            # watch for it (App.jsx polls while anything is in this state).
            # Without this the user is told "files are missing" and given
            # nothing to do about it. The two on-demand downloads are excluded
            # -- they have a real INSTALL button.
            manual = None
            if not exists and not a.get("needs_install"):
                manual = manual_hint(a, hosted=is_fetchable)
            built.append({
                "kind": "pack",
                "label": label,
                "note": g.get("note", ""),
                "iwad": a["iwad"],
                # Mods in load order; the UI shows these.
                "mods": mods,
                "bat": a["bat"],
                "size": os.path.getsize(
                    os.path.join(PACK, "launchers", a["bat"]))
                if os.path.isfile(os.path.join(PACK, "launchers", a["bat"])) else 0,
                "exists": exists,
                # Art resolution, in order of authority:
                #   1. an explicit "art" on the launcher action, set in
                #      build.py when a game has identity art of its own that
                #      load order would otherwise mask;
                #   2. the first mod that ships title art -- the usual case,
                #      since a game is usually named after its main mod;
                #   3. None, and the UI draws a generated poster.
                #
                # Step 1 exists because BDBE loads BDBE_v3.38.pk3 first, so the
                # plain "first match wins" rule gave both Black Edition groups
                # the BDBE art and masked HontE Remastered's own logo.
                "art": a.get("art") or next(
                    (art[m] for m in
                     (os.path.splitext(os.path.basename(x))[0] for x in a.get("mods", []))
                     if m in art), None),
                "group": g["name"],
                "variant": _variant_label(mods, shared_base, _own(a), a.get("label", "")),
                 "hd": bool(a.get("hd")),
                # An on-demand total conversion is never "installed" at build
                # time -- its files are fetched by installer.py on first click.
                # Without this the UI reports exists=True for a game whose 4 MB
                # of content are not on disk, and the install button never
                # appears.
                "needs_install": a.get("needs_install"),
                # True when every mod this action loads has a hosted URL in
                # sources.json. The UI offers INSTALL for these and labels
                # the rest "in pack", instead of hardcoding which games those
                # are.
                "fetchable": is_fetchable,
                # Where to put a hand-placed file, for a "browser" source entry
                # (see manual_hint). None for everything else, including the
                # two on-demand downloads -- those have an INSTALL button.
                "manual": manual,
                "standalone": bool(a.get("standalone")),
                "primary": False,
            })
        # Point every member of the group at all of its configurations, so the
        # UI can offer them without a second request. Ordered fewest-mods-first
        # so "base" is the default the user sees at the top.
        members = sorted(range(start, len(built)), key=lambda i: len(built[i]["mods"]))
        variants = [{"index": i,
                     "label": built[i]["variant"],
                     "mods": built[i]["mods"],
                     "iwad": built[i]["iwad"],
                     "exists": built[i]["exists"],
                     "manual": built[i]["manual"]}
                    for i in members]
        for i in members:
            built[i]["group_size"] = len(members)
            built[i]["variants"] = variants
            built[i]["primary"] = (i == start)
    for s in man.get("standalone_games", []):
        built.append({
            "kind": "standalone",
            "label": s["name"],
            "note": s.get("note", ""),
            "iwad": "",
            "mods": [],
            "exe": s["exe"],
            "wdir": s["wdir"],
            # Extra args, if the build gave any (SRB2 needs -window and a size).
            "args": s.get("args", []),
            "exists": os.path.isfile(s["exe"]),
            # Standalone games have no mods, so the mod-stem art match can
            # never resolve for them. The manifest names the art explicitly;
            # without passing it through here the field was written by
            # build.py, ignored here, and the tiles fell back to a generated
            # poster.
            "art": s.get("art") or "",
            # Present on every entry, not just pack ones. A standalone game has
            # no mods, so there is nothing sources.json could host for it, but
            # leaving the key off made the UI read .fetchable on an entry that
            # did not have it.
            "fetchable": False,
            # Same reasoning: a standalone game ships its own exe and has no
            # mods folder to hand-place anything into.
            "manual": None,
        })
    # Single atomic rebind: concurrent readers see either the whole old list or
    # the whole new one, never a partially built one. Safe under the GIL.
    ENTRIES = built
    return man


def _content_present(action):
    """Is the game content actually on disk, not just the launcher script?

    build.py writes a launcher for an on-demand total conversion whether or not
    it has been downloaded, so the .bat existing proves nothing.

    The manifest's `mods` list is only the tail of each path -- "foo.pk3" while
    the file actually lives at mods\\<subfolder>\\foo.pk3 -- so resolving those
    against mods\\ directly marked most of the shipped pack as uninstalled. The
    launcher .bat is the authoritative record of the real paths, so parse the
    paths out of its -file/-iwad arguments instead. Falls back to the manifest
    only for a standalone total conversion, whose pk3 the installer owns.
    """
    bat = action.get("bat")
    if bat:
        bp = os.path.join(PACK, "launchers", bat)
        try:
            txt = open(bp, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            return False
        # Expand %~dp0.. and %~dp0 to real absolute prefixes, exactly as cmd
        # would, then check each referenced file.
        base = os.path.dirname(bp)
        txt = txt.replace("%~dp0..\\", PACK + "\\").replace("%~dp0", base + "\\")
        refs = re.findall(r'"([^"]+\.(?:pk3|pk7|wad|WAD|iwad))"', txt)
        if refs:
            return all(os.path.isfile(r) for r in refs)
        # No quoted paths (a plain engine launch): nothing extra to verify.
        return True

    iwad = action.get("standalone_iwad")
    if iwad:
        return os.path.isfile(os.path.join(PACK, "mods", iwad.replace("\\", os.sep)))
    return True


def resolve(idx):
    """Index -> the entry, or None. The only path to launching anything."""
    if not isinstance(idx, int) or not (0 <= idx < len(ENTRIES)):
        return None
    return ENTRIES[idx]


def reveal_folder_for(idx):
    """The real on-disk folder an entry's content lives in, or None.

    Takes only a validated integer index -- the same guard /api/launch uses
    -- and resolves it entirely server-side. Never builds a path out of
    anything a request supplied.

    A standalone game's "install folder" is its working directory, which is
    whatever STANDALONE in tools/build.py recorded (outside the pack, next
    to its own exe).

    A pack entry's folder is read out of its OWN launcher .bat -- the same
    file _content_present() already parses -- rather than out of the mods
    list on the entry, because that list only carries basenames (see
    load_entries(): "mods": [os.path.basename(m) ...]), with the mods\\<slug>\\
    folder component stripped off. The .bat is the one place that still has
    the real path, and it is a file this server wrote at build time, not
    something a client can influence.
    """
    entry = resolve(idx)
    if entry is None:
        return None
    if entry["kind"] == "standalone":
        wdir = entry.get("wdir") or ""
        return wdir if os.path.isdir(wdir) else None
    bat = entry.get("bat")
    if not bat:
        return None
    bp = os.path.join(PACK, "launchers", bat)
    try:
        txt = open(bp, "r", encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    base = os.path.dirname(bp)
    txt = txt.replace("%~dp0..\\", PACK + "\\").replace("%~dp0", base + "\\")
    refs = re.findall(r'"([^"]+\.(?:pk3|pk7|wad|WAD))"', txt)
    mods_prefix = os.path.join(PACK, "mods") + os.sep
    # Prefer a reference that actually lives under mods\ -- for an on-demand
    # total conversion that is the installer.py destination; for a regular
    # pack entry it is the copied mod. Falls back to the IWAD's own folder
    # (iwads\) only if somehow nothing under mods\ was found.
    mod_refs = [r for r in refs if os.path.normcase(r).startswith(os.path.normcase(mods_prefix))]
    pick = mod_refs[0] if mod_refs else (refs[0] if refs else None)
    if not pick:
        return None
    folder = os.path.dirname(os.path.abspath(pick))
    # Must resolve inside the pack. Every input above came from a file this
    # server itself wrote, but checking costs nothing and the launch/-iwad
    # resolution logic this mirrors is exactly the kind of thing a future
    # edit could get subtly wrong.
    if not folder.lower().startswith(PACK.lower()):
        return None
    if os.path.isdir(folder):
        return folder
    # Not installed (an on-demand entry before its first download): nothing
    # to reveal rather than pointing Explorer at a folder that is not there.
    return None


def command_for(entry):
    """The command that entry runs, as a string, for display."""
    if entry["kind"] == "pack":
        bat = os.path.join(PACK, "launchers", entry["bat"])
        return f'cmd /c "{bat}"'
    args = " ".join(entry.get("args") or ())
    return (f'start "" /D "{entry["wdir"]}" "{entry["exe"]}"'
            + (f" {args}" if args else ""))


def launch(idx):
    entry = resolve(idx)
    if entry is None:
        return False, "no such entry"
    if not entry.get("exists"):
        return False, "that entry's files are missing"
    if entry["kind"] == "pack":
        bat = os.path.join(PACK, "launchers", entry["bat"])
        # cwd is the pack root so the launcher's relative paths resolve.
        subprocess.Popen(["cmd", "/c", bat], cwd=PACK,
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    else:
        # "start" treats the first quoted token as a window title, hence the
        # empty "". Args come after the exe so they reach the game, and each is
        # passed as a separate list element so nothing is re-split by the shell.
        argv = ["cmd", "/c", "start", "", "/D", entry["wdir"], entry["exe"]]
        argv += list(entry.get("args") or ())
        subprocess.Popen(argv, cwd=PACK)
    return True, entry["label"]


# ----------------------------------------------------------------- HTTP

def page():
    """Read the built UI's index.html per request.

    Deliberately not cached at startup: during development the bundle changes far
    more often than the server does, and a cached copy means every rebuild
    silently does nothing until you restart. One small file, one disk read.

    The UI is a Vite/React bundle ENTRIES to app/ by `npm run build` in ui/. The
    old hand-written index.html is kept as index.html.vanilla so it can be
    compared against or restored without a git checkout.
    """
    with open(INDEX, encoding="utf-8") as f:
        return f.read()


def handler_factory():
    from http.server import BaseHTTPRequestHandler
    import json as _json
    import urllib.parse as _up

    class Handler(BaseHTTPRequestHandler):
        server_version = "DoomNite"

        def log_message(self, format, *a):
            # Keep the console readable; launch lines are more useful than hits.
            if "/api/launch" in (self.path or ""):
                sys.stderr.write("  launch: " + (format % a) + "\n")

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = _up.urlparse(self.path).path
            if path in ("/", "/index.html"):
                if not os.path.isfile(INDEX):
                    # No bundle yet: say so, rather than serving a 404 and
                    # letting it look like a broken server.
                    return self._send(
                        503,
                        "<h1>DoomNite UI not built</h1>"
                        "<p>Run <code>npm run build</code> in "
                        "<code>ui/</code>, or <code>npm run dev</code> for "
                        "hot reload.</p>",
                        "text/html; charset=utf-8",
                    )
                return self._send(200, page(), "text/html; charset=utf-8")
            # Vite emits content-hashed files into app/assets/. Serving them is
            # what lets the built UI run without a bundler in the request path.
            if path.startswith("/assets/"):
                fn = os.path.basename(path)
                target = os.path.join(PACK, "app", "assets", fn)
                if not os.path.isfile(target):
                    return self._send(404, "", "text/plain")
                ctype = "text/css" if fn.endswith(".css") else (
                    "application/javascript" if fn.endswith(".js") else "application/octet-stream"
                )
                with open(target, "rb") as f:
                    return self._send(200, f.read(), ctype)
            if path == "/api/entries":
                man = load_entries()
                return self._send(200, _json.dumps({
                    "entries": ENTRIES,
                    "missing": man.get("missing", []),
                    "pack": os.path.basename(PACK),
                }))
            if path.startswith("/art/"):
                # Cover art extracted from the mods' own title screens. Served
                # from a fixed directory with a whitelisted extension -- the name
                # is a basename, so no traversal, and non-image types never get
                # a content type from us.
                # Percent-decode before touching the filesystem: art names carry
                # spaces and commas ("The Bikini Bottom Massacre 1,3.png"), so a
                # browser sends them as %20 and an undecoded lookup 404s.
                rel = _up.unquote(path[len("/art/"):])
                name = posixpath.basename(rel)
                if not name or "/" in name or "\\" in name:
                    return self._send(404, _json.dumps({"error": "not found"}))
                ext = os.path.splitext(name)[1].lower()
                ctype = {".png": "image/png", ".jpg": "image/jpeg",
                         ".jpeg": "image/jpeg", ".gif": "image/gif"}.get(ext)
                if not ctype:
                    return self._send(404, _json.dumps({"error": "not found"}))
                fp = os.path.join(PACK, "art", name)
                if not os.path.isfile(fp):
                    return self._send(404, _json.dumps({"error": "not found"}))
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), ctype)
            if path == "/api/setup":
                # First-run state. The UI shows the WAD finder only while
                # needs_setup() is non-empty, so a configured install never
                # sees it again. The paths reported are the ones a launch
                # actually uses, not whatever config.json happens to say.
                return self._send(200, _json.dumps({
                    "missing": _iwad.needs_setup(),
                    "iwads": {w: p for w in _iwad.WANTED
                              if (p := _iwad.available(w))},
                }))
            if path == "/api/setup/scan":
                found, searched = _iwad.scan()
                return self._send(200, _json.dumps({
                    "found": found, "searched": len(searched),
                    "missing": _iwad.needs_setup(),
                }))
            if path == "/api/install":
                # Status for every installable entry. The UI polls this while a
                # download runs, so it must be cheap and never block.
                return self._send(200, _json.dumps({"entries": _inst.status()}))
            if path == "/api/packmods":
                # Install status for every BAKED-IN game, derived live from
                # pack-manifest.json + what is actually on disk -- see
                # installer.pack_mod_registry(). Cheap: no hashing, just
                # os.path.isdir on each mod folder, so this is as pollable as
                # /api/install.
                per_game, _owners = _inst.pack_mod_registry()
                return self._send(200, _json.dumps({
                    "entries": [_inst.pack_mod_status(n) for n in per_game]
                }))
            if path == "/api/dryrun":
                q = _up.parse_qs(_up.urlparse(self.path).query)
                try:
                    idx = int(q.get("i", ["-1"])[0])
                except ValueError:
                    idx = -1
                e = resolve(idx)
                if e is None:
                    return self._send(400, _json.dumps({"error": "no such entry"}))
                return self._send(200, _json.dumps({
                    "label": e["label"], "command": command_for(e)}))
            return self._send(404, _json.dumps({"error": "not found"}))

        def do_DELETE(self):
            # Only used to remove an installed total conversion. Routed through
            # the same guard as POST: the name is looked up in SPECS, never
            # turned into a path.
            self.do_POST()

        def do_POST(self):
            path = _up.urlparse(self.path).path
            if path == "/api/setup":
                n = int(self.headers.get("Content-Length") or 0)
                if n > 8192:
                    return self._send(413, _json.dumps({"error": "body too large"}))
                try:
                    raw = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._send(400, _json.dumps({"error": "bad json"}))
                action = raw.get("action")
                install_problem = None
                if action == "scan":
                    found, _ = _iwad.scan()
                    # A WAD already sitting in the pack needs no scan hit and no
                    # copy -- record what is actually there so the launchers and
                    # config.json cannot disagree.
                    for w in ("DOOM.WAD", "DOOM2.WAD", "Hexen.wad"):
                        if not found.get(w) and _iwad.available(w):
                            found[w] = [_iwad.available(w)]
                    try:
                        saved = _iwad.record({w: ps[0] for w, ps in found.items()})
                    except OSError as e:
                        saved = _iwad.iwads()
                        install_problem = str(e)
                elif action == "set":
                    # The player picked a folder or named a file. Every path is
                    # resolved and CHECKED to actually be an IWAD before it is
                    # stored -- the UI cannot be trusted to have validated it,
                    # and a bad path here means every launch silently fails.
                    chosen = raw.get("iwads") or {}
                    good = {}
                    for w, p_ in chosen.items():
                        if w not in _iwad.WANTED or not isinstance(p_, str):
                            continue
                        ap = _iwad.resolve_wad_path(w, p_)
                        if ap:
                            good[w] = ap
                    if not good:
                        return self._send(400, _json.dumps({
                            "error": "no valid IWAD in that location",
                            "rejected": [w for w in chosen if w not in good],
                        }))
                    try:
                        saved = _iwad.record(good)
                    except OSError as e:
                        saved = _iwad.iwads()
                        install_problem = str(e)
                else:
                    return self._send(400, _json.dumps({"error": "bad action"}))
                missing = _iwad.needs_setup()
                body = {"iwads": saved, "missing": missing}
                if install_problem:
                    body["error"] = (
                        "saved your choice, but DoomNite could not put the WAD "
                        f"where the launcher reads it: {install_problem}")
                return self._send(200, _json.dumps(body))
            if path.startswith("/api/install/") and self.command == "DELETE":
                name = path[len("/api/install/"):]
                if name not in _inst.SPECS:
                    # Same reasoning as POST: never turn user input into a
                    # filesystem path.
                    return self._send(404, _json.dumps({"error": "unknown"}))
                try:
                    r = _inst.remove(name)
                except RuntimeError as e:
                    return self._send(409, _json.dumps({"error": str(e)}))
                return self._send(200, _json.dumps(r))
            if path.startswith("/api/packmods/") and self.command == "DELETE":
                # Uninstall of a BAKED-IN game -- every mod the pack ships
                # with, not just the two on-demand downloads. The name is
                # decoded then looked up in installer.pack_mod_registry(),
                # which is built straight from pack-manifest.json: there is
                # no path here that a request body or query string could
                # redirect, same discipline as the /api/install/ route above.
                name = _up.unquote(path[len("/api/packmods/"):])
                try:
                    r = _inst.remove_pack_mod(name)
                except KeyError:
                    return self._send(404, _json.dumps({"error": "unknown"}))
                return self._send(200, _json.dumps(r))
            if path.startswith("/api/install/"):
                # Only a known installer name from the POST body, and the name
                # is looked up in installer.SPECS -- never used to build a path
                # or a URL, so this cannot be steered at arbitrary files.
                name = _up.unquote(path[len("/api/install/"):])
                if name not in _inst.SPECS:
                    return self._send(404, _json.dumps({"error": "no such entry"}))
                force = False
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    if n > 4096:
                        return self._send(413, _json.dumps({"error": "body too large"}))
                    try:
                        raw = json.loads(self.rfile.read(n) or b"{}")
                    except ValueError:
                        return self._send(400, _json.dumps({"error": "bad json"}))
                    force = bool(raw.get("force"))
                # Runs in a worker thread: these are 4 MB and 44 MB downloads
                # and must not hold the request open.
                return self._send(202, _json.dumps(_inst.start(name, force=force)))
            if path == "/api/reveal" and self.command == "POST":
                # Open Explorer on an entry's own install folder. The body
                # carries only an integer INDEX -- the same shape and the same
                # guard as /api/launch -- and reveal_folder_for() resolves it
                # entirely server-side, exactly mirroring remove()'s "look it
                # up by a known key, never build a path from user input".
                n = int(self.headers.get("Content-Length") or 0)
                if n > 4096:
                    return self._send(413, _json.dumps({"error": "body too large"}))
                try:
                    raw = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._send(400, _json.dumps({"error": "bad json"}))
                idx = raw.get("index")
                if isinstance(idx, bool) or not isinstance(idx, int):
                    return self._send(400, _json.dumps({
                        "error": "index must be an integer"}))
                folder = reveal_folder_for(idx)
                if folder is None:
                    return self._send(404, _json.dumps({
                        "error": "no install folder for that entry"}))
                # explorer.exe on a path WE resolved -- never one from the
                # request. Popen, not run(): explorer can legitimately outlive
                # the request (it is a user-facing window, not a worker job),
                # and a non-zero exit from explorer.exe is normal (it returns
                # 1 fairly often even on success) so the exit code is not
                # checked the way a real failure elsewhere would be.
                try:
                    subprocess.Popen(["explorer.exe", folder])
                except OSError as e:
                    return self._send(500, _json.dumps({"error": str(e)}))
                return self._send(200, _json.dumps({"ok": True, "folder": folder}))
            if path != "/api/launch":
                return self._send(404, _json.dumps({"error": "not found"}))
            n = int(self.headers.get("Content-Length") or 0)
            if n > 4096:
                return self._send(413, _json.dumps({"error": "body too large"}))
            try:
                raw = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, _json.dumps({"error": "bad json"}))
            idx = raw.get("index")
            # Only an integer index. Never a path or a command.
            if isinstance(idx, bool) or not isinstance(idx, int):
                return self._send(400, _json.dumps({
                    "error": "index must be an integer"}))
            ok, info = launch(idx)
            if not ok:
                return self._send(400, _json.dumps({"error": info}))
            return self._send(200, _json.dumps({"ok": True, "label": info}))

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(MANIFEST):
        sys.exit(f"no {MANIFEST}\nrun: python tools\\build.py")
    load_sources()
    man = load_entries()
    missing = [e for e in ENTRIES if not e.get("exists")]

    from http.server import ThreadingHTTPServer
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), handler_factory())
    url = f"http://127.0.0.1:{args.port}/"
    n_pack = sum(1 for e in ENTRIES if e["kind"] == "pack")
    print(f"DoomNite  ->  {url}")
    print(f"  {len(ENTRIES)} entries ({n_pack} in-pack, "
          f"{len(ENTRIES) - n_pack} standalone)")
    if missing:
        print(f"  WARNING: {len(missing)} entries missing files: "
              + ", ".join(e['label'] for e in missing))
    print("  Ctrl-C to stop.")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        srv.server_close()


if __name__ == "__main__":
    main()
