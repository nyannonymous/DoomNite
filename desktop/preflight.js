// Explains a missing dependency instead of failing with npm's
// "'electron' is not recognized as an internal or external command".
//
// Same reasoning as ui/preflight.mjs: node_modules is gitignored, so a fresh
// clone has nothing installed and every script here dies identically and
// uninformatively.
//
// Note this is the *shell* only. It needs Python and a populated pack, which is
// why the app checks those at startup with real dialogs instead -- this script
// only guards the npm step.
const { existsSync } = require("node:fs");
const { join } = require("node:path");

if (existsSync(join(__dirname, "node_modules"))) process.exit(0);

console.error(`
electron is missing: desktop/node_modules does not exist.

The desktop shell is optional. The launcher already runs with no Electron at
all, just a browser tab:

    python serve.py

To build the desktop app, install the build tooling once:

    cd desktop
    npm ci
    npm run dist

That produces an installer in desktop/release/. The app still needs Python and
the 3.4 GB pack present on the machine -- Electron is the window, not the game.
`);

process.exit(1);