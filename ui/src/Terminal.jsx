import { useEffect, useRef, useState } from "react";

/**
 * A UAC terminal readout: green-on-black monospace with a blinking block caret,
 * used for the details pane.
 *
 * `text` types itself out character by character. The effect is deliberately
 * not skippable on click here -- callers pass a `key` to restart it when the
 * selection changes, which is what makes switching games feel mechanical.
 */
export function Typed({ text = "", speed = 12, caret = true, onDone }) {
  const [n, setN] = useState(0);
  const doneRef = useRef(false);

  useEffect(() => {
    setN(0);
    doneRef.current = false;
    if (!text) {
      onDone?.();
      return;
    }
    // A fixed interval rather than a per-character timeout: 4,000 characters
    // at 12ms is 4,000 timers otherwise.
    const id = setInterval(() => {
      setN((cur) => {
        if (cur >= text.length) {
          clearInterval(id);
          if (!doneRef.current) {
            doneRef.current = true;
            onDone?.();
          }
          return cur;
        }
        return cur + 1;
      });
    }, speed);
    return () => clearInterval(id);
    // onDone is intentionally omitted: callers pass an inline arrow, which
    // would restart the typing on every parent render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, speed]);

  const shown = text.slice(0, n);
  const typing = n < text.length;

  return (
    <span className={caret && typing ? "d-caret" : undefined}>{shown}</span>
  );
}

/**
 * The boot-sequence bar shown while a new game's details are loading.
 *
 * Segmented fill that steps rather than slides, which is the UAC look. Runs
 * for `ms` then calls onDone; the parent swaps in the real content.
 */
export function BootBar({ ms = 620, label = "INITIALISING", onDone }) {
  const [pct, setPct] = useState(0);

  useEffect(() => {
    setPct(0);
    const started = Date.now();
    const id = setInterval(() => {
      const t = Math.min(1, (Date.now() - started) / ms);
      // Quantised so the bar fills in visible steps. A smooth fill reads as a
      // web progress bar, which is exactly the wrong reference.
      setPct(Math.round(t * 20) * 5);
      if (t >= 1) {
        clearInterval(id);
        onDone?.();
      }
    }, 40);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, label]);

  return (
    <div className="d-bootwrap" role="status" aria-live="polite">
      <div className="d-bootlabel">
        <span>{label}</span>
        <span>{pct}%</span>
      </div>
      <div className="d-bootbar">
        <div className="d-bootbar-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/**
 * A labelled fact row, terminal style: dim key on the left, bright value on
 * the right, with a dotted leader between them like a status readout.
 */
export function TermRow({ k, v, accent }) {
  return (
    <div className="d-termrow">
      <span className="d-termkey">{k}</span>
      <span className="d-termdots" aria-hidden="true" />
      <span className={`d-termval ${accent ? "is-accent" : ""}`}>{v}</span>
    </div>
  );
}

/**
 * Falling "data streams", decorative. Rendered only while a panel is active,
 * since they are pure motion and cost a compositor layer each.
 */
export function DataStreams() {
  return (
    <div className="d-streamwrap" aria-hidden="true">
      <div className="d-streams" />
      <div className="d-streams d-streams-2" />
    </div>
  );
}

export default function TermPane({ title, subtitle, facts = [], bootKey, children }) {
  // Show the boot bar briefly whenever the selected game changes, then the
  // content. Keyed on bootKey so switching games replays it.
  const [booting, setBooting] = useState(true);
  useEffect(() => {
    setBooting(true);
  }, [bootKey]);
  useEffect(() => {
    if (!booting) return;
    const t = setTimeout(() => setBooting(false), 560);
    return () => clearTimeout(t);
  }, [booting, bootKey]);

  return (
    <section className="d-termpane d-term d-bevel">
      <DataStreams />
      <header className="d-termpane-head">
        <h2 className="d-head d-termpane-title">{title}</h2>
        {subtitle && <p className="d-termpane-sub">{subtitle}</p>}
        <div className="d-rule" />
      </header>
      {booting ? (
        <BootBar ms={520} />
      ) : (
        <div className="d-termpane-body">
          {facts.map((f) => (
            <TermRow key={f.k} k={f.k} v={f.v} accent={f.accent} />
          ))}
          {children}
        </div>
      )}
    </section>
  );
}
