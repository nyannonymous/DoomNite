import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchEntries, groupEntries, FILTERS, launchIndex } from "./api";
import Tile from "./Tile";
import Panel from "./Panel";
import EmberField from "./EmberField";
import VariantMenu from "./VariantMenu";

function Toast({ msg, bad }) {
  if (!msg) return null;
  return (
    <div className={`toast ${bad ? "is-bad" : ""}`} role="status">
      {msg}
    </div>
  );
}

export default function App() {
  const [raw, setRaw] = useState([]);
  const [error, setError] = useState(null);
  const [sel, setSel] = useState(null);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [picks, setPicks] = useState({});
  const [pinned, setPinned] = useState(null);

  // A pinned game is a standing choice, so it must survive a reload. Without
  // this the pin silently resets to nothing on refresh, which reads as
  // "pinning doesn't work".
  useEffect(() => {
    try {
      const saved = localStorage.getItem("doomnite.pinned");
      if (saved) setPinned(JSON.parse(saved));
    } catch {
      // Private mode or blocked storage: pinning still works, just not sticky.
    }
  }, []);

  useEffect(() => {
    try {
      if (pinned) localStorage.setItem("doomnite.pinned", JSON.stringify(pinned));
      else localStorage.removeItem("doomnite.pinned");
    } catch {
      /* non-fatal */
    }
  }, [pinned]);
  // Which game's build menu is open, and where. Null key means closed.
  const [menu, setMenu] = useState(null);
  const [toastMsg, setToastMsg] = useState(null);
  const [toastBad, setToastBad] = useState(false);
  const [count, setCount] = useState(0); // entrance animation trigger
  const toastTimer = useRef(null);

  const toast = useCallback((msg, bad = false) => {
    setToastMsg(msg);
    setToastBad(bad);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToastMsg(null), 2600);
  }, []);

  useEffect(() => {
    fetchEntries()
      .then((e) => {
        setRaw(e);
        // Next frame, so tiles mount with --i stagger already applied.
        requestAnimationFrame(() => setCount(e.length));
      })
      .catch((err) => setError(err.message));
    return () => clearTimeout(toastTimer.current);
  }, []);

  const groups = useMemo(() => groupEntries(raw), [raw]);

  // Merge the per-group picked config into the group object the components use.
  const merged = useMemo(
    () => groups.map((g) => ({ ...g, pick: picks[g.key] ?? g.pick ?? 0 })),
    [groups, picks]
  );

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const matches = merged.filter((g) => {
      const cfg = g.cfgs[g.pick] || g.cfgs[0];
      if (needle) {
        const hay = [g.label, g.note || "", ...cfg.mods, cfg.iwad || ""]
          .join(" ")
          .toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      switch (filter) {
        case "doom1":
          return g.cfgs.some((c) => (c.iwad || "").toUpperCase() === "DOOM.WAD");
        case "combo":
          return cfg.mods.length > 1;
        case "variants":
          return g.cfgs.length > 1;
        case "missing":
          return g.cfgs.every((c) => c.exists === false);
        default:
          return true;
      }
    });
    // A pinned game is a standing choice, so it stays in the grid even when a
    // filter or search would otherwise hide it -- but it keeps its original
    // position. Reordering the grid out from under the cursor on click made
    // pinning feel like the click had done nothing.
    if (pinned && !matches.some((g) => g.key === pinned)) {
      const pg = merged.find((g) => g.key === pinned);
      if (pg) return [...matches, pg];
    }
    return matches;
  }, [merged, q, filter, pinned]);

  // Default the selection to the first visible tile. When a pin is restored from
  // storage, the panel must follow it -- otherwise the page comes back with the
  // pin marked on one tile and the details of another, which reads as broken.
  useEffect(() => {
      if (!filtered.length) {
        setSel(null);
        return;
      }
      if (pinned && filtered.some((g) => g.key === pinned)) {
        setSel((cur) => (cur === pinned ? cur : pinned));
        return;
      }
      if (!sel || !filtered.some((g) => g.key === sel)) {
        setSel(filtered[0].key);
      }
    }, [filtered, sel, pinned]);

  const current = filtered.find((g) => g.key === sel) || null;

  /**
   * Launch one build of a group.
   *
   * `n` indexes that group's cfgs. 0 is the primary build, which is what a
   * left-click on the hover play button and what Space on a focused card both
   * do. The primary is first because tools/build.py lists the HD build first for
   * BDBE, so "the default" is the best-looking one.
   */
  const launchBuild = useCallback(
    async (group, n) => {
      if (!group) return;
      const cfg = group.cfgs[n] || group.cfgs[0];
      if (!cfg || cfg.exists === false) {
        toast(`Cannot launch ${group.label}: files are missing.`, true);
        return;
      }
      try {
        const r = await launchIndex(cfg.index);
        toast(`Launched: ${r.label}`);
      } catch (e) {
        toast(`Failed: ${e.message}`, true);
      }
    },
    [toast]
  );

  const openVariants = useCallback((group, x, y) => {
    setMenu({ group, x, y });
  }, []);

  const closeVariants = useCallback(() => setMenu(null), []);

  // The grid owns a contextmenu handler per tile, but a right-click on the
  // surrounding empty space should still dismiss an open menu.
  useEffect(() => {
    if (!menu) return;
    function onKey(e) {
      if (e.key === "Escape") setMenu(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menu]);

  const move = useCallback(
    (dir) => {
      if (!filtered.length) return;
      const i = filtered.findIndex((g) => g.key === sel);
      const next = filtered[(Math.max(0, i) + dir + filtered.length) % filtered.length];
      setSel(next.key);
    },
    [filtered, sel]
  );

  const cycleCfg = useCallback(
    (dir) => {
      if (!current || current.cfgs.length < 2) return;
      const n = (current.pick + dir + current.cfgs.length) % current.cfgs.length;
      setPicks((p) => ({ ...p, [current.key]: n }));
    },
    [current]
  );

  // Keyboard: arrows move, Enter plays, Tab-in-config cycles variants.
  useEffect(() => {
    function onKey(e) {
      if (e.target instanceof HTMLInputElement) return;
      const k = e.key;
      if (k === "ArrowDown" || k === "ArrowRight") {
        e.preventDefault();
        move(1);
      } else if (k === "ArrowUp" || k === "ArrowLeft") {
        e.preventDefault();
        move(-1);
      } else if (k === "Enter") {
        if (document.activeElement?.tagName === "BUTTON") return;
        const btn = document.querySelector(".play");
        if (btn && !btn.disabled) btn.click();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [move]);

  useEffect(() => {
    function onKey(e) {
      if (e.target instanceof HTMLInputElement) return;
      if (e.key === "Tab" && current && current.cfgs.length > 1) {
        e.preventDefault();
        cycleCfg(e.shiftKey ? -1 : 1);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, cycleCfg]);

  if (error) {
    return (
      <div className="boot boot-error">
        <h1>DoomNite</h1>
        <p>Could not reach the launcher server.</p>
        <code>{error}</code>
        <p className="hint">Is serve.py running?</p>
      </div>
    );
  }

  if (!count) {
    return (
      <div className="boot">
        <div className="boot-mark">DOOMNITE</div>
        <div className="boot-bar">
          <span />
        </div>
      </div>
    );
  }

  const nVariants = merged.filter((g) => g.cfgs.length > 1).length;

  return (
    <div className="app">
      <EmberField />
      <div className="vignette" aria-hidden="true" />
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-text">
            DOOM<span>NITE</span>
          </span>
        </div>

        <div className="search">
          <svg className="search-icon" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3.5-3.5" />
          </svg>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search games, mods, IWADs…"
            spellCheck={false}
            aria-label="Search"
          />
          {q && (
            <button className="search-clear" onClick={() => setQ("")} aria-label="Clear">
              ×
            </button>
          )}
        </div>

        <div className="chips" role="tablist">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              role="tab"
              aria-selected={filter === f.id}
              className={`chip ${filter === f.id ? "is-on" : ""}`}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </header>

      <main className="stage">
        <div className="grid-wrap">
          {filtered.length === 0 ? (
            <p className="none">Nothing matches that.</p>
          ) : (
            <div className="grid">
              {filtered.map((g, i) => (
                <Tile
                  key={g.key}
                  group={g}
                  index={i}
                  selected={g.key === sel}
                  onSelect={setSel}
                  onPin={setPinned}
                  pinned={g.key === pinned}
                  onHover={setSel}
                  onLaunch={launchBuild}
                  onOpenVariants={openVariants}
                />
              ))}
            </div>
          )}
        </div>

        <Panel
          group={current}
          onPick={(n) =>
            current && setPicks((p) => ({ ...p, [current.key]: n }))
          }
          toast={toast}
        />
      </main>

      {menu && (
        <VariantMenu
          group={menu.group}
          at={{ x: menu.x, y: menu.y }}
          onClose={closeVariants}
          onLaunched={(g, c) => toast(`Launched: ${c.label || g.label}`)}
          onError={(m) => toast(`Failed: ${m}`, true)}
        />
      )}

      <footer className="statusbar">
        <span>{filtered.length} of {merged.length} games</span>
        <span className="dot" aria-hidden="true" />
        <span>{nVariants} with extra configs</span>
        {current && pinned === current.key && (
          <>
            <span className="dot" aria-hidden="true" />
            <span className="status-pin">pinned: {current.label}</span>
          </>
        )}
        <span className="grow" />
        <span className="keys">
          <kbd>↑</kbd>
          <kbd>↓</kbd> move · <kbd>Tab</kbd> config · <kbd>↵</kbd> play
        </span>
      </footer>

      <Toast msg={toastMsg} bad={toastBad} />
    </div>
  );
}