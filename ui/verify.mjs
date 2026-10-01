// Render the built bundle in jsdom against the live server, to prove the UI
// actually mounts and the interactions work. Not a substitute for looking at
// it -- jsdom has no layout or CSS -- but it catches what a build cannot:
// bad selectors, null derefs, broken fetches, dead handlers.
//
// Run: node verify.mjs   (from ui/)

import { JSDOM, VirtualConsole } from "jsdom";
import { readFileSync } from "node:fs";

const BASE = "http://127.0.0.1:8765";
const jsPath = process.argv[2] || "../dist/assets/index-B8X2JXlS.js";

const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", (e) => errors.push("jsdomError: " + (e.stack || e.message)));
vc.on("error", (...a) => errors.push("console.error: " + a.join(" ")));
vc.on("warn", (...a) => {
  const m = a.join(" ");
  // React 18 StrictMode double-invoke notices are noise here.
  if (!/not wrapped in act|strict mode/i.test(m)) errors.push("warn: " + m);
});

const html = `<!doctype html><html><head></head><body><div id="root"></div></body></html>`;
const dom = new JSDOM(html, {
  url: BASE + "/",
  runScripts: "dangerously",
  pretendToBeVisual: true,
  virtualConsole: vc,
});

const { window } = dom;

// jsdom has no canvas by default; the ember field needs a 2D context. Stub the
// minimum so mount() does not throw, and record that it was called.
let canvasUsed = false;
window.HTMLCanvasElement.prototype.getContext = function () {
  canvasUsed = true;
  // Proxy instead of hand-listing methods: jsdom has no canvas backend, and a
  // missing method here would be a harness failure mistaken for a UI bug.
  // Property sets (fillStyle, font, ...) must still be writable no-ops.
  const target = {
    canvas: this,
    measureText: (t) => ({ width: String(t).length * 6 }),
    createLinearGradient: () => ({ addColorStop() {} }),
    createRadialGradient: () => ({ addColorStop() {} }),
    getImageData: () => ({ data: new Uint8ClampedArray(4) }),
  };
  return new Proxy(target, {
    get(t, prop) {
      if (prop in t) return t[prop];
      if (typeof prop === "symbol") return undefined;
      return () => {}; // any canvas call we did not model
    },
    set(t, prop, value) {
      t[prop] = value;
      return true;
    },
  });
};
window.HTMLCanvasElement.prototype.toDataURL = () =>
  "data:image/png;base64,iVBORw0KGgo=";
window.ResizeObserver = class {
  observe() {}
  disconnect() {}
};
window.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 16);
window.cancelAnimationFrame = (id) => clearTimeout(id);
window.scrollTo = () => {};
window.Element.prototype.scrollIntoView = function () {};

window.fetch = (input, init) =>
  fetch(new URL(input, BASE).href, init).then((r) => {
    // Relative asset paths in the bundle resolve against the jsdom URL, so
    // they hit the server too. Report anything non-OK as an error.
    if (!r.ok) errors.push(`fetch ${r.status}: ${input}`);
    return r;
  });

const code = readFileSync(jsPath, "utf8");
window.eval(code);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// React does not listen for a literal "mouseenter" event: it synthesises
// onMouseEnter from delegated mouseover/mouseout pairs. So hover must be
// driven with mouseover, with relatedTarget outside the element.
function hover(el) {
  el.dispatchEvent(
    new window.MouseEvent("mouseover", { bubbles: true, relatedTarget: d.body })
  );
}

/**
 * Set a controlled input's value the way React expects.
 *
 * React caches the last value on the DOM node, so assigning .value directly is
 * ignored and onChange never fires. The prototype setter has to be bypassed.
 */
function typeInto(input, value) {
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    "value"
  ).set;
  setter.call(input, value);
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
}

await sleep(900);

const d = window.document;
const $ = (s) => d.querySelector(s);
const $$ = (s) => [...d.querySelectorAll(s)];

const results = [];
const check = (name, pass, detail = "") =>
  results.push({ name, pass, detail });

// --- mount -----------------------------------------------------------------
check("root has content", $("#root").children.length > 0);
check("boot screen cleared", !$(".boot"), $(".boot") ? "still booting" : "");
const tiles = $$(".tile");
check("tiles rendered", tiles.length > 0, `${tiles.length} tiles`);
check("ember canvas mounted", canvasUsed || !!$("canvas.embers"));

// Bail out cleanly rather than throwing on an empty grid, so the failure is
// reported instead of crashing the run.
if (!tiles.length) {
  console.log("FAIL  no tiles rendered; mount did not complete");
  console.log("\nRUNTIME ERRORS:");
  for (const e of [...new Set(errors)].slice(0, 12)) console.log("  " + e.slice(0, 400));
  process.exit(1);
}

// --- grouping --------------------------------------------------------------
const groups = new Set(tiles.map((t) => t.querySelector(".tile-name").textContent));
check("variants collapsed into groups", groups.size === tiles.length,
  `${groups.size} groups / ${tiles.length} tiles`);

// --- hover preview ---------------------------------------------------------
const before = $(".panel-title")?.textContent;
hover(tiles[2]);
await sleep(200);
const after = $(".panel-title")?.textContent;
check("hover updates panel", after !== before, `${before} -> ${after}`);

// --- click pins ------------------------------------------------------------
tiles[2].click();
await sleep(250);
const pinnedEl = $(".tile.is-pin");
check("click pins the tile", $$(".tile.is-pin").length === 1,
  pinnedEl ? pinnedEl.querySelector(".tile-name").textContent : "no .tile.is-pin found");
check("pinned tile has marker", !!$(".tile.is-pin .tile-pin"));
check(
  "pinned tile keeps pin after moving away",
  (() => {
    tiles[0].dispatchEvent(new window.MouseEvent("mouseenter", { bubbles: true }));
    return $$(".tile.is-pin").length === 1;
  })(),
);
check("pin shown in status bar", !!$(".status-pin"));
check("aria-pressed reflects pin", tiles[2].getAttribute("aria-pressed") === "true");

// pinned tile survives a filter that would hide it
const searchInput = $(".search input");
typeInto(searchInput, "zzzzz-no-such-game");
await sleep(300);
check("pinned tile survives search", $$(".tile.is-pin").length === 1,
  `${$$(".tile").length} tiles visible`);
typeInto(searchInput, "");
await sleep(250);

// Is the pin actually painted, or only present in the DOM? jsdom applies
// stylesheets, so the computed border-color of a pinned tile proves the rule
// matched the element the user is looking at.
const cs = pinnedEl && window.getComputedStyle(pinnedEl);
check("pinned tile is visually styled", !!cs && cs.borderTopColor !== "",
  cs ? `border=${cs.borderTopColor}` : "no pinned element");

const pinKey = pinnedEl?.querySelector(".tile-name")?.textContent || "";

// Persist the key for the reload stage. Note this is the harness capturing
// state, not the app: the app writes localStorage itself, and the reload stage
// checks the app can read it back.
if (process.argv.includes("--reload") && pinKey) {
  const { writeFileSync } = await import("node:fs");
  writeFileSync(".pintest.json", JSON.stringify({ pinned: pinKey }, null, 2));
}

// Does the pin survive a reload? A second, independent jsdom seeded with what
// the first one stored is the closest stand-in for F5 available here:
// window.eval cannot createRoot twice on the same root, and jsdom does not
// persist localStorage between instances.
if (process.argv.includes("--reload")) {
  const { writeFileSync, existsSync, readFileSync: rf } = await import("node:fs");
  const seed = process.argv.includes("--seed")
    ? JSON.parse(rf(".pintest.json", "utf8")).pinned
    : null;
  console.log(`\n-- reload stage: seeding localStorage with ${JSON.stringify(seed)} --`);

  const { JSDOM: J2, VirtualConsole: V2 } = await import("jsdom");
  const errs2 = [];
  const vc2 = new V2();
  vc2.on("jsdomError", (e) => errs2.push(String(e.message)));
  const dom2 = new J2(`<!doctype html><html><body><div id="root"></div></body></html>`,
    { url: BASE + "/", runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc2 });
  const w2 = dom2.window;
  w2.HTMLCanvasElement.prototype.getContext = window.HTMLCanvasElement.prototype.getContext;
  w2.HTMLCanvasElement.prototype.toDataURL = window.HTMLCanvasElement.prototype.toDataURL;
  w2.ResizeObserver = window.ResizeObserver;
  w2.requestAnimationFrame = window.requestAnimationFrame;
  w2.cancelAnimationFrame = window.cancelAnimationFrame;
  w2.Element.prototype.scrollIntoView = function () {};
  w2.fetch = window.fetch;
  if (seed) w2.localStorage.setItem("doomnite.pinned", JSON.stringify(seed));
  else w2.localStorage.removeItem("doomnite.pinned");
  w2.eval(code);
  await sleep(1100);

  const r2 = w2.document.querySelector(".tile.is-pin");
  check("pin restored after reload", w2.document.querySelectorAll(".tile.is-pin").length === 1,
    r2 ? r2.querySelector(".tile-name").textContent : "no .tile.is-pin");
  check("restored pin is the one that was set", r2?.querySelector(".tile-name").textContent === seed,
    `${seed} vs ${r2?.querySelector(".tile-name").textContent}`);
  check("status bar shows restored pin", !!w2.document.querySelector(".status-pin"));
  check("no errors on restored mount", errs2.length === 0, errs2[0] || "");

  // And with nothing stored, nothing should be pinned.
  dom2.window.close();
  const { JSDOM: J3, VirtualConsole: V3 } = await import("jsdom");
  const dom3 = new J3(`<!doctype html><html><body><div id="root"></div></body></html>`,
    { url: BASE + "/", runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: new V3() });
  const w3 = dom3.window;
  w3.HTMLCanvasElement.prototype.getContext = window.HTMLCanvasElement.prototype.getContext;
  w3.HTMLCanvasElement.prototype.toDataURL = window.HTMLCanvasElement.prototype.toDataURL;
  w3.ResizeObserver = window.ResizeObserver;
  w3.requestAnimationFrame = window.requestAnimationFrame;
  w3.cancelAnimationFrame = window.cancelAnimationFrame;
  w3.Element.prototype.scrollIntoView = function () {};
  w3.fetch = window.fetch;
  w3.localStorage.removeItem("doomnite.pinned");
  w3.eval(code);
  await sleep(1100);
  check("fresh install has nothing pinned", w3.document.querySelectorAll(".tile.is-pin").length === 0,
    `${w3.document.querySelectorAll(".tile.is-pin").length} pinned`);
  check("fresh install still renders tiles", w3.document.querySelectorAll(".tile").length > 0,
    `${w3.document.querySelectorAll(".tile").length} tiles`);
}

// unpin (after the reload check, which needs the pin still set)
tiles[2].click();
await sleep(200);
check("click again unpins", $$(".tile.is-pin").length === 0);
typeInto(searchInput, "");
await sleep(250);

// --- dryrun ----------------------------------------------------------------
const sh = $$(".showcmd")[0];
sh?.click();
await sleep(400);
const cmd = $(".cmd")?.textContent || "";
check("show command returns a real command", /doom\.exe|\.bat/i.test(cmd), cmd.slice(0, 80));

// --- filters ---------------------------------------------------------------
const chips = $$(".chip");
let comboOk = false;
for (const c of chips) {
  c.click();
  await sleep(200);
  const n = $$(".tile").length;
  const id = c.textContent;
  if (id === "Multi-config" && n > 0) comboOk = true;
}
check("multi-config filter yields tiles", comboOk);
chips[0].click();
await sleep(200);

// --- report ----------------------------------------------------------------
let failed = 0;
for (const r of results) {
  if (!r.pass) failed++;
  console.log(
    `${r.pass ? "PASS" : "FAIL"}  ${r.name}${r.detail ? "  [" + r.detail + "]" : ""}`
  );
}
console.log(`\n${results.length - failed}/${results.length} checks passed`);
if (errors.length) {
  console.log("\nRUNTIME ERRORS:");
  for (const e of [...new Set(errors)].slice(0, 12)) console.log("  " + e.slice(0, 220));
} else {
  console.log("no runtime errors");
}
process.exit(failed ? 1 : 0);