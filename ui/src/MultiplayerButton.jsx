import { useState, useCallback, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Users } from "lucide-react";

/* ---------------------------------------------------------------
   MULTIPLAYER -- host or join a game, without NukemNet.

   The whole point of this panel is that the user never has to know
   NukemNet exists, never opens it, and never runs a command.

   Pressing MULTIPLAYER:
     1. calls /api/multiplayer/setup, which does the hidden prep server-side
        (NukemNet's junctions and preset, when NN is on the machine at all --
        it is optional and multiplayer does not need it) and reports whether a
        game can actually be started (idempotent, safe every time);
     2. shows two buttons: HOST and JOIN.

   HOST starts Zandronum with -host and reports what to share.
   JOIN takes an address and starts Zandronum with +Connect.

   Why no NukemNet GUI is needed: NN's own log records the whole session as
   plain Zandronum arguments -- `-host 64 -port 23513 +sv_hostname ...` to
   host, `+Connect host:port` to join. The room list is the only part that
   genuinely needs NN's network, and that is deliberately out of scope here;
   the UI says so rather than pretending otherwise.

   Props
   -----
   toast(msg, bad?)   -- the App-level toast callback
   entries            -- flat entry array from /api/entries
   selected           -- the entry index the sidebar/grid is on, so "play
                        multiplayer" defaults to the game you are looking at
   --------------------------------------------------------------- */
export default function MultiplayerButton({ toast, entries = [], selected = null }) {
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState("idle");   // idle | working | ready | error
  const [ready, setReady] = useState(null);     // /setup payload
  // Two different things, deliberately separate. `setupLines` is the server's
  // NukemNet report -- kept only so a failure can be diagnosed, never rendered.
  // `command` is the argument line this session actually ran, which IS shown.
  const [setupLines, setSetupLines] = useState([]);
  const [command, setCommand] = useState("");
  const [pick, setPick] = useState(0);          // position in `playable`
  const [addr, setAddr] = useState("");
  const [dm, setDm] = useState(false);
  // The PLAYER name, not the game name.
  //
  // It used to be the game label, which meant every participant was called
  // "Brutal Doom v22 test 6 [Doom 1]". Zandronum keys its scoreboard and its
  // connect/disconnect log by NAME, so two players shared one identity: the
  // scoreboard showed a single row, and the log read "<game label> joined"
  // for what was really a second instance. The owner's two-instance screenshot
  // showed exactly that -- one row, and a "Player 741" that was the host's own
  // duplicate.
  //
  // "NukemNet" is NukemNet's own default and NN's Settings.json has an
  // InGamePlayerName, so seeding from that keeps this consistent with NN rather
  // than inventing a second convention.
  const [name, setName] = useState(() => {
    try {
      return localStorage.getItem("doomnite.mp.name") || "NukemNet";
    } catch {
      return "NukemNet";   // private mode: works, just not remembered
    }
  });
  const [busy, setBusy] = useState(false);
  const [sharing, setSharing] = useState(null); // what to hand to a friend
  const [punch, setPunch] = useState(null);     // survives only for the STUN tier
  const [relayInfo, setRelayInfo] = useState(null); // survives only for the relay tier
  const [mismatch, setMismatch] = useState(null); // mod differs from the host
  const [err, setErr] = useState(null);
  // The lobby: open relay rooms, polled while the panel is open. A fetch
  // failure here must never surface as the panel's main error -- it just
  // means the list stays empty (or stale), same as any other "can't reach
  // the internet right now" degradation. roomCode is the manual fallback
  // for the one case polling can't cover: the host's room not showing up
  // yet (network hiccup, or they only just announced it).
  const [lobbyRooms, setLobbyRooms] = useState([]);
  const [roomCode, setRoomCode] = useState("");

  /* Which entries can be played online.

     `kind === "pack"` drops the standalone exes (SRB2, Doom Half-Life) --
     multiplayer is Zandronum, and those run their own engine. `iwad` drops
     an entry with no IWAD, because Zandronum needs one to start.

     `exists` is deliberately NOT filtered: an entry whose files are not on
     disk should still be selectable so the user gets "that file is missing"
     rather than a silently shorter list. Zandronum will say so itself.

     THE ORDER IS LOAD-BEARING. _idx is each entry's REAL server index, and it
     is what gets posted. The first version of this file used the array
     position, which is wrong the moment anything is filtered out -- serve.py
     emits no `index` field, so the original `playable[i]?.index ?? i` fell
     through to the position and picking the 12th game launched the wrong one. */
  const playable = entries
    .map((e, i) => ({ ...e, _idx: i }))
    .filter((e) => e.kind === "pack" && e.iwad);

  // Default to the entry the user is actually looking at, else the first.
  useEffect(() => {
    if (selected == null || !playable.length) return;
    const at = playable.findIndex((e) => e._idx === selected);
    if (at >= 0) setPick(at);
  }, [selected, playable.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const chosen = playable[pick];

  // A standing choice, so it survives a reload -- same reasoning as the pinned
  // game in App.jsx.
  useEffect(() => {
    try {
      localStorage.setItem("doomnite.mp.name", name);
    } catch {
      /* non-fatal */
    }
  }, [name]);

  // Poll the open-rooms list while the panel is actually open. Silent on
  // failure -- the verify harness refuses every multiplayer POST except
  // /setup with a fake 418, and that refusal must read as "no rooms right
  // now", not as a panel-breaking error.
  useEffect(() => {
    if (!open) {
      setLobbyRooms([]);
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await fetch("/api/multiplayer/lobby", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
        if (!r.ok) return;
        const d = await r.json();
        if (!cancelled) setLobbyRooms(Array.isArray(d.rooms) ? d.rooms : []);
      } catch {
        /* a dropped lobby fetch should not clear what was already shown */
      }
    };
    poll();
    const id = setInterval(poll, 4000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [open]);

  /* One call does the hidden setup: junctions + preset. Runs every time the
     panel opens, because it is idempotent and because the alternative is the
     user discovering a missing junction only when a game fails to load. */
  const openPanel = useCallback(async () => {
    setOpen(true);
    setPhase("working");
    setErr(null);
    setSetupLines([]);
    setCommand("");
    setSharing(null);
    setPunch(null);
    setMismatch(null);
    try {
      const idx = chosen ? chosen._idx : 0;
      const r = await fetch("/api/multiplayer/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index: idx }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
      setReady(d);
      setSetupLines(d.log || []);
      // The panel is gated on the ENTRY resolving, never on this machine being
      // able to play: a missing engine or a missing WAD is rendered as the
      // status line's reason, with Host/Join still in front of the user. A
      // refused setup shows the panel too -- the user needs to read WHY, not be
      // bounced back to the grid.
      setPhase(d.ready && d.ready.ok ? "ready" : "error");
      if (!d.ready || !d.ready.ok) {
        setErr(d.ready?.error || d.error ||
               "Multiplayer is not set up on this machine.");
      }
    } catch (e) {
      setPhase("error");
      setErr(String(e.message || e));
    }
  }, [chosen]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = useCallback(
    // opts: { stun?: bool, relay?: bool, room?: string }. `room` is only
    // meaningful with relay: true on a join -- it comes from a lobby click
    // or the manual code field, never from `addr`.
    async (which, opts = {}) => {
      if (!chosen) return;
      setBusy(true);
      setErr(null);
      setSharing(null);
      setPunch(null);
      setRelayInfo(null);
      try {
        const body = { index: chosen._idx, port: 23513, name };
        if (opts.stun) body.stun = true;
        if (opts.relay) body.relay = true;
        if (which === "host") {
          body.deathmatch = dm;
        } else if (opts.relay) {
          body.room = opts.room;
        } else {
          // The whole line is sent, code included -- the server splits it, so
          // the user pastes exactly what the host handed them.
          body.addr = addr.trim();
        }
        const r = await fetch(`/api/multiplayer/${which}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const d = await r.json();
        if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
        setCommand(d.command || "");
            if (which === "host") {
          setSharing(d.sharing);
          setPunch(d.punch || null);
          setRelayInfo(d.relay || null);
          setMismatch(null);
          toast(
            opts.relay
              ? `Hosting ${d.label} — it's now listed above for anyone to join.`
              : opts.stun
              ? `Punched an internet path for ${d.label}. Send the internet line to your friend.`
              : `Hosting ${d.label}. Share the address with your friends.`
          );
        } else {
          if (opts.stun) setPunch(d.punch || null);
          if (opts.relay) setRelayInfo(d.relay || null);
          // mod_match is true / false / null (nothing was pasted to check).
          // A mismatch WARNS and still connects: a slightly different build is
          // often still worth trying, and blocking would leave someone stuck
          // with a subtle desync and no way to diagnose it.
          if (d.mod_match === false) {
            setMismatch({ theirs: addr.trim().split(/\s+/)[1] || "", ours: d.fingerprint });
            toast(`Joined ${d.label}, but your mod differs from theirs.`, true);
          } else {
            setMismatch(null);
            toast(
              d.mod_match === true
                ? `Joining ${d.label} — same mod, good.`
                : `Joining ${d.label}…`
            );
          }
        }
      } catch (e) {
        setErr(String(e.message || e));
        toast(String(e.message || e), true);
      } finally {
        setBusy(false);
      }
    },
    [chosen, addr, dm, toast]
  );

  // Escape closes, as it does everywhere else in the app.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button className="mp-btn" onClick={openPanel} aria-label="Multiplayer">
        <Users size={13} aria-hidden="true" /> Multiplayer
      </button>

      {/* PORTALLED to <body>. .topbar sets `backdrop-filter: blur(16px)`, which
          establishes a containing block for `position: fixed` descendants -- an
          overlay rendered in place resolves against the 60px header strip
          instead of the viewport. Measured in Chromium before this was
          understood: the dialog rendered as a squashed sliver. */}
      {open && createPortal(
        <div className="mp-overlay" onClick={() => setOpen(false)}>
          <div className="mp-modal" onClick={(e) => e.stopPropagation()}>
            <header className="mp-header">
              <span className="mp-title">Multiplayer</span>
              <button className="mp-close" onClick={() => setOpen(false)} aria-label="Close">
                &#x2715;
              </button>
            </header>

            <div className="mp-scroll">
              {phase === "working" && (
                <p className="mp-note">Setting up&hellip;</p>
              )}

              {ready && (
                <section className="mp-section">
                  {/* Say what this panel is for before asking for anything.
                      The owner opened it, saw only a name field, and pasted a
                      network address into it. Lead with the choice instead. */}
                  {phase === "ready" && (
                    <p className="mp-lead">
                      Hosting a game or joining one? Everything else is already
                      set up.
                    </p>
                  )}
                  <div className="mp-game">
                    <label className="mp-field">
                      <span className="mp-label">Game</span>
                      <select
                        className="mp-select"
                        value={pick}
                        onChange={(e) => setPick(Number(e.target.value))}
                      >
                        {playable.map((e, i) => (
                          <option key={e._idx} value={i}>
                            {e.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {/* ONE status line, and it reports whether a game can start --
                      never whether NukemNet is installed. The previous version
                      needed `nn.found && nn.linked` to say "Multiplayer is set
                      up", so the machines that most needed to hear it (a fresh
                      install, which does not ship NukemNet) were the only ones
                      that never saw it, and the panel looked unconfigured on a
                      machine where nothing was wrong. NukemNet is not needed to
                      host or join: the engine is started directly. */}
                  {ready.ready && (!ready.ready.zandronum ? (
                    <p className="mp-warn">
                      Zandronum was not found on this machine, so a game cannot
                      be started yet.
                    </p>
                  ) : ready.ready.can_play ? (
                    <p className="mp-ok">
                      Multiplayer is set up. Nothing else to configure.
                    </p>
                  ) : ready.ready.can_play === false ? (
                    <p className="mp-warn">
                      {ready.ready.why || "This game cannot be started yet."}
                    </p>
                  ) : null)}
                </section>
              )}

              {err && (
                <p className="mp-err" role="alert">
                  {err}
                </p>
              )}

              {/* THE EASY PATH. Everything below this (addresses, STUN
                  lines, codes) exists because the engine's own networking
                  needs it -- this section exists so a normal person never
                  has to see any of that. Hosting here lists the game for
                  anyone with DoomNite open; joining is one click. No
                  address, no port, no VPN, on either side. */}
              {phase === "ready" && (
                <section className="mp-section mp-lobby">
                  <h3>Open games</h3>
                  {lobbyRooms.length === 0 ? (
                    <p className="mp-hint">
                      No one's hosting right now — be the first.
                    </p>
                  ) : (
                    <ul className="mp-lobby-list">
                      {lobbyRooms.map((r) => (
                        <li key={r.room} className="mp-lobby-row">
                          <span className="mp-lobby-label">{r.label || "Doom"}</span>
                          <span className="mp-lobby-players">
                            {r.players || 1} player{(r.players || 1) === 1 ? "" : "s"}
                          </span>
                          <button
                            className="mp-action mp-action--primary"
                            onClick={() => start("join", { relay: true, room: r.room })}
                            disabled={busy || !chosen}
                          >
                            Join
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  <button
                    className="mp-action mp-action--primary mp-lobby-host"
                    onClick={() => start("host", { relay: true })}
                    disabled={busy || !chosen}
                  >
                    Host — let anyone find it
                  </button>
                  {relayInfo && relayInfo.room && !relayInfo.connect && (
                    <p className="mp-hint">
                      Your game is listed above now. If a friend's list is
                      slow to update, they can also join by typing this
                      code: <code>{relayInfo.room}</code>
                    </p>
                  )}
                  {/* Fallback for the one gap polling can't cover: a room
                      that hasn't shown up yet. Not the primary path -- the
                      list above is -- so it is small and out of the way. */}
                  <div className="mp-row mp-lobby-code">
                    <input
                      className="mp-input"
                      value={roomCode}
                      onChange={(e) => setRoomCode(e.target.value)}
                      placeholder="Or type a room code"
                      spellCheck={false}
                      autoComplete="off"
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && roomCode.trim()) {
                          start("join", { relay: true, room: roomCode.trim() });
                        }
                      }}
                    />
                    <button
                      className="mp-action"
                      onClick={() => {
                        if (!roomCode.trim()) return;
                        start("join", { relay: true, room: roomCode.trim() });
                      }}
                      disabled={busy || !chosen || !roomCode.trim()}
                    >
                      Join by code
                    </button>
                  </div>
                </section>
              )}

              {phase === "ready" && (
                <section className="mp-section mp-choose">
                  {/* The address field is the first control, not a second
                      screen. Reaching it behind a mode toggle meant the panel
                      appeared to have no way to join at all. */}
                  <label className="mp-field mp-addrfield">
                    <span className="mp-label">
                      Their address — paste the whole line here
                    </span>
                    <input
                      className="mp-input"
                      value={addr}
                      onChange={(e) => setAddr(e.target.value)}
                      placeholder="192.168.0.226:23513 ABCD2345"
                      spellCheck={false}
                      autoComplete="off"
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && addr.trim()) start("join");
                      }}
                    />
                    <span className="mp-hint">
                      Leave this empty to host instead. The code after the port
                      only checks you have the same version.
                    </span>
                  </label>

                  <div className="mp-row mp-choice">
                    <button
                      className="mp-action mp-action--primary"
                      onClick={() => start("host")}
                      disabled={busy || !chosen}
                    >
                      Host a game
                    </button>
                    <button
                      className="mp-action"
                      onClick={() => {
                        // An empty address is a real mistake on Join, not a
                        // request to open another screen. Say so rather than
                        // silently doing nothing.
                        if (!addr.trim()) {
                          setErr("Paste the address they gave you, or use Host.");
                          return;
                        }
                        start("join");
                      }}
                      disabled={busy || !chosen}
                    >
                      Join a game
                    </button>
                  </div>
                  {/* The STUN punch tier: internet play without router work,
                      on the same routes with one body flag. Kept VISIBLE
                      rather than gesture-hidden -- it is the answer to the
                      question this whole multiplayer feature exists for:
                      playing with someone NOT on this network. Cost is real
                      CPU: the host's probe runs first, in place, before the
                      engine can start, and refuses cleanly rather than
                      silently. */}
                  <div className="mp-row mp-choice mp-internet">
                    <button
                      className="mp-action"
                      onClick={() => start("host", { stun: true })}
                      disabled={busy || !chosen}
                    >
                      Host over the internet
                    </button>
                    <button
                      className="mp-action"
                      onClick={() => {
                        if (!addr.trim()) {
                          setErr("Paste the internet line they gave you -- it works exactly like an address here.");
                          return;
                        }
                        start("join", { stun: true });
                      }}
                      disabled={busy || !chosen}
                    >
                      Join over the internet
                    </button>
                  </div>
                  <p className="mp-hint">
                    Internet play with no router changes and no VPN: DoomNite
                    asks STUN servers which port the internet sees for THIS
                    machine, and keeps it open with pings until your friend
                    arrives through it. A few routers hand every destination a
                    different port — the panel says so, and "Host" plus your
                    VPN (or a forwarded port) covers those instead.
                  </p>


                  {/* Deliberately one line of reassurance, not a report. The
                      junctions and the preset are already handled; the user has
                      no action to take here and no reason to care. */}
                  <label className="mp-field mp-field--name">
                    <span className="mp-label">Your name</span>
                    <input
                      className="mp-input"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="NukemNet"
                      maxLength={16}
                      spellCheck={false}
                    />
                  </label>
                  <p className="mp-hint">
                    Everyone playing together should use a different one -- the
                    scoreboard and the connect log identify players by name.
                  </p>
                  <label className="mp-check">
                    <input
                      type="checkbox"
                      checked={dm}
                      onChange={(e) => setDm(e.target.checked)}
                    />
                    <span>Deathmatch instead of cooperative</span>
                  </label>

                  
                </section>
              )}

              {punch && (
                <section className="mp-section">
                  {punch.line ? (
                    <>
                      <h3>Internet line — send this to them</h3>
                      <ul className="mp-share">
                        <li>
                          <code>{punch.line}</code>
                          <span className="mp-share-why">
                            reached from anywhere without router work; valid
                            while this panel's server stays open
                          </span>
                        </li>
                      </ul>
                      {/* Windows Firewall judges profiles separately and Block
                          beats Allow: the same trap that once put ten block
                          rules on zandronum.exe can hold the punch socket
                          broken on a Public adapter. The user gets the exact
                          one-line fix, not a shrug. */}
                      {punch.firewall && !punch.firewall.ok && (
                        <p className="mp-warn">
                          <b>Windows Firewall will block this line.</b>{" "}
                          Inbound UDP is banned for this app on the{" "}
                          <i>Public</i> profile by rule{" "}
                          <code>{punch.firewall.rule || "(unnamed)"}</code>,
                          and a block rule outranks every allow. Clear it in an
                          <b>administrator</b> PowerShell with:{" "}
                          <code>Remove-NetFirewallRule -DisplayName "{punch.firewall.rule}"
                          </code> — or host over Tailscale instead.
                        </p>
                      )}
                    </>
                  ) : (
                    <>
                      <h3>Joining through the punch</h3>
                      <p className="mp-hint">
                        The game connects through a local socket DoomNite keeps
                        open toward <code>{punch.host}</code>, so no VPN and no
                        router work is needed on your side. Leave this window's
                        server running for the path to stay alive.
                      </p>
                    </>
                  )}
                </section>
              )}

              {sharing && (
                <section className="mp-section">
                  <h3>{punch ? "Share a direct address (LAN / VPN)" : "Share this address"}</h3>
                  <ul className="mp-share">
                    {(sharing.addresses || []).map((a) => {
                      const line =
                        `${a.ip}:${sharing.port}` +
                        (sharing.fingerprint ? " " + sharing.fingerprint : "");
                      // Virtual adapters are shown but marked unusable: they
                      // are on the machine, and the user should be able to see
                      // WHY one of their addresses is not in the list rather
                      // than wonder where it went.
                      const dead = a.kind === "virtual";
                      return (
                        <li key={a.ip} className={dead ? "is-dead" : ""}>
                          <code title={dead
                            ? "This is a virtual machine adapter, not your network."
                            : undefined}>{line}</code>
                          <span className="mp-share-why">
                            {dead
                              ? "virtual machine — nobody can reach this"
                              : a.kind === "cgnat-tailscale"
                              ? "only works if they are on your VPN"
                              : a.kind === "link-local"
                              ? "this computer only"
                              : a.kind === "public"
                              ? `needs UDP ${sharing.port} forwarded on your router`
                              : ""}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                  <p className="mp-hint">
                    Send them the whole line, code included. It lets them check
                    they have the same version before connecting — so nobody
                    joins a game that is quietly desyncing.
                  </p>
                  <p className="mp-hint">
                    <b>They do not need to change anything</b> — no ports, no
                    settings, no installer. Only the host (you) needs anything
                    set up, and only for people who are not on your network.
                  </p>
                  {/* Only relevant when a non-LAN address was actually offered.
                      On the same network there is nothing to forward, and
                      saying otherwise is how people end up needlessly logging
                      into their router. The owner asked exactly this question
                      ("does the friend need to forward a port too?"), which is
                      why it is stated plainly here rather than implied. */}
                  {/* Suppressed once the punch tier is on: then the internet
                      ANSWER IS the internet line above, and forwarding is the
                      thing the user no longer has to be told about. */}
                  {!punch &&
                    (sharing.addresses || []).some(
                      (a) => a.kind === "cgnat-tailscale" || a.kind === "public"
                    ) && (
                    <p className="mp-hint">
                      To play from <i>outside</i> your network, you (the host)
                      must forward port {sharing.port} on your router. If your
                      router cannot do that, use "Host over the internet" —
                      or put them on your VPN, and the address marked above
                      then works with no router changes.
                    </p>
                  )}
                  {/* The withheld case, stated rather than left as an absence.
                      When STUN reports a CGNAT mapping there is no internet
                      line above on purpose: the address a lookup service would
                      print is one their ISP is already NATing, so forwarding
                      the port to it cannot work and printing it would send
                      someone into their router settings for nothing. Saying so
                      is the honest version of an empty list. */}
                  {!punch && sharing.public?.kind === "cgnat" && (
                    <p className="mp-hint">
                      No internet address is listed because your connection
                      sits behind your ISP's own NAT — forwarding the port on
                      your router cannot make it reachable. Use "Host over the
                      internet", or put them on your VPN.
                    </p>
                  )}
                </section>
              )}

              {/* A mod mismatch: warn, do not block. Already connected by the
                  time this renders -- the point is the user now knows why the
                  game may misbehave. */}
              {mismatch && (
                <section className="mp-section">
                  <p className="mp-warn">
                    <b>Your mod is a different version than theirs.</b> They
                    were running <code>{mismatch.theirs || "another version"}</code>,
                    you have <code>{mismatch.ours || "yours"}</code>. The game
                    may look wrong or desync -- missing sprites, changed
                    behaviour. Ask them for the exact version, or install it
                    from the same source.
                  </p>
                </section>
              )}

              {/* THE SERVER LOG IS SHOWN ONLY WHEN SETUP FAILED. /setup returns
                                nn_preset's report, full of "NN user folder", "junction :" and
                                file paths -- internals the user is not meant to see during a
                                normal session, and this panel's whole purpose is that they
                                never have to know NukemNet exists.

                                verify-mp-button.mjs caught an earlier version rendering that
                                log unconditionally: the panel said "NukemNet" and "junction"
                                on every open. So it is now (a) never shown on success, and
                                (b) shown on failure, where hiding it would leave the user
                                with "not set up" and nothing to act on. The command this
                                session ran is a separate, always-safe disclosure. */}
                            {setupLines.length > 0 && phase === "error" && (
                              <section className="mp-section">
                                <details className="mp-details" open>
                                  <summary>What went wrong</summary>
                                  <pre className="mp-out">{setupLines.join("\n")}</pre>
                                </details>
                              </section>
                            )}

              {/* The exact command line this session ran. Safe to show always:
                  it is the engine's own arguments, which is what you paste
                  into a terminal when a mod will not load online. Contains no
                  NukemNet paths -- the junctions mean the engine reads the
                  pack's own files directly. */}
              {command && (
                <section className="mp-section">
                  <details className="mp-details">
                    <summary>Technical details</summary>
                    <pre className="mp-out">{command}</pre>
                  </details>
                </section>
              )}
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}