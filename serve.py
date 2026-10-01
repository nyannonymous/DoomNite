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
* The launcher .bat files are what actually start ZDoom; the server shells out
  to cmd /c on a path it built itself, never one supplied by a request.
* /api/dryrun does the same resolution but only prints the command, so the UI
  can show what an entry runs without launching anything.

This is a launcher for one person on one machine. It is not hardened for
exposure to anything else.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import webbrowser

PACK = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(PACK, "pack-manifest.json")
INDEX = os.path.join(PACK, "index.html")

# Resolved once at startup: a flat, ordered list of runnable entries. The UI and
# the launch endpoint both work off this, so a number always means the same game.
ENTRIES = []


def load_entries():
    """Build the flat entry list from the manifest."""
    ENTRIES.clear()
    man = json.load(open(MANIFEST, encoding="utf-8"))
    for g in man.get("games", []):
        acts = g.get("actions", [])
        variants = {a["iwad"] for a in acts}
        for a in acts:
            label = g["name"]
            if len(acts) > 1 and len(variants) > 1:
                label += " [Doom 1]" if a["iwad"] == "DOOM.WAD" else " [Doom 2]"
            ENTRIES.append({
                "kind": "pack",
                "label": label,
                "note": g.get("note", ""),
                "iwad": a["iwad"],
                # Mods in load order; the UI shows these.
                "mods": [os.path.basename(m) for m in a.get("mods", [])],
                "bat": a["bat"],
                "size": os.path.getsize(
                    os.path.join(PACK, "launchers", a["bat"]))
                if os.path.isfile(os.path.join(PACK, "launchers", a["bat"])) else 0,
                "exists": os.path.isfile(os.path.join(PACK, "launchers", a["bat"])),
            })
    for s in man.get("standalone_games", []):
        ENTRIES.append({
            "kind": "standalone",
            "label": s["name"],
            "note": s.get("note", ""),
            "iwad": "",
            "mods": [],
            "exe": s["exe"],
            "wdir": s["wdir"],
            "exists": os.path.isfile(s["exe"]),
        })
    return man


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
    return f'start "" /D "{entry["wdir"]}" "{entry["exe"]}"'


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
        subprocess.Popen(["cmd", "/c", "start", "", "/D", entry["wdir"], entry["exe"]],
                         cwd=PACK)
    return True, entry["label"]


# ----------------------------------------------------------------- HTTP

def page():
    """Read index.html per request.

    Deliberately not cached at startup: during development the file changes far
    more often than the server does, and a cached copy means every UI edit
    silently does nothing until you restart. One small file, one disk read.
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
                return self._send(200, page(), "text/html; charset=utf-8")
            if path == "/api/entries":
                man = load_entries()
                return self._send(200, _json.dumps({
                    "entries": ENTRIES,
                    "missing": man.get("missing", []),
                    "pack": os.path.basename(PACK),
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

        def do_POST(self):
            path = _up.urlparse(self.path).path
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