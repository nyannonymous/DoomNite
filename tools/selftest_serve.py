"""Assert serve.py's HTTP refusal paths actually refuse.

Every guard in the HTTP layer exists because it matters -- integer-only
launch index, the 413 body cap, unknown install/packmod names -> 404, a
bool is not an int. ui/verify.mjs only ever exercises the happy path
through the UI, so nothing today fails if one of these guards is deleted.

This starts the real handler_factory() on an ephemeral port against a
throwaway one-game pack (same shape as selftest_watch.py's) and probes
each refusal directly with stdlib urllib. The pack's single entry has its
mod file ABSENT on purpose: launch() then refuses with "files are
missing" instead of spawning anything, so this test never starts a game.

  python tools/selftest_serve.py
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)      # serve.py lives in the pack root
sys.path.insert(0, PACK)

import serve  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}"
          + ("" if ok else f"   got {got!r}, want {want!r}"))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def build_pack(root):
    """A one-game pack whose only entry's mod is NOT on disk.

    Absent mod => launch() refuses before any Popen, so nothing here can
    start a game. The IWAD is present so the entry is a normal pack entry
    rather than a needs-setup one.
    """
    write(os.path.join(root, "pack-manifest.json"), json.dumps({
        "games": [{
            "name": "Refusal Game",
            "note": "",
            "actions": [{
                "bat": "refusal.bat", "iwad": "DOOM2.WAD", "hd": False,
                "label": "", "art": "",
                "mod": "mods\\refusal\\refusal.pk3",
                "mods": ["mods\\refusal\\refusal.pk3"],
            }],
        }],
        "standalone_games": [], "missing": [],
    }))
    write(os.path.join(root, "launchers", "refusal.bat"),
          '@echo off\r\nstart "" "%~dp0..\\runtime\\doom.exe"'
          ' -file "%~dp0..\\mods\\refusal\\refusal.pk3"'
          ' -iwad "%~dp0..\\iwads\\DOOM2.WAD"\r\n')
    write(os.path.join(root, "iwads", "DOOM2.WAD"), "iwad")
    write(os.path.join(root, "sources.json"),
          json.dumps({"base_url": "", "files": {}}))


def req(method, url, body=None):
    """One HTTP request. Returns (status, parsed-json-or-None).

    urllib raises HTTPError on 4xx/5xx; that is the *answer* here, not a
    failure -- catch it and read the code the server actually sent.
    """
    data = body.encode() if isinstance(body, str) else body
    r = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = {"_raw": raw.decode("utf-8", "replace")}
        return e.code, parsed


def main():
    saved = (serve.PACK, serve.MANIFEST, serve.SOURCES, serve.ENTRIES)
    tmp = tempfile.mkdtemp(prefix="doomnite-serve-")
    try:
        serve.PACK = tmp
        serve.MANIFEST = os.path.join(tmp, "pack-manifest.json")
        build_pack(tmp)
        serve.load_sources()
        serve.load_entries()
        check("the throwaway pack really has one entry", len(serve.ENTRIES), 1)

        Handler = serve.handler_factory()
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            print("\n/api/launch -- the index must be an integer, never a path")

            code, body = req("POST", base + "/api/launch", '{"index": "0"}')
            check("string index -> 400", code, 400)
            check("and the error says why",
                  (body or {}).get("error"), "index must be an integer")

            code, body = req("POST", base + "/api/launch", '{"index": true}')
            check("bool index -> 400 (True is an int in python, this is the"
                  " isinstance(idx, bool) guard)", code, 400)

            code, body = req("POST", base + "/api/launch", '{"index": 1.5}')
            check("float index -> 400", code, 400)

            code, body = req("POST", base + "/api/launch", '{"index": 999}')
            check("out-of-range index -> 400", code, 400)

            code, body = req("POST", base + "/api/launch", '{"index": 0}')
            check("valid index but files missing -> 400, and nothing"
                  " launched", code, 400)
            check("the error names the missing files",
                  (body or {}).get("error"), "that entry's files are missing")

            print("\n/api/launch -- body cap and json guard")

            code, body = req("POST", base + "/api/launch",
                             b'{"index": 0, "pad": "' + b"x" * 5000 + b'"}')
            check("oversized body -> 413", code, 413)
            check("and the error says why",
                  (body or {}).get("error"), "body too large")

            code, body = req("POST", base + "/api/launch", "{not json")
            check("unparseable body -> 400 bad json", code, 400)

            print("\n/api/reveal -- same integer-only guard")

            code, body = req("POST", base + "/api/reveal", '{"index": "0"}')
            check("string index -> 400", code, 400)

            code, body = req("POST", base + "/api/reveal", '{"index": 7}')
            check("unknown entry -> 404", code, 404)

            print("\n/api/install and /api/packmods -- unknown names -> 404")

            code, body = req("POST", base + "/api/install/definitely-not-a-spec",
                             "{}")
            check("unknown install name -> 404", code, 404)

            code, body = req("DELETE", base + "/api/install/definitely-not-a-spec")
            check("unknown install name on DELETE -> 404", code, 404)

            code, body = req("DELETE", base + "/api/packmods/not-a-game")
            check("unknown packmod name -> 404", code, 404)

            code, body = req("DELETE",
                             base + "/api/packmods/..%5C..%5Cwindows")
            check("a path-shaped name is just an unknown name -> 404,"
                  " never a filesystem path", code, 404)

            print("\n/api/dryrun -- the happy path, so the refusals above"
                  " are seen against a server that works")

            code, body = req("GET", base + "/api/dryrun?i=0")
            check("valid dryrun -> 200", code, 200)
            check("it returns a label",
                  (body or {}).get("label"), "Refusal Game")
            check("it returns a command",
                  "command" in (body or {}), True)

            code, body = req("GET", base + "/api/dryrun?i=abc")
            check("string index -> 400", code, 400)

            code, body = req("GET", base + "/api/dryrun")
            check("missing index -> 400", code, 400)

            print("\nunknown paths")

            code, body = req("POST", base + "/api/not-an-endpoint", "{}")
            check("unknown POST path -> 404", code, 404)

            code, body = req("GET", base + "/api/not-an-endpoint")
            check("unknown GET path -> 404", code, 404)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
    finally:
        serve.PACK, serve.MANIFEST, serve.SOURCES, serve.ENTRIES = saved
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print(f"FAILED ({len(FAILED)}): " + "; ".join(FAILED))
        sys.exit(1)
    print("all serve refusal-path checks passed")


if __name__ == "__main__":
    main()
