"""End-to-end check: does a clone fetch itself from a hosted base_url?

Serves the publishable subset over loopback, makes a bare clone (manifest +
fetcher, nothing else), and fetches into it. Verifies the landed file's sha256
against sources.json -- the same check fetcher.py itself makes.

This is the step that proves the "self-fetching clone" claim rather than
asserting it. Run:  python tools/selftest_fetch.py
"""
import functools
import hashlib
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    src = json.load(open(os.path.join(PACK, "sources.json"), encoding="utf-8"))
    files = src["files"]
    pub_files = {r: v for r, v in files.items() if not v.get("no_host")}
    vetoed = [r for r, v in files.items() if v.get("no_host")]
    # Only files actually on disk can be served as a mirror. A published file
    # the operator does not hold locally is not a failure -- it lives in the
    # bucket, and this self-test never reaches the network. Copying or linking
    # it used to raise FileNotFoundError here and take the whole run down,
    # which is why this only bites once a WAD is published but not owned.
    local = {}
    absent = []
    for rel in pub_files:
        fp = os.path.join(PACK, rel.replace("/", os.sep))
        if os.path.isfile(fp):
            local[rel] = pub_files[rel]
        else:
            absent.append(rel)

    tmp = tempfile.mkdtemp(prefix="doomnite-selftest-")
    pub = os.path.join(tmp, "pub")
    for rel in local:
        dst = os.path.join(pub, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            os.link(os.path.join(PACK, rel.replace("/", os.sep)), dst)
        except OSError:
            shutil.copy2(os.path.join(PACK, rel.replace("/", os.sep)), dst)

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=pub)
    handler.log_message = lambda *a, **k: None

    class Quiet(socketserver.TCPServer):
        allow_reuse_address = True

    with Quiet(("127.0.0.1", 0), handler) as srv:
        port = srv.server_address[1]
        base = f"http://127.0.0.1:{port}/"
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        # A clone: the two committed files, and literally nothing else.
        clone = os.path.join(tmp, "clone")
        os.makedirs(clone)
        shutil.copy2(os.path.join(PACK, "fetcher.py"), clone)
        with open(os.path.join(clone, "sources.json"), "w", encoding="utf-8") as f:
            json.dump(dict(src, base_url=base), f, indent=1, sort_keys=True)

        print(f"serving {len(local)} files at {base}")
        if absent:
            print(f"  not local, not served: {', '.join(sorted(absent))}")
        print(f"clone at {clone} (fetcher.py + sources.json, nothing else)\n")

        r = subprocess.run([sys.executable, "fetcher.py", "--check"],
                           cwd=clone, capture_output=True, text=True)
        print("--- fetcher --check ---")
        print(r.stdout.strip())
        if r.returncode != 0:
            print(r.stderr.strip())
            srv.shutdown()
            return 1

        # Fetch one small file and one big one. Small proves correctness fast;
        # big proves the streaming, Content-Length and .part->rename path.
        picks = []
        # Pick from what is actually being served: a published file the
        # operator lacks is a 404 on this mirror, and the self-test would then
        # report a fetch failure that says nothing about the fetcher.
        small = min(local, key=lambda r: local[r].get("size", 0))
        picks.append(small)
        big = max((r for r in local if r.startswith("mods/")),
                  key=lambda r: local[r].get("size", 0))
        if big != small:
            picks.append(big)

        r = subprocess.run([sys.executable, "fetcher.py", "--only",
                            picks[0].split("/")[0], "--jobs", "2"],
                           cwd=clone, capture_output=True, text=True)
        print("\n--- fetcher (one root) ---")
        print("\n".join(l for l in r.stdout.strip().split("\n")[-6:]))

        # Now fetch the exact picks directly, verifying each hash ourselves.
        sys.path.insert(0, clone)
        import fetcher
        files_map = fetcher.load()
        ok = True
        for rel in picks:
            rec = files_map[rel]
            url_list = fetcher.urls_for(rel, rec)
            state, path = fetcher.file_state(rel, rec)
            _rel, st, detail = fetcher.fetch_one(rel, rec, force=True,
                                                  verbose=False)
            got = sha256(path) if os.path.isfile(path) else None
            good = got == rec.get("sha256")
            ok = ok and good
            print(f"  [{'ok' if good else 'FAIL'}] {rel}")
            print(f"        {human(rec.get('size') or 0)}  "
                  f"url={url_list[0] if url_list else '(none)'}")
            print(f"        before={state} result={st} sha={str(got)[:12]}")

        # The veto must hold: a URL must never be synthesised for these.
        print("\n--- veto check ---")
        for rel in vetoed:
            urls = fetcher.urls_for(rel, files_map[rel])
            good = urls == []
            ok = ok and good
            print(f"  [{'ok' if good else 'FAIL'}] {rel} urls={urls}")

        srv.shutdown()

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())