"""Prove a bare clone fetches itself from the live R2 bucket.

    python tools/selftest_live.py

This is the end-to-end check the whole hosting effort exists to satisfy: a
directory holding ONLY the two committed files (fetcher.py + sources.json),
with base_url pointing at the real public bucket, fetching over real HTTPS and
verifying sha256 against the manifest.

The sandbox this normally runs in has no CA bundle wired into the default
interpreter, so it points SSL_CERT_FILE at certifi when certifi is present. On
an ordinary machine with a working Python that is unnecessary and the variable
is simply not set.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


def main():
    src = json.load(open(os.path.join(PACK, "sources.json"), encoding="utf-8"))
    base = (src.get("base_url") or "").strip()
    if not base:
        sys.exit("sources.json has no base_url -- nothing to test against")
    files = src["files"]
    pub = {r: v for r, v in files.items() if not v.get("no_host")}
    vetoed = {r for r, v in files.items() if v.get("no_host")}

    print(f"base_url: {base}")
    print(f"manifest: {len(files)} files, {len(vetoed)} vetoed\n")

    # A clone is what git actually hands someone: the committed files only.
    tmp = tempfile.mkdtemp(prefix="doomnite-live-")
    clone = os.path.join(tmp, "clone")
    os.makedirs(clone)
    for f in ("fetcher.py", "sources.json"):
        shutil.copy2(os.path.join(PACK, f), clone)
    print(f"clone holds only: {sorted(os.listdir(clone))}")
    print(f"  {human(sum(v.get('size') or 0 for v in pub.values()))} to fetch\n")

    # Fetch a spread: smallest, a runtime lib, a mid-size mod, and the largest
    # mod. The large one is the one that exercises streaming and the
    # .part-then-rename path, so it is worth the bandwidth.
    picks = sorted(pub, key=lambda r: pub[r].get("size", 0))
    chosen = [picks[0]]
    for cand in ("runtime/uzdoom.pk3", "mods/dn3doom/DN3DooM.pk3"):
        if cand in pub and cand not in chosen:
            chosen.append(cand)
    big = max(pub, key=lambda r: pub[r].get("size", 0))
    if big not in chosen:
        chosen.append(big)
    print("fetching:", ", ".join(chosen), "\n")

    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")

    # The fetch driver lives in the clone so it imports that fetcher.py, not
    # this one. Writing a file beats an inline -c string, which is unreadable
    # once it has newlines in it.
    driver = os.path.join(clone, "_drive.py")
    with open(driver, "w", encoding="utf-8") as f:
        f.write(
            "import json, sys\n"
            "import fetcher\n"
            "fm = fetcher.load()\n"
            "ok = True\n"
            "for rel in json.load(open('_picks.json', encoding='utf-8')):\n"
            "    rec = fm[rel]\n"
            "    urls = fetcher.urls_for(rel, rec)\n"
            "    print('   %s -> %s  (%d url(s))' % (rel, urls and '' or '', len(urls)),\n"
            "          flush=True)\n"
            "    _r, st, detail = fetcher.fetch_one(rel, rec, force=True,\n"
            "                                     verbose=False)\n"
            "    print('   %s -> %s  %s' % (rel, st, detail), flush=True)\n"
            "    # fetch_one's success state is 'fetched'; 'ok' means 'already\n"
            "    # present', which force=True skips past. Accept both.\n"
            "    ok = ok and st in ('fetched', 'ok')\n"
            "print('ALL_OK' if ok else 'SOME_FAILED')\n")
    with open(os.path.join(clone, "_picks.json"), "w", encoding="utf-8") as f:
        json.dump(chosen, f)

    r = subprocess.run([sys.executable, "-u", "_drive.py"], cwd=clone,
                       env=env, capture_output=True, text=True, timeout=3000)
    print(r.stdout.strip())
    if r.stderr.strip():
        print("stderr:", r.stderr.strip()[-400:])

    # Verify independently rather than trusting fetcher's own return code.
    ok = True
    print("\n--- independent hash check ---")
    for rel in chosen:
        p = os.path.join(clone, rel.replace("/", os.sep))
        if not os.path.isfile(p):
            print(f"  [FAIL] {rel} not present")
            ok = False
            continue
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        good = h.hexdigest() == pub[rel]["sha256"]
        ok = ok and good
        print(f"  [{'ok' if good else 'FAIL'}] {rel}  "
              f"{human(os.path.getsize(p))}  {h.hexdigest()[:12]}")

    print("\n--- veto enforcement in the clone ---")
    sys.path.insert(0, clone)
    import fetcher
    fm = fetcher.load()
    for rel in sorted(vetoed):
        urls = fetcher.urls_for(rel, fm[rel])
        good = urls == []
        ok = ok and good
        print(f"  [{'ok' if good else 'FAIL'}] {rel} urls={urls}")

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("PASS -- a bare clone fetches itself from Cloudflare"
                  if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())