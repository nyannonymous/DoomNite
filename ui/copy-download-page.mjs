// Post-build: put the download page at dist/index.html, which is the file
// Cloudflare Pages serves at the root.
//
// The deploy used to serve dist/ directly, and dist/index.html was the launcher
// shell -- so the public site was a React app that immediately failed to fetch
// /api/entries. There was no download link anywhere on it. That is the bug this
// script exists to make impossible to reintroduce.
//
// Layout after a build:
//
//   dist/index.html       download page  -> published at /
//   dist/app/index.html   launcher UI    -> served by serve.py, never public
//
// Fixing it here rather than in the Cloudflare dashboard means a fresh clone
// deploys correctly with no configuration, and the check below fails the build
// if the release link is ever missing from the page that ships.

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");

const src = resolve(root, "site", "index.html");
const dest = resolve(root, "dist", "index.html");
const launcher = resolve(root, "dist", "app", "index.html");

function fail(msg) {
  console.error(`\ncopy-download-page: ${msg}\n`);
  process.exit(1);
}

if (!existsSync(src)) fail(`no download page at ${src}`);
if (!existsSync(launcher)) {
  fail(`no launcher at ${launcher}\n\nDid the vite build run first? Try: npm run build`);
}

const page = readFileSync(src, "utf8");

// The whole point of this file is the release link. Fail the build if it is
// absent, because a deploy that ships without it is worse than no deploy.
if (!/releases\/download|releases\/latest/.test(page)) {
  fail(
    "the download page links to no release.\n" +
      "Every download button must point at a real asset."
  );
}

writeFileSync(dest, page, "utf8");
console.log(`copy-download-page: dist/index.html <- site/index.html (${page.length} bytes)`);

// Cheap guard against the layout silently regressing: dist/app/index.html is the
// launcher and must NOT be the same file as the download page.
const l = readFileSync(launcher, "utf8");
if (l === page) {
  fail("dist/app/index.html is the download page -- the launcher was not built.");
}
console.log("copy-download-page: launcher intact at dist/app/index.html");
