import { useEffect, useRef, useState } from "react";
import { Download, X, ShieldCheck } from "lucide-react";

/* Confirmation before an on-demand download.

   Clicking INSTALL used to start a network fetch immediately, with nothing on
   screen but a progress bar -- so a misclick cost a real download from a third
   party before anyone could see where it was going. The two games this affects
   are the only ones in the pack that are not already on disk, which is exactly
   why they get a prompt: it is the one action in the app that reaches the
   network.

   It names the file, the size, the host it will come from, and where it lands,
   because "download 42 MB from adventuresofsquare.com" is a decision someone
   can actually make. Escape and Cancel both abort; focus goes to Cancel so a
   stray Enter does not start the download. */

export default function ConfirmDownload({ spec, onCancel, onConfirm }) {
  const cancelRef = useRef(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    cancelRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const files = spec?.files?.length ? spec.files.join(", ") : "";

  async function go() {
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="setup" role="dialog" aria-modal="true" aria-labelledby="cd-h">
      <div className="setup-card">
        <header className="setup-hd">
          <h2 id="cd-h">DOWNLOAD</h2>
          <button
            type="button"
            className="setup-x"
            onClick={onCancel}
            aria-label="Cancel download"
            disabled={busy}
          >
            <X size={15} aria-hidden="true" />
          </button>
        </header>

        <p className="setup-lede">
          {spec?.label} is not in the pack. It has to be downloaded before it
          can be played.
        </p>

        <ul className="cd-list">
          <li>
            <span className="cd-k">FILE</span>
            <span className="cd-v">{files}</span>
          </li>
          <li>
            <span className="cd-k">SIZE</span>
            <span className="cd-v">{spec?.size_h}</span>
          </li>
          <li>
            <span className="cd-k">FROM</span>
            <span className="cd-v">{spec?.host || "unknown host"}</span>
          </li>
          <li>
            <span className="cd-k">INTO</span>
            <span className="cd-v">modsl{"/"}&lt;game&gt;{"/"}&lt;file&gt;</span>
          </li>
        </ul>

        <p className="cd-note">
          <ShieldCheck size={13} aria-hidden="true" />
          Checked against a pinned SHA-256. A file that does not match is
          discarded, not installed.
        </p>

        <div className="setup-ft">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={onCancel}
            ref={cancelRef}
            disabled={busy}
          >
            CANCEL
          </button>
          <button type="button" className="btn btn-inst" onClick={go} disabled={busy}>
            <Download size={14} aria-hidden="true" />
            {busy ? "STARTING" : `DOWNLOAD ${spec?.size_h || ""}`}
          </button>
        </div>
      </div>
    </div>
  );
}
