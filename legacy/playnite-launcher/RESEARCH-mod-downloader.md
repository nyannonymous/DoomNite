# DoomNite — mod downloader research (2026-10-04)

Research for turning DoomNite into a mod browser/downloader: image per mod, dimmed
when not installed, Install button where Play normally sits, entry joins the library
once installed. Mods must NOT ship pre-installed.

## Blocker: ModDB cannot be automated

Tested, not assumed:

- `curl` (normal browser UA) -> **HTTP 403**, Cloudflare "Just a moment..."
- Real driven browser -> still blocked; the interstitial never clears (Ray ID shown)

So a silent "download from ModDB" install button is **not buildable**, and would also
fail on a user's machine — Cloudflare blocks them too. A one-click Install that no-ops
is worse than no button.

## Hosts that ARE scriptable (verified HTTP 200 via curl)

| Host | Scriptable | Notes |
|---|---|---|
| GitHub API + raw.githubusercontent | yes | best case for one-click |
| `zandronum.com/downloads` | yes | how Zandronum 3.2.1 was installed |
| archive.org | yes | good mirror of older releases |
| itch.io | yes | some indie TCs publish here |
| gamebanana.com | yes | alternative TC host |
| **moddb.com** | **NO** | Cloudflare challenge |
| doomwiki.org | 403 | reference only, not a source |
| forum.zdoom.org | connection fails | — |

## Design: per-mod source, chosen at data-entry time

`data/mods.json` gains a `source` per entry:

- `direct` — file is on a scriptable host (GitHub release, archive.org, itch.io).
  Real one-click, fully automatic: download, verify, extract, add to library.
- `browser` — file is only on ModDB. Install button opens the download page in the
  user's browser with clear instructions. A human clears Cloudflare; the launcher
  watches the mods folder and flips the entry to "installed" when the file appears.

Never a silent no-op. Every Install button either installs or explains itself.

Open question for Stooge: whether to accept the two-tier model, or restrict the
launcher to `direct`-source mods only so every button is genuinely one-click.

## Candidate mods (total conversions preferred)

Ranking still to be confirmed against ModDB download counts, but the well-known TCs
that fit "mod downloader" are: Brutal Doom, Aliens Eradication TC, Dusk 'Til Dawn
(Doom III), Aliens TC (1994, the first TC ever), Call of Doom: Black Warfare,
DBP37: Auger;Zenith, Shadow Warrior, QuakinDoom, Army of Darkness TC, DOOM 64 EX.

Multiplayer note carried over from the NN work: Doom III's `D3.pk3` is ~4 GB, which
makes it a bad NukemNet transfer target (NukemNet pushes mod files to every joiner).
Brutal Doom / Aliens Eradication / Call of Doom are the sane online picks.

## Multiplayer (NukemNet) status

- NukemNet 0.6.5 installed at `C:\Users\Serge\Desktop\NUKEMNET`, GPL-3.0, public at
  `gitlab.com/aabluedragon/NukemNet`, last activity Aug 2026.
- Zandronum **already** installed at `C:\Users\Serge\AppData\Local\Zandronum`, plus
  Doomseeker. A room was created successfully end-to-end.
- NAT ladder confirmed in source: IPv6 (UDP-over-KCP tunnel) -> STUN (detects
  symmetric NAT) -> relay. That is why it feels instant.
- Room hosting is GUI-only (no CLI/API), so DoomNite can only write NN's
  `LaunchDefaults.json` presets and let NN own the room.
- `data/mp_verified.json` from `tools/qa_mp_probe.py` is currently UNTRUSTWORTHY:
  its 14s settle window is too short for large PK3s (Doom III = 3.99 GB). Needs
  per-mod timeouts sized to file size before any MP list is generated.

## Cleanup owed

`Z:\GAMES\Zandronum` was installed by mistake before the existing AppData copy was
found. Redundant; awaiting Stooge's go-ahead to delete.