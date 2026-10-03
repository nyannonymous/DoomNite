import { motion, useReducedMotion } from "framer-motion";
import {
  Play,
  Terminal as TerminalIcon,
  Wrench,
  Download,
  Trash2,
  Check,
  HardDrive,
} from "lucide-react";
import { useEffect, useState } from "react";
import { dryrun, launchIndex, startInstall, removeInstall, removePackMod as apiRemovePackMod } from "./api";
import { Cover } from "./Tile";
import ConfirmDownload from "./ConfirmDownload";
import { Typed, TermRow, BootBar, DataStreams } from "./Terminal";

function bytes(n) {
  if (!n) return "";
  return n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`;
}

export default function Panel({
  group,
  onPick,
  toast,
  inst,
  pm,
  onInstalled,
  onPackModRemoved,
}) {
  const reduced = useReducedMotion();
  const [busy, setBusy] = useState(false);
  // Brief boot readout on every game switch. Purely presentational: the details
  // below are already mounted, this just covers them for half a second.
  const [booting, setBooting] = useState(true);
  useEffect(() => {
    setBooting(true);
    const t = setTimeout(() => setBooting(false), 480);
    return () => clearTimeout(t);
  }, [group?.key]);
  const [cmd, setCmd] = useState(null);
  const [cmdOpen, setCmdOpen] = useState(false);

  /* ---------------------------------------------------------- on-demand install */
  // Same pattern as the card: the server's answer is authoritative. The prop
  // is refreshed by App's poll, so this panel never invents install state.
  const installed = !!inst?.installed;
  const instBusy = !!inst?.state && inst.state === "downloading";
  const instPct = inst?.size
    ? Math.round(((inst.received || 0) / inst.size) * 100)
    : 0;
  const [instError, setInstError] = useState(null);

  // Prompts before downloading, like the card does. A download is the only
  // action here that touches the network.
  const [confirming, setConfirming] = useState(false);

  async function doInstall() {
    setInstError(null);
    try {
      await startInstall(group.needsInstall);
    } catch (e) {
      setInstError(String(e.message || e));
    }
  }

  async function doUninstall() {
    setInstError(null);
    try {
      await removeInstall(group.needsInstall);
      onInstalled?.();
    } catch (e) {
      setInstError(String(e.message || e));
    }
  }

  /* ------------------------------------------------ baked-in mod removal */
  // The card used to own this (a trash icon in its top-left corner). Both
  // kinds of removal now live in this sidebar, side by side: one place to
  // look for "remove this", and the destructive action is never sitting under
  // a scanning cursor.
  const [pmBusy, setPmBusy] = useState(false);
  const [pmError, setPmError] = useState(null);
  // pm is null for a group with no mods\ folders at all (a pure-IWAD entry)
  // and for the two on-demand entries, which use `inst` above instead.
  const pmInstalled = !!pm?.installed;
  const pmPartial = !!pm?.partial;
  const pmRemovable = !!pm && (pmInstalled || pmPartial) && pm.exclusive.length > 0;

  async function removePackMod() {
    if (!pmRemovable || pmBusy) return;
    setPmBusy(true);
    setPmError(null);
    try {
      await apiRemovePackMod(group.key);
      onPackModRemoved?.();
      onInstalled?.(); // the tile's `exists` must flip too
    } catch (e) {
      setPmError(String(e.message || e));
    } finally {
      setPmBusy(false);
    }
  }

  // Re-fetch the command whenever the selected config changes, so the panel
  // never shows a stale command for the previous variant.
  useEffect(() => {
    let alive = true;
    setCmd(null);
    if (!group) return;
    // Preview the command the PLAY button will actually run.
    const cfg = group.cfgs[0];
    dryrun(cfg.index)
      .then((d) => {
        if (alive) setCmd(d);
      })
      .catch(() => {
        if (alive) setCmd({ error: true });
      });
    return () => {
      alive = false;
    };
  }, [group?.key, group?.pick]);

  if (!group) {
    return (
      <aside className="panel panel-empty">
        <p>Select a game</p>
      </aside>
    );
  }

  // The selected config (for the Details readout) is NOT the one the big PLAY
  // button launches. This used to be one variable, so the top button silently
  // launched whatever row happened to be highlighted -- and the card buttons,
  // which always passed index 0, launched something different from the sidebar
  // for the same game. Now the primary build is its own named thing:
  //
  //   PRIMARY  = the build the big PLAY button and every card PLAY button run.
  //   pick     = which build's details are shown in the readout below.
  //
  // Anything other than the primary is launched deliberately, from its own row.
  const primary = group.cfgs[0];
  const cfg = group.cfgs[group.pick] || primary;
  const disabled = busy || primary.exists === false;

  async function play(which) {
    setBusy(true);
    try {
      const r = await launchIndex(which.index);
      toast(`Launched: ${r.label}`);
    } catch (e) {
      toast(`Failed: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  }

  return (
    // key={group.key} remounts on every switch, which is what replays the
    // entrance. x offset plus a slight skew reads as a mechanical slide rather
    // than a fade.
    <motion.aside
      className="panel"
      key={group.key}
      initial={reduced ? false : { opacity: 0, x: 34, skewX: -1.6 }}
      animate={reduced ? undefined : { opacity: 1, x: 0, skewX: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 26, mass: 0.8 }}
    >
      <Cover group={group} className="panel-cover" />
      {/* Falling data streams behind the readout. Decorative only, so it is
          aria-hidden and pointer-transparent in the component. */}
      <DataStreams />
      {/* UAC boot sequence, shown once per game switch. The panel remounts on
          key change, so a fresh mount is a fresh boot -- no extra state. */}
      {booting ? (
        <div className="panel-boot">
          <BootBar ms={520} label="LOADING" />
        </div>
      ) : null}

      {/* Primary action lives ABOVE the scroll area, not at the bottom of it.
          It used to be the last thing in .panel-scroll, below Configs,
          Details, the term rows and the whole mod list -- so on a short window
          the one control you actually want was the one you had to scroll to
          find. Pinned here, under the title, it is always reachable. */}
      <div className="panel-head">
        <h2 className="panel-title d-head d-glitch" data-text={group.label}>
          {group.label}
        </h2>
        <div className="panel-actions">
          <button
            type="button"
            className="play"
            onClick={() => play(primary)}
            disabled={disabled}
            // Naming the build on the button itself: with several configs on a
            // game it was otherwise impossible to tell what PLAY would run, and
            // it was not the highlighted row.
            title={`Launch ${primary.label || "config 1"}`}
          >
            <span className="play-glow" aria-hidden="true" />
            <Play size={18} strokeWidth={2.5} aria-hidden="true" />
            <span className="play-label">{busy ? "Starting…" : "Play"}</span>
            <span className="play-key">↵</span>
          </button>
          <button
            type="button"
            className="showcmd"
            onClick={() => setCmdOpen((v) => !v)}
          >
            {cmdOpen ? "Hide" : "Cmd"}
          </button>
        </div>
        {/* Which build PLAY runs, stated rather than implied. */}
        <p className="play-target" aria-live="polite">
          <span className="play-target-k">launches</span>
          <span className="play-target-v" title={primary.label || ""}>
            {primary.label || "config 1"}
          </span>
        </p>
      </div>

      <div className="panel-scroll">
        {/* The description types itself out, keyed on the game so switching
            games replays it. That replay is the mechanical feel. */}
        {group.note && (
          <p className="panel-note d-term">
            <Typed text={group.note} speed={10} />
          </p>
        )}

        {group.cfgs.length > 1 && (
          <section className="panel-section">
            <h3>Configs</h3>
            <div className="cfgs">
              {group.cfgs.map((c, n) => (
                // Row = [choose-this-build] + [play-this-build]. Wrapped because
                // the play glyph is a separate button, and the old .cfg button
                // used to be a direct flex child of .cfgs.
                <div className="cfg-row" key={c.index}>
                <button
                  type="button"
                  className={`cfg ${n === group.pick ? "is-on" : ""}`}
                  onClick={() => onPick(n)}
                >
                  <span className="cfg-radio" aria-hidden="true" />
                  <span className="cfg-text">
                    <span className="cfg-label" title={c.label || `config ${n + 1}`}>
                      {c.label || `config ${n + 1}`}
                    </span>
                    {c.mods.length > 0 && (
                      // Long filenames truncate to an ellipsis, so the full list
                      // goes in the title attribute -- otherwise the truncated
                      // row is unreadable and the panel just looks broken.
                      <span className="cfg-mods" title={c.mods.join("\n")}>
                        {c.mods.join("  ·  ")}
                      </span>
                    )}
                  </span>
                  <span className="cfg-iwad">{(c.iwad || "").replace(/\.WAD$/i, "")}</span>
                </button>
                {/* Non-primary builds are launched deliberately, from their own
                    row. Before this the only way to run one was the right-click
                    context menu, which is undiscoverable. Clicking the row itself
                    just chooses which build the Details readout describes. */}
                <button
                  type="button"
                  className={`cfg-go ${n === 0 ? "is-primary" : ""}`}
                  onClick={() => play(c)}
                  disabled={busy || c.exists === false}
                  title={
                    c.exists === false
                      ? `${c.label || `config ${n + 1}`} — not installed`
                      : `Play ${c.label || `config ${n + 1}`}`
                  }
                  aria-label={`Play ${c.label || `config ${n + 1}`}`}
                >
                  <Play size={12} strokeWidth={3} aria-hidden="true" />
                </button>
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="panel-section">
          <h3>Details</h3>
          <dl className="facts">
            <dt>IWAD</dt>
            <dd>{cfg.iwad || "—"}</dd>
            <dt>Config</dt>
            <dd>#{cfg.index + 1}</dd>
            {group.kind === "pack" ? (
              <>
                <dt>Mods</dt>
                <dd>{cfg.mods.length || "none"}</dd>
              </>
            ) : (
              <>
                <dt>Engine</dt>
                <dd>standalone</dd>
              </>
            )}
          </dl>
          {cfg.mods.length > 0 && (
            <ul className="mods">
              {cfg.mods.map((m, i) => (
                <li key={i} style={{ "--i": i }} title={m}>
                  {m}
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Terminal summary strip. TermRow gives the dotted-leader readout
            look; this is the same info the old <dl> carried, restated in the
            UAC idiom. */}
        <div className="panel-termrows">
          <TermRow k="build" v={cfg.label || `#${cfg.index + 1}`} accent={cfg.hd} />
          <TermRow k="iwad" v={(cfg.iwad || "standalone").replace(/\.WAD$/i, "")} />
          <TermRow k="mods" v={cfg.mods.length || "none"} />
          {group.cfgs.length > 1 && (
            <TermRow k="builds" v={`${group.cfgs.length} available`} />
          )}
        </div>

        {cmdOpen && (
          <pre className="cmd">
            {cmd
              ? cmd.error
                ? "Could not read the command."
                : cmd.command
              : "Reading…"}
          </pre>
        )}

        {/* On-demand total conversion: install/uninstall at the bottom of the
            sidebar, where the rest of this game's controls live.

            Everything else in the pack ships inside it, so it has nothing to
            install or remove. That used to mean this whole block simply
            vanished, while the card showed an IN PACK label -- so the same
            game said two different things in two places. It now says the same
            thing here too. */}
        {!group.needsInstall && (
                  <div className="panel-install">
                    {pmError && (
                      <p className="warn" role="alert">
                        {pmError}
                      </p>
                    )}
                    {/* Baked-in mods get their removal HERE, not on the card. Every
                        tile used to carry a trash icon in its top-left corner, which
                        put the pack's most destructive action in the most repeated
                        position on screen -- reachable by a stray click while scanning
                        the grid, with no confirmation step between the click and
                        deleting a folder. One place, beside the on-demand UNINSTALL
                        above, means both kinds of removal read the same way and both
                        are deliberate.

                        Only offered when there is something exclusive to delete. A
                        game whose every file is shared with another (BDBE "HontE
                        Remastered" shares all four of its slugs with "Enhanced
                        Episode 1") would reclaim nothing, and a button that always
                        silently does nothing is worse than no button -- so the
                        explanation is shown instead. */}
                    <p className="panel-inpack">
                      <HardDrive size={13} aria-hidden="true" />
                      {group.fetchable
                        ? "Can be re-fetched from hosted URLs"
                        : "Ships inside the pack"}
                      {pm?.size_h ? ` · ${pm.size_h}` : ""}
                    </p>
                    {pmRemovable ? (
                      <button
                        type="button"
                        className="btn-ghost is-danger"
                        onClick={removePackMod}
                        disabled={pmBusy}
                      >
                        <Trash2 size={13} aria-hidden="true" />
                        {pmBusy ? "Removing..." : "REMOVE FROM PACK"}
                      </button>
                    ) : (
                      pm &&
                      !pmInstalled &&
                      !pmPartial && (
                        <p className="panel-dlhint">
                          <Trash2 size={13} aria-hidden="true" />
                          Already removed. Restore with{" "}
                          <code>python tools\build.py</code>
                        </p>
                      )
                    )}
                    {/* A shared-slug game is still installed and still has nothing
                        removable. Say why, rather than leaving the user wondering
                        where the button went. */}
                    {pm && pmInstalled && !pmRemovable && pm.shared.length > 0 && (
                      <p className="panel-dlhint">
                        <HardDrive size={13} aria-hidden="true" />
                        All {pm.folders.length} file(s) are shared with another game, so
                        removing this entry would free nothing.
                      </p>
                    )}
                  </div>
                )}
        {group.needsInstall && (
          <div className="panel-install">
            {instError && (
              <p className="warn" role="alert">
                {instError}
              </p>
            )}
            {installed ? (
              <>
                <p className="panel-installed">
                  <Check size={13} aria-hidden="true" />
                  Installed{inst?.size_h ? ` · ${inst.size_h}` : ""}
                </p>
                <button
                  type="button"
                  className="btn-ghost is-danger"
                  onClick={doUninstall}
                  disabled={instBusy}
                >
                  <Trash2 size={13} aria-hidden="true" />
                  {instBusy ? "Working..." : "UNINSTALL"}
                </button>
              </>
            ) : (
              <>
                {instBusy ? (
                  <div className="panel-dlbar" role="status" aria-live="polite">
                    <span className="panel-dlfill" style={{ width: `${instPct}%` }} />
                    <span className="panel-dltext">
                      {inst?.size_h ? `${inst.size_h} · ` : ""}
                      {instPct}%
                    </span>
                  </div>
                ) : (
                  <p className="panel-dlhint">
                    <Download size={13} aria-hidden="true" />
                    Not in the pack. Downloaded on demand
                    {inst?.size_h ? ` (${inst.size_h})` : ""}.
                  </p>
                )}
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => setConfirming(true)}
                  disabled={instBusy}
                >
                  <Download size={13} aria-hidden="true" />
                  {instBusy ? "Downloading..." : "INSTALL"}
                </button>
              </>
            )}
          </div>
        )}

        {cfg.exists === false && !group.needsInstall && (
          <p className="warn">This config&apos;s files are missing from the pack.</p>
        )}
      </div>
      {confirming && inst && (
        <ConfirmDownload
          spec={inst}
          onCancel={() => setConfirming(false)}
          onConfirm={doInstall}
        />
      )}
    </motion.aside>
  );
}
