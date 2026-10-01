import { useEffect, useRef } from "react";

/**
 * Ambient ember field.
 *
 * The Nexus Oracle card archive is a <canvas> scene you can grab and rotate.
 * A WebGL card deck is the wrong tool here -- our tiles are real DOM buttons
 * that need focus, keyboard nav and accessible labels -- so this borrows the
 * part that actually sells it: a living backdrop that reacts to the pointer.
 *
 * Embers drift upward like Doom's infernal sky, parallax by pointer depth, with
 * a slow parallax rotation. requestAnimationFrame is paused when the tab is
 * hidden and when the pointer has not moved for a while, so an idle launcher
 * is not burning a core.
 *
 * Deliberately cheap: ~90 particles, no 3D library, no per-frame allocation.
 */
export default function EmberField() {
  const ref = useRef(null);

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const ctx = cv.getContext("2d", { alpha: true });
    if (!ctx) return;

    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    let w = 0;
    let h = 0;
    let dpr = 1;
    let raf = 0;
    let running = false;
    let idle = 0;

    // Pointer in normalised -1..1 space, smoothed toward the raw value.
    const target = { x: 0, y: 0 };
    const cur = { x: 0, y: 0 };

    const N = reduce ? 40 : 90;
    const p = [];

    function seed() {
      p.length = 0;
      for (let i = 0; i < N; i++) {
        p.push({
          x: Math.random(),
          y: Math.random(),
          z: 0.35 + Math.random() * 0.65, // depth: affects size + speed
          r: Math.random() * Math.PI * 2,
          vr: (Math.random() - 0.5) * 0.7,
          s: 0.25 + Math.random() * 0.9, // speed multiplier
        });
      }
    }

    function resize() {
      dpr = Math.min(2, window.devicePixelRatio || 1);
      w = cv.clientWidth;
      h = cv.clientHeight;
      cv.width = Math.max(1, Math.floor(w * dpr));
      cv.height = Math.max(1, Math.floor(h * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function frame(t) {
      ctx.clearRect(0, 0, w, h);

      // Ease the pointer toward its target.
      cur.x += (target.x - cur.x) * 0.045;
      cur.y += (target.y - cur.y) * 0.045;

      const tsec = t / 1000;
      for (let i = 0; i < p.length; i++) {
        const q = p[i];

        // Rise and drift; wrap at the top.
        q.y -= 0.0016 * q.z * q.s;
        if (q.y < -0.05) {
          q.y = 1.05;
          q.x = Math.random();
        }
        q.r += q.vr * 0.004;

        // Parallax: nearer embers (high z) shift further with the pointer.
        const px = (q.x - 0.5) * w + cur.x * 46 * q.z;
        const py = (q.y - 0.5) * h + cur.y * 30 * q.z;
        const wob = Math.sin(tsec * 0.8 + q.r) * 9 * q.z;

        // Flicker, like something burning.
        const flick = 0.55 + 0.45 * Math.sin(tsec * 3.1 * q.s + q.r * 2);
        const rad = (0.7 + q.z * 1.5) * flick;

        // Ember colour: mostly red, a few pale/hot ones.
        const hot = q.s > 1.05;
        const g = ctx.createRadialGradient(px + wob, py, 0, px + wob, py, rad * 5);
        if (hot) {
          g.addColorStop(0, "rgba(255,214,150,0.85)");
          g.addColorStop(0.35, "rgba(255,120,50,0.34)");
        } else {
          g.addColorStop(0, "rgba(255,90,50,0.62)");
          g.addColorStop(0.35, "rgba(190,30,20,0.2)");
        }
        g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(px + wob, py, rad * 5, 0, Math.PI * 2);
        ctx.fill();
      }

      raf = requestAnimationFrame(frame);
    }

    function start() {
      if (running) return;
      running = true;
      raf = requestAnimationFrame(frame);
    }

    function stop() {
      running = false;
      cancelAnimationFrame(raf);
    }

    function onMove(e) {
      const t = e.touches?.[0] || e;
      target.x = (t.clientX / window.innerWidth) * 2 - 1;
      target.y = (t.clientY / window.innerHeight) * 2 - 1;
      idle = 0;
      start();
    }

    const ro = new ResizeObserver(() => {
      resize();
      start();
    });

    function onVis() {
      if (document.hidden) stop();
      else start();
    }

    resize();
    seed();
    start();
    ro.observe(cv);
    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("visibilitychange", onVis);

    return () => {
      stop();
      ro.disconnect();
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  return <canvas ref={ref} className="embers" aria-hidden="true" />;
}