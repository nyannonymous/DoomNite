# v2.5.3 — Duke goes online

Duke multiplayer used to be LAN-only, because EDuke32's netcode is 1996
peer-to-peer: no port flag, no matchmaking, no NAT traversal, joins are a
bare address on one hardwired UDP port (23513). The panel even said so.
It now has a real internet mode, riding the same relay that Doom's
multiplayer and SkyJump3D already use — a Cloudflare worker both sides
connect OUTBOUND to, so no router changes and no VPN on either end:

- The host clicks "Host over the internet" and gets a short room code.
- The friend types that code and hits "Join by code".
- Each engine tunnels through the relay; any NAT works.

The join side needed a trick worth writing down: the engine cannot be
told a port, and a relay socket on 127.0.0.1:23513 collides with the
engine's own bind — its packets loop straight back into itself. Binding
the relay on 127.0.0.2 instead (all of 127/8 is loopback on Windows)
gives the engine a bare address to dial whose packets land in the
tunnel. The host side forwards into whichever port the engine actually
bound — normally 23513, discovered rather than assumed, because the
engine silently falls back to an ephemeral port when 23513 is taken.

Also in this release: hosting now boots the host straight into E1L1
(`-map E1L1.MAP`). Without a map the host engine sat at the title screen
and every connecting client was dropped instantly with "No player spawn
point available" — v2.5.2's Duke panel could hit exactly that if someone
joined before the host picked a level.
