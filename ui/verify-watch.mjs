// Prove the folder watch end to end: a mod that is not on disk must show the
// "where to put it" hint, and the card must come back on its own the moment
// the file reappears -- no reload.
//
// verify.mjs cannot cover this, because the real pack has every file present,
// so the only honest way to test it is to take one away. This renames ONE
// mods/<slug> folder aside, drives the built bundle in jsdom, puts it back in
// a finally block, and fails loudly if it ever has to leave it moved.
//
// Run: node verify-watch.mjs   (from ui/, with serve.py running on 8765)
//      node verify-watch.mjs ../app/assets/index-XXXX.js

import { JSDOM, VirtualConsole } from "jsdom";
import { readFileSync, readdirSync, statSync, renameSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const PACK = resolve(here, "..");
const BASE = "http://127.0.0.1:8765";

// A game with exactly one action and one mod folder of its own, so taking it
// away makes exactly one tile missing and disturbs nothing else.
const SLUG = "hocus";
const GAME = "Hocus Pocus 3D";
const FILE = "HOCUS.pk3";

const live = resolve(PACK, "mods", SLUG);
const away = resolve(PACK, "mods", `${SLUG}.away-verify-watch`);

if (!existsSync(live)) {
  console.error(`verify-watch: ${live} is not there. This check needs the`);
  console.error("pack complete before it starts, so it does not have to guess");
  console.error("whether a missing folder is its own doing. Restore it and retry.");
  process.exit(2);
}
if (existsSync(away)) {
  console.error(`verify-watch: ${away} already exists; refusing to guess.`);
  process.exit(2);
}

function bundlePath() {
  if (process.argv[2]) return resolve(here, process.argv[2]);
  const dir = resolve(PACK, "app", "assets");
  const js = readdirSync(dir)
    .filter((f) => /^index-.*\.js$/.test(f))
    .map((f) => ({ f, t: statSync(resolve(dir, f)).mtimeMs }))
    .sort((a, b) => b.t - a.t);
  if (!js.length) {
    console.error(`verify-watch: no built bundle in ${dir}; run npm run build.`);
    process.exit(2);
  }
  return resolve(dir, js[0].f);
}

const results = [];
const check = (name, pass, detail = "") => results.push({ name, pass, detail });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function mount(jsPath) {
  const errors = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => errors.push("jsdomError: " + (e.stack || e.message)));
  vc.on("error", (...a) => errors.push("console.error: " + a.join(" ")));

  const dom = new JSDOM(
    `<!doctype html><html><body><div id="root"></div></body></html>`,
    { url: BASE + "/", runScripts: "dangerously", pretendToBeVisual: true,
      virtualConsole: vc }
  );
  const w = dom.window;
  w.HTMLCanvasElement.prototype.getContext = () => new Proxy(
    { measureText: (t) => ({ width: String(t).length * 6 }),
      createLinearGradient: () => ({ addColorStop() {} }),
      createRadialGradient: () => ({ addColorStop() {} }),
      getImageData: () => ({ data: new Uint8ClampedArray(4) }) },
    { get: (t, p) => (p in t ? t[p] : () => {}), set: (t, p, v) => (t[p] = v, true) }
  );
  w.HTMLCanvasElement.prototype.toDataURL = () => "data:image/png;base64,iVBORw0KGgo=";
  w.ResizeObserver = class { observe() {} disconnect() {} };
  w.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 16);
  w.cancelAnimationFrame = (id) => clearTimeout(id);
  w.scrollTo = () => {};
  w.Element.prototype.scrollIntoView = function () {};
  // Same relative-URL resolution as verify.mjs: the bundle's own asset fetches
  // must hit the real server, not a dead file:// path.
  w.fetch = (input, init) =>
    fetch(new URL(input, BASE).href, init).then((r) => {
      if (!r.ok) errors.push(`fetch ${r.status}: ${input}`);
      return r;
    });
  w.eval(readFileSync(jsPath, "utf8"));
  return { w, errors };
}

function tileFor(w, name) {
  return [...w.document.querySelectorAll(".tile")].find(
    (t) => t.querySelector(".tile-name")?.textContent === name
  );
}

let moved = false;
try {
  const jsPath = bundlePath();
  console.log(`verify-watch: bundle ${jsPath}`);
  console.log(`verify-watch: taking mods/${SLUG} off disk`);
  renameSync(live, away);
  moved = true;

  const { w, errors } = await mount(jsPath);
  const d = w.document;
  await sleep(1200);

  const tile = tileFor(w, GAME);
  check("the game still has a card", !!tile, tile ? GAME : "no tile found");
  check("its card reports missing files",
    !!tile && tile.className.includes("is-missing"),
    tile ? tile.className : "");
  check("and its PLAY button is disabled",
    !!tile && tile.querySelector(".tile-play")?.disabled === true);

  // Select it, the way a pointer would, and read the panel.
  tile?.dispatchEvent(new w.MouseEvent("mouseover", { bubbles: true, relatedTarget: d.body }));
  await sleep(400);
  const hints = [...d.querySelectorAll(".panel-dlhint")];
  const hint = hints.map((h) => h.textContent).join(" | ");
  check("the panel says where the file goes",
    hint.includes(`mods\\${SLUG}`) || hint.includes(`mods/${SLUG}`), hint.slice(0, 160));
  check("the panel names the missing file", hint.includes(FILE), hint.slice(0, 160));
  check("the panel does not also say 'Already removed'",
    !hint.includes("Already removed"), hint.slice(0, 160));

  // ---- THE FLIP ----------------------------------------------------------
  // Put it back while the page is still open. Nothing reloads the page; the
  // only thing that can change this card is App.jsx's folder watch.
  console.log(`verify-watch: putting mods/${SLUG} back`);
  renameSync(away, live);
  moved = false;

  let flipped = false;
  for (let i = 0; i < 20; i++) {          // up to 10 s; the watch polls at 4 s
    await sleep(500);
    const t = tileFor(w, GAME);
    if (t && !t.className.includes("is-missing")) { flipped = true; break; }
  }
  check("the card comes back on its own, with no reload", flipped);

  const t2 = tileFor(w, GAME);
  check("and it is launchable again",
    !!t2 && t2.querySelector(".tile-play")?.disabled === false);
  // The corner label is driven by /api/packmods, a second source of truth for
  // the same filesystem fact. If the watch refreshes only one of them, the
  // card comes back while the sidebar still says REMOVED.
  const corner = t2?.querySelector(".tile-inpack")?.textContent || "";
  check("and the REMOVED corner is gone too", !/REMOVED/.test(corner),
    corner || "(no corner label)");
  const after = [...d.querySelectorAll(".panel-dlhint")].map((h) => h.textContent).join(" | ");
  check("and the sidebar hint is gone", !after.includes("missing") && !after.includes("Not downloadable"),
    after.slice(0, 120) || "(no hint)");
  check("no runtime errors", errors.length === 0, errors[0] || "");
  w.close();
} finally {
  // Never leave the owner's pack missing a mod because a test fell over.
  if (moved) {
    try {
      renameSync(away, live);
      console.log(`verify-watch: restored mods/${SLUG} in the finally block`);
    } catch (e) {
      console.error(`verify-watch: COULD NOT RESTORE ${live}: ${e.message}`);
      console.error(`verify-watch: it is at ${away} -- move it back by hand.`);
      process.exitCode = 3;
    }
  }
}

let failed = 0;
for (const r of results) {
  if (!r.pass) failed++;
  console.log(`${r.pass ? "PASS" : "FAIL"}  ${r.name}${r.detail ? "  [" + r.detail + "]" : ""}`);
}
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
