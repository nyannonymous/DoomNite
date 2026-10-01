import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { launchIndex } from "./api";

/**
 * The per-game build menu, opened by right-clicking a card.
 *
 * Each row is one build with its own play button, so a game with an HD build,
 * a bare build and two IWADs is fully reachable without a separate picker.
 * The HD build is listed first when present because the server orders the
 * primary action first (see the BDBE entry in tools/build.py) and the primary is
 * what a plain click launches -- the menu must not contradict the card.
 */
export default function VariantMenu({ group, at, onClose, onLaunched, onError }) {
  const ref = useRef(null);
  const [pos, setPos] = useState({ left: at.x, top: at.y, ready: false });
  const [busy, setBusy] = useState(null);

  // Flip the panel back inside the viewport before it paints, otherwise a
  // right-click near the right or bottom edge opens a menu that runs off-screen.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const pad = 8;
    let left = at.x;
    let top = at.y;
    if (left + r.width > window.innerWidth - pad) left = at.x - r.width;
    if (top + r.height > window.innerHeight - pad) top = at.y - r.height;
    setPos({
      left: Math.max(pad, Math.min(left, window.innerWidth - r.width - pad)),
      top: Math.max(pad, Math.min(top, window.innerHeight - r.height - pad)),
      ready: true,
    });
  }, [at.x, at.y, group.key]);

  // Dismiss on Escape, on scroll (the anchor point goes stale), and on any
  // click outside. The outside-click listener is on the capture phase so it
  // fires before the row's own handler.
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    }
    function onDown(e) {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    }
    function onScroll() {
      onClose();
    }
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("pointerdown", onDown, true);
    document.addEventListener("contextmenu", onDown, true);
    window.addEventListener("resize", onScroll);
    // capture:true so scrolling any ancestor (including the grid) closes it.
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("pointerdown", onDown, true);
      document.removeEventListener("contextmenu", onDown, true);
      window.removeEventListener("resize", onScroll);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [onClose]);

  // Move focus into the menu so the keyboard path works and Escape lands here.
  useEffect(() => {
    ref.current?.querySelector("button:not(:disabled)")?.focus();
  }, [group.key]);

  async function play(cfg) {
    if (cfg.exists === false || busy !== null) return;
    setBusy(cfg.index);
    try {
      await launchIndex(cfg.index);
      onLaunched?.(group, cfg);
      onClose();
    } catch (e) {
      onError?.(e.message || String(e));
      setBusy(null);
    }
  }

  return (
    <div
      ref={ref}
      className={`vmenu ${pos.ready ? "is-placed" : ""}`}
      style={{ left: pos.left, top: pos.top }}
      role="menu"
      aria-label={`${group.label} builds`}
    >
      <header className="vmenu-head">
        <span className="vmenu-title">{group.label}</span>
        <span className="vmenu-count">{group.cfgs.length} builds</span>
      </header>
      <ul className="vmenu-list">
        {group.cfgs.map((cfg, i) => {
          const disabled = cfg.exists === false;
          const isDefault = i === 0;
          return (
            <li key={cfg.index} role="none">
              <div className={`vrow ${disabled ? "is-disabled" : ""}`}>
                <button
                  type="button"
                  role="menuitem"
                  className="vrow-info"
                  onClick={() => play(cfg)}
                  disabled={disabled}
                >
                  <span className="vrow-name">
                    {cfg.label || `Build ${i + 1}`}
                    {isDefault && <em className="vrow-def">default</em>}
                    {cfg.hd && <em className="vrow-hd">HD</em>}
                  </span>
                  <span className="vrow-meta">
                    {cfg.iwad
                      ? cfg.iwad.replace(/\.WAD$/i, "").replace(/^DOOM2$/i, "Doom 2").replace(/^DOOM$/i, "Doom 1")
                      : "Standalone"}
                    {cfg.mods?.length ? ` · ${cfg.mods.length} mods` : ""}
                    {disabled ? " · missing files" : ""}
                  </span>
                </button>
                {/* Small play button per row, per the spec. */}
                <button
                  type="button"
                  className="vrow-play"
                  onClick={() => play(cfg)}
                  disabled={disabled}
                  aria-label={`Launch ${group.label} — ${cfg.label || `build ${i + 1}`}`}
                  title="Launch this build"
                >
                  {busy === cfg.index ? (
                    <span className="vrow-spin" aria-hidden="true" />
                  ) : (
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M7 4l13 8-13 8z" />
                    </svg>
                  )}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
