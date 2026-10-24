# 2.3.2 — BUILT and staged locally, NOT published (2026-10-18)

The 2026-10-16 run left this blocked as "no new feature beyond live 2.3.1".
That was wrong: it had not read the log. Everything between `646af93` (2.3.1)
and now includes the STUN punch tier, which had never been released.

## What 2.3.2 contains that 2.3.1 does not

| area | change |
|---|---|
| `tools/stun.py` | new — STUN client, NAT verdict |
| `tools/punch.py` | new — the punched-path relay |
| `tools/mp_http.py` | +209 lines — the punch flow, the public address |
| `tools/mp_session.py` | +109 — address ranking fix, `public_endpoint()` |
| `ui/src/MultiplayerButton.jsx` | +132 — Host/Join "over the internet", public-IP line |
| `desktop/main.js` | ctrl+wheel zoom |

So: two new buttons that make an internet game possible without a VPN, the fix
that stopped the panel offering a dead WSL adapter above the one address that
works, and the public IP listed with an honest "needs UDP 23513 forwarded".

## The artifacts (already built and verified)

```
desktop/release/DoomNite - Windows Setup v2.3.2.exe        143,434,110 bytes
desktop/release/DoomNite - Windows Portable v2.3.2.zip     187,999,688 bytes
desktop/release/DoomNite - Windows Setup v2.3.2.exe.blockmap
desktop/release/win-unpacked/                              the unpacked build
```

Built by:

```bash
cd desktop
DOOMNITE_SOURCE_ROOT="Z:/github/APP · DOOMNITE-PACK" \
  npx electron-builder --win --config.directories.output="<scratch dir>"
```

Built to a scratch directory on `Z:` and copied back, because
`electron-builder` cannot remove an existing `desktop/release/win-unpacked` on
the network drive (the EBUSY documented in BUILDING.md). Copying the finished
files into `desktop/release/` afterwards is safe — it is gitignored.

Verified on the artifact, not the source tree:

- `python tools/selftest_packaged.py` → "a packaged DoomNite would start"
  (measures `desktop/release/win-unpacked`, the real build).
- The packaged app launched with `DOOMNITE_PACK` set served **33 entries, 1
  missing** (only `Sonic Robo Blast 2 v2.2`, a standalone exe that lives on the
  operator's source drive and is not in the bucket), and
  `POST /api/multiplayer/setup` returned `ok: true, can_play: true`.
- Staged payload checked directly: manifest **16 games**, `launchers/` **31**
  scripts, `tools/run_standalone.cmd` **2** entries, `app/index.html` pointing at
  the current bundle `index-DNA_MxhZ.js`, and **0** `.ini` files under
  `runtime/zandronum/` — so the fresh-install property survives packaging and
  the absolute-path `DOOMWADDIR` fix is what actually runs.

## What is NOT done, and why

**The release is not published.** That is an outward-facing step on a public
repository, which is one of the four classes an unattended worker must not
take. `site/index.html` is deliberately still at 2.3.1 for the same reason,
and because this pack's own trap list says publish FIRST — pointing the site at
a release that does not exist yet once put dead 404 links on the live page.

The one-command publish, when the owner wants it:

```bash
gh auth switch -u nyannonymous            # Chimthuwu is pull-only on this repo
cd "Z:/github/APP · DOOMNITE-PACK"
gh release create v2.3.2 \
  "desktop/release/DoomNite - Windows Setup v2.3.2.exe" \
  "desktop/release/DoomNite - Windows Portable v2.3.2.zip" \
  --repo nyannonymous/DoomNite --title "DoomNite 2.3.2" \
  --notes-file desktop/NOTES-2.3.2.md
# only after that returns 200 for both asset URLs, update site/index.html
# from 2.3.1 to 2.3.2 and push -- Cloudflare Pages deploys site/ on push.
```

## Trap this run hit, so the next one does not

`python tools/build.py` regenerates `pack-manifest.json` and `launchers/` from
the operator's **source** drive (`Z:\GAMES\BRUTAL_DOOM (uwu)`), which is now
**empty**. One run rewrote the manifest from 16 games to 4 and `launchers/` from
31 scripts to 5, and clobbered the tracked `tools/run_standalone.cmd`. Both
`pack-manifest.json` and `launchers/` are **gitignored**, so there is no
`git checkout` for them. They were recovered from the staged copy in
`desktop/build/pack/` (left by the 2.3.1 build) and `--check` is green again:

    python tools/build.py --check  ->  pack OK: every referenced file exists

Do not run `tools/build.py` on this checkout without a backup. Filed as a P1
Inbox item in `todo.md`.
