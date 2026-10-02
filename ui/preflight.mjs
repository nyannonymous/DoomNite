// Fail with an explanation instead of "'vite' is not recognized as an internal
// or external command, operable program or batch file."
//
// That message is npm's, not ours, and it is the single most confusing thing a
// newcomer hits in this repo: node_modules is gitignored, so a fresh clone has
// no vite on PATH and every npm script dies the same opaque way. This says what
// actually happened and how to fix it.
//
// Wired in as prebuild and predev, so it only runs when deps are missing.
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ui = dirname(fileURLToPath(import.meta.url));

if (existsSync(join(ui, 'node_modules'))) {
  process.exit(0);
}

const lock = join(ui, 'package-lock.json');
console.error(`
vite is missing: ui/node_modules does not exist.

This repo commits the built UI in dist/, so you only need this if you are
changing the interface. To run the launcher as-is, skip all of this:

    python serve.py

To work on the UI, install the dependencies once:

    cd ui
    npm ci        # exact versions from package-lock.json
    npm run dev

npm install works too, but npm ci is the reproducible one -- it installs
strictly what the lockfile pins.
`);

process.exit(1);