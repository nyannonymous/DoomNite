"""Offline contract checks for the relay-tunnel tier's mp_http.py wiring
("relay": true), same style as selftest_stun.py's "mp_http punch contract"
section: the engine launch and wsrelay's real networking are stubbed, so
this pins the REQUEST/RESPONSE SHAPE -- that host gets a room code back,
join requires one, the two tiers refuse to combine, and the host side wires
set_engine_target() instead of relying on a learned address. It does not
prove a Worker relays real UDP between two machines; selftest_wsrelay.py
covers the tunnel engine itself against a fake local server, and a real
two-peer test against the deployed Worker is the only thing that proves the
whole chain end to end.

    python tools/selftest_relay_mp.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mp_http as H          # noqa: E402
import mp_session as _m      # noqa: E402
import wsrelay as W          # noqa: E402
import subprocess as _subprocess  # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))


class _FakeHandler:
    def __init__(self, body):
        raw = json.dumps(body).encode("utf-8")
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)


class _FakeTunnel:
    def __init__(self, room):
        self.room = room
        self.local_port = 34567
        self.stopped = False
        self.engine_target = None

    def set_engine_target(self, ip, port):
        self.engine_target = (ip, port)

    def stop(self):
        self.stopped = True


_real_popen = _subprocess.Popen
_real_host_argv, _real_join_argv = _m.host_argv, _m.join_argv
_real_fp, _real_cmp = _m._fingerprint_cached, _m.compare_fingerprint
_real_start_tunnel = W.start_tunnel

_argv_calls = []
_spawned = []


def _stub_host_argv(idx, port, **kw):
    _argv_calls.append(("host", idx, port, kw))
    return ["ZANDRA.EXE", "-port", str(port)]


def _stub_join_argv(idx, addr, **kw):
    _argv_calls.append(("join", idx, addr, kw))
    return ["ZANDRA.EXE", "+Connect", addr]


_created_tunnels = []


def _stub_start_tunnel(mode, room, relay_url=None):
    t = _FakeTunnel(room)
    _created_tunnels.append((mode, t))
    W.TUNNELS[mode] = t
    return t


resolve = lambda idx: {"label": "Stub"}

try:
    _subprocess.Popen = lambda argv, **kw: (_spawned.append(argv), None)[1]
    _m.host_argv = _stub_host_argv
    _m.join_argv = _stub_join_argv
    _m._fingerprint_cached = lambda idx: "STUBFING"
    _m.compare_fingerprint = lambda idx, given: (None, "STUBFING")
    W.start_tunnel = _stub_start_tunnel
    W.TUNNELS.clear()

    # ---- relay and stun together are refused
    status, body = H.host(_FakeHandler({"index": 0, "relay": True, "stun": True}), resolve)
    check("relay+stun together is refused with 400", status == 400, str(status))
    check("the refusal names the conflict", "alternatives" in (body.get("error") or ""), str(body))

    # ---- host with no room: one is generated, and the tunnel gets the real port
    status, body = H.host(_FakeHandler({"index": 0, "relay": True}), resolve)
    check("relay host path returns 200", status == 200, str(status))
    rp = body.get("relay") or {}
    check("relay host payload carries a room code", bool(rp.get("room")), str(rp))
    check("relay host payload has no ip:port (nothing routable to share)",
          "ip" not in rp and "connect" not in rp, str(rp))
    mode, tunnel = _created_tunnels[-1]
    check("relay host used a tunnel registered as host", mode == "host", mode)
    check("relay host set the engine target explicitly (no learning step)",
          tunnel.engine_target == ("127.0.0.1", 23513), str(tunnel.engine_target))
    check("relay host's argv used the real engine port, not the tunnel port",
          _argv_calls[-1][2] == 23513, str(_argv_calls[-1]))

    # ---- host with an explicit room: reused, not replaced
    status, body = H.host(_FakeHandler({"index": 0, "relay": True, "room": "myroom"}), resolve)
    check("relay host honours an explicitly supplied room",
          (body.get("relay") or {}).get("room") == "myroom", str(body.get("relay")))

    # ---- join with no room is refused
    status, body = H.join(_FakeHandler({"index": 0, "relay": True}), resolve)
    check("relay join with no room is refused with 400", status == 400, str(status))
    check("the refusal names what's missing", "room" in (body.get("error") or ""), str(body))

    # ---- join with a room: argv points at the tunnel's loopback port
    status, body = H.join(_FakeHandler({"index": 0, "relay": True, "room": "myroom"}), resolve)
    check("relay join path returns 200", status == 200, str(status))
    rp = body.get("relay") or {}
    check("relay join payload echoes the room", rp.get("room") == "myroom", str(rp))
    check("relay join payload gives the loopback connect address",
          rp.get("connect") == "127.0.0.1:34567", str(rp))
    check("relay join's argv pointed the engine at the tunnel's local port, not a real address",
          _argv_calls[-1][2] == "127.0.0.1:34567", str(_argv_calls[-1]))
    mode, tunnel = _created_tunnels[-1]
    check("relay join used a tunnel registered as join", mode == "join", mode)

    check("the stubbed launch for the last join carried the tunnel's loopback address",
          _spawned[-1][-1] == "127.0.0.1:34567", str(_spawned[-1]))
finally:
    _subprocess.Popen = _real_popen
    _m.host_argv, _m.join_argv = _real_host_argv, _real_join_argv
    _m._fingerprint_cached, _m.compare_fingerprint = _real_fp, _real_cmp
    W.start_tunnel = _real_start_tunnel
    W.TUNNELS.clear()

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
raise SystemExit(1 if FAIL else 0)
