// Guards the packaging step with an explanation instead of npm's or
// electron-builder's version of the same failure.
//
// Three things it checks, all of which are uninformative when they break:
//
//   * node_modules is gitignored, so a fresh clone has nothing installed and
//     every script here dies with "'electron' is not recognized as an internal
//     or external command".
//   * The pack bootstrap includes generated files (pack-manifest.json and
//     launchers/), so builds need the complete pack root available.
//     build/stage-pack.js stages the checked inputs automatically; set
//     DOOMNITE_SOURCE_ROOT when building from a separate local-disk directory.
//   * The manifest must describe at least one playable game. A stub manifest
//     passes every file-exists check and still ships an empty launcher grid,
//     with a multiplayer panel that has nothing to offer. tools/check_mp_command.py,
//     run later by stage-pack.js, re-derives the same rule from the real python
//     code rather than a copy of it.
//
// Note this is the *shell* only, and it is not the app's own runtime check. The
// app verifies Python and the pack at startup with real dialogs, because those
// can be missing on a user's machine rather than on the build machine.
const { existsSync, readFileSync } = require("node:fs");
const { join, resolve } = require("node:path");

// What electron-builder copies to resources/pack: enough of a pack for a first
// run to fetch the rest. Anything the app cannot start without belongs here.
//
// `tools` belongs in this list as runtime code, not a dev extra: serve.py
// imports mp_http out of tools/ at module level, and multiplayer resolves the
// IWAD through iwadfinder in the same directory. It was missing once and every
// packaged install died on startup with "No module named 'mp_http'".
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
  "tools",
];

// The pack must hold at least one entry a multiplayer panel can offer -- a
// `games` action that names both an IWAD and a launcher .bat. Manifest shape
// (pack-manifest.json): { iwads, runtime, games: [{ name, actions: [{ bat,
// iwad, mod, mods }] }], standalone_games, missing }. A manifest whose games
// all lack actions, or whose actions name no .bat, is a stub, and a stub
// manifest builds "fine" and ships an empty grid.
function playableCount(manifest) {
  const games = Array.isArray(manifest.games) ? manifest.games : [];
  let n = 0;
  for (const g of games) {
    const actions = Array.isArray(g.actions) ? g.actions : [];
    if (actions.some((a) => a && a.iwad && a.bat)) n++;
  }
  return n;
}

function checkBootstrap() {
  const pack = resolve(
    process.env.DOOMNITE_SOURCE_ROOT || resolve(__dirname, "..")
  );
  const missing = BOOTSTRAP.filter((rel) => !existsSync(join(pack, rel)));
  if (missing.length) {
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

  // The manifest must not be a stub. Checked here because an empty grid is
  // invisible at build time and obvious at use time -- the worst combination.
  let manifest;
  try {
    manifest = JSON.parse(
      readFileSync(join(pack, "pack-manifest.json"), "utf8")
    );
  } catch (e) {
    console.error(`
cannot package: pack-manifest.json in ${pack} is missing or unreadable (${e.message}).

It is generated along with launchers/:

    python tools\\build.py
`);
    process.exit(1);
  }
  const playable = playableCount(manifest);
  if (!playable) {
    console.error(`
cannot package: pack-manifest.json in ${pack} describes no playable game.

An entry is playable when its action names both an IWAD and a launcher .bat.
The multiplayer panel offers exactly those. Regenerate the manifest:

    python tools\\build.py
`);
    process.exit(1);
  }
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
