import { useEffect, useState } from "react";

/**
 * The global CRT treatment: scanlines, a rolling refresh band, a vignette, a
 * little colour fringing, and a crosshair cursor that follows the pointer.
 *
 * Every layer is position:fixed with pointer-events:none except the cursor, so
 * nothing here can eat a click. The cursor is driven by CSS custom properties
 * written straight to the element in a pointermove listener rather than React
 * state -- re-rendering the whole app on every mouse move would make the grid
 * unusable.
 */
export function CRTOverlay({ intensity = 1, showCursor = true }) {
  // Respect the OS setting. The scanlines and sweep are pure decoration; some
  // people find motion genuinely uncomfortable and this is a full-screen
  // moving element, so it is opt-out rather than merely toned down.
  const [reduced, setReduced] = useState(
    () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(mq.matches);
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);

  const motion = !reduced && intensity > 0;

  // Decide ONCE, here, whether a custom cursor will actually exist, and tell
  // the DOM. The old CSS hid the native cursor unconditionally while this
  // component could bail out and render nothing, so on a reduced-motion or
  // touch machine the app had no cursor of any kind.
  const coarse =
    typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
  const customCursor = !reduced && !coarse;
  useEffect(() => {
    document.documentElement.classList.toggle("d-has-crosshair", customCursor);
    return () => document.documentElement.classList.remove("d-has-crosshair");
  }, [customCursor]);

  return (
    <>
      <div className="d-scanlines" style={{ opacity: 0.85 * intensity }} aria-hidden="true" />
      {motion && (
        <div className="d-scan-sweep" aria-hidden="true">
          {/* Fixed keyframe name so the intensity prop can scale the speed
              without the element remounting. */}
          <style>{`@keyframes d-sweep { animation-duration: ${7 / intensity}s }`}</style>
        </div>
      )}
      <div className="d-vignette" style={{ opacity: intensity }} aria-hidden="true" />
      <div className="d-aberration" aria-hidden="true" />
      {showCursor && customCursor && <Crosshair reduced={reduced} />}
    </>
  );
}

/**
 * Doom crosshair cursor.
 *
 * Four bars around a hollow centre, drawn with gradients and border-radius so
 * there is no sprite to load. Hidden entirely on touch devices, where there is
 * no pointer to track and a floating crosshair would just be a stray dot.
 */
function Crosshair({ reduced }) {
  useEffect(() => {
    if (reduced) return;
    let raf = 0;
    let x = 0;
    let y = 0;
    const el = document.getElementById("d-crosshair");

    const paint = () => {
      if (el) {
        el.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      }
      raf = 0;
    };

    // A pointer that never enters the window leaves the crosshair stranded at
    // the origin. Seed it mid-screen and paint once so it is never invisible.
    x = window.innerWidth / 2;
    y = window.innerHeight / 2;
    el?.classList.remove("is-out");
    paint();

    const onMove = (e) => {
      x = e.clientX;
      y = e.clientY;
      // Coalesce to one write per frame; a raw pointermove can fire well
      // above 60Hz on a high-polling mouse.
      if (!raf) raf = requestAnimationFrame(paint);
    };

    const onLeave = () => el?.classList.add("is-out");
    const onEnter = () => el?.classList.remove("is-out");

    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);
    document.addEventListener("pointerenter", onEnter);
    return () => {
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
      document.removeEventListener("pointerenter", onEnter);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [reduced]);

  if (reduced) return null;
  return (
    <div id="d-crosshair" className="d-crosshair" aria-hidden="true">
      <span className="d-xh d-xh-t" />
      <span className="d-xh d-xh-b" />
      <span className="d-xh d-xh-l" />
      <span className="d-xh d-xh-r" />
      <span className="d-xh-dot" />
    </div>
  );
}

/**
 * Full-screen launch flash + glitch bars.
 *
 * Plays once on mount and calls onDone. The game is already starting by then,
 * so this is pure punctuation -- it must never gate the launch itself, which
 * is why onDone fires on a timer rather than on animation events that a
 * reduced-motion user would never get.
 */
export function LaunchFlash({ onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 420);
    return () => clearTimeout(t);
  }, [onDone]);

  return (
    <>
      <div className="d-flash" aria-hidden="true" />
      <div className="d-glitchbars" aria-hidden="true" />
    </>
  );
}

export default CRTOverlay;
