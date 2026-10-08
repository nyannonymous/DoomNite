import { useState, useCallback, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Users } from "lucide-react";

/* ---------------------------------------------------------------
   MULTIPLAYER -- host or join a game, without NukemNet.

   The whole point of this panel is that the user never has to know
   NukemNet exists, never opens it, and never runs a command.

   Pressing MULTIPLAYER:
     1. calls /api/multiplayer/setup, which makes the junctions and refreshes
        the NN preset server-side (idempotent, so this is safe every time);
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
  const [mode, setMode] = useState(null);       // "host" | "join" | null
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
  const [mismatch, setMismatch] = useState(null); // mod differs from the host
  const [err, setErr] = useState(null);

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

  /* One call does the hidden setup: junctions + preset. Runs every time the
     panel opens, because it is idempotent and because the alternative is the
     user discovering a missing junction only when a game fails to load. */
  const openPanel = useCallback(async () => {
    setOpen(true);
    setPhase("working");
    setErr(null);
    setSetupLines([]);
    setCommand("");
    setMode(null);
    setSharing(null);
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
      // A refused setup still shows the panel -- the user needs to read WHY,
      // not be bounced back to the grid.
      setPhase(d.ready && d.ready.ok ? "ready" : "error");
      if (!d.ready || !d.ready.ok) {
        setErr(d.ready?.error || "Multiplayer is not set up on this machine.");
      }
    } catch (e) {
      setPhase("error");
      setErr(String(e.message || e));
    }
  }, [chosen]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = useCallback(
    async (which) => {
      if (!chosen) return;
      setBusy(true);
      setErr(null);
      setSharing(null);
      try {
        const body = { index: chosen._idx, port: 23513, name };
        if (which === "host") {
          body.deathmatch = dm;
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
        setMode(which);
        if (which === "host") {
          setSharing(d.sharing);
          setMismatch(null);
          toast(`Hosting ${d.label}. Share the address with your friends.`);
        } else {
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
                  {phase === "ready" && !mode && (
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
                  {ready.ready && !ready.ready.zandronum && (
                    <p className="mp-warn">
                      Zandronum was not found on this machine, so a game cannot
                      be started yet.
                    </p>
                  )}
                </section>
              )}

              {err && (
                <p className="mp-err" role="alert">
                  {err}
                </p>
              )}

              {phase === "ready" && !mode && (
                <section className="mp-section">
                  <div className="mp-row">
                    <button
                      className="mp-action mp-action--primary"
                      onClick={() => start("host")}
                      disabled={busy || !chosen}
                    >
                      Host a game
                    </button>
                    <button
                      className="mp-action"
                      onClick={() => setMode("join")}
                      disabled={busy || !chosen}
                    >
                      Join a game
                    </button>
                  </div>

                  <label className="mp-check">
                    <input
                      type="checkbox"
                      checked={dm}
                      onChange={(e) => setDm(e.target.checked)}
                    />
                    <span>Deathmatch instead of cooperative</span>
                  </label>
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
                  {ready.ready?.nn?.found && ready.ready?.nn?.linked && (
                    <p className="mp-ok">
                      Multiplayer is set up. Nothing else to configure.
                    </p>
                  )}

                  {mode === "join" && (
                    <div className="mp-join">
                      <label className="mp-field">
                        <span className="mp-label">
                          Their address — paste the whole line here
                        </span>
                        <input
                          className="mp-input"
                          value={addr}
                          onChange={(e) => setAddr(e.target.value)}
                          placeholder="192.168.0.226:23513 ABCD2345"
                          spellCheck={false}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && addr.trim()) start("join");
                          }}
                        />
                      </label>
                      <p className="mp-hint">
                        Paste the whole line they gave you, code included. The
                        code is optional -- it only checks you have the same
                        version.
                      </p>
                      <div className="mp-row">
                        <button
                          className="mp-action mp-action--primary"
                          onClick={() => start("join")}
                          disabled={busy || !addr.trim()}
                        >
                          Join
                        </button>
                        <button className="mp-action" onClick={() => setMode(null)}>
                          Back
                        </button>
                      </div>
                    </div>
                  )}
                </section>
              )}

              {sharing && (
                <section className="mp-section">
                  <h3>Share this address</h3>
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
                  {(sharing.addresses || []).some(
                    (a) => a.kind === "cgnat-tailscale" || a.kind === "public"
                  ) && (
                    <p className="mp-hint">
                      To play from <i>outside</i> your network, you (the host)
                      must forward port {sharing.port} on your router. If your
                      router cannot do that, put them on your VPN instead — the
                      address marked above then works with no router changes.
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