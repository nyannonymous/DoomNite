// Guards the packaging step with an explanation instead of npm's or
// electron-builder's version of the same failure.
//
// Two things it checks, both of which are uninformative when they break:
//
//   * node_modules is gitignored, so a fresh clone has nothing installed and
//     every script here dies with "'electron' is not recognized as an internal
//     or external command".
//   * The pack bootstrap includes generated files (pack-manifest.json and
//     launchers/), so builds need the complete pack root available.
//     build/stage-pack.js stages the checked inputs automatically; set
//     DOOMNITE_SOURCE_ROOT when building from a separate local-disk directory.
//
// Note this is the *shell* only, and it is not the app's own runtime check. The
// app verifies Python and the pack at startup with real dialogs, because those
// can be missing on a user's machine rather than on the build machine.
const { existsSync } = require("node:fs");
const { join, resolve } = require("node:path");

// What electron-builder copies to resources/pack: enough of a pack for a first
// run to fetch the rest. Anything the app cannot start without belongs here.
const BOOTSTRAP = [
  "serve.py",
  "installer.py",
  "iwadfinder.py",
  "fetcher.py",
  "sources.json",
  "pack-manifest.json",
  "launchers",
  "art",
  "app",
];

function checkBootstrap() {
  const pack = resolve(
    process.env.DOOMNITE_SOURCE_ROOT || resolve(__dirname, "..")
  );
  const missing = BOOTSTRAP.filter((rel) => !existsSync(join(pack, rel)));
  if (!missing.length) return;

  console.error(`
cannot package: ${missing.length} bootstrap item(s) are missing from ${pack}.

The installer needs these files to bootstrap the 3.4 GB payload. Build the pack
and UI first, or set DOOMNITE_SOURCE_ROOT to the complete pack root when using a
separate local-disk build directory:

  ${missing.map((m) => join(pack, m)).join("\n  ")}

    python tools\\build.py     # writes pack-manifest.json and launchers/
    npm run build             # writes app/, the launcher UI
    cd desktop && npm run dist

    For a separate local-disk build directory, set DOOMNITE_SOURCE_ROOT to the
    repository/pack root; the bootstrap is staged automatically.
`);

  process.exit(1);
}

if (!existsSync(join(__dirname, "node_modules"))) {
  console.error(`
electron is missing: desktop/node_modules does not exist.

The desktop shell is optional. The launcher already runs with no Electron at
all, just a browser tab:

    python serve.py

To build the desktop app, install the build tooling once:

    cd desktop
    npm ci
    npm run dist

That produces an installer in desktop/release/. The app ships its own Python and
fetches the 3.4 GB pack on first run -- Electron is the window, not the game.
`);

  process.exit(1);
}

checkBootstrap();
