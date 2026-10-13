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
  // tools/ -- and this entry is not optional. serve.py imports mp_http at
  // module level, and mp_http lives in tools/. Without this directory staged,
  // every packaged install dies on startup with
  //
  //     ModuleNotFoundError: No module named 'mp_http'
  //
  // and the launcher shows an error dialog instead of the grid. It was
  // missing because tools/ was assumed to be developer-only; it is not, it is
  // runtime code now.
  "tools",
  // Bundle Zandronum so friends don't need to install it separately.
  "runtime/zandronum",
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

  // The multiplayer command shape is a SHIPPING requirement, verified the
  // same way the single-player launchers are (build.py --check probes the real
  // engine). This exact shape shipped broken twice: the base WAD as a bare
  // name (the "Welcome to Zandronum!" folder dialog) and then also a second
  // time as -file (base game loaded twice). check_mp_command.py stubs only the
  // engine path and the IWAD resolution, so it runs on a machine with no pack
  // content -- exactly the case this bootstrap handles (a friend unpacks, no
  // WADs yet). A regression fails the build, not the user.
  const { spawnSync } = require("node:child_process");
  const py = process.env.DOOMNITE_PYTHON || "python";
  const probe = spawnSync(
    py,
    [path.join(sourceRoot, "tools", "check_mp_command.py")],
    { encoding: "utf8" }
  );
  const tail = (probe.stdout || "").trim().split("\n").slice(-6).join("\n");
  if (probe.error || probe.status !== 0) {
    throw new Error(
      `stage-pack: the multiplayer command line failed its shape check` +
        ` (exit ${probe.status ?? "spawn error"}).\n` +
        (tail ? `--- tools/check_mp_command.py says --\n${tail}\n---\n` : "") +
        `A shipped installer with a broken multiplayer command line opens` +
        ` Zandronum's "point us to your Doom directory" dialog on launch.`
    );
  }
  console.log(`stage-pack: multiplayer command shape OK`);
  fs.mkdirSync(destination, { recursive: true });
  for (const relative of REQUIRED) {
    const source = path.join(sourceRoot, relative);
    const target = path.join(destination, relative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    // Per-user engine config (zandronum-<user>.ini) holds the builder's own
    // IWAD paths and settings; a friend's copy must generate its own.
    fs.cpSync(source, target, {
      recursive: true,
      filter: (src) => !/[\\/]runtime[\\/]zandronum[\\/][^\\/]+\.ini$/i.test(src),
    });
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
