# DoomNite

A portable Doom mod launcher. One folder holds the GZDoom runtime, the IWADs and
the mods; every path is relative, so the whole thing runs from a USB stick or
any drive letter.

```
python fetcher.py            # pull the 3.4 GB of assets, checksum-verified
python serve.py              # open the launcher in your browser
```

No install. No `npm install`. No build step.

---

## What is actually in this repo

Very little, on purpose.

| | |
|---|---|
| **16 games**, **31 launchers** | each is a mod or mod combo on a stock IWAD |
| **66 asset files, 3.4 GB** | the GZDoom runtime, shareware IWADs, 32 mods |
| **~130 tracked files** | the code |

The 3.4 GB is **not** in git. Not because it was forgotten — because it is
copyrighted material and far past what git should hold. `runtime/`, `iwads/`
and `mods/` are gitignored deliberately.

Instead the repo carries the **recipe**, and fetches the ingredients:

- `sources.json` — every file, with exact size and sha256
- one `base_url` pointing at a public Cloudflare R2 bucket
- `fetcher.py` — downloads, verifies each hash, skips anything already correct

That is what makes a clone self-fetching. `git clone` gets you the code;
`fetcher.py` gets you Doom.

---

## Get it running

```bash
git clone https://github.com/nyannonymous/DoomNite.git
cd DoomNite

python fetcher.py --check     # report what is missing, download nothing
python fetcher.py             # fetch it all, verifying sha256 as it goes
python serve.py               # launcher opens at http://127.0.0.1:8765/
```

`--check` first is worth it. It tells you exactly what is present, what is
missing and what is corrupt before you spend 3.4 GB of bandwidth finding out.

Already have some files? Re-running is cheap. `fetcher.py` re-hashes what is
on disk, skips anything correct, and fetches only the rest.

### What it will not do

It will not hand you `DOOM2.WAD` or `Hexen.wad`. Those are commercial
id Software releases, so they are marked `no_host` in `sources.json`, refused
at upload, and absent from the bucket — `HTTP 404`, verified.

Shareware `DOOM.WAD` **is** included. That is the freely distributable one.

If you own `DOOM2.WAD`, drop it in `iwads/` yourself and it will be picked up.

---

## The launcher

`python serve.py` opens a retro-industrial UAC terminal: the selected game's
art fills the background, a details pane types out on the right, arrow keys to
move, Enter to launch.

It binds to `127.0.0.1` only. The launch endpoint takes an **integer index**,
never a path or command string, and resolves it server-side against the
manifest — so the worst a hostile page on localhost can do is start a game that
was already in the menu.

It is a single-user local tool. Do not expose it to a network.

### The games

| | |
|---|---|
| Brutal Doom v22 | Black Edition: Enhanced Episode 1, HontE Remastered |
| Aliens: Eradication TC | The Bikini Bottom Massacre |
| Adventures of Square | Requiem |
| DukeBoomem | QuakinDoom: Total 3-D Edition |
| Shadow Warrior | DBP37: Auger;Zenith |
| MoonMan | MyHouse |
| Hocus Pocus 3D | Hexen Remade HD |
| DN3DooM | |

Most run on either `DOOM.WAD` or `DOOM2.WAD`; the launcher knows which.

---

## Things that bite

These cost real hours. Read them before changing anything.

**ZDoom silently ignores `.zip`.** A zip passed to `-file` is dropped without
error, so the game launches as vanilla Doom with nothing explaining why. Every
mod here is a `.pk3` or `.wad`, and `--check` fails the build if a `.zip` ever
reaches a mod list.

**GZDoom must be copied as a whole set.** Copy `uzdoom.exe` alone and it dies
instantly with `STATUS_DLL_NOT_FOUND` (`0xC0000135`) — `openal32.dll`,
`libsndfile-1.dll`, `libfluidsynth64.dll` and friends have to sit beside it.
It fails *silently*: no console output, no window, and `start` reports success,
so a file-exists check passes happily on a pack that cannot start a single
game. `build.py --check` runs `uzdoom.exe -iwad ... -norun` and reads the exit
code, accepting only `0` and GZDoom's own quit code `1337`.

**Copy the `RUNTIME_PK3` list, not every `.pk3`.** Loose mod pk3s (Brutal
Doom, DN3DooM, SWMapPack) get loaded into every entry if you do.

**Mod order matters in combos.** GZDoom loads `-file` in sequence. A combo
lists its base mod first, patch second. Swapping them usually still runs, but
changes which definition wins.

**Hocus Pocus 3D needs the Doom II IWAD** despite being Doom 1 style.

---

## Layout

```
serve.py            local web server + launcher API (stdlib only)
fetcher.py          the asset fetcher and hash verifier
sources.json        68 entries, sizes + sha256, and the base_url
config.json         settings
art/                game art used by the UI
dist/               built UI, committed so the server runs without npm
ui/                 React + Vite + Tailwind source for dist/
tools/build.py      the game table — the one file you edit to add games
tools/make_menu.py  generate the batch menu from the manifest
tools/selftest_live.py  prove a bare clone fetches from the live bucket
runtime/            uzdoom.exe + DLLs        (fetched)
iwads/              DOOM.WAD                 (fetched)
mods/               one folder per mod        (fetched)
```

`tools/build.py` is the only file you edit to change the game list. Its `GAMES`
table maps each entry to mod files and an IWAD. Everything else reads the
manifest that build produces.

### Verify without launching anything

Launching all 31 entries at once starts 31 copies of ZDoom. Don't.

```bash
python tools/make_menu.py --dryrun 15      # what would entry 15 run?
python tools/build.py --check              # every referenced file exists?
```

`--dryrun` logs the command line it *would* execute instead of running it.

---

## Rebuilding the manifest

After changing what the pack contains:

```bash
python tools/make_sources.py            # re-hash, rewrite sources.json
python tools/make_sources.py --verify   # report drift, write nothing
```

---

## Working on the UI

```bash
cd ui
npm ci          # or npm install
npm run dev
```

React, Vite, Tailwind, Framer Motion. `dist/` is committed so `serve.py` works
on a fresh clone with no `npm install` — rebuild it before committing UI
changes.

`npm run build` and `npm run dev` both check for `node_modules` first and tell
you to run `npm ci` if it's missing, rather than failing with npm's
`'vite' is not recognized`.

### Building from the repository root

There is a root `package.json` that forwards to `ui/`, so tooling which runs
`npm run build` in the repo root works:

```
npm run build     # -> npm --prefix ui ci && npm --prefix ui run build
npm run dev
npm run preview
```

This is what a CI or Pages-style build expects. Set the **build command** to
`npm run build` and the **output directory** to `dist` — the root manifest
builds into the root `dist/`, not `ui/dist`.

Verified from a fresh clone: the root build succeeds and emits byte-identical
assets to the committed `dist/`.

### Deploying the UI to a static host

You can host the interface on Cloudflare Pages or similar, but only the
interface: **there is no backend there.** `serve.py` is the actual server, and
it provides `/api/entries`, `/api/launch` and `/art/`. A static host answers
those paths with `index.html`, so the page loads and then fails.

The UI detects this and says so, rather than reporting a JSON parse error:

```
Expected JSON from .../api/entries but got text/html.

This is the launcher UI talking to a static host, which has no backend.
serve.py is the actual server -- run it from the pack root:
    python serve.py
```

**Launching games needs the Python process on your own machine.** A Pages
deploy is a read-only catalogue view, nothing more.

---

## The desktop app

`desktop/` is an Electron shell around the same server. It resolves the pack,
spawns `serve.py --no-open`, waits for the port, and shows the launcher in a
real window.

```bash
cd desktop
npm ci
npm start              # run from source
npm run dist           # build an installer into release/
```

Produces `DoomNite Setup 1.0.0.exe` (NSIS) and a portable zip. Installers are
published to [GitHub Releases](https://github.com/nyannonymous/DoomNite/releases/latest);
the 3.4 GB pack stays on R2.

**It needs Python 3.11+ on the machine**, and the pack fetched. Electron is the
window; the Python server is what starts the games. Bundling a frozen runtime
would remove the Python requirement at the cost of ~100 MB more.

Two environment variables override the defaults:

- `DOOMNITE_PACK` — where the pack lives, if not beside the executable
- `DOOMNITE_PYTHON` — which interpreter to use

The shell adds no launch capability of its own. `/api/launch` still takes an
integer index and resolves it server-side, so the security model is unchanged.

---

## Credits

Mods are by their respective authors. Doom and GZDoom are by id Software and
contributors. Nothing here is mine to license — check each mod's own terms
before redistributing the pack.
