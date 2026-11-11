"""Offline checks for the tunnel status/lifecycle contract added with the
lobby observability work: ws state words, peer control frames, lobby status
hand-off, and the readiness probe. No network: the lobby HTTP layer is
monkeypatched, and the only sockets touched are loopback binds the test
owns. Live behaviour (real Worker, real UDP both directions) remains
selftest_wsrelay_live.py's job -- a passing test here proves shape, not
connectivity.

    python tools/selftest_tunnel_status.py
"""
import io
import json
import os
import socket
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import wsrelay as W           # noqa: E402
import lobby as L             # noqa: E402
import mp_http as H           # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))


t = W.RelayTunnel("stattest-room")

try:
    # ---- explicit states, never one conflated boolean
    check("a fresh tunnel reports 'connecting' (not just alive)",
          t.state == "connecting", t.state)
    t.connected = True
    check("ws up reports 'connected'", t.state == "connected", t.state)
    t.connected = False
    t.last_error = "connection reset"
    check("ws down with retries pending reports 'reconnecting'",
          t.state == "reconnecting", t.state)
    t.stop()
    check("a stopped tunnel reports 'stopped', not 'reconnecting'",
          t.state == "stopped", t.state)

    # ---- peer identity comes from control frames and traffic, never guesswork
    t2 = W.RelayTunnel("stattest-room2")
    try:
        check("a fresh tunnel has seen no peer", not t2.peer_seen())
        t2._handle_control(b'{"t":"peer","connected":true}')
        check("the Worker's peer-joined frame sets peer_connected",
              t2.peer_connected and t2.peer_seen())
        t2._handle_control(b'{"t":"peer","connected":false}')
        check("the Worker's peer-left frame clears peer_connected",
              not t2.peer_connected)
        t2.snapshot["in_from_relay"] = 1
        check("relay traffic also proves a peer (old-Worker fallback)",
              t2.peer_seen())
        t2._handle_control(b"not json at all")
        t2._handle_control(b'["array","garbage"]')
        check("garbage control frames never crash or set state",
              not t2.peer_connected, str(t2.peer_connected))
    finally:
        t2.stop()

    # ---- status() exposes what the panel's relay-status endpoint serves
    st = t2.status()
    for key in ("state", "peer_connected", "peer_seen", "closed_reason",
                "last_engine_traffic", "last_relay_traffic", "lobby"):
        check(f"status() carries '{key}'", key in st, str(sorted(st)))
    check("status() carries the room", st["room"] == "stattest-room2", str(st.get("room")))

    # ---- _udp_port_taken: the host readiness probe's two outcomes
    blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    blocker.bind(("0.0.0.0", 0))
    held = blocker.getsockname()[1]
    check("a port something already holds reports as taken",
          H._udp_port_taken(held) is True, str(held))
    free = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    free.bind(("127.0.0.1", 0))
    free_port = free.getsockname()[1]
    free.close()
    time.sleep(0.05)
    check("a released port reports as free", H._udp_port_taken(free_port) is False,
          str(free_port))

    # ---- keep_announced fills its status dict (success and failure paths)
    calls = []
    removed = []

    def _fake_post_ex(path, body):
        calls.append(path)
        if path == "/lobby/announce":
            return _announce_verdict
        return True, None

    _announce_verdict = (True, None)
    real_post_ex = L._post_ex
    real_heartbeat_interval = L.HEARTBEAT_INTERVAL
    L.HEARTBEAT_INTERVAL = 0.2
    L._post_ex = _fake_post_ex
    try:
        status = {}
        th = L.keep_announced("roomA", "Label", "doom", lambda: len(calls) < 3,
                              status=status)
        th.join(timeout=5)
        check("a successful announce is reported in the status dict",
              status.get("announced") is True, str(status))
        check("a successful announce records when it was listed",
              isinstance(status.get("listed_at"), float), str(status))
        check("heartbeats run after the announce (3 calls = announce+2 beats)",
              calls.count("/lobby/heartbeat") >= 1, str(calls))
        check("the room is removed when is_alive() goes false",
              "/lobby/remove" in calls, str(calls))

        calls.clear()
        _announce_verdict = (False, "HTTP 503")
        status = {}
        th = L.keep_announced("roomB", "Label", "doom", lambda: False, status=status)
        th.join(timeout=10)   # 3 announce tries x 1s sleep, worst case ~3s + timeouts
        check("a failed announce is reported, with the reason",
              status.get("announced") is False and "503" in str(status.get("error")),
              str(status))
        check("a room that never announced is never heartbeated or removed",
              "/lobby/heartbeat" not in calls and "/lobby/remove" not in calls,
              str(calls))
    finally:
        L._post_ex = real_post_ex
        L.HEARTBEAT_INTERVAL = real_heartbeat_interval

    # ---- lobby_list surfaces directory failure instead of an empty list
    real_lre = L.list_rooms_ex
    L.list_rooms_ex = lambda: ([], "HTTP 503")
    try:
        code, body = H.lobby_list(None, None)
        check("a broken directory reaches the UI as lobby_ok: false",
              code == 200 and body["lobby_ok"] is False
              and "503" in body["lobby_error"], str(body))
        check("a broken directory does not pretend to have zero rooms healthy",
              body["rooms"] == [] and body["lobby_error"], str(body))
    finally:
        L.list_rooms_ex = real_lre
    L.list_rooms_ex = lambda: ([{"room": "r1", "mode": "doom"}], None)
    try:
        code, body = H.lobby_list(None, None)
        check("a healthy empty-ish list still reports lobby_ok: true",
              body["lobby_ok"] is True and body["rooms"] == [{"room": "r1", "mode": "doom"}],
              str(body))
    finally:
        L.list_rooms_ex = real_lre

    # ---- relay_status endpoint: read-only, tolerates no tunnels at all
    W.TUNNELS.clear()
    code, body = H.relay_status(None, None)
    check("relay-status with no tunnels is ok and empty",
          code == 200 and body.get("ok") is True and "host" not in body, str(body))
finally:
    W.TUNNELS.clear()
    t.stop()

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
raise SystemExit(1 if FAIL else 0)
