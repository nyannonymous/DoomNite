# DoomNite — where things stand

Written just before a gateway reset. Everything below is **verified working**
unless marked UNVERIFIED.

Pack root: `Z:\DOOM_PACK` · serve on `http://127.0.0.1:8765` ·
builder `python tools/build.py` · checker `python tools/build.py --check`

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

1. **Launch BDBE Enhanced E1 and HontE.** The only real verification left.
2. If BE is wrong → `-stdout` + logfile capture, read the engine's own error.
3. Look at the UI and tell me about the tilt and the ember density.
4. Delete `mods/bdbe-3-38` once the lock clears.

Last commits: `310ab5e` (UI + pin) · BDBE fix is **uncommitted** — commit it
first if you want it safe before the reset.