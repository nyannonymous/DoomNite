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
INDEX = os.path.join(PACK, "dist", "index.html")

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


def _fetchable():
    """Which pack-relative files sources.json gives a hosted URL for.

    Empty today -- hosting is the operator's choice -- but the point is that
    the UI reads this instead of hardcoding "only two games are installable".
    Add a URL to sources.json and the affected cards become installable with no
    further code change.

    Returns a set of normalised, forward-slash relative paths. Files with no
    URL are absent from the set, which is what makes them "in pack".
    """
    p = os.path.join(PACK, "sources.json")
    if not os.path.isfile(p):
        return set()
    try:
        doc = json.load(open(p, encoding="utf-8"))
    except (ValueError, OSError):
        return set()
    return {k.replace("\\", "/") for k, v in (doc.get("files") or {}).items()
            if v.get("urls")}


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
                # exists means "the launcher AND its content are present". A
                # total conversion that has not been downloaded yet must report
                # False, or clicking PLAY silently does nothing.
                "exists": (
                    os.path.isfile(os.path.join(PACK, "launchers", a["bat"]))
                    and _content_present(a)
                ),
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
                # are. Empty today, so nothing changes yet.
                "fetchable": bool(
                    a.get("mods")
                    and all(m.replace("\\", "/") in fetchable
                            for m in a["mods"])),
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
                     "exists": built[i]["exists"]}
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

    The UI is a Vite/React bundle ENTRIES to dist/ by `npm run build` in ui/. The
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
            # Vite emits content-hashed files into dist/assets/. Serving them is
            # what lets the built UI run without a bundler in the request path.
            if path.startswith("/assets/"):
                fn = os.path.basename(path)
                target = os.path.join(PACK, "dist", "assets", fn)
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
                # sees it again.
                return self._send(200, _json.dumps({
                    "missing": _iwad.needs_setup(),
                    "iwads": _iwad.iwads(),
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
                if action == "scan":
                    found, _ = _iwad.scan()
                    saved = _iwad.record({w: ps[0] for w, ps in found.items()})
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
                        ap = os.path.abspath(p_)
                        if os.path.isfile(ap) and _iwad._wad_score(ap):
                            good[w] = ap
                    if not good:
                        return self._send(400, _json.dumps({
                            "error": "no valid IWAD in that location",
                            "rejected": [w for w in chosen if w not in good],
                        }))
                    saved = _iwad.record(good)
                else:
                    return self._send(400, _json.dumps({"error": "bad action"}))
                return self._send(200, _json.dumps({
                    "iwads": saved, "missing": _iwad.needs_setup()}))
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
