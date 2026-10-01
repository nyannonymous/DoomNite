import { motion, useReducedMotion } from "framer-motion";
import { Play, Terminal as TerminalIcon, Wrench } from "lucide-react";
import { useEffect, useState } from "react";
import { dryrun, launchIndex } from "./api";
import { Cover } from "./Tile";
import { Typed, TermRow, BootBar, DataStreams } from "./Terminal";

function bytes(n) {
  if (!n) return "";
  return n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`;
}

export default function Panel({ group, onPick, toast }) {
  const reduced = useReducedMotion();
  const [busy, setBusy] = useState(false);
  // Brief boot readout on every game switch. Purely presentational: the details
  // below are already mounted, this just covers them for half a second.
  const [booting, setBooting] = useState(true);
  useEffect(() => {
    setBooting(true);
    const t = setTimeout(() => setBooting(false), 480);
    return () => clearTimeout(t);
  }, [group?.key]);
  const [cmd, setCmd] = useState(null);
  const [cmdOpen, setCmdOpen] = useState(false);

  // Re-fetch the command whenever the selected config changes, so the panel
  // never shows a stale command for the previous variant.
  useEffect(() => {
    let alive = true;
    setCmd(null);
    if (!group) return;
    const cfg = group.cfgs[group.pick];
    dryrun(cfg.index)
      .then((d) => {
        if (alive) setCmd(d);
      })
      .catch(() => {
        if (alive) setCmd({ error: true });
      });
    return () => {
      alive = false;
    };
  }, [group?.key, group?.pick]);

  if (!group) {
    return (
      <aside className="panel panel-empty">
        <p>Select a game</p>
      </aside>
    );
  }

  const cfg = group.cfgs[group.pick];
  const disabled = busy || cfg.exists === false;

  async function play() {
    setBusy(true);
    try {
      const r = await launchIndex(cfg.index);
      toast(`Launched: ${r.label}`);
    } catch (e) {
      toast(`Failed: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  }

  return (
    // key={group.key} remounts on every switch, which is what replays the
    // entrance. x offset plus a slight skew reads as a mechanical slide rather
    // than a fade.
    <motion.aside
      className="panel"
      key={group.key}
      initial={reduced ? false : { opacity: 0, x: 34, skewX: -1.6 }}
      animate={reduced ? undefined : { opacity: 1, x: 0, skewX: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 26, mass: 0.8 }}
    >
      <Cover group={group} className="panel-cover" />
      {/* Falling data streams behind the readout. Decorative only, so it is
          aria-hidden and pointer-transparent in the component. */}
      <DataStreams />
      {/* UAC boot sequence, shown once per game switch. The panel remounts on
          key change, so a fresh mount is a fresh boot -- no extra state. */}
      {booting ? (
        <div className="panel-boot">
          <BootBar ms={520} label="LOADING" />
        </div>
      ) : null}

      {/* Primary action lives ABOVE the scroll area, not at the bottom of it.
          It used to be the last thing in .panel-scroll, below Configs,
          Details, the term rows and the whole mod list -- so on a short window
          the one control you actually want was the one you had to scroll to
          find. Pinned here, under the title, it is always reachable. */}
      <div className="panel-head">
        <h2 className="panel-title d-head d-glitch" data-text={group.label}>
          {group.label}
        </h2>
        <div className="panel-actions">
          <button
            type="button"
            className="play"
            onClick={play}
            disabled={disabled}
          >
            <span className="play-glow" aria-hidden="true" />
            <Play size={18} strokeWidth={2.5} aria-hidden="true" />
            <span className="play-label">{busy ? "Starting…" : "Play"}</span>
            <span className="play-key">↵</span>
          </button>
          <button
            type="button"
            className="showcmd"
            onClick={() => setCmdOpen((v) => !v)}
          >
            {cmdOpen ? "Hide" : "Cmd"}
          </button>
        </div>
      </div>

      <div className="panel-scroll">
        {/* The description types itself out, keyed on the game so switching
            games replays it. That replay is the mechanical feel. */}
        {group.note && (
          <p className="panel-note d-term">
            <Typed text={group.note} speed={10} />
          </p>
        )}

        {group.cfgs.length > 1 && (
          <section className="panel-section">
            <h3>Configs</h3>
            <div className="cfgs">
              {group.cfgs.map((c, n) => (
                <button
                  key={c.index}
                  type="button"
                  className={`cfg ${n === group.pick ? "is-on" : ""}`}
                  onClick={() => onPick(n)}
                >
                  <span className="cfg-radio" aria-hidden="true" />
                  <span className="cfg-text">
                    <span className="cfg-label" title={c.label || `config ${n + 1}`}>
                      {c.label || `config ${n + 1}`}
                    </span>
                    {c.mods.length > 0 && (
                      // Long filenames truncate to an ellipsis, so the full list
                      // goes in the title attribute -- otherwise the truncated
                      // row is unreadable and the panel just looks broken.
                      <span className="cfg-mods" title={c.mods.join("\n")}>
                        {c.mods.join("  ·  ")}
                      </span>
                    )}
                  </span>
                  <span className="cfg-iwad">{(c.iwad || "").replace(/\.WAD$/i, "")}</span>
                </button>
              ))}
            </div>
          </section>
        )}

        <section className="panel-section">
          <h3>Details</h3>
          <dl className="facts">
            <dt>IWAD</dt>
            <dd>{cfg.iwad || "—"}</dd>
            <dt>Config</dt>
            <dd>#{cfg.index + 1}</dd>
            {group.kind === "pack" ? (
              <>
                <dt>Mods</dt>
                <dd>{cfg.mods.length || "none"}</dd>
              </>
            ) : (
              <>
                <dt>Engine</dt>
                <dd>standalone</dd>
              </>
            )}
          </dl>
          {cfg.mods.length > 0 && (
            <ul className="mods">
              {cfg.mods.map((m, i) => (
                <li key={i} style={{ "--i": i }} title={m}>
                  {m}
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Terminal summary strip. TermRow gives the dotted-leader readout
            look; this is the same info the old <dl> carried, restated in the
            UAC idiom. */}
        <div className="panel-termrows">
          <TermRow k="build" v={cfg.label || `#${cfg.index + 1}`} accent={cfg.hd} />
          <TermRow k="iwad" v={(cfg.iwad || "standalone").replace(/\.WAD$/i, "")} />
          <TermRow k="mods" v={cfg.mods.length || "none"} />
          {group.cfgs.length > 1 && (
            <TermRow k="builds" v={`${group.cfgs.length} available`} />
          )}
        </div>

        {cmdOpen && (
          <pre className="cmd">
            {cmd
              ? cmd.error
                ? "Could not read the command."
                : cmd.command
              : "Reading…"}
          </pre>
        )}

        {cfg.exists === false && (
          <p className="warn">This config&apos;s files are missing from the pack.</p>
        )}
      </div>
    </motion.aside>
  );
}