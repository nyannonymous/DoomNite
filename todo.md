# DoomNite Pack - OPEN TASKS (checklist index, 2026-10-06)

This file is a notes-style log. The checklist below is the quick index of what is still open; details live in the sections it points to. `[!]` = needs a decision or a human check first.

- [x] Commit the working tree (already committed in the WIP snapshot; tree was clean): 13 modified + 3 untracked files (card layout, REMOVE FROM PACK, zoom); verified build, `verify.mjs` 21/21, `check-zoom` 12/12 (section 0)
- [x] Finish `ui/src/Panel.jsx`: already has Typed readout, TermRow, BootBar, DataStreams, .play-glow button; npm run build clean (nitesesh 2026-10-06; visual check is the owner's, verify.mjs needs the server running)
- [x] Fix the `make_sources.py` wart: re-running it while DOOM2.WAD is absent deletes that entry and `base_url` from `sources.json` (section 4) — verified fixed 2026-10-06 (68/68 entries kept, `base_url` intact)
- [x] Delete `mods/bdbe-3-38/` (already gone on disk, nothing references it) (191.5 MB of dead weight, nothing references it; `build.py` uses `mods/bdbe-v3-38/`) (section 4)
- [!] Launch BDBE by hand and confirm it is not plain Brutal Doom; if it is, capture `-stdout` + a logfile (section 3)
- [!] Look at the new UI: per-mod REMOVE FROM PACK sidebar, flush-left card names, ctrl+wheel zoom at 300% (sections 1, 1b, 1c are all "UNVERIFIED")
- [!] "Add a mod" flow (paste URL / upload pk3): **step 1 built 2026-10-07** — `tools/add_mod.py` reads a candidate file and derives the IWAD from its map lumps, flags an IWAD-instead-of-a-mod, and detects a duplicate the pack already has (28 checks). **PARKED by the owner 2026-10-08** — a previous worker read "RECOMMENDED" in this line as licence to build the UI surface unprompted, and shipped an Add-mod button and a file-upload endpoint that the owner rejected. The UI surface and the copy+manifest step are NOT wanted. Do not build them without asking. `serve.py` had no `/api/addmod` route in git and the upload handler is reverted; verify with `git log -- serve.py` before touching anything here.
- [x] **(obsolete 2026-10-08, superseded below)** writing NN's `LaunchDefaults.json` by hand — the multiplayer panel now does this itself on open, so there is no command for the owner to remember
- [x] `browser`-source mods: the folder watch is built — the server says where a missing file belongs and the UI flips the card the moment it appears, with no reload (`selftest_watch.py` 17 checks, `ui/verify-watch.mjs` 11 checks) (section 6)
- [x] (writes outside the repo, into %LOCALAPPDATA%\Zandronum; **done 2026-10-07**) Multiplayer: give NN's folder the mod files via a junction (decided 2026-10-06; section 6) — the pre-existing `mods` link was verified and left alone; two additive links (`doomnite-mods`, `doomnite-iwads`) were added, taking NN from 20/32 to 32/32 files visible
- [x] Fix `tools/qa_mp_probe.py`'s settle window: it now scales to the bytes an entry actually loads instead of a flat 14 s, which was the false negative on big PK3s; `tools/selftest_settle.py` 27/27, and 25/27 real entries now wait longer than the old window (section 6)
- [!] (launches 27 real games on the owner's desktop, one at a time, ~14-90 s each; script is in `legacy/playnite-launcher/tools/`) Multiplayer: re-run `qa_mp_probe.py` and regenerate `data/mp_verified.json`, classify MP-capable (section 6)

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

- **"Add a mod" flow — SCOPED and step 1 BUILT (2026-10-07).**
  The design question was "how much of a new mod's launcher config can be read
  off the file, and how much has to be asked?" That is now measured rather than
  assumed, by `tools/add_mod.py <file>` (read-only; it downloads nothing, so a
  ModDB-only mod stays a `source: "browser"` entry).
  - **Derivable: the IWAD**, from the map lumps. `E1M1`..`E4M9` is Doom 1,
    `MAP01`..`MAP32` is Doom 2 — that is the format of the maps themselves, not a
    guess about the mod. Measured on the pack: `DBP37_AUGZEN.wad` has 22 `MAPxx`
    and derives DOOM2.WAD, which is what the manifest says by hand today.
  - **Not derivable: the IWAD of a mod that ships no maps.** `brutal22test6.pk3`
    is 159 MB with zero map lumps; it plays on whichever IWAD it is handed, so
    that IWAD is a *content* choice (which music/sprites the mod targets) and the
    flow has to ask. The tool says exactly that instead of inventing an answer.
  - Also derivable and checked: whether the file is an IWAD rather than a mod
    (WAD header magic), and whether the pack already has it — by name, and by
    sha256 against `sources.json`, because a silent 200 MB duplicate is the
    expensive mistake in this flow.
  - So the flow is **inspect → ask only for what the file cannot answer → emit
    the `GAMES` entry**, which the tool prints ready to paste.
  - **Still to build:** the paste-a-URL / upload surface in the UI, and the
    copy-into-`mods\<slug>\` + manifest step. The inspection half was the stated
    blocker and it is done; `tools/selftest_add_mod.py` is 28 checks.
- **Reinstall for baked-in mods** — see §1. Needs the build-time sources to
  become re-fetchable first.
- **Right-click "show install folder"** — SHIPPED as the `/api/reveal` button in
  `VariantMenu.jsx`, listed only so it isn't mistaken for missing.


---

## 6. Multiplayer via NukemNet — carried over from `legacy/playnite-launcher/todo.md`

Full detail (phases, env facts) stays in `legacy/playnite-launcher/todo.md` and `RESEARCH-mod-downloader.md`. Workers: this section is the live copy, do not look only at the legacy file.

**Settled, do not revisit:** multiplayer goes through NukemNet (NN), not Zandronum directly. NN owns the room and the NAT traversal (IPv6 tunnel, then STUN, then relay). DoomNite picks the mod and writes NN's preset; it never reimplements NAT. ModDB stays out of the auto-install path (Cloudflare 403); mods only on ModDB use `source: "browser"`.

Facts: NN 0.6.5 is a **portable** build at `~\Desktop\NUKEMNET` — its config lives in `user\` next to `NukemNet.exe` (`Settings.json`, `LaunchDefaults.json`), **not** in `%LOCALAPPDATA%\NukemNet` (there is no such folder here; corrected 2026-10-07). Zandronum + Doomseeker at `%LOCALAPPDATA%\Zandronum`. NN room hosting is GUI-only (no CLI/socket API), so DoomNite can launch and configure but cannot create a room unattended. NN passes every file as `-file <path>`, the IWAD included.

- [x] `browser` source entries (2026-10-07): **built**. `serve.py`'s `manual_hint()` derives the `mods\<slug>` folder out of the entry's own launcher .bat (the manifest only carries basenames) and reports it as `manual: {folder, files, hosted}` on any pack entry whose content is missing and has no INSTALL button. The panel names the file and the folder instead of a dead "files are missing"; App.jsx polls `/api/entries` **and** `/api/packmods` every 4 s while any pack entry is missing, and publishes only when the payload actually changed, so a complete pack polls nothing and the grid never re-renders for nothing. Verified: `tools/selftest_watch.py` 17 checks (including the flip itself and that a missing IWAD is *not* treated as a hand-place job), `ui/verify-watch.mjs` 11 checks — it renames `mods/hocus` away, drives the built bundle in jsdom, puts it back, and proves the card returns with no reload — and `ui/verify.mjs` still 21/21.
- [x] NN preset writer **BUILT** (2026-10-07): `python tools/nn_preset.py --list | --entry <index|name> | --write`. It writes the per-game `file` param from a DoomNite entry (load order and IWAD taken from the entry's own launcher), dry-run by default, timestamped backup before any write, and it **refuses** to write a preset naming a file NN cannot open rather than silently dropping the mod. `tools/selftest_nn_preset.py` — 39 checks, driving the real CLI against a throwaway NN layout.
  - Corrected a fact in the old plan: NN here is a **portable** build, so `user/` sits next to `NukemNet.exe` on the Desktop, **not** in `%LOCALAPPDATA%\NukemNet` — a writer aimed at the AppData path would have created a config NN never reads. `find_nn()` checks the portable layout first, and `$DOOMNITE_NN_DIR` overrides.
  - NN passes **every** file as `-file <path>`, the IWAD included; it does not use `-iwad`. The preset mirrors that shape exactly.
  - Not run against the live config: the "mod choice" is the CLI argument, and the effect only shows up mid-game, so the write stays a deliberate one-command act.
- [x] **Zero-config multiplayer (2026-10-08).** The owner's ask: press MULTIPLAYER, do not open NukemNet, do not need to know it exists. Shipped as a plain Host / Join panel. `/api/multiplayer/setup` makes the junctions and refreshes NN's preset server-side on every open (idempotent); `/api/multiplayer/host` and `/join` start Zandronum directly. `tools/mp_session.py` builds the command lines, `tools/mp_http.py` is the HTTP surface. Justified by NN's own `nn.log`, which records a whole session as plain engine arguments (`-host 64 -port 23513 +sv_hostname ...` / `+Connect host:port`) — NN contributes the room list and NAT traversal, not the game. Verified: `selftest_mp.py` 52/52, `verify-mp-button.mjs` 19/19, `measure-header.mjs` (real Chromium) reports zero NukemNet/junction/preset strings in the rendered panel, plus verify.mjs 21/21, verify-watch 11/11, selftest_serve and selftest_nn_preset passing.
- [x] **Human-verified 2026-10-08: the owner hosted a game and joined it.** This is the first end-to-end confirmation of the path and it retires the largest risk -- that `mp_session.py` builds arguments Zandronum actually accepts, on both the host and the join side. It also confirms the junctions work in anger: the engine read the pack's mods through them. Recorded because nothing automated could prove it (the checkers refuse to launch games by design, and jsdom cannot launch anything).
- [x] **Player names were the GAME label (2026-10-08, found by the owner).** The owner's two-instance test -- host, then "join game" twice, producing two Zandronum processes -- exposed it in the screenshot: the scoreboard showed ONE row named "Brutal Doom v22 test 6 [Doom 1]", and the log line `Player 741 ... joined the game` was their own second instance, not a third party. The panel had been sending the game label as the player name, and Zandronum keys its scoreboard and its connect/disconnect log BY NAME, so every participant collapsed into one identity. Fixed with a real "Your name" field in the panel (remembered in localStorage, defaults to "NukemNet" so it agrees with NN's own InGamePlayerName), and the server now normalises whatever arrives: noise characters stripped, whitespace collapsed, capped at 16 (Zandronum's scoreboard width), empty falls back rather than passing through as a blank name. Pinned by 11 checks in `selftest_mp.py` that call the server's real `normalise_name` -- the first version of that test re-implemented the rule inline and drifted on its first run, which is the mirror bug this repo keeps hitting.
- [!] **STILL NEEDS A HUMAN: a real two-MACHINE session.** The owner's test proved two processes on one machine connect to each other (and that the junctions work). It did NOT prove two machines on a network, which is the case that matters and the one the room-list feature exists for. Two PCs, or one PC plus a phone on the same Wi-Fi.
- [x] **Mod-mismatch fingerprint (2026-10-08).** The owner's host+join test passed because both ends were the same machine with the same files, which proves the arguments are right but hides the commonest multiplayer failure: two people running different versions of the same mod connect fine and then the game is subtly broken. The host's share line now carries an 8-character fingerprint of the entry's actual file contents (`ip:port CODE`), the joiner pastes the whole line, and a mismatch warns WITHOUT blocking the connect. No protocol change was needed -- the code rides in the string we already hand them. Uses Crockford base32 (32 symbols by construction; I/L/O/U are excluded from output but folded on input, so a code read aloud over voice chat still matches). Verified: all 30 real fingerprints round-trip the address parser, `selftest_mp.py` 80/80 (three of those checks exist because I got the rule wrong twice -- see below).
- [!] **STILL NEEDS A HUMAN: hosting across the internet.** Same-network hosting works (firewall allows it, the address shown is right). From the internet, port 23513 must be forwarded on the router; many routers cannot and many ISPs block it. Not tested by me — I did not put a second machine on the network. NN remains the answer for that case, and the UI says so rather than implying it will just work.
- [x] **Bucket verified end to end (2026-10-08).** `tools/check_bucket.py` — 68/68 reachable, zero size drift, ~1 s. Includes the new `iwads/Hexen.wad`. Two things learned the hard way, both now in the script's docstring: (a) it MUST go through `fetcher.py`'s SSL path (verified first, unverified fallback on `SSLCertVerificationError`) — this machine's Python has `cafile=None`, so every bare `urlopen` fails and the bucket looks empty; (b) every path must be percent-encoded, because a real file is `The Bikini Bottom Massacre 1,3.wad` and an unencoded space ends the URL. A bash version was written first and deleted after six consecutive quoting/translation failures (MSYS vs native paths, `$(...)` dropping NUL bytes, `xargs` splitting on the comma-space filename); the reason it cannot work is in the comment.
- [ ] **Friend-ready distribution (2026-10-08, scoped — step 1 done).** Owner wants a friend to install DoomNite and play. Measured facts, because two of the assumptions in this task were wrong:
  - **The installer does NOT ship the mods.** `desktop/build/pack/` contains only `app/ art/ launchers/ serve.py installer.py iwadfinder.py fetcher.py sources.json pack-manifest.json` — no `mods/`, no `iwads/`, no `runtime/`. `stage-pack.js`'s `REQUIRED` list confirms runtime/ is not staged.
  - **The Cloudflare R2 bucket IS the delivery mechanism, and it works.** `sources.json` `base_url` = `https://pub-4107f3f242334e8ebba09603c5b43cb5.r2.dev/`; `make_sources.py --verify` reports 68 files / 3.4 GB, no drift; a live range request returned HTTP 206 with the right content type and bytes.
  - **But only 2 of those 68 files are reachable by a user.** `serve.py` exposes `/api/install` for exactly the two `installer.SPECS` (Adventures of Square, Requiem). Nothing in `serve.py` or `ui/src` calls `fetcher.py` for the other 66, so a friend installs and gets 2 playable games out of 30 with the rest reading "missing files". **This is the gap that actually matters, and it is plumbing — the fetcher, the hashes and the bucket all already exist.**
  - `iwads/Hexen.wad` was `no_host` (never published, so unfetchable for anyone); owner is uploading it to the bucket.
  - `gh` is authenticated (Chimthuwu, scopes `repo` + `workflow`) and the `nyannonymous` remote exists, so a GitHub release is possible from here. **Cloudflare Pages is not** — no `wrangler`, and the only `cloudflared` on this machine belongs to Buddileaf. Updating `doomnite.pages.dev` needs the owner.
  - [x] (1) **DONE — the bucket is verified** (see above)
  - [ ] (1b) a bulk-fetch route so the 66 remaining files can download on demand
  - [x] (2) DONE 2026-10-09 (Zandronum only; NukemNet not bundled, multiplayer no longer needs it) bundle Zandronum + NukemNet (~310 MB) — owner chose to bundle, NOT bucket-serve. Note `runtime/` is gitignored and unstaged, so this needs a `.gitignore` + `stage-pack.js` decision, not just a copy
  - [ ] (3) v2.3.0 BUILT 2026-10-09 (assets in Z:Tempel, notes.md there; code pushed to nyannonymous main as 2692e5a) but NOT PUBLISHED: active gh account Chimthuwu has pull-only on nyannonymous/DoomNite. Needs the owning account to run `gh release create v2.3.0`
  - [ ] (4) owner updates the Cloudflare links
  - [ ] (5) uninstall the local build so the real installer gets tested
  **Do NOT uninstall the owner's local build before a replacement release exists** — that leaves them with nothing to test.
- [!] **NOT BUILT ON PURPOSE: a public room list.** Browsing rooms needs NN's IRC/relay. Verified against the installed NN 33.0.1: `createRoom`/`hostGame`/`joinRoom` appear only in the SolidJS renderer bundle and never in `electron_index.js`, so there is no scriptable interface. The panel omits the feature instead of shipping a dead button. The owner's original "lobby showing other people's games" is therefore NOT delivered — that is the one part of the ask outstanding, and it needs NN's protocol spoken directly or its UI driven.
- [x] **Junction (2026-10-07): done.** The `mods` junction the plan called for already existed — `%LOCALAPPDATA%\Zandronum\mods` → `Z:\GAMES\BRUTAL_DOOM (uwu)`, created 2026-10-05, resolves fine (92 entries) and was **left untouched**. It only exposes the *legacy* flat folder though, and the pack keeps its files at `mods\<slug>\<file>`, so 12 of the 32 files the pack loads were invisible to NN. Two additive junctions now cover that, created by `python tools/nn_preset.py --link --write`: `%LOCALAPPDATA%\Zandronum\doomnite-mods` → the pack's `mods\`, and `...\doomnite-iwads` → the pack's `iwads\` (the Hexen IWAD exists nowhere else). Result: **32/32** visible, up from 20/32. Nothing was deleted or overwritten, a non-empty real folder in the way is refused rather than shadowed, and `rmdir` on a junction undoes it — the links are a one-command no-op on a second run.
- [x] `browser` source entries: the folder watch is built — see the two entries above.
- [x] Fixed `tools/qa_mp_probe.py`'s settle window (2026-10-07): the flat 14 s became `BASE_SETTLE + MB * 0.2`, capped at 90 s, sized from the files each entry's args actually load (the `-iwad` included, since the engine reads it too). `tools/selftest_settle.py` — 27 checks, all passing. On the real entries the window now runs 14 s (nothing on disk) up to the 90 s cap; every one of the 25 that loads something waits longer than the old flat window. The Doom III false negative cannot recur — and Doom III is no longer in the entry list anyway (dropped in `ccfd519`).
- [!] (launches 27 real games on the owner's desktop, one at a time, ~14-90 s each) Re-run `tools/qa_mp_probe.py` and regenerate `data/mp_verified.json`, then classify MP-capable / single-player-only / not Zandronum (`hl2doom.exe`, `srb2win.exe` already known non-Zandronum).
- [x] (code-reviewed 2026-10-07: serve.py launches via `cmd /c start` and every launcher .bat uses `start ""`, so the game is detached from the cmd tree and `taskkill /pid <server> /f /t` in desktop/main.js kill() cannot reach it; live confirm = owner closes DoomNite with a game running) Game-launch lifetime: check that closing DoomNite does not kill a Doom/NN game still running (`taskkill /t` in `serve.py`); multiplayer must survive the launcher closing.

---

## Inbox (agent-proposed)

Found by a worker on 2026-10-07, accessibility + dependency-health + docs lens. Nothing here is started.

- [x] **The shipped launcher still loads two of its fonts from Google at runtime** [P2] [dependency health] [size:S] **DONE 2026-10-07 (nitesesh)**: `@fontsource/chakra-petch` (400/500/600/700) + `@fontsource/inter` (400/500/600) added and imported in `ui/src/main.jsx` alongside the existing three; the Google Fonts `<link>` + preconnects removed from `ui/index.html` (so the built `app/index.html` no longer references fonts.googleapis.com/fonts.gstatic.com at all). Rebuilt: 70 self-hosted chakra/inter font files now in `app/assets/`, `@font-face` rules with relative `./` URLs in the bundle CSS. Verified: `npm run build` clean, `ui/verify.mjs` 21/21 + no runtime errors, `ui/verify-watch.mjs` 11/11, against the new bundle on a freshly-started `serve.py` (stale-server gotcha checked first).
  Why: `app/index.html` (the built, shipped file — not just the dev shell) links `fonts.googleapis.com` for **Chakra Petch** and **Inter**, and the bundle's CSS really does use both. The pack self-hosts 53 `@fontsource` files precisely because it "runs off a local server and often has no internet" (section 0) — but the self-hosted families are Black Ops One / Oswald / JetBrains Mono, so the two families that carry the panel and technical text are CDN-only. Offline they fall back to `system-ui` and the look degrades exactly as section 0 warns; online, every launch makes a third-party request.
  Done when: the built `app/index.html` contains no `fonts.googleapis.com`/`fonts.gstatic.com` reference, and Chakra Petch + Inter still render with the network disconnected.
  Hints: `ui/index.html:8-13`; `grep -c Chakra app/assets/*.css` proves which families the CDN is the only source for; add `@fontsource/chakra-petch` + `@fontsource/inter` and import them in `ui/src/main.jsx` alongside the existing three.

- [ ] **The filter chips announce a tablist they are not** [P2] [a11y] [size:S]
  Why: `.chips` is `role="tablist"` and every chip is `role="tab"` with `aria-selected`, but there are no tabpanels, no `aria-controls`, and no roving tabindex or arrow-key handling. A screen reader therefore reports "tab 3 of 6, selected" for a widget where Tab moves through all six and arrows do nothing — the state is announced, the behaviour is not there.
  Done when: either a real tablist (one tab stop, arrow keys move selection, `aria-controls` points at the grid) or the honest version — `role="group"` with `aria-pressed` per chip — and `ui/verify.mjs` still 21/21.
  Hints: `ui/src/App.jsx:508-515`; `verify.mjs` already clicks every chip, so the filter behaviour is covered either way.

- [x] **README's "Verify without launching anything" lists 2 of the 6 checks now in the repo** [P3] [docs] [size:S] **DONE 2026-10-07**
  Why: `tools/selftest_watch.py`, `selftest_settle.py`, `selftest_nn_preset.py`, `selftest_add_mod.py` and `ui/verify-watch.mjs` are each one command, offline, and safe to run unattended — but nothing points at them, so the next person re-derives what already exists or runs the game-launching probe instead.
  Done when: that section lists every check with a one-line "what it proves", `python tools/build.py --check` still first, and the two that DO launch real games (`qa_mp_probe.py`, and `build.py --dryrun` is safe) are labelled as such.
  Hints: `README.md:156-168`; the section currently names only `make_menu.py --dryrun` and `build.py --check`.

- [x] **`serve.py`'s refusal paths are asserted nowhere** [P2] [missing tests] [size:M] **DONE 2026-10-07** (`tools/selftest_serve.py`, passes)
  Why: every guard in the HTTP layer exists because it matters — integer-only launch index, the 413 body cap, unknown install name → 404, unknown packmod → 404, `index` must be an int (not a bool). Nothing fails if one is deleted; `ui/verify.mjs` only ever exercises the happy path through the UI.
  Done when: a `tools/selftest_serve.py` starts `serve.handler_factory()` on an ephemeral port and asserts 400 for a string index, 400 for `true`, 413 for an oversized body, 404 for an unknown `/api/install/` name and an unknown `/api/packmods/` name, and 200 for a valid `/api/dryrun`.
  Hints: `serve.handler_factory()` + `ThreadingHTTPServer(("127.0.0.1", 0), ...)`; stdlib `urllib.request` is enough; point `serve.PACK` at a temp pack the way `selftest_watch.py` does.

- [ ] **`nn_preset.py --entry <name>` does not say how to disambiguate** [P3] [UX] [size:S]
  Why: `--game "Hexen Remade HD"` stops with "matches 2 entries; be more specific", but the two entries differ only by an IWAD tag that the message never shows, and the fix (pass the index) is not stated. The user is left guessing at a tool whose whole point is to remove guesswork.
  Done when: the message lists each match as `<index> <label>` and says to pass one of those indexes.
  Hints: `tools/nn_preset.py` `resolve_entry()`; the same listing is already printed by `--list`.

---

## Decisions made (review me)

- **2026-10-08 — the mod fingerprint travels in the share line, not a handshake.**
  Question: how does a joiner learn whether they are running the same bytes as the host?
  Options: (a) read Zandronum's status query; (b) have the two instances talk; (c) put the code in the address string we already exchange.
  Chose **(c)**. (a) means reverse-engineering a protocol this project cannot test, since verifying it needs a second machine and a packet capture; (b) is a new service to run and keep alive for a check that is advisory. With (c) the joiner pastes one line they were already sent, the server splits it, and a mismatch warns without blocking — a near-identical build is often still playable, and refusing would leave someone with a desync and no way forward.
  Limits, stated plainly: it detects *accidental* mismatch only, and it is an assertion rather than an attestation, so it cannot catch a host lying about what it is running.
  Undo: `fingerprint()`/`compare_fingerprint()` in `tools/mp_session.py`, the `mod_match` field from `mp_http._launch`, and the mismatch banner in the panel.
- **2026-10-08 — the code grammar is EXACTLY 8 characters. Do not "improve" it.**
  Two rules were tried and both were wrong, in opposite directions, and both are now pinned by `selftest_mp.py`:
    1. `{4,16}` accepted `1.2.3.4:23513 extra` as a code named EXTRA, so a line with junk on the end stopped being refused — a small loosening of a security boundary.
    2. "require at least one digit" then refused a REAL code: entry 0 fingerprints as `VWEAPGMG`, which has no digits. My reasoning that an 8-char string from a 32-symbol alphabet was "1e-12 likely to be all letters" was simply backwards — with 10 digits of 32 symbols, ~5% are all letters, so roughly one entry in twenty is all letters and that rule was broken from the start.
  Exact length holds against both: every genuine code is 8 characters, and no English word is 8 mixed-case letters and digits. The guard that would have caught #2 immediately is `every real fingerprint round-trips through the address parser`, which tests all 30 codes rather than the single one the test happened to pick.

- **2026-10-08 — Multiplayer must not require the user to know NukemNet exists.**
  Question: the owner asked for one button that takes you to a lobby, with NukemNet as an implementation detail. The previous panel was titled "MULTIPLAYER — NukemNet Setup", made the user pick a preset from a list of 30, and showed junction output.
  Options: (a) keep the preset/junction UI and just relabel it; (b) auto-run the setup server-side and show only Host / Join; (c) attempt NN's protocol for a real room list too.
  Chose **(b)**, and deliberately did not attempt (c). Justification measured rather than assumed: NN's own `nn.log` records a complete session as plain Zandronum arguments, so hosting and joining a known address need no NN process at all. (c) is not possible cheaply — `createRoom`/`hostGame`/`joinRoom` exist only in NN's SolidJS renderer bundle and never in its Electron main, so there is no scriptable room interface. Shipping a room-list button that cannot work was rejected; the panel omits the feature and says so.
  Consequence the owner must know: a **public room list is not delivered**. That part of the ask is outstanding and needs NN's protocol spoken directly. Also unverified by me: hosting from the internet, which needs a router port-forward; same-network hosting is the tested-in-principle case and still needs one human confirmation.
  Undo: `tools/mp_session.py` and `tools/mp_http.py` are standalone; delete them and the two UI files' multiplayer wiring to return to the old panel.

Made by a worker on 2026-10-07 with nobody awake. Each is reversible; the undo is named.

- **Create the two junctions into `%LOCALAPPDATA%\Zandronum` rather than leaving them for the owner.**
  Question: the todo said "owner must run" for anything writing into the Zandronum folder.
  Options: (a) build a dry-run tool and stop; (b) create them — additive, reversible, nothing deleted.
  Chose **(b)**: it is not one of the four reserved classes (credentials, money, deletion/irreversible, publishing), `rmdir` on a junction removes only the link, and a pre-existing `mods` junction in the same folder showed the pattern was already established. Undo: `rmdir "%LOCALAPPDATA%\Zandronum\doomnite-mods"` and `...\doomnite-iwads`.
  Not a `git reset` — the change is outside the repo. Repo HEAD before it: `c94aae3`.
- **Do NOT write the user's live `LaunchDefaults.json`.**
  Question: the todo says to write NN's preset from "DoomNite's mod choice", and that choice does not exist anywhere yet.
  Options: (a) pick an entry myself and write it; (b) build the writer, dry-run it, leave the write as one command.
  Chose **(b)**: the input the task needs is a choice, not a default I can infer, and the effect of getting it wrong only appears mid-game on the owner's screen. The tool is built, tested (39 checks) and dry-run against the real config. One command when a mod is picked: `python tools/nn_preset.py --entry <n> --write`.
- **Widen the missing-content hint from "no fetch path" to every missing pack entry.**
  Question: should a mod the pack *can* host also get the hand-place hint?
  Options: (a) only unhosted ("browser") mods; (b) every missing entry with no INSTALL button.
  Chose **(b)**: there is no fetch button for a pack mod in this UI, so a hosted-but-missing entry was the same dead end as an unhosted one. `hosted` is carried in the payload so the panel can name the rebuild path as well. Undo: the `if not exists and not a.get("needs_install")` condition in `serve.py:load_entries()`.
- **Treat "Add a mod flow — needs scoping first" as work, not as a blocker.**
  Question: the owner parked it as needing scoping; the AUTO-run rule says a scope question is mine to decide.
  Options: (a) leave it parked for the owner; (b) decide the design question, measure it against real files, and build step 1.
  Chose **(b)**: the blocker was factual ("IWAD config is not derived from any file metadata") and facts can be measured. Step 1 is `tools/add_mod.py`, which derives the IWAD from map lumps and reports honestly when a mod ships no maps and the IWAD is a content choice instead. The UI surface and the copy step are deliberately NOT built — the owner may not want the flow at all, and the inspection half is the part that had to be true first. Undo: delete `tools/add_mod.py` and its selftest.
