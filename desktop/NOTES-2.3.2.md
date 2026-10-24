## Playing with someone who is not in your house

2.3.1 shipped the fix that stopped Zandronum asking every player to point it at
their Doom folder. It did not make a game reachable from outside your network,
and the panel said so only by listing a LAN address that could never work for a
friend on the internet. This release closes that.

### Host over the internet

Two new buttons beside Host and Join. They run the same launch, with one extra
step on the wire: a STUN hole-punch.

- `tools/stun.py` asks public STUN servers what a socket on this machine looks
  like from outside, and detects a symmetric NAT by comparing the port two
  servers report. Symmetric NAT is the one case a punch cannot work, and it is
  detected rather than promised.
- `tools/punch.py` keeps a socket open on the punched path. Your engine still
  binds its normal port and never learns any of this happened; the joiner's
  engine dials a localhost port, exactly the shape a tunnel is supposed to have.
- The exchange is the share line you already copy and paste. There is no
  signalling server, because you are already the signalling server.

Two refusals, both before any engine starts, both in plain words: a host behind
a symmetric NAT cannot punch, and a host where no STUN server answers cannot
publish an endpoint. Both say what to do instead.

### The address list tells the truth now

The panel used to offer every non-loopback address with nothing to tell them
apart, and on a machine with WSL or a VirtualBox adapter that meant offering a
dead address in plain green. Two changes:

- The whole of `172.16.0.0/12` is treated as virtual, not just Docker's two
  octets. `172.20.96.1` is `vEthernet (WSL)` — an adapter that exists inside
  one PC and nowhere else — and it used to be ranked **second**, above the
  Tailscale address that actually reaches a remote friend. A real evening was
  lost to a mate sitting on `CONNECTING TO` because of it.
- **Your public IP is now listed**, marked as needing UDP 23513 forwarded on
  your router. It comes from the same STUN lookup, so it needs no "what is my
  IP" website. If your connection sits behind your ISP's own NAT, the address
  is **withheld** rather than printed with a caveat — forwarding a port to an
  address that is already being NATed cannot work, and printing it would send
  you into your router settings for nothing. The panel says why it is absent.

### Also in this release

- `copyTree()` compared files by size and treated a size-identical file as the
  same file. `app/index.html` is 442 bytes whichever `index-<hash>.js` it
  points at, so **every UI rebuild since 8 October was silently skipped** —
  the installer shipped an index.html pointing at an old bundle. Size is now
  only the cheap reject; the bytes settle a tie.
- The NukemNet junction step reported `cmd`'s own message ("The system cannot
  find the path specified") when NukemNet's Zandronum folder was missing. It
  now says that instead. NukemNet is not needed for multiplayer any more, so
  nothing gated on it.
- Multiplayer no longer needs NukemNet at all, and the panel never mentions it.

### Verified

`selftest_mp.py` 129/129 · `selftest_stun.py` 51/51 · `selftest_nn_preset.py` ·
`selftest_packmod_fetch.py` · `check_mp_command.py` 10/10 (run by the packaging
hook, so a build cannot ship the broken command shape) · `verify.mjs` 21/21 ·
`verify-watch.mjs` 11/11 · `verify-mp-button.mjs` 32/32, including the assertion
that the panel contains no NukemNet, junction or preset strings.

The punch tier was verified locally against live STUN servers and by launching
the real engine and watching the port bind. **It has not been proven between
two machines on the internet** — that needs two people and a router, and it is
the one thing this release still owes you.

### Known, and deliberate

- A **public room list is still not built.** Browsing other people's games needs
  NukemNet's IRC/relay protocol; `createRoom`/`hostGame`/`joinRoom` exist only
  in its renderer bundle, with no scriptable interface. The panel omits the
  feature rather than shipping a dead button.
- Baked-in mods have **no reinstall button**. Their copies were made at build
  time, so getting one back is `python tools\build.py`. The two on-demand total
  conversions (Adventures of Square, Requiem) do install and uninstall from the
  panel, and every other game can now be re-fetched from the hosted bucket with
  its INSTALL button.
