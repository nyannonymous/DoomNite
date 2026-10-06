# DoomNite Pack - OPEN TASKS (checklist index, 2026-10-06)

This file is a notes-style log. The checklist below is the quick index of what is still open; details live in the sections it points to. `[!]` = needs a decision or a human check first.

- [x] Commit the working tree (already committed in the WIP snapshot; tree was clean): 13 modified + 3 untracked files (card layout, REMOVE FROM PACK, zoom); verified build, `verify.mjs` 21/21, `check-zoom` 12/12 (section 0)
- [x] Finish `ui/src/Panel.jsx`: already has Typed readout, TermRow, BootBar, DataStreams, .play-glow button; npm run build clean (nitesesh 2026-10-06; visual check is the owner's, verify.mjs needs the server running)
- [x] Fix the `make_sources.py` wart: re-running it while DOOM2.WAD is absent deletes that entry and `base_url` from `sources.json` (section 4) — verified fixed 2026-10-06 (68/68 entries kept, `base_url` intact)
- [x] Delete `mods/bdbe-3-38/` (already gone on disk, nothing references it) (191.5 MB of dead weight, nothing references it; `build.py` uses `mods/bdbe-v3-38/`) (section 4)
- [!] Launch BDBE by hand and confirm it is not plain Brutal Doom; if it is, capture `-stdout` + a logfile (section 3)
- [!] Look at the new UI: per-mod REMOVE FROM PACK sidebar, flush-left card names, ctrl+wheel zoom at 300% (sections 1, 1b, 1c are all "UNVERIFIED")
- [!] "Add a mod" flow (paste URL / upload pk3) needs scoping first, because IWAD/launcher config is hand-authored in `tools/build.py` `GAMES` (section 5)

---

# DoomNite — todo

Repo-local backlog. Hermes-wide goals live in `Z:\HERMES\.hermes\next.md`, not here.

Pack root: `Z:\github\APP · DOOMNITE-PACK` · serve on `http://127.0.0.1:8765` ·
builder `python tools/build.py` · checker `python tools/build.py --check` ·
UI build `npm run build` (in `ui/`) · UI verify `node verify.mjs "../app/assets/<bundle>.js"`

Redesign brief: `ui/BRIEF.md` (verbatim, do not lose it).

---

## ▶ §0 NEXT — commit the working tree

`main` is level with `nyannonymous/main` at `b6cd40f`, but **13 modified + 3
untracked files are uncommitted** — nothing is unpushed, it is just not saved:

    ui/src/Tile.jsx          card is now art + name only; trash icon removed
    ui/src/Panel.jsx         +  sidebar REMOVE FROM PACK (moved off the cards)
    ui/src/VariantMenu.jsx   "show install folder" -> /api/reveal
    ui/src/App.jsx           zoom readout + doomnite:zoom listener
    ui/src/styles.css        card padding, dead tag/trash CSS removed
    ui/src/api.js            fetchPackModStatus / removePackMod / revealFolder
    installer.py             pack_mod_registry / pack_mod_status / remove_pack_mod
    serve.py                 /api/packmods GET+DELETE, /api/reveal POST
    desktop/main.js          attachZoom: ctrl+wheel zoom in the desktop shell
    desktop/build/check-zoom.js  new  drives the REAL attachZoom, 12 checks
    app/assets/              new bundle index-Cqhjp1v3.js / index-DvxMVePE.css

Verified just now: `npm run build` clean, `verify.mjs` **21/21, no runtime
errors**, `preflight.js` clean, real Electron boot clean, `check-zoom` **12/12**.

The 53 self-hosted `@fontsource` files in `app/assets/` are **already
committed** and are not part of this diff. They are deliberate: this pack runs
off a local server and often has no internet, so a Google Fonts `<link>` would
silently fall back and lose the whole look.

---

## 1. Per-mod install/uninstall — BUILT, needs your eyes

Removal now lives in ONE place: the sidebar. Every card used to carry a trash
icon in its top-left corner, which put the pack's most destructive action in the
most repeated position on screen, one stray click from deleting a folder. The
sidebar already owned the on-demand UNINSTALL, so baked-in removal sits beside
it as **REMOVE FROM PACK** — and only appears when there is something exclusive
to delete, so a shared-slug game shows the explanation instead of a button that
would silently do nothing. The card keeps only the IN PACK / REMOVED label.

**How it works:** no second hand-maintained table. `installer.pack_mod_registry()`
*derives* the game -> `mods/<slug>` mapping from `pack-manifest.json`, the same
document `serve.py` already treats as source of truth. A rebuild changes the
manifest, the registry follows. Nothing goes stale.

- `GET /api/packmods` — status for all 14, polled like the existing
  `/api/install`. Returns `folders`, `exclusive`, `shared`, `installed`,
  `partial`, `size_h`.
- `DELETE /api/packmods/<name>` — deletes only the folders that game owns
  **exclusively**. A slug shared with another game is skipped and reported
  back, so uninstalling one entry can never silently break another.
- Path safety: `<slug>` only ever comes from the registry, which is built
  server-side. Never from anything a request supplied. An unknown game name
  raises `KeyError`, same as an unknown `SPECS` name.
- `serve.py` re-checks the filesystem on every `/api/entries`, so the tile
  flips to "missing" immediately after an uninstall — no rebuild needed.

**Registry measured:** 16 games in the manifest, 14 with `mods/` folders. The
2 without are exactly Adventures of Square and Requiem, which are the on-demand
`SPECS`/`DEST` pair and correctly excluded.

**Shared-slug protection, measured:**
`doommetalvol5-44100` (BD v22 + BDBE E1), and `doomhdtextures`,
`bd-black-neuralupscale`, `bdbe-v3-38`, `bd-black-editionv3-35-weaponsounds`
(both BDBE entries). So uninstalling BDBE "HontE Remastered" reclaims nothing
— everything it loads is shared with "Enhanced Episode 1".

**Deliberate limitation:** there is **no reinstall button** for baked-in mods.
The pack's copies were made at build time from the operator's source drive, not
fetched from a URL, so getting them back is `python tools/build.py`. This is
"remove from this pack", not "uninstall and reinstall later".

**UNVERIFIED — genuinely needs you:** that the sidebar button reads clearly,
that the shared-slug explanation is understandable rather than looking broken,
and that the freed-size figure makes sense.

---

## 1b. Card layout — art + name, nothing else

The bottom meta strip is gone: no IWAD/build sub-line, no HD/PINNED/MISSING tag
row. The card is artwork with the name tight underneath and no padding below
it (the old `9px 11px 11px` left an empty 11px band under every name).

Nothing was lost that isn't reachable elsewhere: build count is in the hover
title, PINNED is the pin marker, and IWAD/HD/missing are in the sidebar Details
readout. MISSING additionally got a **dashed underline on the name**, because
removing its tag left that state conveyed by opacity alone — which reads as
"disabled" rather than "files are gone" and fails in greyscale.

**UNVERIFIED — needs your eyes:** whether the flush-left name under the art
looks right, or whether you want it centred / still inset.

---

## 1c. Ctrl+wheel zoom in the desktop app — BUILT

Worked in the browser, did nothing in Electron. Cause: `Menu.setApplicationMenu(null)`
at main.js:805 removes the menu bar, and that is also where the zoom
accelerators live. Nothing in the UI was blocking it — the CRT overlays are all
`pointer-events: none` and there is no wheel handler anywhere in `ui/src`.

`attachZoom(win)` (desktop/main.js) now does it on `webContents` zoom factor, not
a CSS transform: a transform scales without re-layout, which would leave the
ember canvas and the pointer-tracked tilt maths reading stale coordinates.
Platform modifier, not literal Control, so macOS gets Cmd+wheel. 80%–300%,
~+9% per notch. Plain wheel is left alone. Ctrl/Cmd `+`/`-`/`0` also work.

The status bar shows `zoom 175%` when not at 100%, because native zoom otherwise
gives no confirmation at all.

**Two bugs the runtime check caught that reading the code did not:**

1. The export referenced `MIN_ZOOM`/`MAX_ZOOM`; the constants were named
   `ZOOM_MIN`/`ZOOM_MAX` — main.js threw on load and the app would not have
   started. `node --check` passed this happily, since it only parses.
2. `Math.pow(1.2, level)` is *not* a percentage — Chromium's factor is
   `1.2^level`, so my "max 300%" clamp was silently 144%. The checker printed
   `PASS clamps at max (300%) [144%]` and passed, because it compared levels
   against level bounds while labelling them as percentages. Bounds are now
   declared as percentages and converted once via `log(pct)/log(1.2)`, and the
   check reads `webContents.zoomFactor` so the label and the number cannot
   disagree again.

Also caught: `STEP=0.1` was only +2% per notch — technically working,
practically indistinguishable from no zoom, which is how the missing feature
went unnoticed. Now `STEP=0.5` (~+9%).

**desktop/build/check-zoom.js** (new, 12 checks, all passing) boots a real
`BrowserWindow`, requires the real `attachZoom`, and fires the exact
`before-input-event` payload the handler branches on. It deliberately does NOT
re-implement the handler — a copy would only prove the copy works.
`main.js` grew a `ZOOM_CHECK_MODE` guard so it can be imported without booting
the app.

**UNVERIFIED:** real trackpad and real mouse-wheel events (the check synthesises
`before-input-event` rather than injecting trusted OS input), and whether
zooming to 300% is actually usable on your screen.

---

## 2. UI redesign — MOSTLY DONE

Brief in `ui/BRIEF.md`: retro-futuristic UAC terminal, Tailwind + Framer Motion
+ Lucide, hero background of the selected game, terminal details pane with
typing effect, jagged/glitch hover, industrial play button, CRT overlay,
custom crosshair cursor.

**Done:** deps (tailwind 3.4, framer-motion, lucide-react, @fontsource
black-ops-one/oswald/jetbrains-mono), `tailwind.config.js`,
`postcss.config.js`, font imports in `main.jsx`, the `styles.css` layer,
`Tile.jsx`, `App.jsx`, `VariantMenu.jsx`, CRT overlay, hero art.

**Still not done:** `Panel.jsx` — UAC terminal readout, typing effect,
industrial play button.

**UNVERIFIED — I have never seen a rendered pixel of this UI.** Whether the
tilt/jolt feel is right, whether the ember field is too busy behind the art,
whether the CRT overlay is too strong.

---

## 3. Launch BDBE — the one real verification left on the pack

Fixed but never launched by a human. `BDBE_v3.38.pk3` (199 MB) was never copied
into the pack; Black Edition is a game-support pk3 with **zero map lumps**
(12,525 entries, one `MAPINFO` with `AddDefaultMap`, no `MAPxx`), so it
inherits maps from the Brutal Doom base. Both entries were also pinned to the
wrong IWAD — Enhanced E1 → DOOM, HontE → DOOM 2. Load order is now
1. `brutal22test6.pk3` 2. `BDBE_v3.38.pk3` 3. episode wad via `-file`.

If it still looks like plain Brutal Doom, the next step is `-stdout` +
logfile capture so the engine tells us instead of me inferring.

Deliberately not loaded: HD textures (359 MB), neural upscale, music, visor,
terrain splashes. All present in RaZZoR's `addons/` if you want them as extra
config variants.

---

## 4. Loose ends

- **`mods/bdbe-3-38/` — 191.5 MB of dead weight, safe to delete by hand.**
  Hand-copied while diagnosing; `build.py` slugifies into `mods/bdbe-v3-38/`
  instead, and nothing references the old folder. `MoveFileEx` reboot-delete
  returned false because of a stale Hermes kernel handle, not the game.
- **`make_sources.py` wart — FIXED (2026-10-06, nitesesh).** It builds the manifest from local files, so
  re-running it while DOOM2.WAD is absent DELETES that entry and `base_url`
  from `sources.json`. Recover with `git checkout -- sources.json` and hand-edit
  `no_host`. Now carries forward `iwads/*` entries and `no_host` flags, and
  re-emits `base_url` from the old document; verified live: DOOM2.WAD absent
  from disk, one regen run, 68/68 entries kept, `base_url` intact, 0 no_host lost.
- Earlier mod fixes, all verified: Shadow Warrior's asset pack was sitting
  unused in `Z:\GAMES`; Aliens TC needed pk3-before-mapset order or it booted
  the IWAD's own maps wearing Aliens enemies; Hexen Remade needed the Hexen
  IWAD; audio shipped `soft_oal.dll` + `uzdoom.sf2` with RaZZoR's inherited
  `snd_aldevice` (a Philips TV on an NVIDIA GPU) and `snd_samplerate=8000`
  both fixed, and `--check` now fails rather than shipping a broken pack.
- `git add -A` includes the built UI, deliberately — the pack should be usable
  without npm.

---

## 5. Considered, not built

- **"Add a mod" flow** (paste a URL / upload a local pk3). Blocked on a real
  design question, not effort: IWAD and launcher config for a freshly added mod
  is currently hand-authored in `tools/build.py`'s `GAMES` table, not derived
  from any file metadata. Needs scoping first.
- **Reinstall for baked-in mods** — see §1. Needs the build-time sources to
  become re-fetchable first.
- **Right-click "show install folder"** — SHIPPED as the `/api/reveal` button in
  `VariantMenu.jsx`, listed only so it isn't mistaken for missing.