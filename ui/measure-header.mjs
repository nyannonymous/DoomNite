// Drive the multiplayer button in REAL Chromium (Electron) and report what
// actually happens -- layout measurements AND the result of clicking it.
//
// WHY THIS FILE EXISTS
// --------------------
// Two jsdom suites pass while the button is visibly broken in ways they cannot
// see, because jsdom has no layout engine and does not apply the stylesheet:
//   * the header search box collapsed to nothing (a flex sizing bug);
//   * the button "does not work at all" from the user's side.
// Neither is visible to getBoundingClientRect returning zeros.
//
// WHY ELECTRON AND NOT THE BROWSER TOOL
// -------------------------------------
// The browser harness needs chrome://inspect/#remote-debugging enabled.
// Electron ships its own Chromium, runs headlessly, needs no user profile,
// and the desktop app already depends on it -- so this runs unattended.
//
// The probe is written as CommonJS (.cjs) because ui/package.json sets
// "type": "module", which makes a .js probe fail with
// "require is not defined in ES module scope".
//
// Run: node measure-header.mjs <bundle.js>
// Requires: python serve.py already running on 127.0.0.1:8765

import { existsSync, writeFileSync, unlinkSync } from "node:fs";
import { spawn } from "node:child_process";

const BASE = "http://127.0.0.1:8765";
const jsPath = process.argv[2];
if (!jsPath) {
  console.error("usage: node measure-header.mjs <bundle.js>");
  process.exit(2);
}

const ELECTRON =
  process.env.DOOMNITE_ELECTRON ||
  "../desktop/node_modules/electron/dist/electron.exe";
if (!existsSync(ELECTRON)) {
  console.error("electron not found at " + ELECTRON);
  process.exit(2);
}

const PROBE = "probe-main.cjs";
const probe = `
const { app, BrowserWindow } = require("electron");
app.disableHardwareAcceleration();

app.whenReady().then(async () => {
  const out = { consoleErrors: [] };
  const win = new BrowserWindow({ width: 1600, height: 900, show: false });
  win.webContents.on("console-message", (_e, _lvl, msg) => {
    const m = String(msg);
    if (/error|Failed|undefined is not|cannot read/i.test(m)) out.consoleErrors.push(m);
  });
  win.webContents.on("did-fail-load", (_e, code, desc) => {
    out.loadFailed = code + " " + desc;
  });

  try {
    await win.loadURL("${BASE}/");

    // Wait for the selector, do NOT sleep a fixed interval. A fixed 2500ms
    // produced intermittent FALSE NEGATIVES: on a slow run React had not
    // mounted yet, so the header boxes came back null and the click step
    // reported "no .mp-btn in DOM" for a button that was present in the very
    // same run's measurement block. A missing-element result from a harness is
    // only trustworthy if the harness proved it waited.
    const t0 = Date.now();
    let mounted = false;
    while (Date.now() - t0 < 20000) {
      mounted = await win.webContents.executeJavaScript(
        \`!!document.querySelector(".mp-btn") && document.querySelectorAll(".tile").length > 0\`
      );
      if (mounted) break;
      await new Promise((r) => setTimeout(r, 250));
    }
    out.mountedAfterMs = Date.now() - t0;
    out.mounted = !!mounted;
    if (!mounted) {
      out.unmountedHtml = await win.webContents.executeJavaScript(
        \`document.querySelector(".boot") ? "still on boot screen" :
          "root children: " + (document.querySelector("#root") ?
            document.querySelector("#root").children.length : "no #root")\`
      );
    }

    out.before = await win.webContents.executeJavaScript(\`(() => {
      const box = (sel) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        return {
          x: Math.round(r.x), y: Math.round(r.y),
          w: Math.round(r.width), h: Math.round(r.height),
          display: cs.display, flex: cs.flex,
          minWidth: cs.minWidth, maxWidth: cs.maxWidth,
          zIndex: cs.zIndex, position: cs.position, overflow: cs.overflow,
        };
      };
      const topbar = document.querySelector(".topbar");
      return {
        viewport: { w: innerWidth, h: innerHeight },
        topbar: box(".topbar"),
        topbarScrollW: topbar ? topbar.scrollWidth : null,
        topbarClientW: topbar ? topbar.clientWidth : null,
        search: box(".search"),
        searchInput: box(".search input"),
        chips: box(".chips"),
        mpBtn: box(".mp-btn"),
        brand: box(".brand"),
        stage: box(".stage"),
        statusbar: box(".statusbar"),
        tiles: document.querySelectorAll(".tile").length,
        topbarChildren: topbar ? [...topbar.children].map((el) => {
          const r = el.getBoundingClientRect();
          return {
            cls: el.className || el.tagName,
            x: Math.round(r.x), w: Math.round(r.width), right: Math.round(r.right),
            visible: r.width > 1 && r.height > 1,
            inViewport: r.right <= innerWidth + 1 && r.left >= -1,
          };
        }) : [],
      };
    })()\`);

    out.click = await win.webContents.executeJavaScript(\`(async () => {
      const res = { beforeOverlay: !!document.querySelector(".mp-overlay") };
      const btn = document.querySelector(".mp-btn");
      if (!btn) { res.err = "no .mp-btn in DOM"; return res; }
      const r0 = btn.getBoundingClientRect();
      res.btnRect = { x: Math.round(r0.x), y: Math.round(r0.y),
                      w: Math.round(r0.width), h: Math.round(r0.height) };
      res.btnDisabled = btn.disabled;
      res.hitTestAtCentre = (() => {
        const r = btn.getBoundingClientRect();
        const el = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
        return el ? (el.className || el.tagName) : "null";
      })();
      btn.click();
      await new Promise((r) => setTimeout(r, 1200));
      const ov = document.querySelector(".mp-overlay");
      res.afterOverlay = !!ov;
      if (ov) {
        const r = ov.getBoundingClientRect();
        const cs = getComputedStyle(ov);
        res.overlayBox = { x: Math.round(r.x), y: Math.round(r.y),
                           w: Math.round(r.width), h: Math.round(r.height) };
        res.overlayPosition = cs.position;
        res.overlayZ = cs.zIndex;
        res.overlayParent = ov.parentElement.tagName;
        res.coversViewport = r.width >= innerWidth - 2 && r.height >= innerHeight - 2;
        res.titleText = ov.querySelector(".mp-title") ? ov.querySelector(".mp-title").textContent.trim() : null;
        res.selectOptions = ov.querySelectorAll(".mp-select option").length;
        const sp = ov.querySelector(".mp-out--sm");
        res.statusText = sp ? sp.textContent.trim().slice(0, 300) : null;
        const modal = ov.querySelector(".mp-modal");
        const mr = modal.getBoundingClientRect();
        res.modalBox = { x: Math.round(mr.x), y: Math.round(mr.y),
                          w: Math.round(mr.width), h: Math.round(mr.height) };
        res.modalVisible = mr.width > 100 && mr.height > 100;
        res.modalCentreHit = (() => {
          const el = document.elementFromPoint(mr.x + mr.width / 2, mr.y + 30);
          return el ? (el.className || el.tagName) : "null";
        })();
      }
      return res;
    })()\`);

    out.dryRun = await win.webContents.executeJavaScript(\`(async () => {
      const ov = document.querySelector(".mp-overlay");
      if (!ov) return { err: "no overlay open" };
      const dry = [...ov.querySelectorAll(".mp-action")].find((b) => /dry-run/i.test(b.textContent));
      if (!dry) return { err: "no dry-run button" };
      dry.click();
      await new Promise((r) => setTimeout(r, 3000));
      const pre = ov.querySelector(".mp-out");
      return { text: pre ? pre.textContent.trim().slice(0, 400) : "(no output element)" };
    })()\`);

    // ---- the zero-config panel, WITHOUT launching anything ------------
    // The user-facing contract: press the button, setup happens by itself,
    // and two plain choices appear. This block deliberately never clicks Host
    // or Join -- that starts a real game on the owner's desktop. It measures
    // the read-only half, which is what can be proved unattended.
    out.panel = await win.webContents.executeJavaScript(\`(async () => {
      const ov0 = document.querySelector(".mp-overlay");
      if (ov0) ov0.click();
      await new Promise((r) => setTimeout(r, 200));
      const btn = document.querySelector(".mp-btn");
      btn.click();
      await new Promise((r) => setTimeout(r, 1800));
      const ov = document.querySelector(".mp-overlay");
      if (!ov) return { err: "panel did not open" };
      const res = { opened: true };
      const txt = ov.textContent;
      // The product rule: the user must not be shown NukemNet internals.
      res.leaks = {
        nukemnet: /nukemnet/i.test(txt),
        junction: /junction/i.test(txt),
        preset: /preset/i.test(txt),
      };
      // Where the leaked strings live, if any -- so a failure names the node.
      res.leakNodes = [];
      ov.querySelectorAll("*").forEach((el) => {
        const t = (el.textContent || "").trim();
        if (/nukemnet|junction|preset/i.test(t) && el.children.length === 0) {
          res.leakNodes.push((el.className || el.tagName) + ": " + t.slice(0, 60));
        }
      });
      res.buttons = [...ov.querySelectorAll(".mp-action")]
        .map((b) => ({ text: b.textContent.trim(), primary: b.classList.contains("mp-action--primary") }));
      res.selectOptions = ov.querySelectorAll(".mp-select option").length;
      res.selectedOption = ov.querySelector(".mp-select")?.selectedOptions?.[0]?.textContent?.trim();
      res.okBanner = !!ov.querySelector(".mp-ok");
      res.okText = ov.querySelector(".mp-ok")?.textContent?.trim();
      res.checkbox = !!ov.querySelector(".mp-check input");
      // Dialog geometry: does it fit, and is it actually on screen?
      const modal = ov.querySelector(".mp-modal");
      const mr = modal.getBoundingClientRect();
      res.dialog = {
        w: Math.round(mr.width), h: Math.round(mr.height),
        top: Math.round(mr.top), bottom: Math.round(mr.bottom),
        viewportH: innerHeight, viewportW: innerWidth,
        fitsVertically: mr.height <= innerHeight,
        fitsHorizontally: mr.width <= innerWidth,
        scrollsItself: modal.scrollHeight > modal.clientHeight + 1,
      };
      const scroller = ov.querySelector(".mp-scroll");
      res.scrollRegion = scroller ? {
        clientH: scroller.clientHeight, scrollH: scroller.scrollHeight,
        scrolls: scroller.scrollHeight > scroller.clientHeight + 1,
      } : null;
      res.headerPinned = (() => {
        const hd = ov.querySelector(".mp-header");
        const hr = hd.getBoundingClientRect();
        return { visible: hr.height > 10, top: Math.round(hr.top) };
      })();
      return res;
    })()\`);

  } catch (e) {
    out.fatal = String((e && e.stack) || e);
  }

  process.stdout.write("__PROBE__" + JSON.stringify(out) + "__END__");
  app.exit(0);
});
`;
writeFileSync(PROBE, probe);

const child = spawn(ELECTRON, [PROBE], {
  cwd: process.cwd(),
  stdio: ["ignore", "pipe", "pipe"],
});

let buf = "";
child.stdout.on("data", (d) => (buf += d.toString()));
child.stderr.on("data", (d) => process.stderr.write("[electron] " + d.toString()));

const killer = setTimeout(() => {
  child.kill();
  console.error("probe timed out after 90s");
  process.exit(1);
}, 90000);

child.on("exit", () => {
  clearTimeout(killer);
  try { unlinkSync(PROBE); } catch {}
  const m = buf.match(/__PROBE__(.*?)__END__/s);
  if (!m) {
    console.error("no probe output. stdout:\n" + buf.slice(0, 1500));
    process.exit(1);
  }
  const out = JSON.parse(m[1]);
  if (out.fatal) { console.error("probe threw: " + out.fatal); process.exit(1); }

  const b = out.before || {};
  const px = (o) => (o ? `${o.w}px @x=${o.x}` : "MISSING");
  console.log("\n=== viewport " + b.viewport?.w + "x" + b.viewport?.h + " ===");
  console.log("mounted: " + out.mounted + " after " + out.mountedAfterMs + "ms" +
    (out.unmountedHtml ? "  (" + out.unmountedHtml + ")" : ""));
  console.log("tiles rendered: " + b.tiles);
  console.log("\n--- header boxes ---");
  console.log("topbar    " + px(b.topbar) + "  scrollW=" + b.topbarScrollW + " clientW=" + b.topbarClientW);
  console.log("brand     " + px(b.brand));
  console.log("search    " + px(b.search) + "  flex=" + b.search?.flex + " min=" + b.search?.minWidth);
  console.log("  input   " + px(b.searchInput));
  console.log("chips     " + px(b.chips) + "  max=" + b.chips?.maxWidth);
  console.log("mp-btn    " + px(b.mpBtn));
  console.log("\n--- rest of the layout ---");
  console.log("stage     " + px(b.stage));
  console.log("statusbar " + px(b.statusbar));

  console.log("\n--- topbar children in DOM order ---");
  for (const c of b.topbarChildren || []) {
    console.log(
      `  ${String(c.w).padStart(5)}px @x=${String(c.x).padStart(5)} right=${String(c.right).padStart(5)}  <${c.cls}>  ` +
        [c.visible ? "" : "ZERO-WIDTH", c.inViewport ? "" : "OFF-SCREEN"].filter(Boolean).join(" ")
    );
  }

  console.log("\n--- after clicking .mp-btn ---");
  console.log(JSON.stringify(out.click, null, 1));
  console.log("\n--- after clicking dry-run ---");
  console.log(JSON.stringify(out.dryRun, null, 1));
  console.log("\n--- the zero-config panel (Host/Join, no NukemNet) ---");
  console.log(JSON.stringify(out.panel, null, 1));
  if (out.consoleErrors?.length) {
    console.log("\n--- console errors ---");
    for (const e of [...new Set(out.consoleErrors)].slice(0, 8)) console.log("  " + e.slice(0, 300));
  }
});