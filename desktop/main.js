// DoomNite desktop shell.
//
// The whole launcher already works as a local web app -- serve.py serves the UI
// and owns /api/launch, which is what actually starts GZDoom. This process does
// exactly three things: find that server, start it, show it in a window. It does
// not reimplement any of it.
//
// That split matters for correctness. /api/launch takes an integer index and
// resolves it against the manifest server-side, so a malicious page in this
// window can only ever start a game that was already in the menu. Keeping the
// launch logic in Python rather than porting it to Node means that guarantee is
// the one serve.py already makes, instead of a second weaker version of it.

const { app, BrowserWindow, shell, dialog, Menu } = require("electron");
const { spawn } = require("node:child_process");
const net = require("node:net");
const path = require("node:path");
const fs = require("node:fs");
const http = require("node:http");

const PORT = 8765;
const ORIGIN = `http://127.0.0.1:${PORT}`;

// serve.py and everything it imports live in the pack root, one level up from
// this file in a dev checkout. A packaged build cannot use that shortcut -- the
// pack root is 3.4 GB that lives on R2 -- so it builds one instead, from the
// bootstrap below plus a first-run fetch.
const DEV_PACK = path.resolve(__dirname, "..");

// The bootstrap electron-builder copies to resources/pack: serve.py and its
// imports, the generated manifest, the launchers, the built UI and the cover
// art. Everything the pack needs that is NOT part of the 3.4 GB payload.
//
// It is bundled rather than fetched because the code that would do the fetching
// lives in it. serve.py imports installer.py and iwadfinder.py out of this same
// directory, and the window it serves is a file here too, so a fetch-first
// design cannot get as far as writing the fetcher to disk.
const SEED = path.join(process.resourcesPath, "pack");

// Written once the payload is in place. Without it every launch would re-hash
// 3.7 GB to rediscover that nothing is missing, which is minutes of the engine
// spinning on a disk instead of a game starting.
const MARKER = ".doomnite-pack.json";

let server = null;
let fetcher = null;
let win = null;
let quitting = false;
// True until the launcher window exists. Distinguishes "the app has no windows
// yet" from "the user closed the last one", which window-all-closed cannot.
let starting = true;

// Location of the bundled embeddable runtime. In a packaged build it sits in
// resources/python; in a dev checkout, build/python where prepare-python.js
// staged it. Shared with startServer, which rewrites its ._pth file.
function bundledPath() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "python", "python.exe")
    : path.join(__dirname, "build", "python", "python.exe");
}

// Which Python to use, and whether there is one at all. Checked before we make
// a window, so the user gets a dialog naming the actual problem instead of a
// window that loads forever.
//
// The bundled embeddable runtime wins outright when present. It ships in
// resources/python, so an installer user needs nothing preinstalled -- which is
// the entire point of bundling it. A system Python is only a fallback for
// someone running from source in a dev checkout.
function findPython(packRoot) {
  const candidates = [];

  if (process.env.DOOMNITE_PYTHON) candidates.push(process.env.DOOMNITE_PYTHON);

  if (fs.existsSync(bundledPath())) return { cmd: bundledPath(), args: [] };

  // A venv inside the pack wins, if the pack has one.
  for (const rel of ["venv/Scripts/python.exe", ".venv/Scripts/python.exe"]) {
    candidates.push(path.join(packRoot, rel));
  }

  // The python3.11 the rest of this project is developed against, then the
  // Windows "py" launcher, which finds an installed interpreter when several
  // are present and would otherwise leave the user guessing.
  for (const base of [process.env.LOCALAPPDATA, process.env.ProgramFiles, ""]) {
    if (!base) continue;
    candidates.push(path.join(base, "Programs", "Python", "Python311", "python.exe"));
  }
  candidates.push("py", "python", "python3");

  for (const c of candidates) {
    if (path.isAbsolute(c)) {
      if (fs.existsSync(c)) return { cmd: c, args: [] };
    } else {
      return { cmd: c, args: [] }; // rely on PATH resolution by the OS
    }
  }
  return null;
}

// Wait for the port rather than sleeping a fixed amount. serve.py is fast but
// disk-bound on a cold start reading pack-manifest.json, and a fixed sleep is
// either flaky or needlessly slow.
function waitForPort(port, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const sock = net.connect(port, "127.0.0.1");
      sock.once("connect", () => {
        sock.destroy();
        resolve();
      });
      sock.once("error", () => {
        sock.destroy();
        if (Date.now() > deadline) {
          reject(new Error(`serve.py did not open port ${port} in time`));
        } else {
          setTimeout(attempt, 120);
        }
      });
    };
    attempt();
  });
}

// Where the pack root is, and whether it is ours to write to.
//
// The managed flag is the important half. A pack the user already had is
// theirs: this must never write a bootstrap into it, because the version in the
// installer could be older than the one they are running. Only a pack this app
// created is seeded and fetched into.
function resolvePackRoot() {
  if (process.env.DOOMNITE_PACK) {
    return { root: process.env.DOOMNITE_PACK, managed: false };
  }
  if (!app.isPackaged) return { root: DEV_PACK, managed: false };

  // A pack sitting beside the executable: the portable case, and how this was
  // tested before the bootstrap was bundled. Walk up until serve.py shows up.
  let dir = path.dirname(app.getPath("exe"));
  for (let i = 0; i < 4; i++) {
    if (fs.existsSync(path.join(dir, "serve.py"))) {
      return { root: dir, managed: false };
    }
    const up = path.dirname(dir);
    if (up === dir) break;
    dir = up;
  }

  // Nothing we did not create, so build one. userData rather than the install
  // directory: Program Files is not writable, GZDoom writes its own ini beside
  // the pack, iwadfinder writes config.json there, and the fetcher drops .part
  // files all over it.
  return { root: path.join(app.getPath("userData"), "pack"), managed: true };
}

// Copy <src> over <dest>, skipping files whose size already matches.
//
// Size rather than a hash: the seed is a few hundred KB of text plus 15 MB of
// art, and the only reason to overwrite anything is that a newer build shipped
// a newer copy -- a rebuilt UI, a regenerated manifest. A size-identical file
// is the same file.
function copyTree(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  let copied = 0;
  for (const ent of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, ent.name);
    const d = path.join(dest, ent.name);
    if (ent.isDirectory()) {
      copied += copyTree(s, d);
      continue;
    }
    let same = false;
    try {
      same = fs.statSync(d).size === fs.statSync(s).size;
    } catch {
      /* not there yet */
    }
    if (same) continue;
    fs.copyFileSync(s, d);
    copied++;
  }
  return copied;
}

// Materialise the pack root. Runs on every launch of a managed pack, not just
// the first, so that upgrading the app replaces the UI and the manifest instead
// of leaving last version's copies in place forever.
function seedPack(root) {
  if (!fs.existsSync(SEED)) {
    fail(
      "This build is missing its bundled pack.",
      `Expected a pack bootstrap at:\n${SEED}\n\n` +
        "Set DOOMNITE_PACK to a complete pack directory to use that instead."
    );
    return false;
  }
  const n = copyTree(SEED, root);
  console.log(`seedPack: ${n} file(s) -> ${root}`);
  return true;
}

// Is the payload actually in place?
//
// runtime/doom.exe is a cheap and honest proxy: every launcher needs it and
// nothing but a completed fetch produces it. The marker is what makes this
// answerable at all -- without it, the only way to know a pack is complete is
// to re-hash all 3.7 GB, every single launch.
function payloadPresent(root) {
  return (
    fs.existsSync(path.join(root, MARKER)) &&
    fs.existsSync(path.join(root, "runtime", "doom.exe"))
  );
}

// Should this launch fetch?
//
// Only a managed pack is ever fetched into: a pack the user pointed at is
// complete by definition, and if it were not, we could not know what complete
// means for it. DOOMNITE_FETCH=1 forces a run, which is the repair path for a
// pack someone deleted a mod out of.
function needsFetch(root, managed) {
  const canFetch =
    fs.existsSync(path.join(root, "fetcher.py")) &&
    fs.existsSync(path.join(root, "sources.json"));
  if (!canFetch) return false;
  if (process.env.DOOMNITE_FETCH === "1") return true;
  return managed && !payloadPresent(root);
}

// fetcher.py prints for a human -- it is also a tool operators run by hand --
// so its result is scraped out of its own summary line rather than parsed from
// JSON. Kept next to the reason it exists so the two stay in step.
function summarise(text) {
  const m = /fetched (\d+)\s+no-url (\d+)\s+failed (\d+)/.exec(text);
  if (!m) return null;
  return { fetched: +m[1], no_url: +m[2], failed: +m[3] };
}

// The window that is on screen while 3.4 GB arrives. Without it the app looks
// hung for several minutes -- the server has not started, so there is nothing
// else to show -- and a user reasonably kills it halfway through.
function progressWindow() {
  const w = new BrowserWindow({
    width: 720,
    height: 470,
    resizable: false,
    maximizable: false,
    backgroundColor: "#0b0b0f",
    title: "DoomNite - first run",
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  w.once("ready-to-show", () => w.show());
  w.loadFile(path.join(__dirname, "first-run.html"));
  return w;
}

// Download the payload, reporting progress as it goes. Returns true when the
// pack is complete enough to serve.
async function fetchPack(root, py) {
  const w = progressWindow();
  const state = { done: 0, total: 0, current: "", bytes: "", log: [] };
  let pending = null;

  const flush = () => {
    pending = null;
    if (w.isDestroyed()) return;
    w.webContents
      .executeJavaScript(`window.dnUpdate(${JSON.stringify(state)})`)
      .catch(() => {});
  };
  // Coalesced rather than sent per line: the fetcher rewrites its progress line
  // many times a second, and one executeJavaScript per rewrite would spend more
  // time in the renderer than in the download.
  const push = () => {
    if (!pending) pending = setTimeout(flush, 200);
  };
  // The page has to have run its script before an update means anything, and
  // the first bytes of a download can land before it has. Re-send once the
  // document is definitely there.
  w.webContents.once("did-finish-load", flush);
  push();

  // -u because stdout is a pipe here, not a console, and Python block-buffers
  // a pipe: without it the whole first run would show nothing until the buffer
  // filled, which is the opposite of progress.
  const child = spawn(py.cmd, [...py.args, "-u", path.join(root, "fetcher.py")], {
    cwd: root,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  fetcher = child;

  const lines = [];
  const onData = (chunk) => {
    // The per-file progress line is rewritten in place with \r, so a chunk is
    // more lines than it looks and both separators have to be honoured.
    for (const raw of String(chunk).split(/[\r\n]+/)) {
      const line = raw.trim();
      if (!line) continue;
      lines.push(line);
      if (lines.length > 300) lines.shift();

      let m = /^\[\s*(\d+)\/(\d+)\]/.exec(line);
      if (m) {
        state.done = +m[1];
        state.total = +m[2];
        state.current = "";
        push();
        continue;
      }
      m = /^to fetch: (\d+) files, (.+)$/.exec(line);
      if (m) {
        state.total = +m[1];
        state.bytes = m[2];
        push();
        continue;
      }
      m = /^(\S+): ([\d.]+ [A-Z]+) (\d+)%$/.exec(line);
      if (m) {
        state.current = `${m[1]} · ${m[2]} · ${m[3]}%`;
        push();
        continue;
      }
      state.log.push(line);
      if (state.log.length > 24) state.log.shift();
      push();
    }
  };
  for (const stream of [child.stdout, child.stderr]) {
    stream.setEncoding("utf8");
    stream.on("data", onData);
  }

  // Closing the window means stop, not "carry on invisibly". The fetch is
  // resumable, so throwing away partial progress costs only what was already
  // downloaded and not yet kept.
  let cancelled = false;
  let settled = false;
  w.on("closed", () => {
    if (settled) return;
    cancelled = true;
    kill(child);
  });

  const code = await new Promise((res) => child.once("exit", (c) => res(c)));
  fetcher = null;
  settled = true;
  if (pending) clearTimeout(pending);
  flush();

  if (cancelled) return false;

  const text = lines.join("\n");
  const summary = summarise(text);

  // Exit 2 means "finished, but not everything is here", and the expected case
  // for it is the deliberately unhosted commercial IWADs -- DOOM2.WAD and
  // Hexen.wad are vetoed in sources.json and always count as no-url. Failures
  // are the ones that mean a real file is missing.
  if (code === 0 || (summary && summary.failed === 0)) {
    fs.writeFileSync(
      path.join(root, MARKER),
      JSON.stringify(
        { at: new Date().toISOString(), app: app.getVersion(), ...summary },
        null,
        2
      ),
      "utf8"
    );
    if (!w.isDestroyed()) w.destroy();
    return true;
  }

  const why = summary
    ? `${summary.failed} file(s) could not be downloaded.`
    : `The fetcher exited with code ${code}.`;
  fail(
    "The DoomNite pack did not finish downloading.",
    `${why}\n\n` +
      "Files already fetched are kept and re-checked against their hashes, so " +
      `launching again resumes instead of starting over.\n\n${text.slice(-700)}`
  );
  if (!w.isDestroyed()) w.destroy();
  return false;
}

function fail(message, detail) {
  dialog.showErrorBox("DoomNite can't start", message + (detail ? `\n\n${detail}` : ""));
  app.quit();
}

async function startServer(packRoot, py) {
  const servePy = path.join(packRoot, "serve.py");
  if (!fs.existsSync(servePy)) {
    fail(
      "Couldn't find serve.py.",
      `Looked in:\n${packRoot}\n\nSet DOOMNITE_PACK to the pack directory if it lives somewhere else.`
    );
    return false;
  }

  // --no-open: we are the window now, so serve.py must not also open a browser.
  //
  // The embeddable runtime cannot be told where the pack is through the
  // environment. PYTHONPATH looks like it should work and does not: the runtime
  // ships with `import site` commented out in python311._pth, which disables the
  // machinery that reads PYTHONPATH at all. Verified -- serve.py still died with
  // ModuleNotFoundError: No module named 'installer'.
  //
  // The one mechanism that does work is the ._pth file itself, so it is rewritten
  // at startup with the resolved pack root baked in. This also explains the
  // original packaging bug: a relative "..\..\.." entry can only ever resolve to
  // the install directory, never to wherever the user keeps their pack.
  //
  // try/except because the install dir may not be writable (Program Files, a
  // read-only USB stick). If the rewrite fails the server may still start if the
  // pack happens to sit beside the runtime, so this warns rather than aborts.
  if (py.cmd === bundledPath()) {
    try {
      const pth = path.join(path.dirname(bundledPath()), "python311._pth");
      fs.writeFileSync(pth, `python311.zip\n.\n${packRoot}\n`, "utf8");
    } catch (e) {
      console.warn(`could not update python311._pth: ${e.message}`);
    }
  }

  server = spawn(py.cmd, [...py.args, servePy, "--no-open", "--port", String(PORT)], {
    cwd: packRoot,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });

  const log = [];
  for (const stream of [server.stdout, server.stderr]) {
    stream.setEncoding("utf8");
    stream.on("data", (d) => log.push(d.trim()));
  }

  let exited = null;
  server.on("exit", (code) => {
    exited = code;
    // A crash while quitting is expected and must not raise a dialog.
    if (!quitting) {
      fail(
        "The launcher server stopped unexpectedly.",
        (log.join("\n") || `serve.py exited with code ${code}`).slice(0, 900)
      );
    }
  });

  try {
    await waitForPort(PORT);
  } catch (e) {
    fail(
      "The launcher server did not start.",
      (log.join("\n") || e.message).slice(0, 900)
    );
    return false;
  }
  return true;
}

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: "#0b0b0f",
    title: "DoomNite",
    show: false,
    webPreferences: {
      // No node integration: this window shows a local server's output, and it
      // does not need to run any of it.
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  win.once("ready-to-show", () => win.show());
  win.loadURL(ORIGIN);
  starting = false;

  // Anything that isn't the local launcher opens in the user's real browser.
  // Without this, clicking a link inside the app navigates the app itself to
  // the external site and there is no way back.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    if (!url.startsWith(ORIGIN)) {
      e.preventDefault();
      if (/^https?:/.test(url)) shell.openExternal(url);
    }
  });
}

// Kill a child and everything it started. taskkill /t because spawn gives us
// python, but the thing holding a lock or a port is usually deeper: a pip
// download, a cmd /c batch, the engine itself.
function kill(child) {
  if (!child || child.killed || child.exitCode !== null) return;
  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(child.pid), "/f", "/t"], { windowsHide: true });
  } else {
    child.kill("SIGTERM");
  }
}

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);

  const { root: packRoot, managed } = resolvePackRoot();

  // The bootstrap first: it contains the fetcher, so it has to be on disk
  // before anything can be downloaded, and serve.py cannot start without it.
  if (managed && !seedPack(packRoot)) return;

  // Resolved once, here, rather than inside startServer: the fetch needs the
  // same interpreter, and a missing runtime has to be reported before a
  // download is offered rather than after it finishes.
  const py = findPython(packRoot);
  if (!py) {
    fail(
      "No Python runtime found.",
      "This build should include one in resources/python.\n\n" +
        "If you are running from source, install Python 3.11+ or set\n" +
        "DOOMNITE_PYTHON to a python.exe."
    );
    return;
  }

  if (needsFetch(packRoot, managed) && !(await fetchPack(packRoot, py))) return;

  if (!(await startServer(packRoot, py))) return;
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", () => {
  quitting = true;
  // Kill the children with us. Without this, closing the window leaves an
  // invisible python holding port 8765 and the next launch reports EADDRINUSE --
  // and a fetcher that keeps writing into the pack after the app is gone.
  kill(server);
  kill(fetcher);
});

app.on("window-all-closed", () => {
  // Not while the shell is still coming up: a successful first run destroys the
  // progress window before it creates the launcher window, and quitting on that
  // gap would kill the app at the exact moment it finished working.
  if (!starting) app.quit();
});