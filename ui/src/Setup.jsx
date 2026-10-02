import { useEffect, useState } from "react";
import { Search, FolderOpen, Check, X, AlertTriangle } from "lucide-react";

/* First-run IWAD finder.

   The pack ships DOOM.WAD (shareware) and DOOM2.WAD; Hexen.wad is not
   published, so Hexen Remade can only be reached by a player who owns it.
   This dialog therefore appears when a WAD is genuinely absent -- a failed
   download, or Hexen -- and it locates the copy the player already owns.
   It appears only while /api/setup reports a missing WAD, so a configured
   install never sees it again.

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
    // Where the server says each WAD is right now, which is not always a place
    // scan() looks: a path the player typed in last run can be anywhere, and the
    // launchers only read pack\iwads\. Without this a WAD that IS available
    // renders as an empty "done" row, or worse, as missing.
    const [live, setLive] = useState({});
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
        // scan reports where it looked; /api/setup reports what is usable now.
        // After a save the two can differ, so refresh both.
        try {
          setLive((await j(await fetch("/api/setup", { cache: "no-store" }))).iwads || {});
        } catch { /* the scan result is still worth showing */ }
      } catch (e) {
        setErr(String(e.message || e));
      } finally {
        setBusy(false);
      }
    }

  async function browse(wad) {
    setErr(null);
    if (typeof window.doomnite?.browseIwad !== "function") {
      setErr("Browse is available in the DoomNite desktop app. You can enter the full WAD file path below.");
      return;
    }
    try {
      const path = await window.doomnite.browseIwad(wad);
      if (path) setManual((m) => ({ ...m, [wad]: path }));
    } catch (e) {
      setErr(String(e.message || e));
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
            if (d.iwads) setLive(d.iwads);
            if (d.error) setErr(d.error);
            if (!d.missing.length) onDone?.();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  // Paths may be a WAD file or its containing install folder. The server
  // resolves the expected filename and checks the IWAD magic before saving.

  const NEED = ["DOOM.WAD", "DOOM2.WAD"];
    const outstanding = NEED.filter((w) => missing.includes(w));
    const chosen = { ...live, ...manual };
    // A scan hit counts as a choice unless the player overrode it. live[] wins
    // over found[] because it is the path the server confirmed is usable, and
    // pack\iwads\ is the one a launch actually reads.
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
          Doom needs <b>DOOM.WAD</b> and <b>DOOM2.WAD</b>. Both normally arrive with
          the download — this is for when one is missing, or for supplying
          your own copy instead.
        </p>

        {outstanding.length === 0 ? (
          <p className="setup-ok">
            <Check size={16} aria-hidden="true" /> All set. Enjoy.
          </p>
        ) : (
          <>
            <ul className="setup-list">
              {NEED.map((w) => {
                const pick = chosen[w];
                const done = !missing.includes(w);
                return (
                  <li key={w} className={`setup-row ${done ? "is-done" : ""}`}>
                    <span className="setup-name">{w}</span>
                    {done ? (
                      <span className="setup-found">
                        <Check size={14} aria-hidden="true" /> {pick}
                      </span>
                    ) : (
                      <span className="setup-pick">
                        <input
                          type="text"
                          className="setup-path"
                          placeholder={`Path to ${w} or its folder`}
                          value={pick || ""}
                          onChange={(e) =>
                            setManual((m) => ({ ...m, [w]: e.target.value }))
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && pick) {
                              e.preventDefault();
                              save({ [w]: pick });
                            }
                          }}
                          aria-label={`Full path to ${w}`}
                        />
                        <button
                          type="button"
                          className="btn-ghost is-sm"
                          onClick={() => browse(w)}
                          disabled={busy}
                          title={`Browse for ${w}`}
                        >
                          <FolderOpen size={13} aria-hidden="true" /> Browse
                        </button>
                        <button
                          type="button"
                          className="btn-ghost is-sm"
                          onClick={() => pick && save({ [w]: pick })}
                          disabled={busy || !pick}
                        >
                          <Check size={13} aria-hidden="true" /> Use
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
