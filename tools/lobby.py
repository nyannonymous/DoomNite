"""Client for the relay Worker's lobby directory (cloudflare/relay/worker.js's
`Lobby` Durable Object) -- the list of open relay rooms, so joining is
"click a name in a list" instead of "paste a code a friend read out over
voice chat". This module only talks to the lobby's HTTP endpoints; the
actual game traffic never goes through it (that is wsrelay.py's job).

Pure stdlib (urllib), same reasoning as wsrelay.py's hand-rolled websocket
client: this pack ships without a Python package manager step.
"""
from __future__ import annotations

import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request


def _ssl_context() -> ssl.SSLContext:
    """Same fix as wsrelay.py's _ca_bundle(): this machine's Python ships a
    stale default CA bundle that rejects a perfectly live Cloudflare cert as
    expired. Prefer certifi's bundle when installed; certifi stays optional,
    not a new hard dependency."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()

# Same account/deploy as wsrelay.DEFAULT_RELAY_URL; kept separate rather
# than imported from there so this module has no dependency on the tunnel
# engine -- a lobby entry and a relay tunnel are related but distinct, and
# mp_http.py is free to announce a room before (or without) a tunnel.
LOBBY_BASE = os.environ.get("DOOMNITE_RELAY_URL", "https://doomnite-relay.chimske.workers.dev").replace("wss://", "https://").replace("ws://", "http://").rsplit("/relay", 1)[0]

HEARTBEAT_INTERVAL = 20.0   # Worker-side STALE_MS is 45s; this comfortably beats it
TIMEOUT = 5.0

# Cloudflare's bot protection 403s the default "Python-urllib/x.y" User-Agent
# outright (measured live, 2026-10-29: identical request, only the UA
# differs, 403 vs 200). Any non-default string clears it; this one just
# says who is actually asking.
_HEADERS = {"User-Agent": "DoomNite-Lobby/1.0", "Content-Type": "application/json"}


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        LOBBY_BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers=_HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def announce(room: str, label: str, mode: str = "doom", players: int = 1) -> bool:
    try:
        return bool(_post("/lobby/announce", {"room": room, "label": label, "mode": mode, "players": players}).get("ok"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def heartbeat(room: str) -> bool:
    try:
        return bool(_post("/lobby/heartbeat", {"room": room}).get("ok"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def remove(room: str) -> bool:
    try:
        return bool(_post("/lobby/remove", {"room": room}).get("ok"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def list_rooms() -> list[dict]:
    """Never raises: a lobby fetch failing must not break the panel, it
    just shows an empty (or stale, cached client-side) list."""
    try:
        req = urllib.request.Request(LOBBY_BASE + "/lobby/list", headers=_HEADERS, method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rooms = data.get("rooms")
        return rooms if isinstance(rooms, list) else []
    except (urllib.error.URLError, TimeoutError, ValueError):
        return []


def keep_announced(room: str, label: str, mode: str, is_alive) -> threading.Thread:
    """Announce once, then heartbeat every HEARTBEAT_INTERVAL while
    `is_alive()` is true, then remove(). Runs in a daemon thread so a host
    launch returns immediately -- the panel does not wait on a Cloudflare
    round trip to hand the player their game."""

    def _run():
        if not announce(room, label, mode):
            return  # couldn't even announce; nothing to heartbeat or clean up
        while is_alive():
            time.sleep(HEARTBEAT_INTERVAL)
            if is_alive():
                heartbeat(room)
        remove(room)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
