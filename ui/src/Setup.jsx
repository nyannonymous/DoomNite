import { useEffect, useState } from "react";
import { Search, FolderOpen, Check, X, AlertTriangle } from "lucide-react";

/* First-run IWAD finder.

   DOOM.WAD and DOOM2.WAD are commercial id Software / Bethesda content, so
   Doomnite never downloads one -- it locates the copy the player already owns.
   This dialog appears only while /api/setup reports a missing WAD, so a
   configured install never sees it again.

   It scans Steam/GOG first because that is right nearly every time and is
   less work than making someone dig through Program Files. The browse button
   is the fallback, not the default. */

const j = async (r) => {
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  return r.json();
};

export default function Setup({ onDone }) {
  const [missing, setMissing] = useState([]);
  const [found, setFound] = useState({});
  const [searched, setSearched] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [manual, setManual] = useState({});

  useEffect(() => {
    // Auto-scan on open: the common case never needs the button pressed.
    scan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function scan() {
    setBusy(true);
    setErr(null);
    try {
      const d = await j(await fetch("/api/setup/scan", { cache: "no-store" }));
      setFound(d.found || {});
      setSearched(d.searched || 0);
      setMissing(d.missing || []);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function save(paths) {
    setBusy(true);
    setErr(null);
    try {
      const d = await j(
        await fetch("/api/setup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "set", iwads: paths }),
        })
      );
      setMissing(d.missing || []);
      if (!d.missing.length) onDone?.();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  // Every path goes to the server for validation, which checks the IWAD magic
  // itself -- a total conversion ships its own DOOM2.WAD that a size check
  // would happily accept and boot the wrong game.

  const NEED = ["DOOM.WAD", "DOOM2.WAD"];
  const outstanding = NEED.filter((w) => missing.includes(w));
  const chosen = { ...manual };
  // A scan hit counts as a choice unless the player overrode it.
  for (const w of NEED) if (found[w]?.length && !chosen[w]) chosen[w] = found[w][0];

  return (
    <div className="setup" role="dialog" aria-modal="true" aria-labelledby="setup-h">
      <div className="setup-card">
        <header className="setup-hd">
          <h2 id="setup-h">ONE-TIME SETUP</h2>
          <button type="button" className="setup-x" onClick={onDone} aria-label="Skip for now">
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <p className="setup-lede">
          Doom needs <b>DOOM.WAD</b> and <b>DOOM2.WAD</b> to run. They ship with
          the games, so point DoomNite at yours -- it will not download them.
        </p>

        {outstanding.length === 0 ? (
          <p className="setup-ok">
            <Check size={16} aria-hidden="true" /> All set. Enjoy.
          </p>
        ) : (
          <>
            <ul className="setup-list">
              {NEED.map((w) => {
                const auto = found[w]?.[0];
                const pick = chosen[w];
                const done = !missing.includes(w);
                return (
                  <li key={w} className={`setup-row ${done ? "is-done" : ""}`}>
                    <span className="setup-name">{w}</span>
                    {done ? (
                      <span className="setup-found">
                        <Check size={14} aria-hidden="true" /> {pick}
                      </span>
                    ) : auto ? (
                      <span className="setup-found">
                        <Check size={14} aria-hidden="true" /> {auto}
                      </span>
                    ) : (
                      /* A <input type=file> cannot do this job. Browsers no
                         longer expose the real path to JS, and picking a file
                         sends its contents rather than its location -- but the
                         server needs a path to launch from. So this is a plain
                         text field, which always works. */
                      <span className="setup-pick">
                        <input
                          type="text"
                          className="setup-path"
                          placeholder="C:\\SteamLibrary\\steamapps\\common\\DOOM2"
                          value={manual[w] || ""}
                          onChange={(e) =>
                            setManual((m) => ({ ...m, [w]: e.target.value }))
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && manual[w]) {
                              e.preventDefault();
                              save({ [w]: manual[w] });
                            }
                          }}
                          aria-label={`Full path to ${w}`}
                        />
                        <button
                          type="button"
                          className="btn-ghost is-sm"
                          onClick={() => manual[w] && save({ [w]: manual[w] })}
                          disabled={busy || !manual[w]}
                        >
                          <FolderOpen size={13} aria-hidden="true" /> Use
                        </button>
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>

            {err && (
              <p className="setup-err" role="alert">
                <AlertTriangle size={14} aria-hidden="true" /> {err}
              </p>
            )}

            <footer className="setup-ft">
              <button
                type="button"
                className="btn-ghost"
                onClick={scan}
                disabled={busy}
              >
                <Search size={14} aria-hidden="true" />
                {busy ? "Scanning..." : "Scan again"}
                {searched > 0 && !busy ? ` (${searched} places)` : ""}
              </button>
              {NEED.filter((w) => chosen[w]).length === NEED.length && (
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => save(chosen)}
                  disabled={busy}
                >
                  SAVE &amp; CONTINUE
                </button>
              )}
            </footer>
          </>
        )}
      </div>
    </div>
  );
}
