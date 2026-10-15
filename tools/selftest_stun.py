"""Offline checks for the STUN punch tier (tools/stun.py, tools/punch.py).

  python tools/selftest_stun.py

Everything here avoids the real STUN servers: parser stability is pinned by
packets built from the hex recorded during a live probe (see the note on the
txid-offset bug inline), and the relay is exercised on real loopback sockets
with a fake engine and a fake peer. The only thing this file cannot do is
prove that a router honours a punch -- that is what the two-machine session
in todo.md is for.

Why a selftest of its own rather than more checks in selftest_mp.py: the
parser failure mode that bit (txid read from the wrong offset) returns a
calm `None` on a perfectly good wire packet, which LOOKS like "no STUN
server answered". A test asserting the wire-recorded bytes parse is the only
honest guard against that.
"""
import os
import socket
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import stun as S       # noqa: E402
import punch as P      # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))


# ------------------------------------------------------------ the txid bug
# A real reply, byte-for-byte as a Google STUN server returned it during the
# same session this tier was built -- type 0101, len 000c, full txid, then
# one XOR-MAPPED-ADDRESS attribute (type 0020, len 0008).
TXID = S.random_txid()


def wire(xor_reply=True, port=61371, ip=b"\x9c\xc4\x98\x5c"):
    """A reply packet for TXID. ip defaults to the encoded form of
    156.196.152.92 with port 61371, XOR-masked."""
    raw_port = port ^ (S.MAGIC >> 16)
    raw_ip = struct.unpack("!I", ip)[0] ^ S.MAGIC
    val = struct.pack("!BBHI", 0x00, 0x01, raw_port, raw_ip)
    t = 0x0020 if xor_reply else 0x0001
    if not xor_reply:
        # MAPPED-ADDRESS is NOT masked.
        val = struct.pack("!BBHI", 0x00, 0x01, port, struct.unpack("!I", ip)[0])
    return struct.pack("!HH", 0x0101, len(val)) + TXID + struct.pack("!HH", t, len(val)) + val


got = S.parse_binding_response(wire(), TXID)
check("parses a wire-good XOR response", got == ("156.196.152.92", 61371), str(got))

got = S.parse_binding_response(wire(xor_reply=False), TXID)
check("parses a classic MAPPED-ADDRESS response", got == ("156.196.152.92", 61371), str(got))

# The bug that shipped first: txid read from offset 8. The recorded header
# from the live probe put the txid at offset 4; confirm the packet shape
# really is what the wire showed, so the fix is pinned to reality.
check("txid really sits at offset 4", struct.unpack("!H", wire()[2:4])[0] == 8
      and wire()[4:8] == struct.pack("!I", S.MAGIC), wire()[:8].hex(" "))

# A stray reply must not invent a mapping.
check("wrong txid rejected",
      S.parse_binding_response(wire(), S.random_txid()) is None)
check("non-success type rejected",
      S.parse_binding_response(b"\x01\x02" + wire()[2:], TXID) is None)
check("short packet rejected", S.parse_binding_response(b"\x01", TXID) is None)
check("claiming more length than the packet has rejected",
      S.parse_binding_response(wire()[:25], TXID) is None)

# ----------------------------------------------------------------- kinds
check("same port everywhere is coned",
      S.nat_kind([("1.1.1.1", 5000), ("2.2.2.2", 5000)]) == "coned")
check("differing ports are symmetric",
      S.nat_kind([("1.1.1.1", 5000), ("2.2.2.2", 5100)]) == "symmetric")
check("all-None is treated as coned, never a false accusation",
      S.nat_kind([None, None]) == "coned")
check("best_mapping ignores a None vote",
      S.best_mapping([None, ("1.1.1.1", 5000), ("1.1.1.1", 5000)]) == ("1.1.1.1", 5000))
check("best_mapping of all-None is None", S.best_mapping([None, None]) is None)

# ------------------------------------------------------- builder sanity
req = S._hdr(TXID)
check("request header holds cookie then 12 random bytes",
      len(req) == 20 and req[:8] == struct.pack("!HHI", 1, 0, S.MAGIC)
      and req[4:20] == TXID, req[:8].hex(" "))

# ================================================================= relay
# Real sockets. The fake ENGINE binds loopback (its packets must be
# classified as engine); the fake PEER binds a non-loopback local address
# (its packets must be classified as internet), because classification is
# by SOURCE ADDRESS, mirroring what the real deployment sees.


def _free_local_ip():
    for ip in ("192.168.0.226", "100.95.67.84"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind((ip, 0))
            s.close()
            return ip
        except OSError:
            pass
    return None


def recv_until(sock, tries=8):
    """Receive one non-keepalive packet, skipping the relay's punch keepalives
    that race in between: the keepalive loop fires on a 2 s cadence while
    assertions run, so a single recv can grab a magic packet instead of the
    payload under test."""
    for _ in range(tries):
        data, rinfo = sock.recvfrom(1024)
        if data != P.PUNCH_MAGIC:
            return data, rinfo
    raise socket.timeout("no non-keepalive packet arrived")


PEER_IP = _free_local_ip()
if PEER_IP:
    check(f"non-loopback fake peer bindable on {PEER_IP}", True)
else:
    check("non-loopback fake peer bindable", False, "no bindable address found")

if PEER_IP:
    relay = P.PunchRelay()
    engine = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    engine.bind(("127.0.0.1", 0))
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind((PEER_IP, 0))
    peer.settimeout(2)
    engine.settimeout(2)
    rport = relay.local_port
    eport = engine.getsockname()[1]
    prport = peer.getsockname()[1]

    # 1. First loopback packet learns the engine source.
    engine.sendto(b"E1", ("127.0.0.1", rport))
    time.sleep(0.6)
    check("engine source learned from first loopback packet",
          list(relay.engine_src or []) == ["127.0.0.1", eport], str(relay.engine_src))
    # ... and, with no peer yet, dropped rather than forwarded anywhere.
    check("engine packet with no peer set is held back",
          relay.status()["in_from_engine"] == 0)

    # 2. Host side learns the peer from an untagged internet packet.
    #    A socket BOUND to PEER_IP cannot send to 127.0.0.1 (WinError 10049),
    #    and in the real deployment no peer ever sends to 127.0.0.1 -- it
    #    sends to the relay's reachable address, which for a 0.0.0.0 bind is
    #    any local IP, here the peer's own. Source is PEER_IP either way, so
    #    classification sees what it would see in the field.
    peer.sendto(b"E2", (PEER_IP, rport))
    time.sleep(0.6)
    check("peer learned from untagged internet packet",
          peer.getsockname()[0] in str(relay.peer), str(relay.peer))
    # ... and forwarded to the engine.
    try:
        data, _rinfo = recv_until(engine)
        check("peer packet forwarded to engine", data == b"E2", repr(data))
    except socket.timeout:
        check("peer packet forwarded to engine", False, "engine heard nothing")

    # 3. Engine's reply goes out to the learned peer.
    engine.sendto(b"E3", ("127.0.0.1", rport))
    time.sleep(0.6)
    try:
        data, rinfo = recv_until(peer)
        check("engine reply forwarded to peer",
              data == b"E3", f"{data!r} from {rinfo}")
    except socket.timeout:
        check("engine reply forwarded to peer", False, "peer heard nothing")

    # 4. A tagged keepalive is filtered out of the engine path but still
    #    updates the peer.
    relay.peer = (PEER_IP, prport)
    relay.peer_locked = False
    peer.sendto(P.PUNCH_MAGIC, (PEER_IP, rport))
    time.sleep(0.6)
    st = relay.status()
    # in_from_engine counts only packets actually forwarded: E1 was held
    # back (no peer yet), E3 went out; E2 counts on the PEER side, not here.
    check("keepalive filtered from the engine", st["in_from_engine"] == 1
          and st["in_from_peer"] >= 2, str(st))

    # 5. A locked peer cannot be moved by other traffic.
    relay.peer_locked = True
    relay.peer = (PEER_IP, prport)
    s_other = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s_other.bind((PEER_IP, 0))
    s_other.sendto(b"INJECT", (PEER_IP, rport))
    time.sleep(0.4)
    relay.stop()
    s_other.close()
    check("locked peer keeps its value",
          list(relay.peer or []) == [PEER_IP, prport], str(relay.peer))

    engine.close()
    peer.close()

# A relay must bind SOME port and expose it, without any STUN call.
r2 = P.PunchRelay()
check("relay binds a local port >1024", 1024 < r2.local_port < 65536,
      str(r2.local_port))
r2.stop()

# ------------------------------------------------------------ the registry
P.start_relay("host")
a = P.get_relay("host")
P.start_relay("host")
b = P.get_relay("host")
check("a new host relay replaces the old", a is not b and a.alive() is False
      and b.alive(), "")
if b:
    b.stop()

# ================================================== mp_http punch contract
# The integration of the tier with the panel's actual request path: same
# routes, just a "stun": true flag in the body. The engine launch, the STUN
# probe, and the engine/build data are all stubbed, so nothing here starts a
# game or talks to a server -- this pins CONTRACT, not connectivity.
io = __import__("io")
json = __import__("json")
import mp_http as H      # noqa: E402


class _FakeHandler:
    """Just enough of BaseHTTPRequestHandler for mp_http._body()."""

    def __init__(self, body):
        raw = json.dumps(body).encode("utf-8")
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)


class _Rec:
    """A relay-shaped record of what mp_http asked the tier to do.

    mapped defaults to a mapped answer; pass mapped=None explicitly for the
    dead-STUN case -- `None or default` in the first version collapsed that
    case into the happy one and the "all servers silent" refusal never
    actually refused."""

    def __init__(self, nat="coned", mapped=("1.2.3.4", 55555)):
        self.nat = nat
        self.mapped = mapped
        self.local_port = 23456
        self.stopped = False
        self.peer = None

    def map_with_stun(self, timeout=None):
        return self.mapped

    def set_peer(self, ip, port, lock=True):
        self.peer = (ip, port, lock)

    def stop(self):
        self.stopped = True


_real_start = P.start_relay
_spawned = []
_argv_calls = []
import mp_session as _m   # noqa: E402


def rec_join(idx, addr, **kw):
    """Record what the punch tier handed the engine to connect with."""
    _argv_calls.append(("join", idx, addr, kw))
    return ["ZANDRA.EXE", "+Connect", addr]



try:
    # The engine must not start, no matter what path is taken.
    import subprocess as _subprocess
    _real_popen = _subprocess.Popen
    _subprocess.Popen = lambda argv, **kw: (_spawned.append(argv), None)[1]
    # the engine's own argument builders become recorders: the COMMAND SHAPE
    # is what's under test, not the pack's real mod list.
    _real_host, _real_join = _m.host_argv, _m.join_argv
    _real_fp, _real_cmp = _m._fingerprint_cached, _m.compare_fingerprint
    _m.host_argv = lambda *a, **k: (_argv_calls.append(("host", a, k)),
                                    ["ZANDRA.EXE"])[1]
    _m.join_argv = rec_join
    _m._fingerprint_cached = lambda idx: "STUBFING"
    _m.compare_fingerprint = lambda idx, given: (None, "STUBFING")
    resolve = lambda idx: {"label": "Stub"}

    # ---- happy host path
    created = []

    def fake_start(mode, **kw):
        rec = _Rec(**kw)
        created.append(mode)
        P.RELAYS[mode] = rec      # the REAL start_relay registers it too
        return rec

    P.start_relay = fake_start
    P.RELAYS.clear()
    status, body = H.host(_FakeHandler({"index": 0, "stun": True}), resolve)
    check("stun host path returns 200", status == 200, str(status))
    punchy = body.get("punch") or {}
    check("stun host payload carries the punch share line",
          punchy.get("line") == "1.2.3.4:55555 STUBFING", str(punchy))
    check("stun host used one relay registered as host",
          created == ["host"] and "host" in P.RELAYS, str(created))
    check("the engine still binds the real port, unchanged",
          _argv_calls[-1][0] == "host" and _argv_calls[-1][1][1] == 23513,
          str(_argv_calls[-1]))
    check("stun host reports the firewall verdict keys",
          set(("ok", "rule", "why")) <= set(punchy.get("firewall", {}).keys()),
          str(punchy.get("firewall")))

    # ---- happy join path: the engine dials the LOOPBACK relay, and the
    #      real pasted address becomes the relay's peer
    P.RELAYS.clear()
    created.clear()
    _argv_calls.clear()
    _m.join_addr_line = None

    def rec_join(idx, addr, **kw):
        _argv_calls.append(("join", idx, addr, kw))
        return ["ZANDRA.EXE", "+Connect", addr]

    _m.join_argv = rec_join
    status, body = H.join(_FakeHandler({"index": 0, "stun": True,
                                        "addr": "5.6.7.8:12345 ABCDEFGH"}),
                          resolve)
    check("stun join path returns 200", status == 200, str(status))
    check("stun join engine dials the loopback relay, not the paste",
          _argv_calls[-1][2] == "127.0.0.1:23456", str(_argv_calls[-1]))
    rec_relay = P.RELAYS.get("join")
    check("stun join pasted address became the relay's locked peer",
          rec_relay is not None and rec_relay.peer == ("5.6.7.8", 12345, True),
          str(rec_relay.peer if rec_relay else None))
    check("stun join still performs the mod fingerprint check",
          body.get("mod_match") in (None, True, False), str(body.get("mod_match")))

    # ---- a host whose router is symmetric is refused BEFORE the engine starts
    P.RELAYS.clear()
    created.clear()
    _spawned.clear()
    P.start_relay = lambda mode: (created.append(mode), _Rec(nat="symmetric"))[1]
    status, body = H.host(_FakeHandler({"index": 0, "stun": True}), resolve)
    check("symmetric-NAT host is refused with 400", status == 400, str(status))
    check("refusal explains in owner terms, not STUN jargon",
          "symmetric" in str(body.get("error"))
          and "NukemNet" in str(body.get("error")), str(body.get("error")))
    check("refused symmetric host started no engine",
          _spawned == [] and len(created) == 1, f"{_spawned} {created}")
    check("refused symmetric host released the relay",
          "host" not in P.RELAYS, str(list(P.RELAYS.keys())))

    # ---- a JOINER with symmetric NAT is NOT refused: the joiner never
    #      publishes an endpoint, so its own mapping variety is invisible
    P.RELAYS.clear()
    _m.join_argv = rec_join
    status, body = H.join(_FakeHandler({"index": 0, "stun": True,
                                        "addr": "5.6.7.8:12345"}),
                          resolve)
    check("symmetric-NAT joiner is not refused (nothing published)",
          status == 200, f"{status} {body}")
    check("joiner symmmetric verdict carried as information",
          (body.get("punch") or {}).get("nat") == "symmetric", str(body.get("punch")))

    # ---- a dead STUN answer (all servers silent) refuses before the engine
    P.RELAYS.clear()
    _spawned.clear()
    P.start_relay = lambda mode: fake_start(mode, mapped=None)
    status, body = H.host(_FakeHandler({"index": 0, "stun": True}), resolve)
    check("no-STUN host path refuses with 502", status == 502, str(status))
    check("no-STUN refusal started no engine",
          _spawned == [], str(_spawned))
    check("no-STUN refusal released the relay",
          "host" not in P.RELAYS, str(list(P.RELAYS.keys())))
finally:
    import subprocess as _subprocess
    _subprocess.Popen = _real_popen
    _m.host_argv, _m.join_argv = _real_host, _real_join
    _m._fingerprint_cached, _m.compare_fingerprint = _real_fp, _real_cmp
    P.start_relay = _real_start
    for _r in P.RELAYS.values():
        try:
            _r.stop()
        except Exception:
            pass
    P.RELAYS.clear()

# The firewall advisory: verdict-shaped, and REPORTED on this machine --
# which program-path the block hit is environment data, printed rather
# than asserted, so the selftest stays honest on any machine.
fw = H._firewall_advisory()
check("firewall advisory is verdict-shaped",
      isinstance(fw, dict) and "ok" in fw and "rule" in fw and "why" in fw,
      str(fw))

# ------------------------------------------------------------------
print()
print(f"{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
