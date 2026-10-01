import { useEffect, useRef, useState } from "react";
import { artUrl } from "./api";
import { posterFor } from "./poster";

/**
 * A cover image that uses the mod's own extracted title screen when there is
 * one, and a generated poster otherwise.
 *
 * Both paths end up as a plain <img> so the browser does the compositing; the
 * tile only has to supply a src. object-fit: contain in CSS is deliberate --
 * title screens are mixed aspect ratios and cropping them loses the artwork,
 * and the tile box is 16:9 so the largest source fits nearly exactly.
 */
function Cover({ group, className = "" }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);

  // Generated poster is deterministic per label, so computing it inline is
  // cheap and stable across re-renders.
  const generated = group.art && !failed ? artUrl(group.art) : posterFor(group.label, group.note);

  return (
    <div className={`cover ${className} ${loaded ? "is-loaded" : ""}`}>
      <img
        src={generated}
        alt=""
        loading="lazy"
        decoding="async"
        onLoad={() => setLoaded(true)}
        onError={() => {
          // Only fall back to a poster if the real art 404'd.
          if (group.art && !failed) setFailed(true);
          setLoaded(true);
        }}
      />
      <span className="cover-sheen" aria-hidden="true" />
      {/* Specular highlight that tracks the pointer across the "glass". */}
      <span className="cover-glare" aria-hidden="true" />
    </div>
  );
}

export default function Tile({ group, selected, pinned, onSelect, onPin, onHover, index }) {
  const ref = useRef(null);
  const cfg = group.cfgs[group.pick] || group.cfgs[0];

  // Keep the keyboard-selected tile in view without yanking the page around.
  useEffect(() => {
    if (selected && ref.current) {
      ref.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [selected]);

  const multi = group.cfgs.length > 1;

  /**
   * Pointer-tracked 3D tilt.
   *
   * This is the nod to the Oracle's draggable card field: the surface reacts to
   * where your cursor actually is. Deliberately CSS-variable driven and written
   * straight to style, because React state per pointermove would re-render the
   * whole grid on every frame. Only runs while hovering, so an idle grid is free.
   */
  function onMove(e) {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width; // 0..1
    const py = (e.clientY - r.top) / r.height;
    el.style.setProperty("--mx", (px - 0.5) * 2);
    el.style.setProperty("--my", (py - 0.5) * 2);
    el.style.setProperty("--gx", px * 100 + "%");
    el.style.setProperty("--gy", py * 100 + "%");
  }

  function reset() {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--mx", 0);
    el.style.setProperty("--my", 0);
  }

  /**
   * Hover previews, click pins.
   *
   * Hovering selects transiently (so the side panel follows your cursor) but
   * the pin is what survives: it is the game you actually chose, and it stays
   * marked after you move away. Clicking a pinned tile unpins it.
   */
  function activate() {
    onPin(pinned ? null : group.key); // toggle
    onSelect(group.key);
  }

  return (
    <button
      ref={ref}
      type="button"
      className={`tile ${selected ? "is-sel" : ""} ${pinned ? "is-pin" : ""} ${
        group.missing ? "is-missing" : ""
      }`}
      style={{ "--i": index }}
      onClick={activate}
      onMouseEnter={() => onHover?.(group.key)}
      onFocus={() => onSelect(group.key)}
      onPointerMove={onMove}
      onPointerLeave={reset}
      aria-pressed={pinned}
      title={`${group.label}${multi ? ` — ${group.cfgs.length} configs` : ""}${
        pinned ? " (pinned — click to unpin)" : " (click to pin)"
      }`}
    >
      <Cover group={group} />
      <span className="tile-body">
        <span className="tile-name">{group.label}</span>
        <span className="tile-sub">
          {cfg.iwad ? cfg.iwad.replace(/\.WAD$/i, "").replace(/^DOOM2$/i, "Doom 2").replace(/^DOOM$/i, "Doom 1").replace(/^Hexen$/i, "Hexen") : "Standalone"}
          {multi ? ` · ${group.cfgs.length} configs` : ""}
        </span>
      </span>
      {/* Pin marker: pinned state must not be conveyed by glow alone. */}
      <span className="tile-pin" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M9 3h6l-1 7 4 4v2H6v-2l4-4-1-7z" />
          <path d="M12 16v5" />
        </svg>
      </span>
      <span className="tile-edge" aria-hidden="true" />
    </button>
  );
}

export { Cover };