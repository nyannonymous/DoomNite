# DoomNite

A numbered launcher for every Doom engine entry in the Playnite library.
Menu in one window, one `.cmd` per entry, no install step.

## Run it

Double-click `DoomNite.cmd`, type a number, type it again to confirm. `0` exits.

Launch straight from a shell without the menu:

```
DoomNite.cmd 15
```

Each `NN_<slug>.cmd` also works on its own by double-clicking, and carries the
full command in a `rem` line so you can read what it does before it runs.

Dry run — prints every command it would run instead of running it, into
`dryrun.log` next to the launchers:

```
DoomNite.cmd --dryrun
```

## Layout

```
data/doomnite.json     entry list: [label, cwd, exe, args, note]
tools/build_doomnite.py  generator
generated/             build output: DoomNite.cmd + NN_<slug>.cmd
```

`data/doomnite.json` holds machine-specific absolute paths, so the generated
files do too. To build for a different install root:

```
python tools/build_doomnite.py --out "Z:\GAMES\DoomNite"
```

Requires Python 3 for the build step only. The output is plain batch — once
generated, nothing else is needed to run it.

## Provenance

Every entry was read out of Playnite's library
(`%APPDATA%\Playnite\library\database.json`) and cross-checked on disk: the
exe, the working directory, the IWAD and every mod file referenced in the
arguments all exist. Nothing is hand-typed.

All GZDoom/UZDoom entries run from `Z:\GAMES\BRUTAL_DOOM (uwu)` unless the
list says otherwise (Hocus Pocus, Half Life in Doom and SRB2 have their own
install dirs).

## Mods menu — ghost cards + one-click install

`DoomNiteMods.cmd` lists total conversions that are **not** installed yet as
"ghost cards": listed with their artwork, sized, and the action is **Install**
where Play normally sits. Installing downloads the real release asset from
GitHub, verifies its size, extracts if it is a zip, and drops it in the mods
folder — after which the card becomes playable on the next build.

```
python tools/build_mods_menu.py     # regenerate DoomNiteMods.cmd + per-mod .cmd
python tools/install_mod.py --status   # what is installed
python tools/install_mod.py --install <id>
python tools/install_mod.py            # list, with ghost/play state
```

State lives in `data/catalog.json` (one entry per mod: art path, verified
release asset URL + byte size, repo, tag, IWAD, launch args). Installed-ness is
never stored — it is derived by checking whether the payload file exists in the
mods folder, so the menu cannot drift out of sync with reality.

`data/catalog_excluded.json` records the mods that were considered and rejected,
with reasons, so they are not silently re-added later.

Mods folder: `Z:\GAMES\BRUTAL_DOOM (uwu)` (override with `DOOMNITE_MODS_DIR`).
That is deliberate — it is the folder every existing `doomnite.json` entry
already runs out of, so an installed mod and a pre-installed mod are the same
thing to the launcher.

### ModDB is not in the auto path

`moddb.com` returns 403 behind a Cloudflare challenge to scripted requests, and
the interstitial never clears in a real browser either. A ModDB "Install" button
would therefore silently fail for real users, which is worse than not shipping
it. Mods whose binaries live only on ModDB use `source: "browser"` and open the
download page instead.

### Verified working

`--install doom64ex_plus` downloaded 4,107,000 bytes, size-checked, extracted,
and the card flipped to Play on the next build.

## Caveats carried over from Playnite

- `17_DoomRPG + Brutal Doom` is flagged unsupported in Playnite; it may crash
  or misbehave.
- The DOOM / DOOM2 IWAD entries need the shareware WADs that already sit in the
  Brutal Doom folder.
