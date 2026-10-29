"""The relay tunnel: a UDP proxy between the engine and a Cloudflare Worker.

punch.py's PunchRelay is tier 4 of the ladder (STUN hole-punch) and tier 5
is NN's own relay, which §6 of todo.md ruled out as a DoomNite dependency
("someone else's bandwidth and ops bill"). This module is the same idea --
host and joiner each tunnel the engine's raw UDP through a central relay --
but running DoomNite's *own* Worker (cloudflare/relay/), so it is no longer
someone else's infrastructure. This is the trick that already works for
SkyJump3D (cloudflare/worker.js's `Room` Durable Object, same account):
both sides connect OUTBOUND to the same public wss:// endpoint, so neither
one needs a port forward, UPnP, or to survive NAT hole-punching at all --
the thing that was failing for the mate (symmetric NAT, or a firewall that
eats the STUN-punched path) simply cannot happen here.

The cost, same as any relay: traffic makes a round trip through Cloudflare's
network instead of a direct path, so this is deliberately NOT the first
thing tried -- see mp_http.py, which offers it as its own flag ("relay":
true) alongside "stun": true, not as an automatic fallback, so the choice
of who pays the extra latency is the host's, not silently decided for them.

Zandronum shape (mirrors punch.py's PunchRelay exactly, so mp_http.py's
wiring is almost a copy-paste of the STUN branch):

  HOST: engine listens on 127.0.0.1:23513. start_tunnel() opens a local UDP
  socket AND a websocket to wss://<relay host>/relay?room=<code>. The host
  shares the room code (not an IP:port -- there is nothing routable to
  share). Packets from the engine go out over the websocket; packets that
  arrive over the websocket go to the engine's loopback source.

  JOINER: engine connects to 127.0.0.1:<tunnel port> -- same as the STUN
  tier, the join side never touches a real address. Same room code opens
  the second (and only other) seat in that Durable Object room.

No STUN probe, no NAT classification, no keepalive-to-punch-a-hole: the
Worker already relays, so there is nothing to punch. The only "keepalive"
here is a short idle timeout on the Worker side (cloudflare/relay/worker.js)
that closes a room nobody is sending bytes through, so a crashed bridge
does not pin a Durable Object open forever.

Pure stdlib. This project ships without a Python package manager step
(see todo.md's "pack should be usable without npm"), so the websocket
client here is hand-rolled RFC 6455 -- a small, well-known protocol --
rather than a pip dependency the pack would need to vendor.
"""
from __future__ import annotations

import base64
import hashlib
import os
import socket
import ssl
import struct
import threading
import time
from urllib.parse import urlsplit

# Deployed 2026-10-29 (`cd cloudflare/relay && npx wrangler deploy`,
# account Chimske@gmail.com, version 5f27b9d4). Override with the
# DOOMNITE_RELAY_URL env var if it ever moves to a custom route.
DEFAULT_RELAY_URL = os.environ.get("DOOMNITE_RELAY_URL", "wss://doomnite-relay.chimske.workers.dev/relay")

MAX_FRAME = 65535          # Zandronum packets are well under this (~1400B typical)
IDLE_PING_INTERVAL = 20.0  # keep Cloudflare's own idle timeout from closing us
RATE_IDLE_STOP = 15 * 60   # no engine traffic in 15 minutes -> give up the socket


def _is_loopback(ip: str) -> bool:
    return (ip or "").startswith("127.")


def _ca_bundle() -> str | None:
    """None (system default) unless `certifi` happens to be installed, in
    which case prefer its bundle: Windows Python's own default CA file can
    be stale enough to reject a perfectly live Cloudflare cert as expired
    (hit during development on this machine, 2026-10-29 -- curl on the same
    box, using the OS store, verified the same cert fine). Not a hard
    dependency -- this pack still runs with nothing installed, same as
    everywhere else; it is just worse off on whichever machines hit the
    stale-store bug."""
    try:
        import certifi
        return certifi.where()
    except ImportError:
        return None


class _WebSocketClient:
    """The minimal RFC 6455 client this needs: connect, send one binary
    frame, receive one frame. No fragmentation support (Cloudflare does not
    fragment payloads this small), no permessage-deflate (never offered)."""

    def __init__(self, url: str, timeout: float = 10.0):
        parts = urlsplit(url)
        if parts.scheme not in ("ws", "wss"):
            raise ValueError(f"not a ws(s):// url: {url!r}")
        host = parts.hostname
        port = parts.port or (443 if parts.scheme == "wss" else 80)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query

        raw = socket.create_connection((host, port), timeout=timeout)
        if parts.scheme == "wss":
            ctx = ssl.create_default_context(cafile=_ca_bundle())
            self.sock = ctx.wrap_socket(raw, server_hostname=host)
        else:
            self.sock = raw
        self.sock.settimeout(timeout)

        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(req.encode("ascii"))

        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("relay closed during handshake")
            resp += chunk
        head, _, rest = resp.partition(b"\r\n\r\n")
        status_line = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status_line:
            raise ConnectionError(f"relay handshake failed: {status_line!r}")
        expect = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()
        if expect.encode() not in head:
            raise ConnectionError("relay handshake: bad Sec-WebSocket-Accept")

        self._leftover = rest  # bytes already read past the HTTP headers
        self.sock.settimeout(0.5)

    def send_binary(self, data: bytes) -> None:
        self._send_frame(0x2, data)

    def send_close(self) -> None:
        try:
            self._send_frame(0x8, b"")
        except OSError:
            pass

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        header = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack("!H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", n)
        self.sock.sendall(bytes(header) + mask + masked)

    def recv(self) -> tuple[int, bytes] | None:
        """(opcode, payload), or None on a read timeout. Raises on a closed
        or broken socket."""
        header = self._read_exact(2)
        if header is None:
            return None
        b0, b1 = header[0], header[1]
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2, block=True))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8, block=True))[0]
        mask_key = self._read_exact(4, block=True) if masked else None
        payload = self._read_exact(length, block=True) if length else b""
        if masked and payload:
            payload = bytes(c ^ mask_key[i % 4] for i, c in enumerate(payload))
        return opcode, payload

    def _read_exact(self, n: int, block: bool = False) -> bytes | None:
        buf = bytearray()
        if self._leftover:
            take = self._leftover[:n]
            self._leftover = self._leftover[len(take):]
            buf += take
        while len(buf) < n:
            try:
                chunk = self.sock.recv(n - len(buf))
            except socket.timeout:
                if block and buf:
                    continue
                if not buf:
                    return None
                continue
            if not chunk:
                raise ConnectionError("relay connection closed")
            buf += chunk
        return bytes(buf)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class RelayTunnel:
    """One room-relayed UDP path for one game. Same external shape as
    punch.py's PunchRelay (local_port / status() / stop() / alive()), so
    mp_http.py's STUN branch and this one wire up the same way."""

    def __init__(self, room: str, relay_url: str = DEFAULT_RELAY_URL, local_port: int | None = None):
        self.room = room
        self.relay_url = relay_url.rstrip("/") + f"?room={room}"

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", local_port or 0))
        self.local_port = self.sock.getsockname()[1]
        self.created = time.time()

        self.engine_src: tuple[str, int] | None = None
        self.connected = False
        self.last_error: str | None = None

        self.snapshot = {"in_from_engine": 0, "in_from_relay": 0, "reconnects": 0}
        self._stop = threading.Event()
        self._ws: _WebSocketClient | None = None
        self._ws_lock = threading.Lock()

        self._threads = [
            threading.Thread(target=self._udp_loop, daemon=True),
            threading.Thread(target=self._ws_loop, daemon=True),
        ]
        for t in self._threads:
            t.start()

    # ------------------------------------------------------------------ api
    def set_engine_target(self, ip: str, port: int) -> None:
        """Host side only: punch.py's PunchRelay *learns* the engine's
        loopback source from its first reply, which only works because
        something has already made the engine speak to the relay socket
        first. This tunnel does not assume that chicken-and-egg path
        exists -- the host's engine port is already known (mp_http.py
        passes it to host_argv()), so mp_http.py sets it here explicitly
        and the first relayed packet goes straight to the real engine
        instead of waiting on a loopback packet that may never come."""
        self.engine_src = (ip, int(port))

    def status(self) -> dict:
        return {
            "room": self.room,
            "local_port": self.local_port,
            "connected": self.connected,
            "engine_src": list(self.engine_src) if self.engine_src else None,
            "age_s": int(time.time() - self.created),
            "last_error": self.last_error,
            **self.snapshot,
        }

    def stop(self) -> None:
        self._stop.set()
        with self._ws_lock:
            if self._ws:
                self._ws.send_close()
                self._ws.close()
        try:
            self.sock.close()
        except OSError:
            pass

    def alive(self) -> bool:
        return not self._stop.is_set()

    # --------------------------------------------------------------- engine
    def _udp_loop(self) -> None:
        """Engine -> relay. Learns the engine's loopback source the same way
        PunchRelay does: whichever loopback sender speaks first."""
        self.sock.settimeout(0.5)
        last_traffic = time.time()
        while not self._stop.is_set():
            try:
                data, src = self.sock.recvfrom(MAX_FRAME)
            except socket.timeout:
                if time.time() - last_traffic > RATE_IDLE_STOP:
                    self.stop()
                continue
            except OSError:
                return
            if not _is_loopback(src[0]):
                continue  # this socket only ever talks to the local engine
            if self.engine_src is None:
                self.engine_src = src
            if self.engine_src != src:
                continue
            last_traffic = time.time()
            self.snapshot["in_from_engine"] += 1
            with self._ws_lock:
                ws = self._ws
            if ws is not None:
                try:
                    ws.send_binary(data)
                except OSError:
                    pass

    # ------------------------------------------------------------- relay ws
    def _ws_loop(self) -> None:
        """Relay -> engine, with reconnect: a Worker-side idle close or a
        network blip should not permanently kill the tunnel while the UI
        still thinks it is live."""
        backoff = 1.0
        while not self._stop.is_set():
            try:
                ws = _WebSocketClient(self.relay_url)
            except Exception as exc:  # noqa: BLE001 - surfaced via status()
                self.last_error = str(exc)
                self.connected = False
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 15.0)
                continue

            with self._ws_lock:
                self._ws = ws
            self.connected = True
            self.last_error = None
            backoff = 1.0
            self.snapshot["reconnects"] += 1 if self.snapshot["in_from_engine"] else 0

            try:
                while not self._stop.is_set():
                    frame = ws.recv()
                    if frame is None:
                        continue
                    opcode, payload = frame
                    if opcode == 0x8:  # close
                        break
                    if opcode != 0x2:  # only binary game data is ever forwarded
                        continue
                    self.snapshot["in_from_relay"] += 1
                    if self.engine_src:
                        try:
                            self.sock.sendto(payload, self.engine_src)
                        except OSError:
                            pass
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
            finally:
                self.connected = False
                with self._ws_lock:
                    if self._ws is ws:
                        self._ws = None
                ws.close()
            if not self._stop.is_set():
                self._stop.wait(backoff)


# --------------------------------------------------------------- registry
# Same shape as punch.py's RELAYS: one tunnel per mode at a time, a fresh
# host/relay request replaces (and stops) the old one.
TUNNELS: dict[str, RelayTunnel] = {}


def get_tunnel(mode: str) -> RelayTunnel | None:
    return TUNNELS.get(mode)


def start_tunnel(mode: str, room: str, relay_url: str = DEFAULT_RELAY_URL) -> RelayTunnel:
    old = TUNNELS.pop(mode, None)
    if old:
        old.stop()
    t = RelayTunnel(room, relay_url)
    TUNNELS[mode] = t
    return t
