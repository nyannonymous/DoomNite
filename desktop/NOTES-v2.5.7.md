# v2.5.7 — Multiplayer status you can trust

Follow-up to the v2.5.6 STUN relay fix: the multiplayer panel now tells the truth at every step.

## Fixes
- **Honest hosting status** — the room is only announced to the public list after your game is actually listening (not merely launched). If the game list can't be reached, the host is told so, with the room-code fallback always available.
- **No more phantom "friend is here"** — peer presence now comes from the relay's authoritative joined/left signals when available, or falls back to recent relay traffic (18 s window) on older deployments. A friend who disconnects actually shows as gone.
- **Join waits for the relay** — joining waits (bounded) for the tunnel to reach the relay before launching the game, and reports a clear, actionable error instead of a stuck "Connecting".
- **Broken directory ≠ empty list** — a lobby outage now shows a warning instead of a healthy-looking "No one's hosting right now".
- **Lobby self-healing** — if a listing heartbeat fails, the host automatically re-announces on the next cycle.
- **Full relay room fails fast** — a third joiner gets a clear "room is full" instead of endless reconnecting.
- **Branding** — real DoomNite logo in the topbar, with the version number displayed under it.

## Notes
- LAN, direct-IP, STUN and NukemNet paths unchanged.
- The two-peer relay limit is unchanged.
