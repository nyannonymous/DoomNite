"""Prove download_pack_mod() actually restores a game from the bucket.

  python tools/selftest_packmod_fetch.py

Moves ONE small game's mods folder aside, calls installer.download_pack_mod(),
and checks the files came back with the right bytes. Puts everything back
exactly as it was, whatever happens.

Why this is worth having: pack_mod_status() could always report a game as
missing, and the manifest could always say which files it wanted, but nothing
ever connected the two to fetcher.py. So the question "would a fresh install be
able to acquire this game?" had no answer in any test -- the first version of
this function read pack-manifest.json for file records, which it does not
contain, and reported every game as "no-host". That is the class of bug this
catches.

Safe to run: touches one small folder, restores it in a finally block, and
never runs if the folder is not present to begin with.
"""
import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, PACK)

import fetcher          # noqa: E402
import installer        # noqa: E402

# Deliberately the smallest mod in the pack: this test really downloads.
GAME = "Hocus Pocus 3D"
# A second, larger one for the "resolves but does not download" check.
BIG = "Brutal Doom v22 test 6"


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def main():
    fetcher.load()
    per_game, _ = installer.pack_mod_registry()
    if GAME not in per_game:
        print(f"SKIP  {GAME} is not in the registry")
        return 0

    folder = sorted(per_game[GAME])[0]   # a set: unordered, so sort for determinism
    src_dir = os.path.join(PACK, "mods", folder)
    if not os.path.isdir(src_dir):
        print(f"SKIP  mods/{folder} is not present; nothing to restore from")
        return 0

    original = {f: os.path.join(src_dir, f) for f in os.listdir(src_dir)}
    stash = os.path.join(PACK, "mods", f".selftest-stash-{folder}")
    ok = True

    print(f"game   : {GAME}")
    print(f"folder : mods/{folder}  ({len(original)} file(s))")
    print()

    try:
        # Record the true state, then remove the files.
        want = {f: (os.path.getsize(p), sha256(p)) for f, p in original.items()}
        shutil.move(src_dir, stash)

        status = installer.pack_mod_status(GAME)
        print(f"status says installed={status['installed']} "
              f"partial={status['partial']}")
        ok &= status["installed"] is False

        print("\ndownloading from the bucket...")
        results = installer.download_pack_mod(GAME)
        # "present" and "ok" are both successes: fetcher reports "present" for a
        # file already correct and "ok" after a verified fetch. The first
        # version of this test only allowed "ok" and so reported FAIL on a run
        # that had downloaded and verified 37 MB perfectly.
        for r in results:
            print(f"  {r['status']:10} {r['rel']}")
            if r["status"] not in ("ok", "present", "fetched"):
                ok = False

        # Did the bytes actually come back?
        print()
        for f, (size, digest) in want.items():
            back = os.path.join(src_dir, f)
            if not os.path.isfile(back):
                print(f"  MISSING after fetch: {f}")
                ok = False
                continue
            got_size = os.path.getsize(back)
            got_hash = sha256(back)
            same = got_size == size and got_hash == digest
            print(f"  {'OK  ' if same else 'BAD '} {f}  {got_size} bytes")
            ok &= same

    finally:
        # Restore exactly as found, whether or not any of the above worked.
        if os.path.isdir(stash):
            if os.path.isdir(src_dir):
                shutil.rmtree(src_dir)
            shutil.move(stash, src_dir)
        print("\nrestored the original folder")

    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())