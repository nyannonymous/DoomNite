# DoomNite — where things stand

**GATEWAY RESET PENDING.** Last action was a STOP from the user mid-redesign, so
this file was updated by hand rather than by the normal flow. The UI redesign is
**half done** — see §0, which is where you resume.

Pack root: `Z:\DOOM_PACK` · serve on `http://127.0.0.1:8765` ·
builder `python tools/build.py` · checker `python tools/build.py --check`

HEAD: `68b9a56` (pushed). Working tree has **uncommitted UI work** — §0.

---

## ▶ §0 RESUME HERE — UI redesign is HALF DONE

The user sent a full redesign brief, now saved verbatim as **`ui/BRIEF.md`**:
retro-futuristic UAC terminal (1993 Doom UI + Doom Eternal), Tailwind +
Framer Motion + Lucide, hero background of the selected game, terminal details
pane with typing effect, jagged/glitch hover on cards, industrial play button,
CRT overlay, custom crosshair cursor.

I installed the deps and wrote the config, then was interrupted.
**Nothing is broken: the app still builds and runs exactly as before.**

**Done, uncommitted:**
- `npm i` tailwindcss@3.4 postcss autoprefixer **framer-motion@13** **lucide-react@1**
- `npm i` **@fontsource/{black-ops-one,oswald,jetbrains-mono}** — self-hosted on
  purpose: this runs off a local server and often has no internet, so a Google
  Fonts `<link>` would silently fall back and lose the whole look
- `tailwind.config.js` — full Doom palette, fonts, bevel/glow shadows
- `postcss.config.js`, and the six @fontsource imports in `src/main.jsx`

**NOT done — all still the old pre-redesign files:**
- `src/styles.css` — needs `@tailwind base/components/utilities` plus what
  Tailwind can't express: noise, CRT scanlines, vignette, jagged `clip-path`,
  chromatic aberration
- `src/Tile.jsx` — `motion.div`, jagged hover border, glitch title, spring jolt
- `src/Panel.jsx` — UAC terminal readout, typing effect, industrial play button
- `src/App.jsx` — staggered entrance, hero art of selected game, CRT overlay,
  custom crosshair cursor
- **No CRT overlay component exists yet. No hero-art layer exists yet.**

**Why nothing regressed:** the app still doesn't import the new config, and
`styles.css` is untouched, so `npm run build` and `verify.mjs` (22/22) still pass.
Config alone can't break anything. Work in this order — CSS layer, verify, then
one component at a time — which is exactly what I was doing.

---

## 1. BDBE "just launching regular BD" — FIXED, needs your eyes

**Root cause:** `BDBE_v3.38.pk3` (199 MB, `addons/` in RaZZoR's folder) was
**never copied into the pack.** Both BDBE entries loaded only the episode wad.
Black Edition is not a standalone wad — I unzipped it to check: 12,525 entries,
**zero map lumps** (no ExMy, no MAPxx), one `MAPINFO` with `AddDefaultMap` and
its own actor classes (`BEDoomer`, `EvilMarine`). It is a game-support pk3 that
upgrades a Brutal Doom base and inherits the base's maps. So the old launcher
booted vanilla BD wearing nothing. That was the bug, not a config quirk.

**Also wrong:** both entries pinned `-iwad DOOM.WAD`. RaZZoR's `! READ !.txt`
says Enhanced E1 → DOOM, **HontE → DOOM 2**. HontE on Doom 1 quietly fell back
to base content, compounding the same symptom.

**Fix** (`tools/build.py`, GAMES): load order is now
1. `brutal22test6.pk3` — the BD base that owns the maps
2. `BDBE_v3.38.pk3` — BE, last so it wins conflicts
3. episode wad via `-file` — adds maps on top

Plus `BD_Black_Editionv3.35_WeaponSounds.pk3` (adds sounds only, safe after v3.38).
Both entries now have 2 variants (DOOM + DOOM2), so you can test either.

**Deliberately NOT loaded:** HD textures (359 MB), neural upscale, music, visor,
terrain splashes. That's the optional addon layer and belongs behind its own
configs, not forced on every launch. Say the word if you want them as extra
config variants — they're all present in RaZZoR's `addons/`.

**State:** build clean, `--check` OK, 25 launchers, no missing files, all
generated lines inspected and correct. **UNVERIFIED: nobody has actually
launched it yet — that's the one thing I can't confirm without you.**
If it still looks like plain BD, the next step is `-stdout` + logfile capture so
the engine tells us instead of me inferring.

---

## 2. UI — React/Vite rebuild, done, needs your eyes on feel

Was one 26 KB hand-written `index.html`; now a Vite/React app in `ui/`, built
to `dist/`, served from there. Old file kept as `index.html.vanilla`.
`serve.py` learned an `/assets/` route and returns **503 + build instructions**
when there's no bundle, rather than a confusing 404.

Visual: inspired by the Nexus Oracle card archive (dark void, live
pointer-reactive canvas, glass panels) but made Doom, not copied — ember
palette not gold, bevelled DOS-widget edges, CRT scanlines, vignette, blood red
reserved for things you can act on. Deliberately **not** a draggable WebGL deck:
the tiles are real `<button>`s that need focus and keyboard nav, so depth comes
from pointer-tracked tilt + a cursor-following specular glare instead.
`EmberField.jsx` is ~90 canvas embers with parallax, paused when tab hidden.

**Click-to-pin** (what you asked for): hover previews, click locks. Survives the
pointer leaving, survives a search/filter that would hide it, persists across
reload via localStorage. Click again unpins.

**Four real bugs found by testing rather than eyeballing:**
- pinning reordered the grid, moving the card out from under the cursor — this
  is very likely what you saw as "pin doesn't work"
- the pin didn't survive reload at all
- a restored pin marked one tile while the panel showed a different game
- status bar counted a pinned tile as a filter result

**Verification:** `ui/verify.mjs` renders the *real built bundle* against the
live server and asserts 22 behaviours (mount, grouping, hover, pin/unpin,
persistence across a fresh jsdom, filters, show-command). **22/22, no runtime
errors.** Run:
`node verify.mjs "../dist/assets/<bundle>.js" --reload --seed`

**UNVERIFIED — genuinely needs your eyes:**
- how the tile **tilt** actually feels (too subtle? too much?)
- whether the **ember field** is too busy behind the artwork
- the visuals overall; I have not seen a single pixel

---

## 3. Earlier mod fixes (verified)

- **Shadow Warrior** — was launching with no weapons/enemy sprites; the asset
  pack was sitting unused in `Z:\GAMES`
- **Aliens TC** — pk3-first-then-mapset ordering per the author's readme; it was
  booting the IWAD's own maps wearing Aliens enemies/guns, which is exactly the
  symptom you reported
- **Hexen** — Hexen Remade needs the Hexen IWAD, was on DOOM2
- **Audio** — `soft_oal.dll` + `uzdoom.sf2` shipped, and `--check` now *fails*
  rather than silently shipping a broken pack. RaZZoR's config had two inherited
  defects: `snd_aldevice` pointing at a Philips TV on an NVIDIA GPU that never
  existed here, and `snd_samplerate=8000` (telephone-band, no real endpoint
  negotiates it). Both fixed, all video config preserved.

---

## 4. Housekeeping — one loose end

`Z:\DOOM_PACK\mods\bdbe-3-38\` — **191.5 MB of dead weight, safe to delete
manually.** I hand-copied the pk3s there while diagnosing, then discovered
`build.py` slugifies each filename into its own subfolder, so the build created
`mods/bdbe-v3-38/` instead. Nothing references the old folder (confirmed against
the manifest). `MoveFileEx` reboot-delete returned false and the lock came from
a **stale Hermes kernel process (pid 11116)** still holding a `zipfile` handle
from earlier analysis — not the game, not serve.py. I did not kill it: it's a
Hermes kernel and killing it mid-session is not my call. It'll clear on restart.

Also: `git add -A` includes `dist/` so the built UI is committed (deliberate —
the pack should be usable without npm). Old BDBE `.bat` files were auto-pruned
by the builder.

---

## 5. Suggested order after reset

1. **Launch BDBE** (§1) — the only real verification left on the pack.
2. Resume the redesign (§0): CSS layer → Tile → Panel → App → CRT overlay →
   hero art. Verify with `npm run build` + `node verify.mjs
   "../dist/assets/<bundle>.js"` after each step.
3. Delete `mods/bdbe-3-38` (§4).
4. Commit the redesign — the deps, `tailwind.config.js`, `postcss.config.js` and
   the `main.jsx` font imports are currently **uncommitted**.

**On the redesign, two things I still can't check myself:** whether the tilt/jolt
feel is right, and whether the ember field is too busy behind the art. I have
never seen a rendered pixel of the UI.