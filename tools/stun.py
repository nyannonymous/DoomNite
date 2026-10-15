"""A minimal STUN client (one RFC 5389 binding request), no dependencies.

WHY THIS EXISTS
---------------
The multiplayer panel's Host/Join flow only ever worked for players on the
same network (or on a VPN). Out in the internet, 2 of the observable address
sharing has exactly two outcomes: a LAN address that can never reach a remote
peer, or a public address that needs a router forward. The owner's premise for
this feature was that NukemNet plays over the internet with no VPN and no
router config, and reading NN's source proved the mechanism: a STUN
hole-punch, with the mapped ip:port published to the other side.

This file is the measurement half of that: bind a UDP socket, ask public STUN
servers "what do YOU see for this socket", and report the best answer. The
punch itself (keeping the mapping alive and relaying engine traffic through
it) lives in tools/punch.py; this file never forwards game traffic.

WHAT NUKEMNET DOES DIFFERENTLY (recorded so the next reader does not
"improve" this into something worse): NN binds a whole 10000-20000 port range
and probes a shuffled pool of servers, and coordinates endpoints over its IRC
channel with handshake confirmation before handing the game a localhost
tunnel. DoomNite's version is deliberately simpler: this pack already has a
rendezvous in the UI (the user pastes a share line), so no signalling server
is needed, and the mapped port is published rather than kept secret.

RFC notes, because the details are where this goes wrong:
  * We SEND the RFC 5389 form: one 20-byte header whose transaction id starts
    with the magic cookie 0x2112A442, followed by 12 random bytes. Classic
    RFC 3489 servers echo the transaction id verbatim and answer with
    MAPPED-ADDRESS; RFC 5389 servers answer with XOR-MAPPED-ADDRESS. Both
    response types are parsed, XOR first because it survives NATs that
    translate the payload too.
  * Nothing here opens a second port, changes router state, or sends packets
    to anything except the STUN servers named in SERVERS.
"""
from __future__ import annotations

import os
import socket
import struct

# The two request/response shapes we speak.
MAGIC = 0x2112A442
BINDING_REQUEST = 0x0001
MAPPED_ADDRESS = 0x0001
XOR_MAPPED_ADDRESS = 0x0020

# Public, keys-free STUN services. Order is not load-bearing; the probe
# shuffles a copy so a dead first entry does not always cost the timeout.
# Two distinct servers are the minimum, because symmetric-NAT detection
# compares the port TWO peers would see.
SERVERS = (
    ("stun.l.google.com", 19302),
    ("stun1.l.google.com", 19302),
    ("stun.cloudflare.com", 3478),
    ("stun.nextcloud.com", 3478),
)

DEFAULT_TIMEOUT = 1.5


def _hdr(txid: bytes) -> bytes:
    """A binding request carrying `txid` (16 bytes, cookie already inside)."""
    return struct.pack("!HHI", BINDING_REQUEST, 0, MAGIC) + txid[4:]


def random_txid() -> bytes:
    """Bytes 0-3 are the magic cookie; 4-15 random, per RFC 5389."""
    return struct.pack("!I", MAGIC) + os.urandom(12)


def parse_binding_response(msg: bytes, txid: bytes) -> tuple[str, int] | None:
    """(ip, port) out of one STUN response, or None if nothing usable.

    The transaction id must match the request -- a stray reply from some
    other transaction must not be able to invent a mapping. Headers are
    20 bytes: type, length, then the 16-byte txid AT OFFSET 4 -- the
    first version of this read the txid from offset 8 and every real
    reply failed the check, parser returned None on the wire-verified
    packet, which is how a wrong assumption reads as "no STUN servers".
    Attributes are TLVs after that 20-byte header; type 0x0001 is
    MAPPED-ADDRESS (plain), type 0x0020 is XOR-MAPPED-ADDRESS (masked
    with the cookie in the txid). Unknown types are skipped by length,
    never assumed short.
    """
    if len(msg) < 20 or msg[:2] != b"\x01\x01":
        return None
    if msg[4 : 4 + len(txid)] != txid:
        return None
    length = struct.unpack("!H", msg[2:4])[0]
    if 20 + length > len(msg):
        return None

    plain = None
    xor = None
    off = 20
    end = 20 + length
    while off + 4 <= end:
        atype, alen = struct.unpack("!HH", msg[off : off + 4])
        val = msg[off + 4 : off + 4 + alen]
        off += 4 + ((alen + 3) & ~3)  # TLVs pad to 4-byte boundaries

        if (atype == MAPPED_ADDRESS or atype == XOR_MAPPED_ADDRESS) and len(val) >= 8:
            family = val[1]
            if family != 0x01:  # v4 only; the punch is v4 because the engine is
                continue
            try:
                if atype == XOR_MAPPED_ADDRESS:
                    port = struct.unpack("!H", val[2:4])[0] ^ (MAGIC >> 16)
                    raw = struct.unpack("!I", val[4:8])[0] ^ MAGIC
                else:
                    port = struct.unpack("!H", val[2:4])[0]
                    raw = struct.unpack("!I", val[4:8])[0]
                pure = plain
                if atype == XOR_MAPPED_ADDRESS:
                    xor = (socket.inet_ntoa(struct.pack("!I", raw)), port)
                else:
                    if pure is None:
                        plain = (socket.inet_ntoa(struct.pack("!I", raw)), port)
            except (struct.error, OSError):
                continue

    # Prefer the XOR form: it is the one that survives address-rewriting NATs
    # and it is what RFC 5389 servers answer with. Fall back to plain,
    # which is what classic servers answer with.
    return xor or plain


def query(sock: socket.socket, server: tuple[str, int],
          timeout: float = DEFAULT_TIMEOUT) -> tuple[str, int] | None:
    """One binding transaction on `sock`, against one server.

    The SO cards: the socket MUST be the one whose mapping is being measured.
    Holding the question here (rather than in the caller) keeps that
    requirement off punch.py.
    """
    txid = random_txid()
    try:
        host = socket.gethostbyname(server[0])
    except OSError:
        return None
    try:
        sock.settimeout(timeout)
        sock.sendto(_hdr(txid), (host, server[1]))
        deadline = DEFAULT_TIMEOUT * 2
        while True:
            deadline -= timeout
            data, _rinfo = sock.recvfrom(2048)
            out = parse_binding_response(data, txid)
            if out is not None:
                return out
            # A non-matching response (another transaction's, or a game
            # packet racing the probe) is skipped; give up when the
            # deadline is spent.
            if deadline <= 0:
                return None
    except (socket.timeout, ConnectionResetError, OSError):
        return None


def probe(sock: socket.socket, servers: tuple = SERVERS,
          timeout: float = DEFAULT_TIMEOUT) -> list[tuple[tuple[str, int],
          tuple[str, int] | None]]:
    """Every (server, mapping) the servers can be talked into telling us.

    Failure tolerant by construction: a server that is down, DNS-dead, or
    behind a filtering middlebox simply contributes nothing.
    """
    import random as _random
    results: list[tuple[tuple[str, int], tuple[str, int] | None]] = []
    for srv in _random.sample(list(servers), k=len(list(servers))):
        results.append((srv, query(sock, srv, timeout)))
    return results


def nat_kind(mappings: list[tuple[str, int] | None]) -> str:
    """'symmetric' when two servers see DIFFERENT mapped ports.

    This is the one NAT distinction that decides the whole strategy. Cone
    (and restricted) NATs hand every peer the same ip:port, so publishing
    that one endpoint is enough; Symmetric NAT gives each destination its
    own port, so the published endpoint is a lie for everyone except the
    STUN server, and the punch cannot work. Detected via two probes rather
    than promised.
    """
    ports = {m[1] for m in mappings if m is not None}
    if len(ports) > 1:
        return "symmetric"
    return "coned"


def best_mapping(mappings: list[tuple[str, int] | None]) -> tuple[str, int] | None:
    """The mapping to publish, taking truth over recency: a None is not a vote."""
    votes: dict[tuple[str, int], int] = {}
    for m in mappings:
        if m is not None:
            votes[m] = votes.get(m, 0) + 1
    if not votes:
        return None
    # Most-agreeing answer wins ties by count, and a stable sort keeps
    # reruns deterministic.
    return sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
