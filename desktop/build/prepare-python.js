// Fetches and stages the embeddable Python runtime that ships inside the
// installer, so "npm run dist" works from a clean clone with no manual step.
//
// The zip is pinned by SHA256. An unpinned download into an installer is how
// you end up shipping something nobody reviewed, and the failure mode is silent:
// the build succeeds and the app is subtly not the Python you tested against.
//
// Usage: node build/prepare-python.js   (npm run dist calls it automatically)

const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const https = require("node:https");
const { execFileSync } = require("node:child_process");

const VERSION = "3.11.9";
const URL = `https://www.python.org/ftp/python/${VERSION}/python-${VERSION}-embed-amd64.zip`;
const SHA256 = "009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b";

const here = __dirname;
const zipPath = path.join(here, "python-embed.zip");
const dest = path.join(here, "python");

function fail(msg, detail) {
  console.error(`\nprepare-python: ${msg}`);
  if (detail) console.error(`\n${detail}\n`);
  process.exit(1);
}

function get(url, out) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(out);
    https
      .get(url, (res) => {
        if (res.statusCode !== 200) {
          file.close();
          fs.unlinkSync(out);
          reject(new Error(`HTTP ${res.statusCode} for ${url}`));
          return;
        }
        res.pipe(file);
        file.on("finish", () => file.close(resolve));
      })
      .on("error", (e) => {
        fs.existsSync(out) && fs.unlinkSync(out);
        reject(e);
      });
  });
}

function sha256(file) {
  return execFileSync("certutil", ["-hashfile", file, "SHA256"], {
    encoding: "utf8",
  })
    .split(/\r?\n/)
    .find((l) => /^[0-9a-f]{64}$/i.test(l.trim()))
    ?.trim()
    .toLowerCase();
}

// Fresh every time. A stale staged runtime is how you ship last week's Python
// while believing you shipped today's.
fs.rmSync(dest, { recursive: true, force: true });
fs.mkdirSync(dest, { recursive: true });

(async () => {
  console.log(`prepare-python: fetching Python ${VERSION} embeddable...`);
  try {
    await get(URL, zipPath);
  } catch (e) {
    fail(
      "could not download the embeddable runtime",
      `${URL}\n${e.message}\n\nDownload it manually to:\n  ${zipPath}`
    );
  }

  // The hash is pinned. If it drifts, that is either a corrupted download or
  // someone changing the pin -- both need a human, not an automatic retry.
  //
  // Compare only against the expected value when the pin is filled in; the
  // value is intentionally printed if it is not, so a first run cannot silently
  // bake in an unverified runtime.
  const actual = sha256(zipPath);
  console.log(`prepare-python: sha256 ${actual}`);
  if (SHA256.includes("TODO") || SHA256.length !== 64) {
    console.warn(
      "prepare-python: WARNING -- expected-hash pin is not filled in; " +
        "installing unverified. Set SHA256 at the top of this file."
    );
  } else if (actual !== SHA256) {
    fail(
      "hash mismatch -- refusing to install",
      `expected ${SHA256}\nactual   ${actual}`
    );
  }

  // Expand with whatever Python is available; the embeddable runtime cannot
  // unpack itself before it exists.
  const candidates = [
    process.env.DOOMNITE_PYTHON,
    "py",
    "python",
    "python3",
  ].filter(Boolean);

  let unpacked = false;
  for (const c of candidates) {
    try {
      execFileSync(
        c,
        [
          "-c",
          `import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])`,
          zipPath,
          dest,
        ],
        { stdio: "ignore" }
      );
      unpacked = true;
      break;
    } catch {
      /* try the next one */
    }
  }
  if (!unpacked) {
    fail(
      "no usable Python found to unpack the archive with",
      `Tried: ${candidates.join(", ")}\n\nUnzip manually into:\n  ${dest}`
    );
  }

  // CRITICAL: the embeddable runtime ships python311._pth with "import site"
  // commented out and no script-directory entry. Without editing it, running
  // serve.py directly cannot import installer.py or iwadfinder.py, because the
  // script's own directory is not on sys.path. Adding the three-levels-up entry
  // points at the pack root when the runtime is staged inside the repo.
  //
  // In a packaged build the runtime lives in resources/python, three levels
  // below the exe, so the same relative entry resolves to the install dir.
  const pth = path.join(dest, "python311._pth");
  if (!fs.existsSync(pth)) {
    fail("python311._pth missing from the extracted runtime");
  }
  fs.writeFileSync(pth, "python311.zip\n.\n..\\..\\..\n", "utf8");

  const exe = path.join(dest, "python.exe");
  if (!fs.existsSync(exe)) {
    fail("python.exe missing after extraction");
  }

  // Prove the staged runtime actually runs. A build that stages a broken
  // runtime still exits 0, and the failure only shows up on a user's machine.
  const check = execFileSync(exe, ["-c", "import sys; print(sys.version.split()[0])"], {
    encoding: "utf8",
  }).trim();
  console.log(`prepare-python: staged Python ${check} -> ${dest}`);
})();