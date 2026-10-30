## Multiplayer you can set up with no typing and no router access

2.3.2 (never released on its own — folded into this one) added a STUN punch
tier so two people on different networks could play without a VPN, as long as
the host could still forward a port. This release removes that requirement
entirely, and adds a way to find a game without anyone pasting an address.

### Relay tier — works behind CGNAT, works behind any router

A new, self-hosted Cloudflare relay (`doomnite-relay.chimske.workers.dev`).
Both players make an *outbound* `wss://` connection to the same room; neither
side needs a forwarded port, a static IP, UPnP, or Tailscale. This is the tier
for the host who can't or won't touch their router, and the only tier that
works when the host is behind CGNAT (where the STUN punch tier cannot, by
definition — there's no public port to punch to).

- `tools/wsrelay.py` — a pure-stdlib WebSocket client that tunnels raw
  Zandronum UDP packets byte-exact through a Durable Object room.
- `tools/mp_http.py` — a `"relay": true` flag on host/join, mutually
  exclusive with `"stun"`. The host gets a room code back, nothing
  routable to leak; the joiner supplies the code and gets a loopback
  address to connect to.
- This adds latency (an extra round trip through Cloudflare) in exchange for
  working anywhere. STUN punch stays the lower-latency tier when it's usable;
  relay is the one that's never blocked.

### The lobby — click a game instead of pasting anything

A new "Open games" list in the multiplayer panel, backed by the same Worker.
Hosting with relay now announces the room to a shared lobby; anyone with the
panel open sees it appear within a few seconds and clicks **Join** — no code,
no address, no second screen. A host that crashes or closes falls out of the
list automatically (one missed 20-second heartbeat past a 45-second staleness
window), so there's never a dead "join me" entry to click.

- `cloudflare/relay/worker.js` — new `Lobby` Durable Object, one global
  singleton holding the open-room directory.
- `tools/lobby.py` — thin client plus a background thread that announces,
  heartbeats, and removes itself on exit.
- A small "Join by code" fallback stays for the one gap polling can't cover: a
  room that hasn't propagated to the list yet.

### Also in this release

- Multiplayer launches now set sane defaults — 1920x1080 and turned-down sound
  and music volumes — instead of coming up at Zandronum's stock 640x480 with
  everything blaring. Still changeable in-game.
- `nn_preset.py`'s "ambiguous name" error now lists the matching entries with
  their indexes, instead of just saying how many there were and leaving you to
  guess.
- Everything from 2.3.2: the STUN punch tier (`tools/stun.py`, `tools/punch.py`),
  the public-IP line in the panel, and the fix that stopped a dead WSL/Hyper-V
  adapter from outranking a real one.

### Verified

`selftest_mp.py` 140/140 · `selftest_stun.py` 51/51 · `selftest_wsrelay.py` 6/6
· `selftest_relay_mp.py` 19/19 · `verify.mjs` 21/21 · `verify-mp-button.mjs`
32/32. Live, against the real deployed Worker (not a fake local server):
`selftest_wsrelay_live.py` 4/4 and `selftest_lobby_live.py` 10/10 — two
independent tunnels round-tripping a UDP packet through the actual Cloudflare
Durable Object, and the actual lobby announce/heartbeat/remove cycle.
`selftest_packaged.py` passes against this exact build, and the packaged app
served all 33 entries with nothing missing.

### Known, and still open

- The relay and lobby tiers are verified against the live infrastructure from
  one machine running two independent connections. They have not yet been
  proven with two separate computers, each running the real engine, in an
  actual match — that still needs the owner and a friend.
- Visual/UX of the new "Open games" list has not been seen rendered; only
  checked structurally (jsdom has no layout engine).
