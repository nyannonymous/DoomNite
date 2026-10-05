# DoomNite — gameplan

Goal: **modded Doom multiplayer that a non-tech-savvy friend can join with one
click**, and a mod library that downloads itself.

Status as of 2026-10-04. Commit `dba79f4` has the mod catalogue, ghost cards and
a working one-click installer. Everything below is what is NOT done yet.

---

## The two decisions that shape everything

**1. Multiplayer goes through NukemNet, not Zandronum directly.** Settled.

Zandronum is the engine *underneath* NukemNet, not an alternative to it. Wiring
Zandronum in directly leaves every player solving NAT themselves — port
forwarding, firewall, hole punching — which is precisely the wall that stops
non-tech-savvy people. NukemNet already solves it: IPv6 tunnel (UDP-over-KCP) →
STUN (detects symmetric NAT) → relay, in that order. That fallback chain is why
it feels instant instead of hanging on "connecting…".

So: DoomNite picks the mod and writes NN's preset. **NN owns the room.**
DoomNite never reimplements NAT.

**2. ModDB is not in the auto-install path.** Settled, do not revisit.

`moddb.com` returns 403 behind a Cloudflare challenge to scripted requests, and
the interstitial never clears in a real browser either (tested both). A ModDB
Install button would silently no-op for real users, which is worse than not
shipping it. Mods whose binaries live only on ModDB use `source: "browser"`:
open the download page, watch the mods folder, flip to installed when the file
appears.

---

## Phase 1 — Multiplayer presets (the last real gap)

**Why this is next:** NN has no concept of "modded Doom". It stores ONE file list
per game ID, hardcoded. Picking a mod today means hand-editing JSON in
`AppData`. That single fact is what makes the setup non-intuitive, and it is the
whole remaining gap in the UI.

- [ ] Write NN's `LaunchDefaults.json` from DoomNite's mod choice.
      Known schema, already read from a working install:
      `%LOCALAPPDATA%\NukemNet` is Electron, so settings live in
      `NukemNet\user\` — `Settings.json` (games → zandronum path) and
      `LaunchDefaults.json` (per-game `file` list + gamemode/map/skill params).
- [ ] Back up `LaunchDefaults.json` before first write. It is the user's config.
- [ ] **Open decision — one folder or two?** NN launches Zandronum out of
      `%LOCALAPPDATA%\Zandronum`. DoomNite's entries run out of
      `Z:\GAMES\BRUTAL_DOOM (uwu)`. NN needs the mod *files* in its own folder.
      Options: junction (no duplicate disk) or copy. Matters a lot at 364 MB+.
      Do not pick blind — ask Stooge.
- [ ] `browser` source entries: implement the watch-the-mods-folder flip.
- [ ] **Constraint to remember:** NN's room hosting is GUI-only. No CLI, no
      headless, no socket API. DoomNite can launch and configure; it cannot
      create a room unattended. Do not design around one-click hosting.

## Phase 2 — Trust the multiplayer list

- [ ] **Fix `tools/qa_mp_probe.py`.** Its 14 s settle window is too short for
      large PK3s — it produced a FALSE NEGATIVE on Doom III, which is a plain
      PK3 and loads fine. Scale the window to asset size.
- [ ] Re-run across all 29 entries, then delete the current junk
      `data/mp_verified.json` (not committed) and regenerate.
- [ ] Classify: MP-capable / single-player-only / not a Zandronum engine.
      Already known non-Zandronum: `hl2doom.exe` (entry 28), `srb2win.exe`
      (29).
- [ ] **Doom III is disqualified from NN MP regardless of loadability** —
      `D3.pk3` is 3.99 GB and NN pushes mod files to every joiner. Brutal Doom,
      Aliens Eradication and Call of Doom are the sane online picks.

## Phase 3 — Grow the catalogue

Working now: 4 ghost cards + 1 play card. All verified against real GitHub
release assets with exact byte sizes.

- [ ] Install the 4 remaining ghosts so the demo is honest, or leave them
      ghosted to demo the Install path. Stooge's call.
- [ ] Add `browser`-source entries for the famous TCs with no GitHub binaries
      (Brutal Doom 22, Aliens TC, Call of Doom, DBP37, Shadow Warrior,
      QuakinDoom, Army of Darkness, Dusk 'Til Dawn).
- [ ] **Do not rank "most popular" by ModDB download counts** — that data is
      unreachable. Either rank by GitHub stars and say so, or have Stooge paste
      the counts in.
- [ ] Consider hashing (sha256) per asset instead of size-only verification.

## Phase 4 — Actual cards with pictures

- [ ] The launcher is still **plain batch**. "Ghosted" is currently a `~`
      character and different menu text. There is no image yet, because batch
      cannot show images.
- [ ] Artwork is already collected (`art/*.png`, 7 files, verified PNGs) and
      referenced by `data/catalog.json`, so a GUI pass has everything it needs.
- [ ] Opacity-dimming is a rendering decision for that pass. Nothing about the
      data model needs to change.

## Phase 5 — Web UI version (idea from Stooge, 2026-10-05)

A browser version of the same UI as the Electron app, so people can try DoomNite
without downloading the whole mod pack first. **No multiplayer in the web
version** — that stays Electron-only while it is still being built.

- [ ] Same card UI, but **every mod starts greyed out** (the existing ghost-card
      state). Nothing is downloaded up front.
- [ ] Use the browser cache (service worker / Cache Storage / IndexedDB) for the
      catalogue and the card art, so the page loads fast and works on repeat
      visits. `data/catalog.json` + `art/*.png` already hold everything needed.
- [ ] Clicking a greyed card = **download it, install it automatically, and put a
      shortcut to its launcher `.bat` on the user's Desktop.**
- [ ] No multiplayer UI, no NukemNet preset writing in this build.
- [ ] **Things to verify before building — a plain web page cannot do these on
      its own:**
      - Write into a mods folder: the File System Access API can (user picks the
        folder once), but it is Chromium-only. Firefox/Safari would need a
        fallback.
      - Create a Desktop shortcut or run a `.bat`: browsers cannot. Options are a
        tiny local helper / custom protocol handler, or a downloaded `.bat` /
        `.url` the user double-clicks.
      - Download GitHub release assets from the page: check CORS on the asset
        redirect; may need a small proxy (Cloudflare Worker — `wrangler.jsonc`
        already exists in the app repo).
- [ ] Keep the web UI and the Electron UI on **one shared front-end** so the
      catalogue and card behaviour never drift apart.

## Phase 6 — The backend must die with the app (Stooge, 2026-10-05)

The Electron app spawns `serve.py` itself (port 8765) and must never leave it
running after the app closes. Today it only half-does that: `desktop/main.js`
kills the server and fetcher in `before-quit` (`taskkill /t`), and quits on
`window-all-closed`. That covers a normal close and nothing else.

- [ ] **Hard exits leave an orphan.** `before-quit` never fires on a crash,
      "End task" or a power-off, so a stray `python serve.py` keeps port 8765
      and the next launch fails with `EADDRINUSE`. Found three such leftovers on
      2026-10-05 (all from agent test runs, not the app, but the failure mode is
      the same).
- [ ] Make the server **exit on its own when the app dies**: have `serve.py`
      watch the Electron parent PID (or a heartbeat) and shut itself down, and/or
      put the child in a Windows Job Object set to kill-on-close so the OS ends
      it with the parent. Prefer the Job Object: it also covers a crash.
- [ ] **On startup, handle a stale server instead of failing.** If 8765 is
      already taken, check whether it is our own `serve.py` (reuse or stop it)
      before reporting `EADDRINUSE`.
- [ ] **Open question: games started from the app.** `/api/launch` starts the
      game from `serve.py`; `taskkill /t` kills the whole tree. Check whether
      closing DoomNite also kills a Doom game that is still running, and decide
      if that is wanted. Multiplayer (NukemNet/Zandronum) must NOT die when the
      launcher closes.
- [ ] Test every exit path and confirm port 8765 is free afterwards: close the
      window, quit from the tray/menu, End task in Task Manager, crash the main
      process.
- [ ] Same rule for `fetcher.py` — it must stop writing into the pack when the
      app is gone.
- [ ] Web build (Phase 5) has no local server to clean up, so none of this
      applies there.

---

## Open questions for Stooge

- [ ] Junction or copy for the mods folder? (Phase 1 blocker)
- [ ] Install the 4 ghost mods now, or keep them ghosted for the demo?
- [ ] Delete the redundant `Z:\GAMES\Zandronum`? It was installed by mistake
      before finding the existing copy at `%LOCALAPPDATA%\Zandronum`. Still
      sitting there.
- [ ] Push `dba79f4`? Committed locally, not pushed.
- [ ] Web UI (Phase 5): Chromium-only with the File System Access API, or ship a
      tiny local helper so it works in every browser and can make the Desktop
      shortcut?

---

## Environment facts worth not rediscovering

- NukemNet 0.6.5: `C:\Users\Serge\Desktop\NUKEMNET`. GPL-3.0, public at
  `gitlab.com/aabluedragon/NukemNet`, last activity Aug 2026, single maintainer
  (`aaBlueDragon`). Not affiliated with 3D Realms or any game.
- Zandronum **already installed** at `C:\Users\Serge\AppData\Local\Zandronum`,
  plus Doomseeker. A room was created successfully end-to-end.
- Zandronum verified genuinely hosting: `-host 4` binds UDP 10666.
- Scriptable hosts (verified 200): GitHub + raw + API, `zandronum.com/downloads`,
  archive.org, itch.io, gamebanana. Blocked: moddb.com (Cloudflare),
  doomwiki.org (403), forum.zdoom.org (fails to connect).
- Zandronum and doomwiki are both behind bot walls for `curl`; use the browser
  tool or a scriptable mirror.
- Never launch Zandronum without asking — Stooge asked once already.
- Mods folder: `Z:\GAMES\BRUTAL_DOOM (uwu)`, override with `DOOMNITE_MODS_DIR`.
  Chosen because every existing `doomnite.json` entry already runs from it.

## Prior art

Stooge referenced testing this pattern with **Reqiuem** and **The Adventures of
Square**. Neither is on this box — searched `Z:\GITHUB` and the index. Worth
asking where they live; the AoS standalone-download pattern is the closest
existing example of "download a game, drop it in, it just works".
