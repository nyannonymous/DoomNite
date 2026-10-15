"""The punching relay: a UDP proxy between the engine and the punched path.

Every STUN design since Skype needs the same three parts, and NukemNet's
implementation (read from its source and recorded in todo.md, 2026-10-15) is
no exception:

  1. a UDP socket whose NAT mapping the two peers have traded (the punch
     socket -- it MUST be the socket STUN was asked about, or the published
     mapping is a lie);
  2. keepalive packets across that socket every few seconds, so the NAT
     mapping is still alive when the real traffic arrives;
  3. a bidirectional relay: the engine talks to an address that is DERIVED
     from the punch socket, so packets in and out always travel the same
     punched path.

The Zandronum shape of it, host and join in one design:

  HOST: engine listens on 127.0.0.1:23513. The relay's socket is bound on a
  private port; the joiner sends game packets to the relay's PUBLISHED
  external endpoint. Packets arriving from the internet are relayed to the
  local engine, the engine's replies are relayed back out -- both through
  the one punched socket, so the path stays the path.

  JOINER: engine connects to 127.0.0.1:<relay port> -- the join side never
  connects to the real host address at all, so nothing has to be routed.
  The relay forwards those packets to the host's published endpoint and
  sends keepalives from the SAME socket, which is what opens the joiner's
  inbound path to the host's replies.

One line exchange. The JOINER needs the host's published endpoint in the
share line (it already has one: the panel's address field). The HOST needs
nothing but the inbound traffic, and learns the joiner's endpoint from the
first packet that arrives -- its NAT is held open against that peer by the
keepalive loop, and cone/restricted behaviour accepts the return traffic
because the host replies from a socket the peer has already spoken to.

Symmetric NAT is refused upstream (mp_http), because there the published
endpoint is a lie for everyone but the STUN server.

Keepalive packets are tagged (PUNCH_MAGIC) and never forwarded to the
engine: the joiner's punches arrive at the HOST relay, which would otherwise
hand Zandronum garbage. Zandronum ignores most junk, but filtering is free
and letting the engine see fight traffic from a scanner is nobody's idea of
friendship.
"""
from __future__ import annotations

import socket
import threading
import time

import stun

# Keepalives carry this prefix. Both ends run this module, so this is
# private convention, not a protocol.
PUNCH_MAGIC = b"DNPUNCH1"
PUNCH_INTERVAL = 2.0          # while waiting for the first sign of the peer
PUNCH_INTERVAL_SLOW = 10.0    # after traffic has flowed both ways
RATE_IDLE_STOP = 15 * 60      # no peer set in 15 minutes -> give up the socket


def _is_loopback(ip: str) -> bool:
    """True for 127.*: engine traffic always originates on loopback."""
    return (ip or "").startswith("127.")


class PunchRelay:
    """One punched UDP path for one game, both host and joiner share this."""

    def __init__(self, punch_port: int | None = None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", punch_port or 0))
        self.local_port = self.sock.getsockname()[1]
        self.created = time.time()

        # The peer's published endpoint. None until set_peer() (join side)
        # or until the first inbound packet (host side).
        self.peer: tuple[str, int] | None = None
        self.peer_locked = False   # True once learned from traffic or pasted

        # Which loopback source the ENGINE sends from. Known for the host
        # (the engine port is fixed) but unknowable for a joiner before its
        # first packet, so it is LEARNED from the first loopback sender.
        self.engine_src: tuple[str, int] | None = None

        # After the mapping, the published external ip:port for this socket.
        self.mapped: tuple[str, int] | None = None
        self.nat: str | None = None

        self.snapshot = {"in_from_engine": 0, "in_from_peer": 0,
                         "keepalives_sent": 0, "forwarded_bad": 0}
        self._stop = threading.Event()
        self._threads = [threading.Thread(target=self._serve, daemon=True),
                         threading.Thread(target=self._keepalive, daemon=True)]
        for t in self._threads:
            t.start()

    # ------------------------------------------------------------- probing
    def map_with_stun(self, timeout: float = stun.DEFAULT_TIMEOUT) -> tuple[str, int] | None:
        """Ask STUN about THIS socket, in place. Called exactly once, before
        the engine starts, because the answer must be published as the share
        line and then never change."""
        results = [m for _srv, m in stun.probe(self.sock, timeout=timeout)]
        self.mapped = stun.best_mapping(results)
        self.nat = stun.nat_kind(results)
        return self.mapped

    # ------------------------------------------------------------- wiring
    def set_peer(self, ip: str, port: int, lock: bool = True) -> None:
        """The host's published endpoint (join side), or a host locking the
        peer explicitly. `lock` prevents later traffic from MOVING a peer
        the user deliberately gave us."""
        self.peer = (ip, int(port))
        self.peer_locked = bool(lock)

    def status(self) -> dict:
        return {
            "local_port": self.local_port,
            "mapped": list(self.mapped) if self.mapped else None,
            "nat": self.nat,
            "peer": list(self.peer) if self.peer else None,
            "engine_src": list(self.engine_src) if self.engine_src else None,
            "age_s": int(time.time() - self.created),
            **self.snapshot,
        }

    def stop(self) -> None:
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass

    def alive(self) -> bool:
        return not self._stop.is_set()

    # ------------------------------------------------------------ threads
    def _serve(self) -> None:
        """The one loop that both directions pass through."""
        self.sock.settimeout(0.5)
        while not self._stop.is_set():
            try:
                data, src = self.sock.recvfrom(65535)
            except socket.timeout:
                # Idle guard: a relay with no peer set for 15 minutes is a
                # socket somebody forgot; drop it and let the UI's next
                # setup make a fresh one.
                if self.peer is None and time.time() - self.created > RATE_IDLE_STOP:
                    self.stop()
                continue
            except OSError:
                return
            self._classify(data, src)

    def _classify(self, data: bytes, src: tuple[str, int]) -> None:
        """One received packet: punch, engine, or peer. The rules:

        * from the loopback engine (after learning its source): forward to
          the peer, if the peer is known.
        * from the loopback (before the first loopback packet): learn that
          this is the engine's source.
        * tagged keepalive: learn the sender as the peer, never forward.
        * from the internet (non-loopback), untagged: (host) learn the peer
          if unlocked, and forward to the engine. (Joiner) forward ONLY if
          the sender is the peer we were given -- a joiner should not accept
          game packets from strangers.
        """
        # ---- keepalive from the internet? Learn, drop the payload.
        if data.startswith(PUNCH_MAGIC) and not _is_loopback(src[0]):
            self._learn_peer(src)
            self.snapshot["in_from_peer"] += 1
            return

        # ---- from the engine (or the first loopback sender, who IS it)
        if _is_loopback(src[0]):
            if self.engine_src is None:
                self.engine_src = src
            if self.engine_src != src:
                # Loopback sender that is neither the engine nor us: ignore,
                # it is more likely another UI probe than a second enemy.
                self.snapshot["forwarded_bad"] += 1
                return
            if self.peer:
                try:
                    self.sock.sendto(data, self.peer)
                except OSError:
                    pass
                self.snapshot["in_from_engine"] += 1
            return

        # ---- from the internet
        allowed = (self.peer is None) or (src == self.peer) or not self.peer_locked
        if not allowed:
            self.snapshot["forwarded_bad"] += 1
            return
        self._learn_peer(src)
        self.snapshot["in_from_peer"] += 1
        if self.engine_src:
            try:
                self.sock.sendto(data, self.engine_src if isinstance(self.engine_src, tuple) else tuple(self.engine_src))
            except OSError:
                pass

    def _learn_peer(self, src: tuple[str, int]) -> None:
        if self.peer_locked and self.peer == src:
            return
        if self.peer_locked and self.peer is not None and self.peer != src:
            return  # the user gave a peer; traffic cannot change it
        if self.peer != src:
            self.peer = src
            self.peer_locked = True   # learned-from-traffic counts as locked

    def _keepalive(self) -> None:
        """Punch until the peer exists, then slow down; publish nothing."""
        while not self._stop.is_set():
            if self.peer:
                try:
                    self.sock.sendto(PUNCH_MAGIC, self.peer)
                except OSError:
                    pass
                self.snapshot["keepalives_sent"] += 1
            if self.snapshot["in_from_peer"]:
                wait = PUNCH_INTERVAL_SLOW
            elif self.peer:
                wait = PUNCH_INTERVAL
            else:
                wait = PUNCH_INTERVAL
            self._stop.wait(wait)


# --------------------------------------------------------------- registry
# mp_http holds one relay per mode at a time; a fresh host/STUN join request
# replaces the old one. Keyed by mode, not per request, because the share
# line the user already handed out names THIS socket's mapping -- replacing
# the relay under an already-shared line orphans it silently.
RELAYS: dict[str, PunchRelay] = {}


def get_relay(mode: str) -> PunchRelay | None:
    return RELAYS.get(mode)


def start_relay(mode: str) -> PunchRelay:
    old = RELAYS.pop(mode, None)
    if old:
        old.stop()
    r = PunchRelay()
    RELAYS[mode] = r
    return r
