## Multiplayer without NukemNet

Press **MULTIPLAYER** in the header, pick a game, and either host or join. You
do not open NukemNet and you do not need to know it exists — the folder links
and its preset are set up for you when the panel opens.

The installer still ships the launcher shell and the manifest, not the 2.7 GB
of mods; those download from the R2 bucket. What is new is that the button to
do that now exists for every game rather than only two, so a fresh install can
reach a playable state on its own.

### Also in this release

- **Mod-mismatch fingerprint.** When you host, your share line carries an
  8-character code hashed from the files you are running. A joiner who pastes
  it is warned if their version differs, instead of discovering it as a subtle
  desync. It never blocks joining.
- **Shareable addresses are labelled.** A VPN address (Tailscale and similar)
  is marked as only working if your friend is on your VPN, rather than being
  offered as though it were a LAN address.
- **Hexen Remade is fetchable.** It was the one file nobody could download.

### Verified

`verify.mjs` 21/21 · `verify-watch.mjs` 11/11 · `verify-mp-button.mjs` 19/19 ·
`selftest_mp.py` 102/102 · `selftest_packmod_fetch.py` round-trips a real 37 MB
download from the bucket and back · bucket check 68/68 reachable, no size drift.

### Known limits

- Hosting across the internet needs port 23513 forwarded on your router. On the
  same network it works as-is.
- There is no public room list yet. That needs NukemNet, whose room code has no
  scriptable interface — so joining a public room list still means opening it.
  Hosting and joining by address do not.