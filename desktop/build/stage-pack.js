// Assemble the small, non-payload pack bootstrap before electron-builder copies
// extraResources. This hook is deliberately part of the builder config: direct
// calls to electron-builder cannot forget the stage.
const fs = require("node:fs");
const path = require("node:path");

const REQUIRED = [
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

// Checked against the BUILD directory, not the pack root.
//
// preload.js used to be listed in REQUIRED, which asserted it existed at the
// pack root -- but it has always lived in desktop/ (git: added in b6cd40f as
// desktop/preload.js) and main.js loads it with path.join(__dirname,
// "preload.js"), i.e. from beside itself inside the packaged app. So it is
// shipped by electron-builder's `build.files` list, NOT staged here as pack
// payload, and asserting it at the pack root failed every packaged build with
// "missing 1 bootstrap item(s)". Its real delivery requirement is that the
// staging step in BUILDING.md copies it into the build dir; that step was
// missing it (and first-run.html) too, which would have produced an installer
// whose preload silently did not exist. Both are fixed there.
const REQUIRED_IN_BUILD_DIR = ["preload.js", "first-run.html"];

async function stagePack(context = {}) {
  const desktop = path.resolve(
    context.packager?.projectDir || path.join(__dirname, "..")
  );
  const sourceRoot = path.resolve(
    process.env.DOOMNITE_SOURCE_ROOT || path.join(desktop, "..")
  );
  const destination = path.join(desktop, "build", "pack");

  const missing = REQUIRED.filter((relative) =>
    !fs.existsSync(path.join(sourceRoot, relative))
  );
  if (missing.length) {
    throw new Error(
      `stage-pack: missing ${missing.length} bootstrap item(s) in ${sourceRoot}:\n` +
        missing.map((item) => `  ${item}`).join("\n") +
        "\nBuild the pack and UI first, or set DOOMNITE_SOURCE_ROOT to the pack root."
    );
  }

  // Second check: the app-shell files electron-builder ships via build.files.
  // These must already be in the BUILD directory -- BUILDING.md's staging step
  // copies them in from desktop/. Checked here because a missing preload.js
  // produces an installer that builds clean and then fails at runtime, which
  // is far worse than failing the build.
  const missingShell = REQUIRED_IN_BUILD_DIR.filter(
    (relative) => !fs.existsSync(path.join(desktop, relative))
  );
  if (missingShell.length) {
    throw new Error(
      `stage-pack: missing ${missingShell.length} app-shell file(s) in ${desktop}:\n` +
        missingShell.map((item) => `  ${item}`).join("\n") +
        "\nCopy them from desktop/ before building (see BUILDING.md, staging step)."
    );
  }

  fs.rmSync(destination, { recursive: true, force: true });
  fs.mkdirSync(destination, { recursive: true });
  for (const relative of REQUIRED) {
    const source = path.join(sourceRoot, relative);
    const target = path.join(destination, relative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.cpSync(source, target, { recursive: true });
  }

  console.log(`stage-pack: staged ${REQUIRED.length} items -> ${destination}`);
}

module.exports = { default: stagePack };

if (require.main === module) {
  stagePack().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
