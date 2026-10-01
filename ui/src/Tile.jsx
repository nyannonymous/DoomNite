import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { Play, Swords, Skull, Radio } from "lucide-react";
import { artUrl } from "./api";
import { posterFor } from "./poster";

/** Entrance: cards rise from below, staggered like loading into a level. */
const rise = {
  hidden: { opacity: 0, y: 34, scale: 0.97 },
  show: (i) => ({
    opacity: 1,
    y: 0,
    scale: 1,
    transition: {
      // Spring, not a fixed duration: the overshoot is the mechanical snap the
      // brief asks for. delay is capped so a 14-card grid does not take 3s.
      type: "spring",
      stiffness: 420,
      damping: 30,
      mass: 0.7,
      delay: Math.min(i * 0.035, 0.7),
    },
  }),
};

/** Hover jolt: short, overshooting, settles fast. */
const jolt = {
  rest: { scale: 1 },
  hover: { scale: 1.028, transition: { type: "spring", stiffness: 700, damping: 17, mass: 0.5 } },
  press: { scale: 0.985, transition: { type: "spring", stiffness: 900, damping: 30 } },
};

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

/**
 * One game card.
 *
 * The element is a <div role="button"> rather than a real <button> because it
 * now contains its own buttons (the hover play button and the per-variant play
 * buttons in the context menu). Nesting interactive elements inside a <button>
 * is invalid HTML and browsers flatten it unpredictably, so the card is a div
 * with the keyboard and ARIA wiring done by hand instead.
 *
 * Interaction model, per the user's spec:
 *   - hover           reveals a play button
 *   - click the play  launches the DEFAULT build (the primary variant)
 *   - click the card  selects it for the details pane
 *   - right-click     opens the variant menu, each variant with its own play
 */
export default function Tile({
  group,
  selected,
  pinned,
  onSelect,
  onPin,
  onHover,
  onLaunch,
  onOpenVariants,
  index,
}) {
  const ref = useRef(null);
  // One flag for every motion decision below. Framer's own hook, so it also
  // respects the OS setting without me re-reading matchMedia.
  const reduced = useReducedMotion();
  const cfg = group.cfgs[group.pick] || group.cfgs[0];

  // Keep the keyboard-selected tile in view without yanking the page around.
  useEffect(() => {
    if (selected && ref.current) {
      ref.current.scrollIntoView({ block: "nearest", behavior: reduced ? "auto" : "smooth" });
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
    if (!el || reduced) return;
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
    el.style.setProperty("--gx", "50%");
    el.style.setProperty("--gy", "50%");
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

  /** Launch the default build: the primary variant, never the hovered pick. */
  function playDefault(e) {
    e.stopPropagation(); // don't let the click also pin/select
    e.preventDefault();
    // Pass the group OBJECT. This used to pass group.key (a string), which
    // App's launchBuild signature is (group, n) -- so group.cfgs was
    // undefined, cfg came out undefined, and every card PLAY button reported
    // "files are missing" instead of launching. The sidebar PLAY button was
    // wired correctly, which is why only the cards looked broken.
    onLaunch?.(group, 0);
  }

  function openVariants(e) {
    // Right-click must not also fire the context menu, and must not select.
    e.preventDefault();
    e.stopPropagation();
    onOpenVariants?.(group, e.clientX, e.clientY);
  }

  function onKeyDown(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      activate();
    } else if (e.key === " ") {
      // Space is the conventional activate key; on this card it plays, which
      // is the action people expect from a game launcher tile.
      e.preventDefault();
      onLaunch?.(group, 0);
    } else if (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) {
      // The keyboard route to the same menu the right mouse button opens.
      e.preventDefault();
      const r = ref.current?.getBoundingClientRect();
      onOpenVariants?.(group, r ? r.left + r.width / 2 : 0, r ? r.top : 0);
    }
  }

  // Long IWAD names get in the way of the title, so normalise them once here
  // rather than inline in the JSX.
  const iwadShort = (w) =>
    (w || "")
      .replace(/\.WAD$/i, "")
      .replace(/^DOOM2$/i, "Doom 2")
      .replace(/^DOOM$/i, "Doom 1")
      .replace(/^Hexen$/i, "Hexen");

  return (
    <motion.div
      ref={ref}
      role="button"
      tabIndex={0}
      className={[
        "tile",
        "d-noise",
        selected ? "is-sel" : "",
        pinned ? "is-pin" : "",
        group.missing ? "is-missing" : "",
        // The notch profile changes with state: a deeper cut when selected.
        selected ? "d-jagged-lg" : "d-jagged",
        selected ? "d-jag-glow-blood" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={{ "--i": index }}
      variants={reduced ? undefined : rise}
      initial={reduced ? false : "hidden"}
      animate={reduced ? undefined : "show"}
      whileHover={reduced ? undefined : "hover"}
      whileTap={reduced ? undefined : "press"}
      onClick={activate}
      onKeyDown={onKeyDown}
      onContextMenu={openVariants}
      onMouseEnter={() => onHover?.(group.key)}
      onFocus={() => onSelect(group.key)}
      onPointerMove={onMove}
      onPointerLeave={reset}
      aria-pressed={pinned}
      aria-haspopup={multi ? "menu" : undefined}
      title={`${group.label}${multi ? ` — ${group.cfgs.length} builds` : ""}\nClick to pin · Right-click for builds`}
    >
      <Cover group={group} />
      {/* Notch glow, revealed on hover so it snaps into place rather than
          always being present. */}
      <span className="tile-jag" aria-hidden="true" />

      <span className="tile-body">
        {/* data-text is what .d-glitch's pseudo-elements copy. Without it the
            chromatic aberration has nothing to render. */}
        <span className="tile-name d-glitch" data-text={group.label}>
          {group.label}
        </span>
        <span className="tile-sub">
          {iwadShort(cfg.iwad) || "Standalone"}
          {multi ? ` · ${group.cfgs.length} builds` : ""}
        </span>
        {/* Icons carry state the text does not, so state is not colour-only. */}
        <span className="tile-tags">
          {cfg.hd && (
            <span className="tile-tag is-hd" title="High definition build">
              <Radio size={10} aria-hidden="true" /> HD
            </span>
          )}
          {pinned && (
            <span className="tile-tag is-pin" title="Pinned">
              <Swords size={10} aria-hidden="true" /> PINNED
            </span>
          )}
          {group.missing && (
            <span className="tile-tag is-bad" title="Files are missing">
              <Skull size={10} aria-hidden="true" /> MISSING
            </span>
          )}
        </span>
      </span>
      {/* Hover play button. Always in the DOM and only revealed by CSS, so it
          costs no layout thrash and cannot pop in late. A real <button> inside
          a <button> is invalid, which is why the card is a div. */}
      <span className="tile-playwrap">
        <button
          type="button"
          className="tile-play"
          onClick={playDefault}
          disabled={group.missing || cfg.exists === false}
          aria-label={`Launch ${group.label} (default build)`}
          title="Launch (Space)"
        >
          <Play size={18} strokeWidth={2.5} aria-hidden="true" />
          <span className="tile-playtext">PLAY</span>
        </button>
      </span>
      {/* Pin marker: pinned state must not be conveyed by glow alone. */}
      <span className="tile-pin" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M9 3h6l-1 7 4 4v2H6v-2l4-4-1-7z" />
          <path d="M12 16v5" />
        </svg>
      </span>
      <span className="tile-edge" aria-hidden="true" />
    </motion.div>
  );
}

export { Cover };