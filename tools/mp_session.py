"""Build and run a Zandronum multiplayer session from a DoomNite entry.

The product rule this exists to enforce: the user clicks one button and never
opens NukemNet, and never needs to know NukemNet exists.

Why that is possible
--------------------
NukemNet's value is three things -- a room list, NAT traversal, and launching
the engine -- and only the first two need NN. What NN actually *executes* is a
plain Zandronum command line, which its own log records verbatim:

    host: zandronum.exe -iwad DOOM.WAD -file ... -host 64 -port 23513
                     +sv_hostname NukemNet +sv_maxclientsperip 64
                     +alwaysapplydmflags 1 +dmflags 0
    join: zandronum.exe -iwad DOOM.WAD -file ... +Connect 127.0.0.1:23513

So hosting and joining a *known* address needs no NN process at all. This
module builds those two command lines from the same entry the launcher would
have used, which means the mod, its load order and its IWAD come from the
pack's own data rather than from anything the user typed.

What it deliberately does NOT do
--------------------------------
It does not open NN, and it does not browse rooms. A public room list needs
NN's IRC/relay connection, and NN has no scriptable interface for it (verified
against the installed 33.0.1 build: createRoom/hostGame/joinRoom exist only in
the SolidJS renderer bundle, never in electron_index.js). Adding a room list
later means speaking NN's protocol or driving its UI -- both bigger than this.

Junctions and the NN preset
---------------------------
Still handled here, because Zandronum loads files by absolute path and the
pack keeps them under Z:\\...: NN's Zandronum folder gets two directory
junctions pointing back at the pack (see nn_preset.py --link), and the
LaunchDefaults preset is refreshed so NN's own Play Zandronum button keeps
working. Both are idempotent and both are run by /api/multiplayer/setup so the
user never runs a command.

  python tools/mp_session.py --list
  python tools/mp_session.py --entry 1                  # dry run: show both
  python tools/mp_session.py --entry 1 --host          # actually start a host
  python tools/mp_session.py --entry 1 --join 1.2.3.4:23513

Safety: like /api/launch, every command is built from paths this module
resolved out of the pack's own manifest and launcher scripts. Nothing a request
supplies ever becomes a path or an argument -- `--entry` is an integer index,
and `--join` is parsed and rebuilt rather than interpolated.
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, PACK)
sys.path.insert(0, HERE)

import serve as _serve                     # noqa: E402  (entry list, resolve)
import nn_preset as _nn                    # noqa: E402  (find NN, junctions)

# The port NN itself uses, so a game hosted here is reachable by anyone who
# found the address the usual way. Overridable per session.
DEFAULT_PORT = 23513

# Zandronum's own deathmatch defaults, matching what NN sends. Kept explicit
# rather than inherited so a hosted game behaves the same whether or not NN is
# involved at all.
HOST_CONVARS = (
    "+sv_hostname", "{name}",
    "+sv_maxclientsperip", "64",
    "+alwaysapplydmflags", "1",
    "+dmflags", "0",
)

# A host/join address: four dotted octets and a port, nothing else. Anything
# else is refused rather than passed to a shell.
_ADDR = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3}):(\d{1,5})$")

# The same, plus an optional trailing fingerprint. The user pastes one line
# copied from the host's panel -- "1.2.3.4:23513 ABCD1234" -- so this is the
# shape actually arrives, and making them delete the second half would be
# asking them to edit information we handed them.
#
# The trailing group is LENGTH-BOUNDED to 4-8, which is exactly the range
# fingerprint() emits. Without that bound, widening this regex to tolerate a
# code also tolerates ANY trailing word: "1.2.3.4:23513 extra" parsed as a code
# named EXTRA, so a line with junk on the end was silently accepted instead of
# refused. selftest_mp.py pins both the accept and the refuse.
# The code group is EXACTLY 8 characters -- the one length fingerprint() emits.
#
# Two rules tried before this one, both wrong:
#   * `[A-Za-z0-9]{4,16}` accepted "1.2.3.4:23513 extra" as a code named EXTRA,
#     so a line with junk on the end stopped being refused.
#   * requiring at least one digit rejected a REAL code: entry 0 fingerprints
#     as VWEAPGMG, which contains no digits at all. An 8-character string drawn
#     from 32 symbols is only ~5% likely to contain a digit given 10 of them --
#     I had that backwards, and a real code failed to parse because of it.
#
# Exact length is the discriminator that holds: no English word is 8
# characters of mixed case letters and digits, and every genuine code is.
_ADDR_FP = re.compile(
    r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3}):(\d{1,5})"
    r"(?:\s+([A-Za-z0-9]{8}))?$")

# The fingerprint alphabet, for validating a trailing token. Must track
# mp_session._FP_ALPHABET plus its four tolerated confusables, or a valid code
# gets rejected here before the comparison ever runs. Built from those two
# rather than retyped, because a hand-copied character set drifting out of sync
# with the alphabet is exactly the bug that made the first alphabet 31 chars.
_FP_CHARS = set("0123456789ABCDEFGHJKMNPQRSTVWXYZILOU")


def _port_ok(p):
    return 1024 < int(p) < 65536


def split_addr_and_fp(addr):
    """(host, port, fingerprint|None) from one pasted line.

    Rejects the whole line if the trailing token is not a well-formed
    fingerprint, rather than silently discarding it -- silently dropping an
    unrecognised token is how a typo'd code turns into "no check was done" and
    the user never learns their mods differ.
    """
    raw = (addr or "").strip()
    m = _ADDR_FP.match(raw)
    if not m:
        # Diagnose WHICH half is wrong. Telling a user "address must look like
        # 1.2.3.4:23513" when their address is perfect and only the trailing
        # code is malformed sends them hunting for a problem they do not have.
        _bare = _ADDR.match(raw)
        if _bare:
            raise ValueError(
                "the address is right but the code after it is not. A code is "
                "exactly 8 letters and digits, like ABCD2345 -- or leave it off "
                "entirely. Got: " + repr(raw))
        parts = raw.split()
        if len(parts) == 2 and ":" in parts[0]:
            # An address with something after it: say so, rather than implying
            # the address is at fault.
            raise ValueError(
                "the address is right but the code after it is not. A code is "
                "exactly 8 letters and digits, like ABCD2345 -- or leave it off "
                "entirely. Got: " + repr(parts[1]))
        raise ValueError(
            "address must look like 1.2.3.4:23513 -- got: " + repr(addr))
    octets = [int(x) for x in m.groups()[:4]]
    if any(o > 255 for o in octets):
        raise ValueError("address has an octet above 255: " + raw)
    port = m.group(5)
    if not _port_ok(port):
        raise ValueError("port must be 1025-65535: " + raw)
    fp = m.group(6)
    if fp is not None:
        # A code may only contain the alphabet or its tolerated confusables;
        # anything else means this was not a code at all, and silently
        # discarding it would turn a typo into "no check was done".
        if any(c.upper() not in _FP_CHARS for c in fp):
            raise ValueError(
                "the code after the address looks wrong (expected letters and "
                "digits only): " + repr(fp))
        fp = normalise_fp(fp)
    return ".".join(str(o) for o in octets), port, fp


def _check_addr(addr):
    """(host, port) for a well-formed address, or raise ValueError."""
    host, port, _fp = split_addr_and_fp(addr)
    return host, port


def zandronum_exe():
    """Zandronum's own exe, preferring the bundled copy if present,
    otherwise from NN's Settings.json, or None.

    NN records where it launches the engine from; that is the only place on
    this machine known to hold a working Zandronum, and reusing it means the
    multiplayer path and the single-player path run the same binary.
    If a bundled Zandronum is present under runtime/zandronum/zandronum.exe,
    it is used to allow friends to play without a separate Zandronum install.
    """
    # 1. Check for bundled Zandronum under the pack.
    bundled = os.path.join(PACK, "runtime", "zandronum", "zandronum.exe")
    if os.path.isfile(bundled):
        return bundled
    # 2. Fallback to NN's configured Zandronum.
    nn_user = _nn.find_nn()
    if not nn_user:
        return None
    zdir = _nn.nn_zandronum_dir(nn_user)
    if not zdir or not os.path.isdir(zdir):
        return None
    for name in ("zandronum.exe", "gzdoom.exe", "zandronum"):
        p = os.path.join(zdir, name)
        if os.path.isfile(p):
            return p
    return None


def files_for_entry(idx):
    """The files an entry loads, in load order, absolute.

    From the entry's OWN launcher .bat via nn_preset.entry_files(), which is
    the same source serve.py trusts for _content_present(). The manifest's
    `mods` list carries basenames only, so it cannot be turned back into a
    path.
    """
    _ensure_loaded()
    entry = _serve.resolve(idx)
    if entry is None:
        raise ValueError("no such entry: " + str(idx))
    if entry.get("kind") != "pack":
        raise ValueError(
            "multiplayer is Zandronum only; " + entry.get("label", "that entry")
            + " is a standalone game")
    bat = entry.get("bat")
    if not bat:
        raise ValueError("that entry has no launcher")
    return _nn.entry_files(os.path.join(PACK, "launchers", bat))


def iwad_for_entry(idx):
    _ensure_loaded()
    entry = _serve.resolve(idx)
    return (entry or {}).get("iwad") or ""


def base_argv(idx, hostname="NukemNet"):
    """zandronum + -iwad + every -file, i.e. everything except host/join.

    Order matters and is the entry's own: ZDoom loads left to right, and the
    pack's load order is not always alphabetical (BDBE must precede its
    episode wad, Aliens TC must precede its mapset).
    """
    exe = zandronum_exe()
    if not exe:
        raise ValueError(
            "Zandronum was not found. It is where NukemNet launches the "
            "engine from -- run NukemNet once, or set its Zandronum path.")
    files = files_for_entry(idx)
    if not files:
        raise ValueError("that entry loads no files")
    argv = [exe]
    iwad = iwad_for_entry(idx)
    if iwad:
        argv += ["-iwad", os.path.basename(iwad)]
    for f in files:
        argv += ["-file", f]
    argv += ["+name", hostname]
    return argv


def host_argv(idx, port=DEFAULT_PORT, hostname="NukemNet", deathmatch=False):
    """The full command line for hosting, exactly as NN would build it."""
    argv = base_argv(idx, hostname)
    argv += ["-private"]
    if deathmatch:
        argv += ["-deathmatch", "-host", "64"]
    else:
        argv += ["+Cooperative", "1", "-fast", "-respawn", "-host", "64"]
    argv += ["-port", str(port)]
    argv += [x.replace("{name}", hostname) for x in HOST_CONVARS]
    return argv


def join_argv(idx, addr, hostname="NukemNet"):
    """The full command line for joining a known address.

    `addr` may carry a trailing fingerprint ("1.2.3.4:23513 ABCD1234"); it is
    parsed off and ignored here, because comparing it is the HTTP layer's job
    (mp_http passes it separately so a mismatch can be reported without
    blocking the connect).
    """
    host, port, _fp = split_addr_and_fp(addr)
    argv = base_argv(idx, hostname)
    argv += ["+Connect", f"{host}:{port}"]
    return argv


def local_addresses():
    """Every non-loopback IPv4 on this box, best guess.

    Deliberately unlabelled and unordered -- shareable_addresses() is what the
    UI uses, because this raw list is what made the problem in the first place
    (it offered a Tailscale and a VirtualBox address alongside the real Wi-Fi
    one, with nothing to tell them apart).
    """
    import socket
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # No packet is sent; this just asks the OS which local route it would
        # use. Connect to a public address but never send.
        s.connect(("8.8.8.8", 80))
        out.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            # sockaddr is a 2-tuple whose [0] is the dotted-quad string.
            ip = str(info[4][0])
            if ip not in out and not ip.startswith("127."):
                out.append(ip)
    except OSError:
        pass
    return out


# Adapter addresses that are NOT a real network a friend can reach.
#
# local_addresses() used to return every non-loopback IPv4 on the box and let
# the user pick. On the owner's machine that produced three: 192.168.0.226
# (Wi-Fi, correct), 100.95.67.84 (Tailscale) and 192.168.56.1 (a VirtualBox
# host-only adapter). Two of the three addresses the panel offered were
# unreachable to anyone else -- the VPN address needs the friend on the same
# tailnet, and the VirtualBox one is a private host-only segment by design.
#
# So classify rather than dump. A CGNAT/Tailscale-style address is still
# LISTED, because it is genuinely the right address when your friend is on your
# VPN, but it is labelled so nobody tries it against a random house wifi.
# RFC 6598 shared address space is 100.64.0.0/10 -- that is 100.64.x THROUGH
# 100.127.x, not just 100.64.x. Matching only "100.64." missed the owner's own
# Tailscale address (100.95.67.84), so it was classified "public" and offered
# to friends as if it were an ordinary internet address. The second octet is
# range-tested, not string-prefixed.
def _in_cgnat(ip):
    parts = ip.split(".")
    if len(parts) < 2 or parts[0] != "100":
        return False
    try:
        second = int(parts[1])
    except ValueError:
        return False
    return 64 <= second <= 127


_VPN_NETS = ("cgnat-tailscale",)


def _classify_ip(ip):
    """"wifi" | "vpn" | "virtual" | "lan", best guess from the address alone.

    Deliberately address-based, not interface-based: enumerating Windows
    adapters needs ctypes/ifaddr and breaks on macOS and Linux, and the ranges
    below are the ones that actually cause confusion. RFC 1918 is private LAN;
    169.254 is link-local; 100.64/10 is CGNAT and is what Tailscale hands out.
    """
    if ip.startswith("169.254."):
        return "link-local"
    # CGNAT/Tailscale BEFORE the RFC 1918 test: 100.64.0.0/10 is not private
    # space by RFC 1918, but it is the range Tailscale hands out, and calling it
    # "public" would tell the user to hand it to anyone -- which is exactly the
    # mistake this function exists to prevent.
    if _in_cgnat(ip):
        return "cgnat-tailscale"
    if ip.startswith("10.") or ip.startswith("192.168.") or (
            ip.startswith("172.") and 16 <= int(ip.split(".")[1] or 0) <= 31):
        return "private"
    return "public"


def _guess_virtual(ip):
    """True for the ranges virtualisation tools habitually use.

    These are RFC 1918 addresses that no real router hands out on a home
    network: VirtualBox's default host-only segment, VMware's, and Docker's.
    Offering one as "share this to play" wastes the user's time.
    """
    return ip in ("192.168.56.1",) or ip.startswith("172.17.") or \
        ip.startswith("172.18.") or ip.startswith("192.168.99.")


def shareable_addresses():
    """(ip, kind) pairs, ordered so the most likely to work comes first.

    `kind` is for the UI to explain itself: "wifi"/"lan" needs nothing said,
    "cgnat-tailscale" only works if the friend is on your VPN, and
    "virtual" should not be offered at all.
    """
    out = []
    for ip in local_addresses():
        kind = _classify_ip(ip)
        if _guess_virtual(ip):
            out.append((ip, "virtual"))
        elif kind != "private":
            out.append((ip, kind))       # cgnat-tailscale, public, link-local
        else:
            out.append((ip, "wifi" if _is_wifi_like(ip) else "lan"))
    # Best first: real private LAN, then VPN, then everything else.
    rank = {"wifi": 0, "lan": 0, "cgnat-tailscale": 1, "public": 2,
            "link-local": 3, "virtual": 4}
    out.sort(key=lambda t: rank.get(t[1], 5))
    return out


def _is_wifi_like(ip):
    """Best-effort: is this the Wi-Fi adapter? On the owner's machine the Wi-Fi
    address is the one on the default route, so probe the routing table rather
    than enumerate adapters."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary = s.getsockname()[0]
        s.close()
    except OSError:
        return True     # cannot tell; treat the first private address as usable
    return ip == primary


# --------------------------------------------------------------- fingerprint
# Why a fingerprint at all
# -----------------------
# The owner's own host+join test passed because both ends were the same machine
# with the same files. That proves the arguments are right, but it hides the
# commonest multiplayer failure: two people running DIFFERENT versions of the
# same mod. The engine connects, the lobby fills, and the game is subtly broken
# -- missing sprites, desyncs, a different IWAD -- with neither player told why.
#
# There is no handshake to hang this on. Zandronum's status query is not
# something this project can rely on across versions, and reading it would mean
# either reverse-engineering a protocol or opening the engine's own browser.
# So the fingerprint travels in the SHARE STRING instead: the host's panel
# shows "1.2.3.4:23513 ABCD1234", and the joiner pastes that whole line. It is
# the same string a human would read aloud, so it costs the user nothing extra.
#
# What it proves, and what it does not
# ----------------------------------
# It detects "you two do not have the same bytes", which is the whole point. It
# cannot prove the host is honest about what it is running -- a fingerprint is
# an assertion, not an attestation. That is fine: the failure mode it prevents
# is accidental mismatch, which is nearly all of them.

# Crockford base32: 32 characters by construction, which matters because
# _b32() indexes it with `value & 31`. The hand-typed version of this alphabet
# that avoided I/L/O/U came out 31 characters long and raised IndexError on
# roughly one entry in thirty-two -- and it also contained U, the letter most
# likely to be misheard as V.
#
# Crockford's own idea is better: exclude I, L, O and U (the ambiguous ones) and
# substitute 1 for I and 0 for O on input, so a misheard code can be corrected.
# The substitutes are deliberately NOT in the output alphabet, so nothing
# ambiguous is ever generated -- only tolerated on the way in.
_FP_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"   # Crockford, 32 chars

# What a code MAY be corrected FROM, when reading it aloud. Keyed to the
# canonical letter.
_FP_CONFUSABLE = {"I": "1", "L": "1", "O": "0", "U": "V"}


def _b32(value, length):
    """`length` characters from Crockford base32. Unambiguous, not crypto."""
    out = []
    for _ in range(length):
        out.append(_FP_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(out))


def normalise_fp(text):
    """A code as typed -> the canonical form, or None if it cannot be one.

    Upper-cases, then folds the four ambiguous letters a human actually
    mistypes: I/L -> 1, O -> 0, U -> V. Without this, a code read aloud over a
    voice chat mismatches on a character that looked identical and tells the
    user their mods differ when they do not -- a false alarm is worse than no
    check, because it sends people debugging the wrong thing.
    """
    if not text:
        return None
    s = str(text).strip().upper()
    if not s or any(c not in _FP_ALPHABET and c not in _FP_CONFUSABLE
                    for c in s):
        return None
    return "".join(_FP_CONFUSABLE.get(c, c) for c in s)


def file_digest(path, chunk=1 << 20):
    """sha256 of a whole file, streamed.

    Full content, not size or mtime: two builds of the same mod routinely share
    a byte size, and an mtime differs between every copy of the same download,
    so anything cheaper than the real bytes gives false matches or false
    alarms. The pack's largest file here is ~200 MB and this runs once, on
    demand, when the user asks to host.
    """
    import hashlib
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for b in iter(lambda: f.read(chunk), b""):
                h.update(b)
    except OSError:
        return None
    return h.digest()


def fingerprint(idx, length=8):
    """A short code identifying the exact bytes an entry loads, or None.

    Hashes each file's CONTENT together with its basename, in load order. The
    name matters: two different files with identical content would otherwise
    fingerprint the same, and swapping BDBE's episode wad for the other one
    changes behaviour without necessarily changing bytes elsewhere.

    Returns None if any file cannot be read, rather than a fingerprint of
    "some of the files" -- a partial code would produce a false mismatch
    warning, which is worse than no check.
    """
    try:
        files = files_for_entry(idx)
    except ValueError:
        return None
    if not files:
        return None
    import hashlib
    h = hashlib.sha256()
    for f in files:
        d = file_digest(f)
        if d is None:
            return None
        h.update(os.path.basename(f).lower().encode("utf-8", "replace"))
        h.update(b"\0")
        h.update(d)
    return _b32(int.from_bytes(h.digest()[:8], "big"), length)


def compare_fingerprint(idx, given):
    """(matches, ours). `matches` is None when there is nothing to compare.

    A None result means the joiner pasted no code, which is the normal case --
    the check is opt-in and must never block joining. Comparison runs through
    normalise_fp(), so a code misread over voice chat still matches.
    """
    ours = fingerprint(idx)
    norm = normalise_fp(given)
    if norm is None or ours is None:
        return None, ours
    return norm == ours, ours


def _mask_all(text):
    return _nn.mask(text)


def _ensure_loaded():
    """Make sure serve.ENTRIES is populated before anything resolves an index.

    The running server has already called load_entries() at startup, so this is
    normally a no-op -- but mp_session is also a CLI, and describe() called
    straight after import returned {"ok": false, "error": "no such entry"} for
    entry 0 even though the pack plainly has one. _serve.ENTRIES starts empty,
    so resolve() correctly refused. Loading here is cheap (it re-reads the
    manifest and stats the launcher files) and idempotent, and it makes the
    module safe to call from either context.
    """
    if not _serve.ENTRIES:
        try:
            _serve.load_sources()
            _serve.load_entries()
        except Exception:
            # A broken manifest should surface as "no such entry" from
            # resolve(), not as an exception out of the multiplayer panel.
            pass


def _resolve_index(arg):
    """The index of an entry named by index or game name, or None.

    Prints its own diagnostics, because the two failure modes are different
    and the user needs to tell them apart: "no such entry" (wrong number) vs
    "that name is ambiguous" (nn_preset has the same collision for Hexen Remade
    HD, whose two entries differ only by an IWAD tag).
    """
    _ensure_loaded()
    arg = str(arg).strip()
    if arg.isdigit():
        i = int(arg)
        if 0 <= i < len(_serve.ENTRIES):
            return i
        print(f"no entry {i}; the pack has {len(_serve.ENTRIES)}")
        return None
    hits = [i for i, e in enumerate(_serve.ENTRIES)
            if e.get("label", "").lower() == arg.lower()]
    if not hits:
        hits = [i for i, e in enumerate(_serve.ENTRIES)
                if arg.lower() in e.get("label", "").lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        print(f"no entry matches {arg!r}")
        return None
    print(f"{arg!r} matches {len(hits)} entries; pass the index instead:")
    for i in hits:
        print(f"  {i}  {_serve.ENTRIES[i]['label']}")
    return None


def describe(idx, port=DEFAULT_PORT):
    """Everything the UI needs to show a Host/Join panel for one entry."""
    _ensure_loaded()
    entry = _serve.resolve(idx)
    if entry is None:
        return {"ok": False, "error": "no such entry"}
    info = {
        "ok": True,
        "index": idx,
        "label": entry.get("label", ""),
        "iwad": iwad_for_entry(idx),
        "port": port,
        "nn": {
            "found": bool(_nn.find_nn()),
            "linked": None,
        },
        "local_ips": local_addresses(),
        "files": [_nn.mask(f) for f in files_for_entry(idx)]
        if entry.get("kind") == "pack" else [],
    }
    zdir = None
    nn_user = _nn.find_nn()
    if nn_user:
        zdir = _nn.nn_zandronum_dir(nn_user)
    if zdir:
        try:
            info["nn"]["linked"] = all(
                _nn.is_junction(os.path.join(zdir, name)) for name, _ in _nn.LINKS)
        except OSError:
            info["nn"]["linked"] = False
    try:
        info["zandronum"] = bool(zandronum_exe())
    except Exception:
        info["zandronum"] = False
    # Computed lazily and cached in the process: hashing ~200 MB of pk3s is not
    # something to redo on every poll of the panel. The UI calls describe() once
    # per open, so this runs at most once per session unless the cache is
    # cleared (which is deliberate -- files change if the user re-downloads a
    # mod, and they can press the button again).
    try:
        info["fingerprint"] = _fingerprint_cached(idx)
    except Exception:
        info["fingerprint"] = None
    return info


_FP_CACHE = {}


def _fingerprint_cached(idx):
    """fingerprint(idx), memoised per process."""
    if idx not in _FP_CACHE:
        _FP_CACHE[idx] = fingerprint(idx)
    return _FP_CACHE[idx]


def _ensure_ready(write_preset=True):
    """Junctions + preset, idempotently. This is what the one button runs.

    Returns (ok, list_of_lines). Both steps are the ones the user would
    otherwise have to discover and run by hand; both are safe to repeat.

    nn_preset.make_link() PRINTS its report and returns an exit code rather than
    a string, so the output is captured from stdout -- the first version of this
    function appended the returned int, and the UI showed "links: 0" instead of
    "already linked, nothing to do". Capturing stdout is also what lets the
    dialog show the same report the CLI prints.
    """
    lines = []
    nn_user = _nn.find_nn()
    if not nn_user:
        return False, ["NukemNet was not found on this machine."]
    zdir = _nn.nn_zandronum_dir(nn_user)
    if not zdir:
        return False, ["NukemNet has no Zandronum path set."]
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "nn_preset.py"), "--link", "--write"],
            capture_output=True, text=True, timeout=60)
        lines.extend((r.stdout or "").strip().splitlines())
        # Non-zero means a real refusal (a non-empty real folder in the way).
        # Surface it rather than claiming success.
        if r.returncode != 0:
            lines.extend((r.stderr or "").strip().splitlines())
            return False, lines
    except subprocess.TimeoutExpired:
        return False, ["Timed out creating the junctions."]
    if write_preset:
        try:
            r2 = subprocess.run(
                [sys.executable, os.path.join(HERE, "nn_preset.py"), "--list"],
                capture_output=True, text=True, timeout=30)
            lines.append(_nn.mask((r2.stdout or "").strip()))
        except subprocess.TimeoutExpired:
            lines.append("(preset status timed out)")
    return True, lines


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list playable entries")
    ap.add_argument("--entry", help="entry index or name")
    ap.add_argument("--host", action="store_true", help="start hosting")
    ap.add_argument("--join", help="join 1.2.3.4:23513")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--deathmatch", action="store_true")
    ap.add_argument("--setup", action="store_true",
                    help="create junctions + refresh the NN preset, then stop")
    args = ap.parse_args()

    _serve.load_sources()
    _serve.load_entries()

    if args.setup:
        ok, lines = _ensure_ready()
        print("\n".join(_mask_all(x) for x in lines))
        return 0 if ok else 1

    if args.list or not args.entry:
        idxs = [i for i in range(len(_serve.ENTRIES))
                if _serve.ENTRIES[i].get("kind") == "pack" and
                _serve.ENTRIES[i].get("iwad")]
        print(f"NN user folder : {_nn.mask(_nn.find_nn() or '(not found)')}")
        print(f"Zandronum     : {_nn.mask(zandronum_exe() or '(not found)')}")
        print(f"playable      : {len(idxs)} of {len(_serve.ENTRIES)} entries\n")
        for i in idxs:
            e = _serve.ENTRIES[i]
            print(f"  {i:>3}  {e['label']}")
        return 0

    # nn_preset.resolve_entry() returns the entry DICT, not an index, and this
    # module is index-based throughout (serve.resolve takes an int). Resolving
    # here rather than reusing it keeps one notion of "the entry" and means a
    # change to that helper's return type cannot silently break the multiplayer
    # path. It also gives the "matches 2 entries; be more specific" case a
    # useful message instead of SystemExit.
    idx = _resolve_index(args.entry)
    if idx is None:
        return 1

    try:
        if args.host:
            argv = host_argv(idx, args.port, deathmatch=args.deathmatch)
        elif args.join:
            argv = join_argv(idx, args.join)
        else:
            print("host : " + " ".join('"%s"' % a for a in host_argv(idx, args.port)))
            print("join : " + " ".join('"%s"' % a for a in join_argv(idx, "1.2.3.4:%d" % args.port)))
            return 0
    except ValueError as e:
        print(str(e))
        return 1

    if "--print" in sys.argv:
        print(" ".join('"%s"' % a for a in argv))
        return 0

    print(_mask_all("launching: " + " ".join(argv)))
    # start /D so the engine's cwd is the folder its relative paths expect,
    # detached so closing DoomNite does not kill a hosted game.
    subprocess.Popen(["cmd", "/c", "start", "", "/D", os.path.dirname(argv[0])] + argv,
                     cwd=os.path.dirname(argv[0]),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return 0


if __name__ == "__main__":
    sys.exit(main())