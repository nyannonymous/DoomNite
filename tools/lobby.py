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
    """Prefer certifi's bundle, then the bundle shipped with the pack
    (tools/cacert.pem), then the system default. A fresh install has no pip
    packages, so without the shipped bundle announce() silently fails and a
    hosted game never appears in anyone's list -- including the host's."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cacert.pem")
    if os.path.exists(bundled):
        return ssl.create_default_context(cafile=bundled)
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


def _post_ex(path: str, body: dict) -> tuple[bool, str | None]:
    """(ok, error). The *_ex variants are how a caller that REPORTS state
    (mp_http.py's host path, the panel) talks to the lobby: a False must
    always be explainable, never a silent shrug."""
    try:
        return bool(_post(path, body).get("ok")), None
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return False, str(e)


def announce_ex(room: str, label: str, mode: str = "doom",
                players: int = 1) -> tuple[bool, str | None]:
    return _post_ex("/lobby/announce",
                    {"room": room, "label": label, "mode": mode, "players": players})


def heartbeat_ex(room: str) -> tuple[bool, str | None]:
    return _post_ex("/lobby/heartbeat", {"room": room})


def remove_ex(room: str) -> tuple[bool, str | None]:
    return _post_ex("/lobby/remove", {"room": room})


def announce(room: str, label: str, mode: str = "doom", players: int = 1) -> bool:
    return announce_ex(room, label, mode, players)[0]


def heartbeat(room: str) -> bool:
    return heartbeat_ex(room)[0]


def remove(room: str) -> bool:
    return remove_ex(room)[0]


def list_rooms_ex() -> tuple[list[dict], str | None]:
    """The open-rooms list WITH the failure separated out: `(rooms, None)`
    on a real, successful directory response (even a zero-room one), and
    `([], reason)` when the directory itself could not be reached. The
    distinction is the whole point -- a broken Worker must never render as
    a healthy "No one's hosting right now"."""
    try:
        req = urllib.request.Request(LOBBY_BASE + "/lobby/list", headers=_HEADERS, method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rooms = data.get("rooms")
        if isinstance(rooms, list):
            return rooms, None
        return [], "lobby returned no room list"
    except urllib.error.HTTPError as e:
        return [], f"HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return [], str(e)


def list_rooms() -> list[dict]:
    """Compat wrapper. Never raises: a lobby fetch failing must not break
    the panel, it just shows an empty (or stale, cached client-side) list.
    New callers should prefer list_rooms_ex() so failure stays visible."""
    return list_rooms_ex()[0]


def keep_announced(room: str, label: str, mode: str, is_alive,
                   status: dict | None = None) -> threading.Thread:
    """Announce once, then heartbeat every HEARTBEAT_INTERVAL while
    `is_alive()` is true, then remove(). Runs in a daemon thread so a host
    launch returns immediately -- the panel does not wait on a Cloudflare
    round trip to hand the player their game.

    `status`, when given, is filled in as the thread runs:
    {"announced": bool, "error": str|None, "listed_at": ts|None,
     "last_heartbeat_error": str|None}. A caller that needs the announce
    verdict SYNCHRONOUSLY should call announce_ex() itself first (that is
    what mp_http.py's host path now does) and treat this thread's retries
    as recovery, not as the source of truth."""

    def _run():
        # Retry the first announce: a transient Cloudflare/SSL failure on a
        # fresh install must not silently drop the room from everyone's list
        # (including the host's) for the whole session.
        announced = False
        last_err = None
        for _ in range(3):
            ok, err = announce_ex(room, label, mode)
            if ok:
                announced = True
                break
            last_err = err
            time.sleep(1.0)
        if status is not None:
            status["announced"] = announced
            status["error"] = None if announced else last_err
            status["listed_at"] = time.time() if announced else None
        if not announced:
            return  # couldn't announce; nothing to heartbeat or clean up
        while is_alive():
            time.sleep(HEARTBEAT_INTERVAL)
            if not is_alive():
                break
            # A failed heartbeat means the listing may have lapsed; the
            # next cycle re-ANNOUNCES instead (an idempotent upsert) so a
            # transient Cloudflare blip self-heals rather than quietly
            # dropping the room for everyone. Success clears the flag,
            # which is also what tells the UI "listed again, warning off".
            if status is not None and status.get("last_heartbeat_error"):
                ok, err = announce_ex(room, label, mode)
            else:
                ok, err = heartbeat_ex(room)
            if status is not None:
                if ok:
                    status["last_heartbeat_error"] = None
                    if not status.get("announced"):
                        status["announced"] = True
                        status["listed_at"] = time.time()
                else:
                    status["last_heartbeat_error"] = err
        remove(room)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
