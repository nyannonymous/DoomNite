# Packaging an Electron release from the Z: drive

`npm run dist` writes `desktop/release/`. When the pack lives on the `Z:`
network drive this fails:

```
rm: cannot remove 'release/win-unpacked/resources/app.asar': Device or resource busy
  ⨯ EBUSY: resource busy or locked, rmdir '...\release\win-unpacked'
```

It is **not** a stuck process. Killing every `electron.exe` / `DoomNite.exe` /
`python.exe` does not clear it, and `tasklist` shows no holder. It is the
network drive refusing to release the directory.

**Build to local disk, then copy the artifacts back.** `release/` is gitignored,
so copying the finished files in afterwards is safe.

```bash
BD="$LOCALAPPDATA/Temp/dn-build/desktop"
rm -rf "$BD"; mkdir -p "$BD"

cd desktop
cp main.js preflight.js package.json package-lock.json "$BD/"
cp -r build "$BD/"
cp -r node_modules "$BD/"

cd "$BD" && npm run dist

cp release/"DoomNite Setup 1.0.0.exe" release/DoomNite-1.0.0-win.zip \
   "Z:/DOOM_PACK/desktop/release/"
```

`build/python` is staged by `prepare-python.js`, so copying `build/` is enough —
no need to re-download the runtime.

## Uploading

```bash
cd "Z:/DOOM_PACK/desktop/release"
export GH_TOKEN=$(cat ~/Desktop/ghp_* | tr -d '\r\n')
gh release upload v1.0.0 "DoomNite Setup 1.0.0.exe" DoomNite-1.0.0-win.zip \
  --repo nyannonymous/DoomNite --clobber
gh release edit v1.0.0 --repo nyannonymous/DoomNite --notes-file NOTES.md
```

Roughly 270 MB, so budget a few minutes. `--clobber` is needed when replacing
assets on an existing release.

## Verifying the build before shipping it

Run the packaged exe with the system `PATH` stripped, so a system interpreter
cannot mask a missing bundled one:

```bash
cd release/win-unpacked
DOOMNITE_PACK='Z:/DOOM_PACK' PATH="/c/Windows/system32:/c/Windows" ./DoomNite.exe
```

Then confirm entries are served and that `resources/python/python311._pth` was
rewritten to the pack root.

Two traps worth remembering, both of which fail only in a *packaged* build and
therefore survive any test run from a source checkout:

- **`PYTHONPATH` is ignored.** The embeddable runtime has `import site`
  commented out in `python311._pth`, and `site` is what reads `PYTHONPATH`.
- **A relative `..\..\..` entry in `._pth` cannot work.** From
  `resources/python` it resolves to the install directory, never to wherever the
  user's pack lives. `main.js` rewrites the file with the resolved absolute path
  at startup.

Chromium writes `ERROR:net::disk_cache ... Access is denied (0x5)` when run from
`release/` in the sandbox. Those are cache warnings, not app faults — the app
still serves.