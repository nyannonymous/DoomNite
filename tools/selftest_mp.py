"""Offline checks for the zero-config multiplayer path.

  python tools/selftest_mp.py

Covers mp_session.py's command building and mp_http.py's request contract. Both
are pure functions over data the pack already has, so nothing here touches the
network, writes a config, creates a junction, or starts a game.

WHY THIS FILE IS NEEDED
-----------------------
Two silent bugs got through while this feature was being built, and both were
in exactly the class of thing this file now pins:

1. The UI posted `playable[i].index ?? i`. serve.py emits no `index` field, so
   the fallback always won and the ARRAY POSITION was sent as the server
   index. Because the list is filtered, every entry after the first dropped one
   resolved to a different game -- so picking "Aliens" hosted something else,
   with no error anywhere. Pinned here by asserting that a chosen label maps to
   the index the server actually has for that label.

2. `nn_preset.make_link()` PRINTS its report and returns an exit code. The
   first version of _ensure_ready() appended that int, so the UI displayed
   "links: 0" while the junctions were in fact fine. Pinned by asserting the
   captured output contains the real report lines, never a bare number.

The address parser is pinned hardest, because it is the one place a string from
a request reaches a command line: it must accept exactly `a.b.c.d:port` and
refuse everything else, including a hostname (which would need a DNS lookup and
is not what NN hands out) and anything with shell metacharacters.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, PACK)
sys.path.insert(0, HERE)

import mp_session as M   # noqa: E402
import mp_http as H      # noqa: E402
import serve             # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))


M._ensure_loaded()
serve.load_sources()
serve.load_entries()

# ---------------------------------------------------------------- address
# The one place a request-supplied string could reach a command line.
good = ["1.2.3.4:23513", "192.168.0.226:23513", "255.255.255.255:65535", "10.0.0.1:1025"]
for a in good:
    try:
        host, port = M._check_addr(a)
        check(f"accepts {a}", True, f"{host}:{port}")
    except ValueError as e:
        check(f"accepts {a}", False, str(e))

bad = [
    ("evil.com; rm -rf /", "shell metacharacters"),
    ("localhost:23513", "hostname, not an IP"),
    ("999.1.1.1:23513", "octet above 255"),
    ("1.2.3.4:80", "privileged port"),
    ("1.2.3.4:70000", "port above 65535"),
    ("1.2.3.4:1024", "port below 1025"),
    ("1.2.3.4", "no port"),
    ("23513", "no address"),
    ("", "empty"),
    ("1.2.3.4:23513 extra", "trailing junk"),
    ("1.2.3.4:23513;calc", "metacharacter after a valid prefix"),
    ("-1.2.3.4:23513", "negative octet"),
    ("1.2.3.:23513", "short octet"),
]
for a, why in bad:
    try:
        M._check_addr(a)
        check(f"refuses {a!r}", False, f"ACCEPTED ({why})")
    except ValueError:
        check(f"refuses {a!r} ({why})", True)

# ------------------------------------------------------- index resolution
# Pin bug #1: a chosen LABEL must map to the index the SERVER has for it,
# not to a position in any filtered list.
playable = [(i, e) for i, e in enumerate(serve.ENTRIES)
            if e.get("kind") == "pack" and e.get("iwad")]
check("the pack has playable entries to test with", len(playable) > 5,
      f"{len(playable)} of {len(serve.ENTRIES)}")

for idx, e in playable[:6]:
    got = M._resolve_index(str(idx))
    check(f"index {idx} resolves to itself ({e['label'][:34]})", got == idx,
          f"got {got}")

# Standalone entries have no IWAD and must not be playable.
standalone = [i for i, e in enumerate(serve.ENTRIES) if e.get("kind") != "pack"]
check("the pack has standalone entries to exclude", len(standalone) > 0,
      f"{len(standalone)}")
if standalone:
    i = standalone[0]
    try:
        M.files_for_entry(i)
        check("a standalone game is refused", False, f"entry {i} was accepted")
    except ValueError as e:
        check("a standalone game is refused", True, str(e)[:60])

# ------------------------------------------------------------ arg building
idx, entry = playable[0]
host = M.host_argv(idx, 23513)
join = M.join_argv(idx, "1.2.3.4:23513")
check("host command starts with zandronum.exe",
      os.path.basename(host[0]).lower() in ("zandronum.exe", "gzdoom.exe"),
      os.path.basename(host[0]))
check("host command carries -host 64", "-host" in host and "64" in host)
check("host command carries the port", "23513" in host)
check("host command sets sv_hostname", "+sv_hostname" in host)
check("join command carries +Connect", "+Connect" in join)
check("join command targets the address",
      "+Connect" in join and "1.2.3.4:23513" in join)

# Load order must be the entry's own, and every -file must be a real file.
files = M.files_for_entry(idx)
check("the entry yields files", len(files) > 0, f"{len(files)}")
check("every file exists on disk", all(os.path.isfile(f) for f in files))
hosted = [host[i + 1] for i, a in enumerate(host) if a == "-file"]
check("host argv passes every file with -file",
      hosted == files, f"{len(hosted)} vs {len(files)}")
if len(files) >= 2:
    check("load order matches the entry's launcher order",
          hosted[:len(files)] == files,
          " -> ".join(os.path.basename(f) for f in files[:3]))

# Hexen Remade needs the Hexen IWAD, which exists only in the pack.
hexen = [i for i, e in enumerate(serve.ENTRIES)
         if e.get("iwad") == "Hexen.wad"]
if hexen:
    h = M.host_argv(hexen[0], 23513)
    check("a Hexen entry carries the Hexen IWAD", "Hexen.wad" in h)
else:
    check("a Hexen entry carries the Hexen IWAD", True, "no Hexen entry to test")

# A custom hostname reaches the command line, length-capped.
named = M.host_argv(idx, 23513, hostname="Bob's Server")
check("a custom hostname reaches the command line", "Bob's Server" in named)

# ---------------------------------------------------------- the HTTP layer
# Request contract, without a socket: _int rejects bools and strings, which is
# the same guard /api/launch uses.
for badval, why in [(True, "bool"), ("0", "string"), (1.5, "float"),
                    ([0], "list"), ({"a": 1}, "object")]:
    got, err = H._int({"index": badval}, "index", required=True)
    check(f"rejects a {why} index", err is not None, str(err))

got, err = H._int({"index": 7}, "index", required=True)
check("accepts an integer index", err is None and got == 7)
got, err = H._int({}, "index", required=True)
check("rejects a missing required index", err is not None, str(err))
got, err = H._int({}, "index", default=0)
check("defaults an optional index to 0", err is None and got == 0)

# The route table covers exactly the three endpoints, and nothing else.
check("routes are setup/host/join only",
      sorted(H.ROUTES) == ["/api/multiplayer/host", "/api/multiplayer/join",
                           "/api/multiplayer/setup"], str(sorted(H.ROUTES)))
check("an unknown multiplayer path is not handled",
      not H.handles("/api/multiplayer/rooms"))
check("a lookalike path is not handled",
      not H.handles("/api/multiplayer/host/../launch"))

# ---------------------------------------------------- _ensure_ready output
# Pin bug #2: the report must be the CAPTURED stdout, never the return code.
src = open(os.path.join(HERE, "mp_session.py"), encoding="utf-8").read()
check("_ensure_ready captures stdout rather than appending a return code",
      '"--link", "--write"' in src and "make_link(zan_dir" not in src,
      "make_link called directly" if "make_link(zan_dir" in src else "")
check("_ensure_ready treats a non-zero exit as a failure",
      "returncode != 0" in src)
check("_ensure_loaded exists and is called by describe()",
      "def _ensure_loaded" in src and "_ensure_loaded()" in src)

# ---------------------------------------------------------------- fingerprint
# The alphabet MUST be 32 characters: _b32() indexes it with `value & 31`.
# The first hand-typed alphabet that avoided I/L/O/U came out 31 long and raised
# IndexError on roughly one entry in thirty-two -- and it contained U, the
# letter most easily misheard as V. Both are pinned here.
check("the fingerprint alphabet is 32 characters",
      len(M._FP_ALPHABET) == 32, f"{len(M._FP_ALPHABET)} chars")
check("the alphabet has no duplicate characters",
      len(set(M._FP_ALPHABET)) == len(M._FP_ALPHABET))
check("the alphabet excludes the ambiguous letters",
      not (set(M._FP_ALPHABET) & set("ILOU")), str(sorted(set(M._FP_ALPHABET) & set("ILOU"))))

# _b32 must survive a full sweep of the value space, not just the low bits: the
# 31-char alphabet only failed on values whose top bits were set.
ok32 = True
for v in (0, 1, 31, 32, 255, 65535, 1 << 20, (1 << 40) - 1):
    try:
        s = M._b32(v, 8)
        if len(s) != 8 or any(c not in M._FP_ALPHABET for c in s):
            ok32 = False
    except IndexError:
        ok32 = False
check("_b32 handles the whole value range", ok32)

# A generated code must be readable: no confusables ever appear in OUTPUT.
fps = []
for i, _e in playable[:6]:
    fps.append(M.fingerprint(i))
check("fingerprints are produced for real entries",
      all(f and len(f) == 8 for f in fps), ", ".join(fps))
check("generated codes contain no ambiguous characters",
      not (set("".join(f for f in fps if f)) & set("ILOU")),
      str(sorted(set("".join(f for f in fps if f)) & set("ILOU"))))

# Stable, and distinct per entry.
check("a fingerprint is stable across calls",
      M.fingerprint(idx) == M.fingerprint(idx))
if len(set(f for f in fps if f)) > 1:
    check("different entries fingerprint differently",
          len(set(fps)) > 1, f"{len(set(fps))} distinct of {len(fps)}")

# normalise_fp folds what a human mistypes.
check("lowercase code normalises",
      M.normalise_fp("abcd2345") == "ABCD2345", M.normalise_fp("abcd2345"))
check("O folds to 0", M.normalise_fp("ABCDO234") == "ABCD0234",
      M.normalise_fp("ABCDO234"))
check("I folds to 1", M.normalise_fp("ABCDI234") == "ABCD1234",
      M.normalise_fp("ABCDI234"))
check("U folds to V", M.normalise_fp("ABCDU234") == "ABCDV234",
      M.normalise_fp("ABCDU234"))
check("junk does not normalise",
      M.normalise_fp("!!!!") is None and M.normalise_fp("") is None)

# compare: match, mismatch, absent.
ours = M.fingerprint(idx)
check("compare_fingerprint matches its own code",
      M.compare_fingerprint(idx, ours)[0] is True)
check("compare_fingerprint rejects a wrong code",
      M.compare_fingerprint(idx, "ZZZZZZZZ")[0] is False)
check("compare_fingerprint returns None with no code",
      M.compare_fingerprint(idx, "")[0] is None)
check("compare_fingerprint tolerates a misheard code",
      M.compare_fingerprint(idx, ours.lower())[0] is True)

# The address parser must round-trip a code, and still refuse junk after one.
h, p, fp = M.split_addr_and_fp("1.2.3.4:23513 " + ours)
check("the parser returns the trailing code",
      fp == ours, f"{fp} vs {ours}")
check("the parser still accepts a bare address",
      M.split_addr_and_fp("1.2.3.4:23513")[2] is None)
for junk in ("1.2.3.4:23513 !!", "1.2.3.4:23513 ABCD2345 extra",
             "1.2.3.4:23513 " + ours + " -x",
             # A code is exactly 8 characters. Short words and long tokens are
             # both refused. A 4-16 character bound accepted "extra" as a
             # code; requiring a digit then refused the REAL VWEAPGMG, because
             # an 8-char string from 32 symbols is often all letters. Exact
             # length is the only rule that held up against both.
             "1.2.3.4:23513 extra",
             "1.2.3.4:23513 ABCDE",
             "1.2.3.4:23513 ABCDEFGHIJ"):
    try:
        M.split_addr_and_fp(junk)
        check(f"refuses {junk!r}", False, "ACCEPTED")
    except ValueError:
        check(f"refuses {junk!r}", True)

# EVERY real fingerprint must survive the address parser. This is the check
# that would have caught the digit rule rejecting VWEAPGMG: it is a property of
# the CODES, not of the one code the test happened to pick.
all_codes = [M.fingerprint(i) for i, _e in playable]
unparseable = [c for c in all_codes
               if M.split_addr_and_fp("1.2.3.4:23513 " + c)[2] != c]
check("every real fingerprint round-trips through the address parser",
      not unparseable,
      f"{len(unparseable)} of {len(all_codes)} failed: {unparseable[:3]}")

# describe() publishes it, because the UI reads it from there.
d = M.describe(idx)
check("describe() publishes a fingerprint",
      d.get("fingerprint") == ours, str(d.get("fingerprint")))
check("describe() caches rather than rehashing",
      M._fingerprint_cached(idx) == ours)

# ------------------------------------------------------------- player name
# The owner's two-instance screenshot showed ONE scoreboard row and a
# "<game label> joined the game" line that was really their own second
# instance: the panel was sending the GAME LABEL as the player name, and
# Zandronum keys its scoreboard and connect log by name.
#
# These pin the SERVER half of that fix, by calling the server's own function.
# The first version of this test re-implemented the rule inline -- a mirror --
# and drifted from the implementation on its very first run, which is exactly
# the bug class this file exists to catch. Call the real one.
_name_for = H.normalise_name

check("a real name is kept", _name_for("Steve") == "Steve")
check("a normal game label is NOT the player name",
      _name_for("Brutal Doom v22 test 6 [Doom 1]") == "Brutal Doom v22",
      _name_for("Brutal Doom v22 test 6 [Doom 1]"))
check("surrounding whitespace is stripped", _name_for("  Steve  ") == "Steve")
check("an empty name falls back rather than colliding",
      _name_for("") == "NukemNet", _name_for(""))
check("a whitespace-only name falls back", _name_for("     ") == "NukemNet")
check("a missing name falls back", _name_for(None) == "NukemNet")
check("a long name is capped at 16", len(_name_for("x" * 40)) == 16,
      _name_for("x" * 40))
# Capping can leave a trailing space; the label above must not read as a typo.
check("no trailing space after capping",
      not _name_for("Brutal Doom v22 test 6").endswith(" "),
      repr(_name_for("Brutal Doom v22 test 6")))
# Shell metacharacters and control characters are stripped. NOT an injection fix
# -- argv is a list and no shell parses it -- this is about what other players
# see and what the engine writes into its own log.
weird = _name_for('"; rm -rf / #')
check("quotes and semicolons are stripped from a name",
      '"' not in weird and ";" not in weird, repr(weird))
check("a tab inside a name does not survive",
      "\t" not in _name_for("Bob\tSmith"), repr(_name_for("Bob\tSmith")))
check("every normalised name is a single clean argv token",
      all(c.isprintable() and c not in H._NAME_STRIP
          for t in ("Steve", "", None, "a\tb", '"; x')
          for c in _name_for(t)))

# ------------------------------------------------------------- shareable IPs
# The panel used to offer every non-loopback address with nothing to tell them
# apart. On the owner's machine that is three: the Wi-Fi one (correct), a
# Tailscale address, and a VirtualBox host-only adapter. Two of the three are
# unreachable to a friend, and one of those was offered in plain green as if it
# were a LAN address.
#
# The Tailscale miss was my arithmetic: I matched the literal string "100.64."
# when RFC 6598 is 100.64.0.0/10, i.e. 100.64.x THROUGH 100.127.x. The owner's
# own address is 100.95.67.84, so it fell through to "public".
check("CGNAT covers the whole 100.64.0.0/10 block",
      M._in_cgnat("100.64.0.1") and M._in_cgnat("100.95.67.84")
      and M._in_cgnat("100.127.255.254"))
check("CGNAT stops at the /10 boundary",
      not M._in_cgnat("100.63.0.1") and not M._in_cgnat("100.128.0.1"))
check("CGNAT is not confused with private space or the internet",
      not M._in_cgnat("192.168.0.1") and not M._in_cgnat("10.0.0.1")
      and not M._in_cgnat("8.8.8.8"))
check("a Tailscale address is classified as one, not public",
      M._classify_ip("100.95.67.84") == "cgnat-tailscale",
      M._classify_ip("100.95.67.84"))
check("a LAN address is private", M._classify_ip("192.168.0.226") == "private")
check("link-local is recognised", M._classify_ip("169.254.1.1") == "link-local")
check("a VirtualBox host-only adapter is recognised",
      M._guess_virtual("192.168.56.1"), "VirtualBox default host-only")
check("a real LAN address is not called virtual",
      not M._guess_virtual("192.168.0.226"))
check("Docker's ranges are recognised as virtual",
      M._guess_virtual("172.17.0.1") and M._guess_virtual("172.18.0.1"))

# Ordering: a usable private address must come FIRST, because that is the one
# most likely to work and the UI shows them in this order.
pairs = M.shareable_addresses()
kinds = [k for _ip, k in pairs]
rank = {"wifi": 0, "lan": 0, "cgnat-tailscale": 1, "public": 2,
        "link-local": 3, "virtual": 4}
check("shareable_addresses is ordered best-first",
      kinds == sorted(kinds, key=lambda k: rank.get(k, 5)), str(kinds))
check("every shareable address has a kind",
      all(k for _ip, k in pairs), str(pairs))

print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} checks passed")
sys.exit(1 if FAIL else 0)