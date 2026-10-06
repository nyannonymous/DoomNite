"""Check qa_mp_probe's settle window scales with the bytes an entry loads.

The probe's flat 14 s window produced a FALSE NEGATIVE on large PK3s: the
engine was still reading the file off disk when the window closed, so a mod
that hosts fine was recorded as "not hostable". This checks the replacement
without launching a game -- settle_for() is a pure function of the entry's args
and the files on disk.

  python tools/selftest_settle.py

Exit code 0 = all checks passed.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import qa_mp_probe as q  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}"
          + ("" if ok else f"   got {got!r}, want {want!r}"))
    return ok


def near(name, got, want, tol=0.05):
    ok = abs(got - want) <= tol
    if not ok:
        FAILED.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}"
          + ("" if ok else f"   got {got!r}, want ~{want!r}"))
    return ok


def sized(path, nbytes):
    """Create a file of exactly nbytes without writing all of them.

    NTFS zero-fills SetEndOfFile, so a sparse-ish 8 MB file is cheap enough for
    a test; the sizes here are megabytes, not the 200 MB the real bug was about.
    """
    with open(path, "wb") as f:
        f.truncate(nbytes)
    return path


print("parsing (the shapes real doomnite.json entries use)")
check("plain list",
      q.asset_names("brutal22test6.pk3 -iwad DOOM2.WAD -file DoomMetalVol5_44100.wad"),
      ["brutal22test6.pk3", "DOOM2.WAD", "DoomMetalVol5_44100.wad"])
# The bug this guards: shlex in POSIX mode eats the backslash and returns
# "DoomRPGDoomRPG.pk3" -- two distinct files silently become one bad name.
check("backslash subdir path survives",
      q.asset_names(r"DoomRPG\DoomRPG.pk3 DoomRPG\DoomRPG-Extras.pk3 -iwad DOOM2.WAD"),
      [r"DoomRPG\DoomRPG.pk3", r"DoomRPG\DoomRPG-Extras.pk3", "DOOM2.WAD"])
check("quoted name with spaces and a comma",
      q.asset_names('"The Bikini Bottom Massacre 1,3.wad" -iwad DOOM2.WAD'),
      ["The Bikini Bottom Massacre 1,3.wad", "DOOM2.WAD"])
check("flags and their values are not files",
      q.asset_names("mod.pk3 -file extra.wad -skill 4"),
      ["mod.pk3", "extra.wad"])
check("empty args", q.asset_names(""), [])
check("no -iwad anywhere", q.asset_names("mod.pk3"), ["mod.pk3"])

print("\nwindow scaling")
with tempfile.TemporaryDirectory() as tmp:
    sized(os.path.join(tmp, "small.pk3"), 3_000_000)        # 3 MB
    sized(os.path.join(tmp, "big.pk3"), 200_000_000)        # 200 MB
    os.makedirs(os.path.join(tmp, "sub"))
    sized(os.path.join(tmp, "sub", "nested.pk3"), 50_000_000)
    sized(os.path.join(tmp, "DOOM2.WAD"), 14_000_000)

    check("empty args -> base window", q.settle_for("", tmp), q.BASE_SETTLE)
    small = q.settle_for("small.pk3", tmp)
    print(f"  ----  3 MB mod -> {small:.1f}s "
          f"(base {q.BASE_SETTLE:.0f}s; the common case must not get slower)")
    check("small mod is within a second of the base window",
          small <= q.BASE_SETTLE + 1.0, True)
    near("200 MB mod -> base + 200*0.2",
         q.settle_for("big.pk3", tmp), q.BASE_SETTLE + 200 * q.SETTLE_PER_MB)
    check("nested path is sized, not skipped",
          q.settle_for(r"sub\nested.pk3", tmp) > q.BASE_SETTLE, True)
    check("the -iwad is counted too",
          q.settle_for("small.pk3 -iwad DOOM2.WAD", tmp)
          > q.settle_for("small.pk3", tmp), True)
    check("bigger asset set -> bigger window",
          q.settle_for("big.pk3 small.pk3", tmp)
          > q.settle_for("big.pk3", tmp), True)
    check("a missing file contributes 0, not an exception",
          q.settle_for("nope.pk3", tmp), q.BASE_SETTLE)
    check("the cap holds",
          q.settle_for("big.pk3 big.pk3 big.pk3 big.pk3 big.pk3 big.pk3", tmp),
          q.MAX_SETTLE)
    check("window is never below the floor",
          q.settle_for("small.pk3", tmp) >= q.BASE_SETTLE, True)

print("\nreal entries (data/doomnite.json)")
with open(os.path.join(REPO, "data", "doomnite.json"), encoding="utf-8") as fh:
    games = json.load(fh)
windows = []
for idx, (label, cwd, _exe, args, _note) in enumerate(games, start=1):
    if idx in q.NON_ZANDRONUM:
        continue
    w = q.settle_for(args, cwd)
    windows.append((w, idx, label))
    ok = q.BASE_SETTLE <= w <= q.MAX_SETTLE
    if not ok:
        FAILED.append(f"entry {idx} out of bounds")
    print(f"  {'PASS' if ok else 'FAIL'}  [{idx:2d}] {w:5.1f}s  {label}")

on_disk = [w for (w, _i, _l) in windows if w > q.BASE_SETTLE]
print(f"\n  {len(on_disk)}/{len(windows)} entries get more than the flat "
      f"{q.BASE_SETTLE:.0f}s window (the rest load nothing, or nothing that is on disk)")
if windows:
    top = max(windows)
    check("the heaviest entry is no longer capped at the old flat 14 s",
          top[0] > q.BASE_SETTLE, True)
    print(f"  heaviest: [{top[1]}] {top[2]} -> {top[0]:.1f}s")

print()
if FAILED:
    print(f"FAILED ({len(FAILED)}): " + "; ".join(FAILED))
    sys.exit(1)
print("all settle-window checks passed")
