# v2.5.6 — internet multiplayer actually connects

Cross-network Brutal Doom (and every other Zandronum game) was getting stuck on
"Connecting" because the STUN hole-punch relay had a lifecycle bug. This release
fixes it.

What was wrong and what changed:

- **The UDP socket was racing itself.** The relay started its background
  packet-serving threads the moment it was created — *before* STUN discovery ran
  on that same socket. The serve thread could swallow a STUN response meant for
  the discovery call, so the public mapping was occasionally never learned and
  the punch silently failed. Threads now start only *after* STUN discovery
  completes (`PunchRelay.start()`), so discovery has exclusive use of the socket.
- **A delayed STUN reply could hijack the peer slot.** If a late STUN response
  arrived once the relay was live, it was treated as legitimate peer traffic and
  locked the peer address onto the STUN server, dropping every real game packet.
  STUN packets (RFC 5389 magic cookie) are now explicitly recognised and dropped
  in the classifier.
- **The host relay didn't know where Zandronum was listening.** It waited to
  "learn" the engine address from the first loopback packet, so early inbound
  peer traffic was discarded. The host relay now gets its engine target
  (`set_engine_target("127.0.0.1", 23513)`) configured up front, matching the
  Cloudflare relay's existing behaviour.
- **Better diagnostics.** Relay status now reports packets forwarded in both
  directions, seconds since last traffic, and the last error, so a stuck
  connection shows a reason instead of hanging forever.

Verified by the existing multiplayer self-tests plus a new
`tools/selftest_punch_lifecycle.py` covering the three regressions above.

LAN play, direct-IP join, and the Cloudflare relay tunnel are unchanged and
still work. Symmetric-NAT hosts are still refused with a plain-English message
(switch to the relay or a Tailscale LAN) — STUN genuinely cannot punch those.
