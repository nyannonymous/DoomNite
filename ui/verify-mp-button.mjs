// Assert the multiplayer panel's structural + request-contract invariants,
// against the LIVE server, in jsdom.
//
// WHY A NEW CHECK RATHER THAN ADDING TO verify.mjs
// -------------------------------------------------
// The first version of this button broke the entire layout while both existing
// suites still passed (21/21 and 11/11). Neither asserts where the button
// lives, and jsdom has no layout engine, so the symptom was invisible:
//
//   .app is `display: grid; grid-template-rows: auto minmax(0,1fr) auto`.
//   The button was a `position: static` <button> rendered as a direct child of
//   .app, BEFORE the <header>. A static element-level child of a grid
//   container is auto-placed into a cell, so it took row 1 (the header's row)
//   and pushed header, stage and footer down a row each -- an implicit 4th row
//   in a container pinned to `height: 100%`. The fix is tree-shape, which is
//   exactly what jsdom CAN assert.
//
// It runs against the REAL /api/entries, because the index contract is only
// meaningful against the server's actual entry order: serve.py emits no
// `index` field on entries (verified against the keys load_entries() writes),
// so an earlier `playable[i]?.index ?? i` ALWAYS fell through to the array
// position. `playable` is FILTERED (standalone games and IWAD-less entries are
// dropped), so position and server index diverge for every entry after the
// first drop -- picking "Aliens" would have hosted a different game.
//
// WHAT IT WILL NOT CLAIM
// ---------------------
// jsdom has no layout, so this file proves DOM shape and request bodies. It
// says nothing about whether the dialog is actually on screen. That needs
// measure-header.mjs (real Chromium) -- the two are complementary, and a bug
// like "the toast is painted behind the modal" is only visible in the latter.
//
// Run: node verify-mp-button.mjs <bundle.js>
// Requires: python serve.py already running on 127.0.0.1:8765.

import { readFileSync } from "node:fs";
import { JSDOM, VirtualConsole } from "jsdom";

const BASE = "http://127.0.0.1:8765";
const jsPath = process.argv[2];
if (!jsPath) {
  console.error("usage: node verify-mp-button.mjs <bundle.js>");
  process.exit(2);
}

const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", (e) => errors.push("jsdomError: " + (e.stack || e.message)));
vc.on("error", (...a) => errors.push("console.error: " + a.join(" ")));
vc.on("warn", (...a) => {
  const m = a.join(" ");
  if (!/not wrapped in act|strict mode/i.test(m)) errors.push("warn: " + m);
});

const dom = new JSDOM(
  `<!doctype html><html><head></head><body><div id="root"></div></body></html>`,
  { url: BASE + "/", runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc }
);
const { window } = dom;

// jsdom has neither canvas nor ResizeObserver; a missing API here would read as
// a UI bug rather than a harness gap.
window.HTMLCanvasElement.prototype.getContext = function () {
  const target = {
    canvas: this,
    measureText: (t) => ({ width: String(t).length * 6 }),
    createLinearGradient: () => ({ addColorStop() {} }),
    createRadialGradient: () => ({ addColorStop() {} }),
    getImageData: () => ({ data: new Uint8ClampedArray(4) }),
  };
  return new Proxy(target, {
    get: (t, p) => (p in t ? t[p] : typeof p === "symbol" ? undefined : () => {}),
    set: (t, p, v) => ((t[p] = v), true),
  });
};
window.HTMLCanvasElement.prototype.toDataURL = () => "data:image/png;base64,iVBORw0KGgo=";
window.ResizeObserver = class { observe() {} disconnect() {} };
window.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 16);
window.cancelAnimationFrame = (id) => clearTimeout(id);
window.scrollTo = () => {};
window.Element.prototype.scrollIntoView = function () {};

// Record the multiplayer POSTs so the request contract can be asserted, and
// forward everything else untouched. HOST AND JOIN ARE NEVER CALLED HERE: a
// launch would start a real game on the owner's desktop, which is not this
// file's job to do unattended. measure-header.mjs covers the read-only half.
const mpCalls = [];
window.fetch = (input, init) => {
  const url = new URL(input, BASE).href;
  if (url.includes("/api/multiplayer/")) {
    let body = {};
    try { body = JSON.parse(init?.body || "{}"); } catch {}
    mpCalls.push({ path: url.replace(BASE, ""), method: init?.method || "GET", body });
    // Every multiplayer POST here is setup-only; anything else would launch a
    // game, so refuse it loudly rather than pretending it succeeded.
    if (!url.includes("/setup")) {
      return Promise.resolve({
        ok: false, status: 418,
        json: () => Promise.resolve({ error: "verify harness will not launch games" }),
        text: () => Promise.resolve("refused"),
        headers: { get: () => "application/json" },
      });
    }
  }
  return fetch(url, init);
};

window.eval(readFileSync(jsPath, "utf8"));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await sleep(1200);

const d = window.document;
const results = [];
const check = (name, pass, detail = "") => results.push({ name, pass, detail });

// --- the button --------------------------------------------------------
const btn = d.querySelector(".mp-btn");
check("the multiplayer button renders", !!btn,
  btn ? btn.textContent.trim() : "no .mp-btn in DOM");
if (!btn) {
  console.log("FAIL  no .mp-btn; the component did not mount");
  for (const e of [...new Set(errors)].slice(0, 12)) console.log("  " + e.slice(0, 400));
  process.exit(1);
}

// --- it must not be a grid child of .app -------------------------------
const topbar = d.querySelector(".topbar");
const app = d.querySelector(".app");
check("the button lives inside .topbar", !!topbar?.contains(btn),
  `parent=<${btn.parentElement.className || btn.parentElement.tagName}>`);
check("the button is NOT a direct child of .app",
  !btn.parentElement.classList.contains("app"),
  `parent=<${btn.parentElement.className || btn.parentElement.tagName}>`);

// .app's last three children must be topbar -> stage -> statusbar. This is the
// condition a stray in-flow child breaks. Filtered by getComputedStyle
// position would be WRONG here: jsdom does not apply the stylesheet, so the
// nine decorative overlays (d-hero, embers, ...) all report position:static
// even though they are fixed in CSS.
const kids = app ? [...app.children] : [];
const kidClasses = kids.map((el) => el.className || el.tagName);
const tail = kidClasses.slice(-3);
check("the last three children of .app are topbar -> stage -> statusbar",
  tail.length === 3 && tail[0].includes("topbar") &&
  tail[1].includes("stage") && tail[2].includes("statusbar"),
  `[${tail.join(" -> ")}] of ${kids.length}`);
check("no topbar/stage/statusbar appears before them",
  kidClasses.slice(0, -3).every((c) => !/topbar|stage|statusbar/.test(c)),
  `[${kidClasses.slice(0, -3).join(", ")}]`);

// --- opening runs the hidden setup --------------------------------------
mpCalls.length = 0;
btn.click();
await sleep(900);

const overlay = d.querySelector(".mp-overlay");
check("clicking the button opens the dialog", !!overlay);
check("the dialog is portalled to document.body",
  !!overlay && overlay.parentElement === d.body,
  overlay ? `parent=<${overlay.parentElement.tagName}>` : "");
check("the dialog is NOT nested inside .topbar",
  !!overlay && !topbar.contains(overlay));

const setup = mpCalls.find((c) => c.path.endsWith("/setup"));
check("opening it calls /api/multiplayer/setup automatically", !!setup,
  setup ? `${setup.method} ${setup.path} ${JSON.stringify(setup.body)}` : "never called");

// --- and the user is not asked about NukemNet ---------------------------
// The product rule: they should not know NukemNet exists. So the visible panel
// must not name it. This is a real assertion, not a comment: the previous
// dialog was titled "MULTIPLAYER - NukemNet Setup" and made the user pick a
// preset out of a list of 30, which is exactly the complexity being removed.
const visible = overlay?.textContent || "";
check("the panel never mentions NukemNet", !/nukemnet/i.test(visible),
  /nukemnet/i.test(visible)
    ? "found: " + visible.match(/.{0,30}nukemnet.{0,30}/i)?.[0]
    : "");
check("the panel offers Host and Join",
  /host/i.test(visible) && /join/i.test(visible));
check("the panel never mentions junctions",
  !/junction/i.test(visible),
  /junction/i.test(visible) ? "found" : "");
check("the panel never mentions a preset",
  !/preset/i.test(visible),
  /preset/i.test(visible) ? "found" : "");

// --- the game list matches the server's playable set --------------------
const realEntries = (await (await fetch(`${BASE}/api/entries`)).json()).entries || [];
const expectPlayable = realEntries
  .map((e, i) => ({ e, i }))
  .filter(({ e }) => e.kind === "pack" && e.iwad);
const select = overlay?.querySelector(".mp-select");
const options = select ? [...select.options].map((o) => o.textContent.trim()) : [];
check("a game picker renders", !!select);
check("it lists every pack entry with an IWAD",
  options.length === expectPlayable.length,
  `${options.length} options vs ${expectPlayable.length} eligible of ${realEntries.length}`);

// --- and every option carries its OWN server index ----------------------
// setup() is the only multiplayer POST this harness allows, and the panel
// sends the SELECTED entry's index in its body. Walk the list and confirm the
// index moves with the selection -- which is only true if _idx survived the
// filter. An array position would send a constant wrong number for all but the
// first option.
let idxMismatch = null;
if (select && setup) {
  const before = setup.body.index;
  if (options.length > 1) {
    select.value = String(options.length - 1);
    select.dispatchEvent(new window.Event("change", { bubbles: true }));
    await sleep(120);
    // Re-open to observe a second setup body with the new selection.
    const again = d.querySelector(".mp-btn");
    d.querySelector(".mp-overlay")?.click();
    await sleep(150);
    again?.click();
    await sleep(700);
    const second = mpCalls.filter((c) => c.path.endsWith("/setup")).pop();
    const want = expectPlayable[options.length - 1]?.i;
    if (!second || second.body.index !== want) {
      idxMismatch = `picked the last option (${options[options.length - 1]}) and setup ` +
        `posted index=${second?.body.index}, server index is ${want} ` +
        `(first option posted ${before})`;
    }
  }
}
check("the selected game's own server index is what gets posted",
  !idxMismatch, idxMismatch || (options.length > 1
    ? `${options.length} options, first=${expectPlayable[0]?.i} last=${expectPlayable[expectPlayable.length - 1]?.i}`
    : "only one option"));

// --- closing ------------------------------------------------------------
d.querySelector(".mp-overlay")?.click();
await sleep(250);
check("clicking the backdrop closes the dialog", !d.querySelector(".mp-overlay"));

// --- the harness never launched anything -------------------------------
const launched = mpCalls.filter((c) => c.path.endsWith("/host") || c.path.endsWith("/join"));
check("the harness never launched a game", launched.length === 0,
  launched.length ? launched.map((c) => c.path).join(", ") : "only /setup was called");

check("no unexpected runtime errors", errors.length === 0,
  [...new Set(errors)].slice(0, 2).join(" | "));

// --- ordering: the choice comes before the name field -------------------
// The panel used to render "Your name" above the Host/Join buttons, so the
// only visible input was a name box and a network address got pasted into it.
// Assert the order in the source, since jsdom here renders no layout.
{
  const f = readFileSync(new URL("./src/MultiplayerButton.jsx", import.meta.url), "utf8");
  const hostBtn = f.indexOf("Host a game");
  const joinBtn = f.indexOf("Join a game");
  const nameLbl = f.search(/<span className="mp-label">\s*Your name/);

  check("Host button exists", hostBtn !== -1);
  check("Join button exists", joinBtn !== -1);
  check("name field exists", nameLbl !== -1);
  check("Host/Join come BEFORE the name field",
    hostBtn !== -1 && nameLbl !== -1 && hostBtn < nameLbl,
    `host@${hostBtn} name@${nameLbl}`);
  check("panel leads with the host-or-join question",
    f.includes("Hosting a game or joining one?"));
  check("address field says to paste the whole line",
    f.includes("paste the whole line here"));
}

let pass = 0, fail = 0;
for (const r of results) {
  if (r.pass) { pass++; console.log(`PASS  ${r.name}${r.detail ? "  [" + r.detail + "]" : ""}`); }
  else { fail++; console.log(`FAIL  ${r.name}${r.detail ? "  [" + r.detail + "]" : ""}`); }
}

console.log(`\n${pass}/${pass + fail} checks passed`);
if (fail) process.exit(1);
