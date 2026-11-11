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
import base64
import json as _json
import os
import subprocess
import sys
import time

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

    Runs the hidden prep (NN's junctions and preset, when NN is here at all),
    then answers the question the panel actually needs: can this machine start
    a game for this entry? Idempotent, so the UI can call it every time the
    button is pressed.

    `ok` is that answer -- engine and IWAD present -- and NOT whether the
    NukemNet step succeeded. NukemNet is not needed to host or join, so a
    machine without it used to get `ok: false` and a log line calling a working
    machine unconfigured; anything reading that field would fail closed on a
    fresh install. `log` stays the prep step's own report, for diagnosis.
    """
    raw, err = _body(handler)
    if err:
        return err
    idx, err = _int(raw, "index", default=0)
    if err:
        return err
    try:
        import mp_session
        # Prep first, THEN describe: `ready.nn.linked` is read off the disk and
        # is meant to report the state after this call, which is how it read
        # before. can_play() does not depend on either step.
        #
        # EDuke32 entries skip the prep entirely. The NukemNet junction/preset
        # step is Zandronum machinery: running it for a Duke game printed the
        # scan of NN's doom/doom2 file lists -- "DOOM2.WAD <- MISSING" and
        # friends -- into the panel's log for a game that never touches
        # Zandronum, IWADs or NukemNet. That log read like a failure and
        # convinced at least one player Duke multiplayer was broken while the
        # engine was, in fact, about to launch.
        ready = mp_session.describe(idx)
        if ready.get("engine") == "eduke32":
            lines = ["EDuke32 LAN multiplayer: the engine ships inside the "
                     "pack, so there is nothing to set up. Host or join with "
                     "a plain IP address (LAN or VPN; the engine has no "
                     "internet matchmaking of its own)."]
        else:
            _prepared, lines = mp_session._ensure_ready()
        ok = bool(ready.get("can_play"))
        return 200, {"ok": ok,
                     "error": None if ok else (ready.get("why") or
                                               "Multiplayer is not set up on "
                                               "this machine."),
                     "ready": ready,
                     "log": lines}
    except Exception as exc:
        return 500, {"error": str(exc)}


def host(handler, resolve):
    """POST /api/multiplayer/host -- start a hosted game, no NN GUI involved."""
    return _launch(handler, resolve, "host")


def join(handler, resolve):
    """POST /api/multiplayer/join -- connect to a known address."""
    return _launch(handler, resolve, "join")


# EDuke32's net port is hardwired: no -port flag exists and -connect takes a
# bare host only, so every Duke game lives on this one UDP port. Empirically
# confirmed on the shipped engine (netstat during a -server run). It happens
# to be the same port the Zandronum flow uses as DEFAULT_PORT, which is why
# the punch/relay machinery's assumptions line up.
DUKE_NET_PORT = 23513
# The loopback address the JOIN side's relay socket binds. The engine's own
# socket is a wildcard bind of the same port, and a UDP send to 127.0.0.1:<own
# port> is delivered back into the engine itself -- a relay on 127.0.0.1 never
# sees a packet. 127.0.0.2 is a distinct loopback address (all of 127/8 works
# on Windows), so the engine can dial it as a bare IP and its packets arrive
# at the tunnel. Verified live before this constant existed.
DUKE_RELAY_BIND = "127.0.0.2"


def _launch_duke(idx, entry, mode, raw):
    """Host/join an EDuke32 game on its own netcode.

    EDuke32 has no -port flag and no fingerprint: the share line is a bare
    address, and joining is -connect <ip>. Two transports:

    * direct (default): the pasted address is used as-is. LAN, or a VPN like
      Tailscale, where no NAT stands between the players.
    * relay ({"relay": true}): both sides connect outbound to the DoomNite
      Cloudflare worker (the same tunnel SkyJump3D and the Zandronum flow
      use), so no NAT has to be punched at all. The joiner's engine dials
      127.0.0.2 -- the tunnel's bind address -- because the engine cannot be
      told a port, only a host.
    """
    import mp_session
    want_relay = bool(raw.get("relay"))
    tunnel = None
    argv = None
    # A relay host needs a room before anything else: generated when the
    # panel didn't send one, same alphabet as the Zandronum flow.
    room = str(raw.get("room") or "").strip()
    try:
        if mode == "host":
            if want_relay and not room:
                import base64
                room = base64.b32encode(os.urandom(5)).decode().rstrip("=").lower()
            argv = mp_session.duke_host_argv(
                idx, deathmatch=bool(raw.get("deathmatch")))
        elif want_relay:
            room = str(raw.get("room") or "").strip()
            if not room:
                return 400, {"error": "Paste the room code they gave you, "
                                      "or use Host."}
        else:
            addr = str(raw.get("addr") or "").strip()
            if not addr:
                return 400, {"error": "Paste the address they gave you, "
                                      "or use Host."}
            argv = mp_session.duke_join_argv(idx, addr)
    except ValueError as e:
        return 400, {"error": str(e)}
    except Exception as exc:
        return 500, {"error": str(exc)}

    relay_payload = {}
    if want_relay:
        import wsrelay as _wsrelay
        if mode == "host":
            # The engine is already bound to DUKE_NET_PORT by the time this
            # returns, so the tunnel forwards inbound relay traffic straight
            # into it. A join request replaces an older tunnel first.
            tunnel = _wsrelay.start_tunnel("host", room)
            tunnel.set_engine_target("127.0.0.1", DUKE_NET_PORT)
            relay_payload = {"room": tunnel.room, "mode": "relay"}
        else:
            # The tunnel MUST own the engine's hardwired port on the loopback
            # alias BEFORE the engine starts: the engine dials 127.0.0.2 (its
            # -connect target) and every packet it sends must land in the
            # tunnel, not in its own wildcard socket. Binding 127.0.0.2 while
            # the engine holds the wildcard works on Windows; verified live.
            try:
                tunnel = _wsrelay.start_tunnel(
                    "join", room, local_port=DUKE_NET_PORT,
                    bind_ip=DUKE_RELAY_BIND)
            except OSError as e:
                return 502, {"error": (
                    "Could not hold the engine's network port for the relay "
                    "(another Duke game may already be running): "
                    + str(e))}
            argv = mp_session.duke_join_argv(idx, DUKE_RELAY_BIND)
            relay_payload = {"room": tunnel.room,
                             "connect": DUKE_RELAY_BIND, "mode": "relay"}
    if argv is None:
        # Unreachable by construction -- every mode/transport pair above
        # either builds argv or returns -- but a None here would Popen a
        # TypeError instead of an answer, and the panel would hang.
        if tunnel:
            tunnel.stop()
        return 500, {"error": "internal: no command line was built"}

    try:
        # cmd start detaches, so the Popen handle is the launcher, not the
        # engine -- the engine PID comes from tasklist right after.
        subprocess.Popen(
            ["cmd", "/c", "start", "", "/D", os.path.dirname(argv[0])] + argv,
            cwd=os.path.dirname(argv[0]), env=mp_session.launch_env(),
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    except OSError as e:
        if tunnel:
            tunnel.stop()
        return 500, {"error": str(e)}

    if tunnel is not None and mode == "host":
        # The tunnel must forward into the port the engine ACTUALLY bound.
        # It is 23513 except when that port was taken and the engine fell
        # back to an ephemeral one -- discover it instead of assuming.
        engine_pid = None
        deadline = time.time() + 15
        while engine_pid is None and time.time() < deadline:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq eduke32.exe"],
                                 capture_output=True, text=True).stdout
            pids = [l.split()[1] for l in out.splitlines()
                    if "eduke32" in l.lower()]
            if pids:
                engine_pid = int(pids[0])
            else:
                time.sleep(0.5)
        port = mp_session.duke_engine_udp_port(engine_pid) if engine_pid else None
        if port:
            tunnel.set_engine_target("127.0.0.1", port)
        else:
            tunnel.stop()
            return 500, {"error": "The Duke engine did not open a network "
                                  "port, so internet hosting cannot start."}
        # Announce the room in the shared lobby, same as the Doom relay
        # host path: a Duke host shows up in everyone's "Open games" list,
        # so a friend joins by CLICKING instead of typing a code someone
        # read out. mode "duke" keeps the two engines' rooms apart. The
        # heartbeat thread also removes the room when the engine dies.
        import lobby as _lobby
        _lobby.keep_announced(tunnel.room, entry.get("label", ""), "duke",
                              tunnel.alive)

    sharing = None
    if mode == "host":
        sharing = {
            # No port: EDuke32 fixes its own, and the address is bare.
            "port": None,
            "addresses": [{"ip": ip, "kind": kind}
                          for ip, kind in mp_session.shareable_addresses()],
            "public": {"kind": "unavailable"},
            "fingerprint": None,
            "engine": "eduke32",
        }

    return 200, {
        "ok": True,
        "label": entry.get("label", ""),
        "command": " ".join(argv),
        "engine": "eduke32",
        "sharing": sharing,
        "relay": relay_payload or None,
    }


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

    # EDuke32 games play their own netcode: a bare address, no -port flag, no
    # fingerprint, no STUN/relay punch. None of the Zandronum machinery below
    # applies, so divert before any of it runs.
    if entry.get("engine") == "eduke32":
        return _launch_duke(idx, entry, mode, raw)

    port = raw.get("port", DEFAULT_PORT)
    if isinstance(port, bool) or not isinstance(port, int):
        return 400, {"error": "port must be an integer"}
    if not (1024 < port < 65536):
        return 400, {"error": "port must be 1025-65535"}

    # STUN punch mode for this launch. Same routes, same body, one new
    # flag -- the UI asks for it by sending {"stun": true}. Nothing else
    # about the request changes: direct (LAN/Tailscale) play and punched
    # play are the same flow with one extra bulletproof step on the wire.
    want_stun = bool(raw.get("stun"))

    # Relay-tunnel mode: DoomNite's own Cloudflare Worker (cloudflare/relay/),
    # same trick that already works for SkyJump3D -- both sides connect
    # OUTBOUND to one wss:// endpoint, so there is no NAT to punch and no
    # port to forward. Mutually exclusive with STUN: they are two different
    # answers to "how do we reach across the internet", and relay is the one
    # that works when STUN's punch can't (symmetric NAT, a firewall that
    # eats the punched path) at the cost of a round trip through Cloudflare
    # instead of a direct peer path.
    want_relay = bool(raw.get("relay"))
    tunnel = None
    relay_payload = {}
    if want_relay and want_stun:
        return 400, {"error": "stun and relay are alternatives, not both"}
    if want_relay:
        import wsrelay as _wsrelay
        if mode == "join":
            room = str(raw.get("room") or "").strip()
            if not room:
                return 400, {"error": "room is required to join over the relay"}
        else:
            room = str(raw.get("room") or "").strip() or base64.b32encode(os.urandom(5)).decode().rstrip("=").lower()
        tunnel = _wsrelay.start_tunnel("host" if mode == "host" else "join", room)

    relay = None
    punch_payload = {}
    host_ip, host_port = None, None
    if want_stun:
        import punch as _punch
        # One relay per side at a time, and a NEW request replaces an
        # older one: the share line the user handed out names THAT
        # socket's mapping, so an orphaned relay is a silent dead address.
        # start_relay() stops the previous one on purpose.
        relay = _punch.start_relay("host" if mode == "host" else "join")
        try:
            # THE mapping question. Must be answered on the relay's own
            # socket: a second socket's answer would describe a path the
            # engine never sends on. ~4 servers x ~2 s worst case; live
            # probes have answered in a few hundred ms.
            mapped = relay.map_with_stun()
            if mapped is None:
                relay.stop()
                _punch.RELAYS.pop("host" if mode == "host" else "join", None)
                return 502, {"error": (
                    "No STUN server answered, so DoomNite cannot open the "
                    "internet hole here. Check the connection (or play on "
                    "the same network / VPN instead).")}
            if mode == "host" and relay.nat == "symmetric":
                # Refuse BEFORE launching: the host's published endpoint
                # would be a lie for every peer, punches would fail with no
                # error anywhere, and the fix (Tailscale / NukemNet) is a
                # user choice no panel can make for them.
                relay.stop()
                _punch.RELAYS.pop("host" if mode == "host" else "join", None)
                return 400, {"error": (
                    "Your router gives every internet destination a "
                    "different port (symmetric NAT), so the punch can't "
                    "open a stable path. Host with NukemNet or make it a "
                    "Tailscale LAN instead -- both work with no changes "
                    "from the other player.")}
        except Exception as exc:
            # Probe failure is a state, not a game. The engine must not
            # start into a hole nobody drilled.
            try:
                relay.stop()
                _punch.RELAYS.pop("host" if mode == "host" else "join", None)
            except Exception:
                pass
            return 502, {"error": f"the STUN probe failed: {exc}"}

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
        inline_fp = ""
        if mode == "host":
            argv = mp_session.host_argv(idx, port, hostname=name,
                                        deathmatch=bool(raw.get("deathmatch")))
            # Memoised: this hashes the entry's whole load list.
            ours = mp_session._fingerprint_cached(idx)
            if want_relay:
                # No learning step needed -- the host's engine port is
                # already known, so point the tunnel at it directly.
                tunnel.set_engine_target("127.0.0.1", port)
            elif want_stun and relay:
                relay.set_engine_target("127.0.0.1", port)
        elif want_relay:
            # A relay join has no address to parse at all: there is
            # nothing routable to paste, only the room code the host
            # shared and (optionally) its fingerprint, sent as separate
            # fields rather than packed into an "addr" string.
            argv = mp_session.join_argv(idx, "127.0.0.1:%d" % tunnel.local_port,
                                        hostname=name)
        else:
            # The pasted line may be "1.2.3.4:23513 ABCD1234". Split it here so
            # the fingerprint is compared explicitly rather than being left
            # inside the string the address parser silently discards.
            addr = str(raw.get("addr") or "")
            _h, _p, inline_fp = mp_session.split_addr_and_fp(addr)
            host_ip, host_port = _h, int(_p)
            # PUNCHED joins never dial the host's real address: the engine
            # gets the loopback relay, whose socket has already punched
            # toward the real endpoint, so the route is one path with all
            # its packets on it. The real address becomes the relay's peer
            # (set below, right before the engine starts).
            if want_stun:
                argv = mp_session.join_argv(idx, "127.0.0.1:%d" % relay.local_port,
                                            hostname=name)
            else:
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
        if tunnel:
            import wsrelay as _wsrelay
            tunnel.stop()
            _wsrelay.TUNNELS.pop("host" if mode == "host" else "join", None)
        return 400, {"error": str(e)}
    except Exception as exc:
        if tunnel:
            import wsrelay as _wsrelay
            tunnel.stop()
            _wsrelay.TUNNELS.pop("host" if mode == "host" else "join", None)
        return 500, {"error": str(exc)}

    if want_relay and mode == "join":
        relay_payload = {"room": tunnel.room, "connect": "127.0.0.1:%d" % tunnel.local_port, "mode": "relay"}

    if want_stun and relay:
        import punch as _punch
        relay.start()
        if mode == "host":
            # Only the HOST can be firewalled for inbound on the punch
            # socket (the joiner's replies ride its outbound flow). Windows
            # Firewall applies Block before Allow, which is EXACTLY the
            # state these rules can reach: a program-block on this very
            # python.exe for the Public profile says the punched packets
            # will be dropped and the user must be TOLD, not left guessing
            # while the share line looks fine.
            # Payload assembled HERE rather than beside the probe: the share
            # line embeds the entry fingerprint, which is only defined after
            # the argv block below — the first version built it early and
            # died with UnboundLocalError on every punched host, found by
            # selftest_stun.py's contract section before any real session.
            fw = _firewall_advisory()
            _ip, _mp = relay.mapped
            punch_payload = {"ip": _ip, "punch_port": _mp,
                             "nat": relay.nat,
                             "local_port": relay.local_port,
                             "line": (f"{_ip}:{_mp} {ours or ''}".strip()),
                             "firewall": fw}
        else:
            # BEFORE the engine starts, not after: the first packet out of a
            # fresh Zandronum client may already be the server handshake, and
            # without a peer that packet is held back -- a held-back handshake
            # is a silent connect that never completes.
            relay.set_peer(host_ip, host_port, lock=True)
            punch_payload = {"connect": "127.0.0.1:%d" % relay.local_port,
                             "host": f"{host_ip}:{host_port}", "nat": relay.nat}

    if want_relay and mode == "join" and tunnel is not None:
        # Launch the engine only once THIS side's websocket has actually
        # reached the Worker (bounded): starting Zandronum toward a relay
        # that never connected is another silent "Connecting" forever. A
        # terminal 'room full' close (new client vs old worker both stop
        # and report it) fails the launch with a clear reason instead.
        deadline = time.time() + 10.0
        while not tunnel.connected and tunnel.state not in ("stopped",):
            if time.time() >= deadline:
                tunnel.stop()
                import wsrelay as _wsrelay
                _wsrelay.TUNNELS.pop("join", None)
                return 502, {"error": (
                    "Could not reach the game relay to join that room. "
                    "Check your connection and try again -- the host's "
                    "game is probably still up." + (
                        " (" + tunnel.last_error + ")" if tunnel.last_error else ""))}
            time.sleep(0.25)
        if tunnel.state == "stopped" and tunnel.last_error:
            import wsrelay as _wsrelay
            _wsrelay.TUNNELS.pop("join", None)
            return 502, {"error": "Join failed: " + tunnel.last_error}

    try:
        # Detached via cmd /c start, so closing DoomNite cannot kill a hosted
        # game -- the same reason launch() does this. /D sets the working
        # directory to the folder the engine's relative paths expect.
        subprocess.Popen(
            ["cmd", "/c", "start", "", "/D", os.path.dirname(argv[0])] + argv,
            cwd=os.path.dirname(argv[0]), env=mp_session.launch_env(),
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    except OSError as e:
        # The engine never started: a relay host must not leave a tunnel or
        # a public listing behind. (The STUN path has nothing registered yet.)
        if tunnel is not None:
            import wsrelay as _wsrelay
            tunnel.stop()
            _wsrelay.TUNNELS.pop("host" if mode == "host" else "join", None)
        return 500, {"error": str(e)}

    if want_relay and mode == "host":
        # Bounded engine-readiness gate: Popen of `cmd /c start` proves
        # nothing, so wait until something is ACTUALLY bound to the engine's
        # UDP port before declaring the room public. Advertising a room
        # whose engine never opened its socket is exactly the failure this
        # file exists to prevent: the joiner clicks, connects to the relay,
        # and talks to nobody, forever.
        deadline = time.time() + 12.0
        while not _udp_port_taken(port):
            if time.time() >= deadline:
                import wsrelay as _wsrelay
                tunnel.stop()
                _wsrelay.TUNNELS.pop("host", None)
                return 502, {"error": (
                    "The game engine started but never opened its network "
                    "port (%d/UDP). Check the game window for an error "
                    "dialog, then try hosting again." % port)}
            time.sleep(0.4)

        # Now -- engine port confirmed bound. The announce is SYNCHRONOUS
        # (one bounded round trip) so the response can honestly say whether
        # the room is public; keep_announced then re-announces + heartbeats
        # in the background and removes the room when the tunnel dies. A
        # failed first announce is REPORTED (`listed: false`) instead of
        # firing a daemon thread and hoping -- the host toast must never
        # claim "it's listed" for a room the directory never accepted.
        import lobby as _lobby
        listed, list_err = _lobby.announce_ex(tunnel.room, entry.get("label", ""), "doom")
        # Record the SYNC verdict in the tunnel's lobby_status too: the
        # background thread overwrites it with the same (re-announced)
        # verdict moments later, but between the response and that thread's
        # first cycle, relay-status must agree with what we just told the UI.
        tunnel.lobby_status.update({
            "announced": listed, "error": list_err,
            "listed_at": time.time() if listed else None})
        _lobby.keep_announced(tunnel.room, entry.get("label", ""), "doom", tunnel.alive,
                              status=tunnel.lobby_status)
        relay_payload = {"room": tunnel.room, "mode": "relay",
                         "listed": listed, "list_error": list_err}

    import mp_session

    # Only a host has something to share; a joiner has nothing to hand on. The
    # fingerprint rides along so the joiner can check they are running the same
    # bytes before connecting.
    #
    # Built here rather than inline so the STUN probe only runs for a host: an
    # expression inside the return dict would pay its round trip on the join
    # path too, where nothing is ever shown.
    sharing = None
    if mode == "host":
        # The one address a friend OUTSIDE the network can use, which
        # shareable_addresses() can never produce because it only ever
        # describes a local adapter. Appended only when STUN reports a
        # globally routable mapping: a CGNAT mapping is withheld, because
        # telling someone to forward a port to an address their ISP is
        # already NATing is worse than saying nothing.
        pub = mp_session.public_endpoint()
        addresses = [{"ip": ip, "kind": kind}
                     for ip, kind in mp_session.shareable_addresses()]
        if pub.get("kind") == "public":
            addresses.append({"ip": pub["ip"], "kind": "public"})
        sharing = {
            "port": port,
            # (ip, kind) pairs, best-first, so the UI can label a Tailscale
            # address as "only works if they are on my VPN" instead of
            # offering it like a LAN address.
            "addresses": addresses,
            # The verdict itself, so the panel can explain a WITHHELD address
            # instead of leaving the user wondering why there is no internet
            # line at all.
            "public": pub,
            "fingerprint": ours,
        }

    return 200, {
        "ok": True,
        "label": entry.get("label", ""),
        "command": " ".join(argv),
        "fingerprint": ours,
        # None when nothing was pasted to compare, True on a match, False on a
        # mismatch. The UI must only warn -- never block -- on False.
        "mod_match": fp_state,
        "sharing": sharing,
        # Present when this launch ran the punch path; the key is simply
        # absent otherwise, so the UI reacts to its presence alone.
        **({"punch": punch_payload} if punch_payload else {}),
        # Same convention for the relay-tunnel path: a host gets a room
        # code to share (there is no ip:port -- nothing is routable), a
        # joiner gets confirmation of the local loopback address the engine
        # is actually talking to.
        **({"relay": relay_payload} if relay_payload else {}),
    }


# ---------------------------------------------------------------- firewall
_FW_CACHE = {"t": 0.0, "payload": {"ok": True, "rule": None, "why": None}}


def _firewall_advisory():
    """Will Windows Firewall let punched packets IN to this process?

    Windows-only, tolerant, and definitive wherever netsh can answer. The
    trap this file's history documented (Block beats Allow; the owner's
    zandronum.exe had TEN such rules) applies byte for byte to the python
    that runs the punch socket: two inbound Block rules on python.exe exist
    for the Public profile on the machine this tier was built on. An Allow
    for the Private profile does not oppose a Block for the Public one,
    because each profile is judged on its own.

    Cached ~30 s: netsh costs a few hundred ms, and the host flow may be
    retried while the user dithers over the invitation dialog.
    """
    import time as _time
    import re as _re
    when = _time.time()
    if when - _FW_CACHE["t"] < 30:
        return _FW_CACHE["payload"]

    out = {"ok": True, "rule": None, "why": None}
    if os.name != "nt":
        _FW_CACHE.update({"t": when, "payload": out})
        return out
    try:
        me = os.path.normcase(os.path.abspath(sys.executable))
        txt = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule",
             "name=all", "dir=in", "verbose"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10).stdout or ""
        for block_text in txt.split("\n\n"):
            if "python.exe" not in block_text.lower():
                continue
            if not _re.search(r"Action[ \t]*:[ \t]*Block\b", block_text):
                continue
            m = _re.search(r"Program[ \t]*:[ \t]*(\S+)", block_text)
            prog = os.path.normcase(m.group(1)) if m else ""
            if prog != me:
                continue
            if not _re.search(r"Protocol[ \t]*:[ \t]*UDP\b", block_text):
                continue
            rname = _re.search(r"Rule Name[ \t]*:[ \t]*(.+)", block_text)
            out = {"ok": False,
                   "rule": rname.group(1).strip() if rname else "a block rule",
                   "why": ("Windows Firewall has an inbound BLOCK rule on "
                           "the python that would run the punch socket, "
                           "Public profile -- and Block beats Allow, so "
                           "the punched packets would be dropped. Clear "
                           "that block rule (or host over Tailscale, whose "
                           "adapter is Private).")}
            break
    except Exception:
        # An unreadable firewall state must never stop a launch the user
        # asked for: report unknown-ok and let the real session tell.
        out = {"ok": True, "rule": None, "why": None}
    _FW_CACHE.update({"t": when, "payload": out})
    return out


def _udp_port_taken(port: int) -> bool:
    """True once SOMETHING on this machine is bound to UDP `port` (the
    engine's listen socket). Probed by attempting a brief bind of our own:
    a normal UDP socket does not set SO_REUSEADDR, so a second bind of a
    live engine's port fails immediately. Cheap, Windows-safe, and the only
    launch-side signal available -- `cmd /c start` detaches, so there is no
    process handle to poll and a Popen success proves nothing about the
    engine (see the host path below, which now waits on this)."""
    import socket as _socket
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
    try:
        s.bind(("0.0.0.0", port))
        return False
    except OSError:
        return True
    finally:
        s.close()


def lobby_list(handler, resolve):
    """POST /api/multiplayer/lobby -- the open-rooms list, proxied server
    side rather than fetched by the browser/renderer directly, so the UI
    never needs CORS or to know the relay Worker's URL at all; it is just
    another same-origin call to the pack's own local server, like every
    other /api/ route. Body is ignored (no filters yet); accepts POST only
    to match this file's one route shape (serve.py's table is POST-only).

    `lobby_ok`/`lobby_error` separate "directory reachable, zero rooms"
    from "directory unreachable" -- the UI must never show the former's
    friendly empty state for the latter."""
    import lobby as _lobby
    rooms, err = _lobby.list_rooms_ex()
    return 200, {"ok": True, "rooms": rooms,
                 "lobby_ok": err is None,
                 "lobby_error": err,
                 "checked_at": int(time.time())}


def relay_status(handler, resolve):
    """POST /api/multiplayer/relay-status -- what the active tunnel(s) are
    ACTUALLY doing, as distinct from "a launch request succeeded once":
    ws state to the Worker, whether the peer seat has joined, packet
    counters, last traffic times, and (host side) whether the engine's UDP
    port is still held. Read-only; absent when a side has no tunnel."""
    import wsrelay as _wsrelay
    import punch as _punch
    out = {}
    for side in ("host", "join"):
        t = _wsrelay.TUNNELS.get(side)
        if t is not None:
            st = t.status()
            if side == "host" and t.engine_src:
                st["engine_port"] = t.engine_src[1]
                st["engine_bound"] = _udp_port_taken(t.engine_src[1])
            out[side] = st
        r = _punch.RELAYS.get(side)
        if r is not None:
            try:
                out[side] = {**out.get(side, {}), "punch": r.status()}
            except Exception:
                pass
    return 200, {"ok": True, **out}


# The path -> (method, handler) table serve.py consults. Keeping it explicit
# means an unknown multiplayer path 404s like every other unknown path.
ROUTES = {
    "/api/multiplayer/setup": setup,
    "/api/multiplayer/host": host,
    "/api/multiplayer/join": join,
    "/api/multiplayer/lobby": lobby_list,
    "/api/multiplayer/relay-status": relay_status,
}


def handles(path):
    return path in ROUTES