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
