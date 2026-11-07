# v2.5.0 — Duke Nukem joins the roster

Three standalone Duke titles ship with the pack and install on demand from
the bucket, each with native EDuke32 LAN multiplayer:

- **Duke Nukem 3D** (ATOMIC EDITION)
- **Duke Nukem 64** (N64 port content)
- **KickAss Duke** (1.2 HRP mod)

## Multiplayer

The Multiplayer picker now lists the Duke titles alongside the Zandronum
games. EDuke32 netplay is plain LAN: the host shares their bare IPv4
address, the joiner types it in, no STUN, no relay, no port config —
`eduke32 -connect <ip>` under the hood.

## Installer

`sources.json` grew to 6,191 entries (~0.3 GB of Duke engine + game data).
A fresh install downloads all of it from the R2 bucket on first run; the
Duke games need nothing else on the target machine. Found and fixed a
`make_sources.py` bug where SKIP_DIRS pruning at any depth silently
dropped `runtime/eduke32/duke64/duke64/art` (3,545 PNGs) from the manifest.

## Numbers

- 19 games, 34 launchers
- Setup 137 MiB / Portable 180 MiB (bootstrap only; game data streams)
