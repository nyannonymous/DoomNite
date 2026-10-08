"""HTTP surface for multiplayer, kept out of serve.py on purpose.

serve.py's do_POST is already ~180 lines of flat `if path == ...` branches, and
adding three more inline branches there is how the block got mangled once
already (a botched edit left the file unparseable). So multiplayer gets its own
dispatch function returning (status, payload), and serve.py stays a two-line
call. Each function here is also directly testable without a socket.

Security, matching /api/launch exactly:
  * `index` is an integer into the pack's own entry list, never a path.
  * `addr` is parsed by mp_session._check_addr (four octets + port) and
    rebuilt; it is never interpolated into a shell string.
  * Nothing a request supplies ever becomes a filesystem path or an argument.
"""
import json as _json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

DEFAULT_PORT = 23513


def normalise_name(value):
    """A player name, safe to show and safe to write to a log.

    Strip noise characters, collapse whitespace, cap at 16 (Zandronum's
    practical scoreboard width), and fall back to "NukemNet" rather than
    passing an empty name through -- a blank name is the same identity
    collision as any duplicate, with less information.

    NOT an injection fix: Popen takes argv as a list, so no shell parses this.
    It is about what other players see and what lands in the engine's log.
    """
    cleaned = "".join(c for c in str(value or "")
                      if c.isprintable() and c not in _NAME_STRIP)
    return (" ".join(cleaned.split())[:16]).strip() or "NukemNet"

# Characters dropped from a player name. A set literal, not an inline string,
# so the backslash cannot turn into a syntax error inside a quote -- which is
# exactly how the first version of this broke.
_NAME_STRIP = set('"\\\'`;&|<>$^\n\r\t')


def _body(handler, limit=4096):
    """(raw_dict, error_response). `error_response` is None when the body is fine."""
    n = int(handler.headers.get("Content-Length") or 0)
    if n > limit:
        return None, (413, {"error": "body too large"})
    try:
        raw = _json.loads(handler.rfile.read(n) or b"{}")
    except ValueError:
        return None, (400, {"error": "bad json"})
    if not isinstance(raw, dict):
        return None, (400, {"error": "body must be an object"})
    return raw, None


def _int(raw, key, default=None, required=False):
    """(value, error). Rejects bools on purpose: True is an int in Python and
    `index: true` must not resolve to entry 1."""
    if key not in raw or raw[key] is None:
        if required:
            return None, (400, {"error": f"{key} is required"})
        return default, None
    v = raw[key]
    if isinstance(v, bool) or not isinstance(v, int):
        return None, (400, {"error": f"{key} must be an integer"})
    return v, None


def setup(handler, resolve):
    """POST /api/multiplayer/setup -- do everything the user should not have to.

    Creates NN's junctions, refreshes its preset, and reports whether this
    machine can host at all. Idempotent, so the UI can call it every time the
    button is pressed.
    """
    raw, err = _body(handler)
    if err:
        return err
    idx, err = _int(raw, "index", default=0)
    if err:
        return err
    try:
        import mp_session
        ok, lines = mp_session._ensure_ready()
        return 200, {"ok": bool(ok), "ready": mp_session.describe(idx),
                     "log": lines}
    except Exception as exc:
        return 500, {"error": str(exc)}


def host(handler, resolve):
    """POST /api/multiplayer/host -- start a hosted game, no NN GUI involved."""
    return _launch(handler, resolve, "host")


def join(handler, resolve):
    """POST /api/multiplayer/join -- connect to a known address."""
    return _launch(handler, resolve, "join")


def _launch(handler, resolve, mode):
    parsed, err = _body(handler)
    if err:
        return err
    # _body returns (dict, None) on success, so parsed is a dict here. The
    # explicit None check keeps a future change to _body's contract from
    # turning into an AttributeError instead of a 400.
    raw = parsed if isinstance(parsed, dict) else {}
    idx, err = _int(raw, "index", required=True)
    if err:
        return err
    entry = resolve(idx)
    if entry is None:
        return 400, {"error": "no such entry"}

    port = raw.get("port", DEFAULT_PORT)
    if isinstance(port, bool) or not isinstance(port, int):
        return 400, {"error": "port must be an integer"}
    if not (1024 < port < 65536):
        return 400, {"error": "port must be 1025-65535"}

    try:
        import mp_session
        # Name is DISPLAY-ONLY but still validated, because it reaches the
        # engine as `+name` and `+sv_hostname`, and because Zandronum keys its
        # scoreboard and its connect/disconnect log by it. Two players sharing
        # a name produce one scoreboard row and a confusing "<name> joined"
        # line for what is really a second instance -- the owner's
        # two-instance screenshot showed exactly that, because the panel was
        # sending the GAME LABEL as the player name.
        #
        # Normalised in three steps:
        #   * characters that would be noise in a log or a scoreboard column
        #     are dropped. This is NOT an injection fix -- Popen takes argv as a
        #     list and no shell ever sees it -- but a name is shown to other
        #     players, and carrying quotes and control characters into the
        #     engine's own log file helps nobody.
        #   * whitespace collapses, then the result is capped at 16, which is
        #     Zandronum's practical scoreboard width. The cap is applied AFTER
        #     collapsing, and stripped again after it: slicing can otherwise
        #     leave a trailing space, and "Brutal Doom v22 " looks like a typo.
        #   * an empty result falls back rather than being passed through. A
        #     blank name is the same collision with less detail.
        name = normalise_name(raw.get("name"))
        fp_state, ours = None, None
        if mode == "host":
            argv = mp_session.host_argv(idx, port, hostname=name,
                                        deathmatch=bool(raw.get("deathmatch")))
            # Memoised: this hashes the entry's whole load list.
            ours = mp_session._fingerprint_cached(idx)
        else:
            # The pasted line may be "1.2.3.4:23513 ABCD1234". Split it here so
            # the fingerprint is compared explicitly rather than being left
            # inside the string the address parser silently discards.
            addr = str(raw.get("addr") or "")
            _h, _p, inline_fp = mp_session.split_addr_and_fp(addr)
            argv = mp_session.join_argv(idx, addr, hostname=name)
        # The fingerprint is optional and NEVER blocks a join. The joiner pastes
        # "1.2.3.4:23513 ABCD1234"; a match is reported, a mismatch warns but
        # still connects -- a near-identical build is worth trying, and refusing
        # would leave someone stuck with no way to diagnose a subtle desync.
        if mode == "join":
            # An explicit field wins over one embedded in the address, so a
            # future UI can send them separately without changing this.
            given = str(raw.get("fingerprint") or "") or inline_fp
            fp_state, ours = mp_session.compare_fingerprint(idx, given)
    except ValueError as e:
        # Malformed address, or an entry that cannot be played online. That is
        # the caller's input being wrong, not a server fault -- so 400, and the
        # message is written for a human rather than for a log.
        return 400, {"error": str(e)}
    except Exception as exc:
        return 500, {"error": str(exc)}

    try:
        # Detached via cmd /c start, so closing DoomNite cannot kill a hosted
        # game -- the same reason launch() does this. /D sets the working
        # directory to the folder the engine's relative paths expect.
        subprocess.Popen(
            ["cmd", "/c", "start", "", "/D", os.path.dirname(argv[0])] + argv,
            cwd=os.path.dirname(argv[0]),
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    except OSError as e:
        return 500, {"error": str(e)}

    import mp_session
    return 200, {
        "ok": True,
        "label": entry.get("label", ""),
        "command": " ".join(argv),
        "fingerprint": ours,
        # None when nothing was pasted to compare, True on a match, False on a
        # mismatch. The UI must only warn -- never block -- on False.
        "mod_match": fp_state,
        # Only a host has something to share; a joiner has nothing to hand on.
        # The fingerprint rides along so the joiner can check they are running
        # the same bytes before connecting.
        "sharing": ({"port": port,
                     # (ip, kind) pairs, best-first, so the UI can label a
                     # Tailscale address as "only works if they are on my VPN"
                     # instead of offering it like a LAN address.
                     "addresses": [
                         {"ip": ip, "kind": kind}
                         for ip, kind in mp_session.shareable_addresses()
                     ],
                     "fingerprint": ours}
                    if mode == "host" else None),
    }


# The path -> (method, handler) table serve.py consults. Keeping it explicit
# means an unknown multiplayer path 404s like every other unknown path.
ROUTES = {
    "/api/multiplayer/setup": setup,
    "/api/multiplayer/host": host,
    "/api/multiplayer/join": join,
}


def handles(path):
    return path in ROUTES