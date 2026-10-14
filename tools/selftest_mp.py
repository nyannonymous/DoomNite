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
import io
import json
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
try:
    host = M.host_argv(idx, 23513)
    join = M.join_argv(idx, "1.2.3.4:23513")
except ValueError as e:
    # mp_session refuses to build a command when the entry's IWAD cannot be
    # found (see the refusal check below). A pack without iwads is already
    # reported by the "every file exists on disk" check; degrade to the empty
    # list so the checks below FAIL with a reason instead of crashing the run.
    host, join = [""], [""]
    check("host/join argv can be built (the entry's IWAD is present)",
          False, str(e))
check("host command starts with zandronum.exe",
      os.path.basename(host[0]).lower() in ("zandronum.exe", "gzdoom.exe"),
      os.path.basename(host[0]))
# The IWAD must reach the engine as a PATH. It was passed as a bare basename
# ("DOOM2.WAD"), which only resolves when the engine's own IWAD search list
# already names the folder holding it -- and a freshly unzipped pack's does
# not, so every multiplayer launch opened Zandronum's "Welcome to Zandronum! /
# point us to your Doom directory" dialog even after the user pointed it at the
# right folder by hand.
iwad_args = [host[i + 1] for i, a in enumerate(host) if a == "-iwad"]
check("the engine is handed exactly one -iwad", len(iwad_args) == 1,
      str(len(iwad_args)))
check("the IWAD is passed as an absolute path, not a bare name",
      bool(iwad_args) and os.path.isabs(iwad_args[0]),
      iwad_args[0] if iwad_args else "(none)")
check("the IWAD path exists and is the entry's own",
      bool(iwad_args) and os.path.isfile(iwad_args[0])
      and os.path.basename(iwad_args[0]).upper() == (entry.get("iwad") or "").upper(),
      iwad_args[0] if iwad_args else "(none)")
check("iwad_path_for_entry agrees with the command line",
      bool(iwad_args) and M.iwad_path_for_entry(idx) == iwad_args[0],
      M.iwad_path_for_entry(idx) or "(unresolved)")
check("DOOMWADDIR points at the pack's iwads",
      os.path.normcase(M.launch_env().get("DOOMWADDIR") or "")
      == os.path.normcase(os.path.join(PACK, "iwads")),
      M.launch_env().get("DOOMWADDIR") or "(unset)")
check("launch_env keeps the rest of the environment",
      "PATH" in M.launch_env() or "Path" in M.launch_env())

# A pack that is missing the IWAD must be REFUSED with a readable reason. The
# bug this replaces was silent: the engine was handed a name it could not
# resolve, opened its own folder picker, and the user had no way to tell that
# dialog apart from the launcher being broken.
_orig_available = M._iwad.available
try:
    M._iwad.available = lambda name: None
    try:
        M.host_argv(idx, 23513)
        check("a missing IWAD refuses to build a launch command", False,
              "built a command anyway")
    except ValueError as e:
        check("a missing IWAD refuses to build a launch command", True,
              str(e)[:60])
finally:
    M._iwad.available = _orig_available

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
# The base game is passed ONCE, as -iwad.
#
# files_for_entry() reads the pack's launcher .bat, and that file names its IWAD
# too, so the WAD used to come back out of this list and go onto the command
# line a second time as `-file`: the engine then loaded the base game twice,
# once as the game and once as a mod stacked on itself. Every other file keeps
# the entry's own order, which is load-bearing.
mods_only = [f for f in files
             if os.path.normcase(os.path.abspath(f))
             != os.path.normcase(os.path.abspath(iwad_args[0]))] \
    if iwad_args else list(files)
check("host argv passes every file with -file, minus the base WAD",
      hosted == mods_only, f"{len(hosted)} vs {len(mods_only)}")
check("the base WAD is not also passed as -file (it would load twice)",
      len(hosted) == len(files) - 1 if iwad_args else len(hosted) == len(files),
      f"{len(hosted)} -file vs {len(files)} entry files")
check("the base WAD appears exactly once in the whole command line",
      sum(1 for a in host
          if iwad_args and os.path.normcase(os.path.abspath(a))
          == os.path.normcase(os.path.abspath(iwad_args[0]))) == 1,
      str(host.count(iwad_args[0]) if iwad_args else 0))
if len(mods_only) >= 2:
    check("load order matches the entry's launcher order",
          hosted[:len(mods_only)] == mods_only,
          " -> ".join(os.path.basename(f) for f in mods_only[:3]))

# Hexen Remade needs the Hexen IWAD, which exists only in the pack.
hexen = [i for i, e in enumerate(serve.ENTRIES)
         if e.get("iwad") == "Hexen.wad"]
if hexen:
    try:
        h = M.host_argv(hexen[0], 23513)
        check("a Hexen entry carries the Hexen IWAD",
              any(os.path.basename(x).upper() == "HEXEN.WAD" for x in h),
              ", ".join(os.path.basename(x) for x in h[:6]))
    except ValueError as e:
        check("a Hexen entry carries the Hexen IWAD", False, str(e)[:60])
else:
    check("a Hexen entry carries the Hexen IWAD", True, "no Hexen entry to test")

# A custom hostname reaches the command line, length-capped.
named = M.host_argv(idx, 23513, hostname="Bob's Server")
check("a custom hostname reaches the command line", "Bob's Server" in named)

# ------------------------------------------------- readiness without NukemNet
# NukemNet is not needed to host or join -- the engine is started directly -- so
# nothing that answers "can this machine play?" may depend on it. The setup
# route used to report `ok: false` and log "NukemNet was not found on this
# machine" on a perfectly working machine that simply does not have NN
# installed, which is every fresh install of the shipped pack.
_ok_play, _why_play = M.can_play(idx)
check("a real entry reports itself playable", _ok_play is True, _why_play or "ok")
check("describe() carries the playability verdict",
      M.describe(idx).get("can_play") is True,
      str(M.describe(idx).get("why")))

# describe() must not raise for an entry that cannot be played online. It used
# to raise ValueError out of files_for_entry() for a standalone game, which
# mp_http.setup turned into a 500 -- and a 500 is what hides the panel.
if standalone:
    i = standalone[0]
    try:
        info = M.describe(i)
        check("describe() survives a standalone entry instead of raising",
              info.get("ok") is True and info.get("can_play") is False,
              str(info.get("why"))[:70])
    except Exception as e:
        check("describe() survives a standalone entry instead of raising",
              False, f"{type(e).__name__}: {e}")

# The HTTP payload, through the real handler: the same class of request the
# panel makes, with no socket and no game launched.
class _FakeHandler:
    """Just enough of BaseHTTPRequestHandler for mp_http._body()."""

    def __init__(self, body):
        raw = json.dumps(body).encode("utf-8")
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)


# Every setup() call below runs with NukemNet reported ABSENT, on purpose, and
# that is also what keeps this file side-effect free: _ensure_ready() returns
# before it runs nn_preset, so nothing writes a junction or a preset. With NN
# present it shells out to nn_preset.py, which is a real write and is pinned by
# tools/selftest_nn_preset.py instead. The no-NukemNet machine is also the case
# this whole section exists for.
_orig_find_nn = M._nn.find_nn
try:
    M._nn.find_nn = lambda: None
    status, body = H.setup(_FakeHandler({"index": idx}), serve.resolve)
    log = " ".join(body.get("log") or [])

    check("a machine with no NukemNet is reported as ok",
          status == 200 and body.get("ok") is True,
          f"{status} ok={body.get('ok')} err={body.get('error')}")
    check("a machine with no NukemNet still reports can_play",
          (body.get("ready") or {}).get("can_play") is True,
          str((body.get("ready") or {}).get("why")))
    check("a machine with no NukemNet reports no error",
          body.get("error") is None, str(body.get("error")))
    check("setup still describes the entry for the panel",
          (body.get("ready") or {}).get("label") == entry.get("label"))
    check("the no-NukemNet log explains itself instead of complaining",
          "not installed" in log and "does not need" in log,
          log[:90] or "(empty log)")
    check("the no-NukemNet log never calls a working machine unconfigured",
          "was not found" not in log, log[:90])
    check("the NukemNet step reports success when there is nothing to do",
          M._ensure_ready()[0] is True, str(M._ensure_ready()[1])[:70])

    # A machine that genuinely cannot play says so, in the payload and in words,
    # and still describes the entry so the panel can render with the reason.
    M._iwad.available = lambda name: None
    try:
        status, body = H.setup(_FakeHandler({"index": idx}), serve.resolve)
        check("an unplayable machine is reported as not ok",
              status == 200 and body.get("ok") is False,
              f"{status} ok={body.get('ok')}")
        check("and it explains why in a sentence for a human",
              "was not found" in str(body.get("error")),
              str(body.get("error"))[:80])
        check("it still describes the entry, so the panel can render",
              (body.get("ready") or {}).get("label") == entry.get("label"))
        check("an unplayable machine says so in describe() too",
              M.describe(idx).get("can_play") is False)
    finally:
        M._iwad.available = _orig_available
finally:
    M._nn.find_nn = _orig_find_nn

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
#
# fingerprint() is None for an entry whose files are not all on disk -- this
# pack is not always complete -- and a None carries no code to round-trip.
# Concatenating one crashed this file with a TypeError before any of the checks
# below had run, so the codes that DO exist are what gets tested, and the count
# of uncoded entries is reported rather than silently shrinking the sample.
all_codes = [M.fingerprint(i) for i, _e in playable]
codes = [c for c in all_codes if c]
unparseable = [c for c in codes
               if M.split_addr_and_fp("1.2.3.4:23513 " + c)[2] != c]
check("every real fingerprint round-trips through the address parser",
      bool(codes) and not unparseable,
      f"{len(unparseable)} of {len(codes)} failed: {unparseable[:3]}"
      + (f"  ({len(all_codes) - len(codes)} entries have no code: files missing)"
         if len(codes) != len(all_codes) else ""))

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
# The WSL case, which cost a real evening: 172.20.96.1 is vEthernet (WSL), an
# adapter that exists only inside one PC, and it used to be classified "lan"
# and ranked SECOND -- above the Tailscale address that is the only one that
# reaches a friend who is not in the house. A mate sat on "CONNECTING TO" until
# it was found. The whole /12 is claimed, so the octet moving between machines
# cannot reintroduce it.
check("WSL's vEthernet segment is virtual, not a LAN",
      M._guess_virtual("172.20.96.1"), "the address that caused the outage")
check("the whole of 172.16.0.0/12 is virtual",
      all(M._guess_virtual(f"172.{n}.0.1") for n in range(16, 32)))
check("the /12 stops where it should",
      not M._guess_virtual("172.15.0.1") and not M._guess_virtual("172.32.0.1"))
check("Tailscale outranks every virtual adapter",
      [k for _, k in M.shareable_addresses()].index("cgnat-tailscale")
      < min([i for i, (_, k) in enumerate(M.shareable_addresses())
             if k == "virtual"] or [99]),
      "a remote friend's only working address must beat a dead one")

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