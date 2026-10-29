"""Live check against the DEPLOYED relay Worker (needs internet + the Worker
to be up) -- the one thing selftest_wsrelay.py's fake local server cannot
prove: that two independent RelayTunnel instances, each opening their own
real wss:// connection to Cloudflare, actually get relayed to each other
through the live Durable Object room. Same role as selftest_live.py plays
for the pack's other live-network checks: run by hand, not part of the
pure-offline suite.

    python tools/selftest_wsrelay_live.py
"""
import socket
import time
import uuid

import wsrelay

PASS, FAIL = 0, 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name} {detail}")


room = f"selftest-{uuid.uuid4().hex[:8]}"
print(f"room: {room}  relay: {wsrelay.DEFAULT_RELAY_URL}")

host_tunnel = wsrelay.RelayTunnel(room)
join_tunnel = wsrelay.RelayTunnel(room)

host_engine = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
host_engine.bind(("127.0.0.1", 0))
host_engine.settimeout(8.0)
host_tunnel.set_engine_target("127.0.0.1", host_engine.getsockname()[1])

join_engine = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
join_engine.bind(("127.0.0.1", 0))
join_engine.settimeout(8.0)

deadline = time.time() + 10.0
while (not host_tunnel.connected or not join_tunnel.connected) and time.time() < deadline:
    time.sleep(0.1)

check("host tunnel connected to the live Worker", host_tunnel.connected, host_tunnel.last_error or "")
check("join tunnel connected to the live Worker", join_tunnel.connected, join_tunnel.last_error or "")

# join -> host, through the real Durable Object room
join_engine.sendto(b"join-says-hi", ("127.0.0.1", join_tunnel.local_port))
try:
    data, _ = host_engine.recvfrom(4096)
except socket.timeout:
    data = None
check("a packet from the join side reaches the host's engine socket, via Cloudflare",
      data == b"join-says-hi", f"got {data!r}")

# host -> join, the other direction
host_engine.sendto(b"host-says-hi", ("127.0.0.1", host_tunnel.local_port))
try:
    data, _ = join_engine.recvfrom(4096)
except socket.timeout:
    data = None
check("a packet from the host reaches the join side's engine socket, via Cloudflare",
      data == b"host-says-hi", f"got {data!r}")

host_engine.close()
join_engine.close()
host_tunnel.stop()
join_tunnel.stop()

print(f"\n{PASS} passed, {FAIL} failed")
raise SystemExit(1 if FAIL else 0)
