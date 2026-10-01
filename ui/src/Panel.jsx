import { useEffect, useState } from "react";
import { dryrun, launchIndex } from "./api";
import { Cover } from "./Tile";

function bytes(n) {
  if (!n) return "";
  return n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`;
}

export default function Panel({ group, onPick, toast }) {
  const [busy, setBusy] = useState(false);
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
    <aside className="panel" key={group.key}>
      <Cover group={group} className="panel-cover" />

      <div className="panel-scroll">
        <h2 className="panel-title">{group.label}</h2>
        {group.note && <p className="panel-note">{group.note}</p>}

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

        <div className="panel-actions">
          <button
            type="button"
            className="play"
            onClick={play}
            disabled={disabled}
          >
            <span className="play-glow" aria-hidden="true" />
            <span className="play-label">{busy ? "Starting…" : "Play"}</span>
            <span className="play-key">↵</span>
          </button>
          <button
            type="button"
            className="showcmd"
            onClick={() => setCmdOpen((v) => !v)}
          >
            {cmdOpen ? "Hide command" : "Show command"}
          </button>
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
    </aside>
  );
}