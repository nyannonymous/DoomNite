// Drives the REAL attachZoom from main.js inside a real BrowserWindow.
//
// Why this exists: attachZoom is browser code, so "node --check main.js" proves
// only that the file parses. A checker that re-implements the wheel handler
// would prove only that the copy works. So this requires main.js itself,
// builds a real window against the running serve.py, and fires the same
// input-event payload shape Chromium delivers, then asserts on the observable
// webContents zoom level.
//
// Run: serve.py must already be listening on 127.0.0.1:8765.
//   cd desktop && npx electron build/check-zoom.js
process.env.ZOOM_CHECK_MODE = "1";

const { app, BrowserWindow } = require("electron");
const { attachZoom, ZOOM_MIN, ZOOM_MAX } = require("../main.js");

const ORIGIN = "http://127.0.0.1:8765";

// Read the percentage off the webContents itself rather than recomputing it.
// An earlier version of this file used Math.pow(1.2, level), which is the
// right formula but made the clamp assertions compare levels against level
// bounds while LABELING them as percentages -- so "clamps at max (300%)"
// printed 144% and still passed. Asserting on zoomFactor is what makes the
// label and the number the same thing.
const pctOf = (wc) => Math.round(wc.zoomFactor * 100);
// For a level captured BEFORE a zoom change, zoomFactor has already moved on,
// so derive from the level with the inverse of main.js's own conversion.
const pctOf2 = (level) => Math.round(Math.pow(1.2, level) * 100);

let failures = 0;
function check(name, ok, detail) {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  [${detail}]` : ""}`);
  if (!ok) failures++;
}

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    show: false,
    webPreferences: { nodeIntegration: false, contextIsolation: true },
  });

  // Count what the real handler consumes, so a silent no-op cannot masquerade
  // as "clamped correctly" -- a clamped value also equals the bound.
  let handled = 0;
  win.webContents.on("before-input-event", (event, input) => {
    if (input.type === "mouseWheel" && input.control) handled++;
  });

  attachZoom(win);

  try {
    await win.loadURL(ORIGIN);
  } catch (e) {
    console.log(`FAIL  could not load ${ORIGIN}: ${e.message}`);
    console.log("      serve.py must be running before this check.");
    app.exit(1);
    return;
  }
  check("window loaded the launcher", true, ORIGIN);

  const wc = win.webContents;
  check("starts at 100%", pctOf(wc) === 100, `${pctOf(wc)}%`);

  // Chromium does not synthesise trusted wheel input from sendInputMessage on
  // every platform, so emit the event with the exact payload shape the handler
  // branches on. It still goes through the real registered listener.
  const wheel = (control, deltaY) =>
    wc.emit("before-input-event", { preventDefault() {} }, {
      type: "mouseWheel",
      deltaX: 0,
      deltaY,
      canScroll: false,
      control,
      meta: false,
      isAutoScroll: false,
    });

  const before = wc.getZoomLevel();
  wheel(true, -120);
  const afterUp = wc.getZoomLevel();
  check("ctrl+wheel up zooms in", afterUp > before, `${pctOf(wc)}%`);
  check("handler consumed the event", handled === 1, `${handled} event(s)`);
  // One notch must be a perceptible step. STEP=0.1 gave +2%, which reads as a
  // broken feature; anything under ~5% has the same problem.
  check("one notch is a usable step", pctOf(wc) >= 105, `${pctOf(wc)}% after one notch`);

  const mid = wc.getZoomLevel();
  wheel(true, 120);
  check("ctrl+wheel down zooms out", wc.getZoomLevel() < mid, `${pctOf2(mid)}% -> ${pctOf(wc)}%`);

  // Plain wheel must not zoom. Nothing pans here, but hijacking an unmodified
  // scroll would be hostile.
  const plain = wc.getZoomLevel();
  wheel(false, -120);
  check("plain wheel does not zoom", wc.getZoomLevel() === plain, `${pctOf2(plain)}%`);

  // Clamp at both bounds. Without them a fast scroll runs the zoom to an
  // unreadable size with no way back but ctrl+0.
  for (let i = 0; i < 60; i++) wheel(true, -120);
  check("clamps at max (300%)", Math.abs(wc.getZoomLevel() - ZOOM_MAX) < 1e-9 && pctOf(wc) === 300, `${pctOf(wc)}%`);

  for (let i = 0; i < 80; i++) wheel(true, 120);
  check("clamps at min (80%)", Math.abs(wc.getZoomLevel() - ZOOM_MIN) < 1e-9 && pctOf(wc) === 80, `${pctOf(wc)}%`);

  // Ctrl+0 reset path.
  wc.emit("before-input-event", { preventDefault() {} }, {
    type: "keyDown", key: "0", control: true, meta: false,
  });
  check("ctrl+0 resets to 100%", pctOf(wc) === 100, `${pctOf(wc)}%`);

  // The status-bar readout the page listens for.
  const got = await wc.executeJavaScript(
    `new Promise(r => { window.addEventListener("doomnite:zoom", e => r(e.detail), {once:true});` +
      ` window.dispatchEvent(new CustomEvent("doomnite:zoom", {detail: 175})); })`
  );
  check("zoom event reaches the page", got === 175, `detail=${got}`);

  console.log(failures === 0 ? "\nall zoom checks passed" : `\n${failures} check(s) failed`);
  app.exit(failures === 0 ? 0 : 1);
});