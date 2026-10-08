"""Would a PACKAGED DoomNite actually start?

    python tools/selftest_packaged.py

Two checks, both of which exist because 2.1.0 shipped a launcher that showed an
error dialog instead of the game grid. Neither was caught by any existing test,
and both are the kind of thing only a packaged install gets wrong:

1. **serve.py's own directory must be on sys.path.** The app runs serve.py with
   the embeddable Python, which ships a `python311._pth` pinning sys.path to
   three fixed entries. A `.pth` file suppresses Python's implicit
   current-directory behaviour, so the folder holding `installer.py` was not
   importable and every install died at:

       ModuleNotFoundError: No module named 'installer'

   This was NOT specific to 2.1.0 -- 2.0.0's serve.py has the same
   `import installer` -- so the app had been at the mercy of whatever the
   third `_pth` entry happened to resolve to.

2. **Everything serve.py imports must be inside the staged pack.** serve.py
   imports `mp_http` at module level and mp_http lives in `tools/`, which
   stage-pack.js did not stage: it was assumed to be developer-only. So a
   packaged install failed a second time with:

       ModuleNotFoundError: No module named 'mp_http'

Run against a REAL packaged build if one exists
(desktop/release/win-unpacked), so this measures the artifact rather than the
source tree. Falls back to the source tree when there is no build, and says so
-- a fallback run cannot catch a staging omission, so it reports that plainly
instead of pretending to pass.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
BUILT = os.path.join(PACK, "desktop", "release", "win-unpacked")

FAILED = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILED.append(name)


def main():
    print("packaged-startup checks\n")

    # ------------------------------------------------------------------
    # Locate a pack to test: the real staged one if it exists.
    pack = os.path.join(BUILT, "resources", "pack")
    from_build = os.path.isfile(os.path.join(pack, "serve.py"))
    py = os.path.join(BUILT, "resources", "python", "python.exe")

    if not from_build:
        pack, py = PACK, sys.executable
        print(f"  no packaged build at {BUILT}")
        print("  falling back to the SOURCE tree -- this cannot detect a")
        print("  staging omission, so treat a pass here as partial.\n")
    else:
        print(f"  testing the packaged build: {pack}")
        if not os.path.isfile(py):
            py = sys.executable
            print("  no embedded python; using this interpreter\n")
        else:
            print(f"  interpreter: {py}\n")

    # ------------------------------------------------------------------
    # 1. serve.py must put its own directory on sys.path before the first
    #    local import.
    serve_py = os.path.join(pack, "serve.py")
    with open(serve_py, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()

    def lineno(pred):
        for i, l in enumerate(lines):
            if pred(l):
                return i + 1
        return None

    def find_path_fix():
        """Locate the sys.path bootstrap, which may span several lines."""
        for i in range(len(lines) - 3):
            window = "\n".join(lines[i:i + 4])
            if ("abspath(__file__)" in window
                    and "sys.path" in window
                    and "_PACK_DIR" in window):
                return i + 1
        return None

    path_fix = find_path_fix()
    first_local_import = lineno(lambda l: l.startswith("import installer"))
    check("serve.py puts its own directory on sys.path", path_fix is not None,
          f"line {path_fix}" if path_fix else "not found")
    check("that happens BEFORE the first local import",
          path_fix is not None and first_local_import is not None
          and path_fix < first_local_import,
          f"sys.path fix line {path_fix}, import line {first_local_import}")

    # ------------------------------------------------------------------
    # 2. every module serve.py imports must be present in the staged pack.
    # A module is local to the pack only if the pack actually ships it.
    # Decide that by looking for the file rather than by guessing from the
    # import line: an earlier version of this test hard-coded a list of stdlib
    # names, then flagged `json` and `urllib.parse` as missing modules --
    # wrong, and it would have buried the real failure (mp_http) in noise.
    shipped = {}
    for root, _dirs, files in os.walk(pack):
        for f in files:
            if f.endswith(".py"):
                mod = f[:-3]
                shipped.setdefault(mod, os.path.relpath(root, pack).replace("\\", "/"))

    mods = set()
    for l in lines:
        s = l.strip()
        if not s.startswith("import "):
            continue
        head = s[len("import "):].split(" as ")[0].strip()
        for name in head.split(","):
            name = name.split(" as ")[0].strip()
            # only a top-level bare name is a candidate; dotted names are
            # stdlib or packages (urllib.parse, http.server, ...)
            if name.isidentifier() and name in shipped:
                mods.add(name)

    print(f"\n  local modules serve.py imports: {sorted(mods)}\n")
    for m in sorted(mods):
        check(f"{m}.py is in the staged pack", m in shipped,
              shipped.get(m, "MISSING"))
    for m in sorted(mods):
        in_root = os.path.isfile(os.path.join(pack, m + ".py"))
        in_tools = os.path.isfile(os.path.join(pack, "tools", m + ".py"))
        check(f"{m}.py is in the staged pack", in_root or in_tools,
              "tools/" if in_tools else ("root" if in_root else "MISSING"))

    # tools/ must exist at all if anything is imported from it.
    needs_tools = any(
        os.path.isfile(os.path.join(pack, "tools", m + ".py")) for m in mods)
    if needs_tools:
        check("tools/ is staged into the pack",
              os.path.isdir(os.path.join(pack, "tools")),
              f"{len(os.listdir(os.path.join(pack, 'tools')))} files"
              if os.path.isdir(os.path.join(pack, "tools")) else "absent")

    # ------------------------------------------------------------------
    # 3. The real proof: run serve.py with this interpreter and see whether it
    #    gets as far as parsing --help, which requires every module-level import
    #    to have succeeded.
    print()
    r = subprocess.run([py, "-u", serve_py, "--help"],
                       capture_output=True, text=True, timeout=90, cwd=pack)
    started = r.returncode == 0 and "usage: serve.py" in r.stdout
    check("serve.py starts (--help runs every module-level import)", started,
          "" if started else (r.stderr.strip().splitlines() or ["?"])[-1][:110])

    print()
    if FAILED:
        print(f"FAILED ({len(FAILED)}): " + "; ".join(FAILED))
        return 1
    print("a packaged DoomNite would start")
    return 0


if __name__ == "__main__":
    sys.exit(main())