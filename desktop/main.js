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
function waitForPort(port, timeoutMs = 30000, child = null) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    let settled = false;
    let retry = null;
    let timeout = null;
    let sock = null;

    const finish = (error) => {
      if (settled) return;
      settled = true;
      if (retry) clearTimeout(retry);
      if (timeout) clearTimeout(timeout);
      if (sock) sock.destroy();
      if (child) {
        child.removeListener("error", onChildError);
        child.removeListener("exit", onChildExit);
      }
      if (error) reject(error);
      else resolve();
    };
    const onChildError = (error) =>
      finish(new Error(spawnFailure("serve.py", child.spawnfile, error)));
    const onChildExit = (code, signal) =>
      finish(
        new Error(
          `serve.py exited before opening port ${port} (code ${code}, signal ${signal || "none"})`
        )
      );

    if (child) {
      child.once("error", onChildError);
      child.once("exit", onChildExit);
    }
    timeout = setTimeout(
      () => finish(new Error(`serve.py did not open port ${port} in time`)),
      timeoutMs
    );

    const attempt = () => {
      if (settled) return;
      const attemptSocket = net.connect(port, "127.0.0.1");
      sock = attemptSocket;
      attemptSocket.once("connect", () => finish());
      attemptSocket.once("error", () => {
        attemptSocket.destroy();
        if (sock === attemptSocket) sock = null;
        if (!settled && Date.now() >= deadline) {
          finish(new Error(`serve.py did not open port ${port} in time`));
        } else if (!settled) {
          retry = setTimeout(attempt, 120);
        }
      });
    };
    attempt();
  });
}

function spawnFailure(label, command, error) {
  const code = error && error.code ? ` (${error.code})` : "";
  const message = error && error.message ? error.message : String(error);
  return `${label} could not start${command ? `: ${command}` : ""}${code}. ${message}`;
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
function copyTree(src, dest, onFile) {
  fs.mkdirSync(dest, { recursive: true });
  let copied = 0;
  for (const ent of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, ent.name);
    const d = path.join(dest, ent.name);
    if (ent.isDirectory()) {
      copied += copyTree(s, d, onFile);
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
    if (onFile) onFile(copied);
  }
  return copied;
}

function countFiles(dir) {
  let n = 0;
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    n += ent.isDirectory()
      ? countFiles(path.join(dir, ent.name))
      : 1;
  }
  return n;
}

// Materialise the pack root. Runs on every launch of a managed pack, not just
// the first, so that upgrading the app replaces the UI and the manifest instead
// of leaving last version's copies in place forever.
//
// Reported through the first-run window rather than done silently: it is ~115
// small files, and on a machine whose antivirus rescans each write that is a
// minute of a black screen before anything appears -- indistinguishable from
// the app failing to start, which is the bug this whole path exists to fix.
function seedPack(root, ui) {
  if (!fs.existsSync(SEED)) {
    fail(
      "This build is missing its bundled pack.",
      `Expected a pack bootstrap at:\n${SEED}\n\n` +
        "Set DOOMNITE_PACK to a complete pack directory to use that instead."
    );
    return false;
  }
  const total = countFiles(SEED);
  let copied = 0;
  let announced = false;
  copyTree(SEED, root, () => {
    // Only on the first real file: a launch with nothing to copy must not open
    // a window just to say it did nothing.
    if (!announced) {
      announced = true;
      ui.phase(
        "Unpacking the launcher",
        "The pack's own files, kept beside your save data so the install stays " +
          "read-only."
      );
    }
    ui.state.done = ++copied;
    ui.state.total = total;
    ui.push();
  });
  if (copied) console.log(`seedPack: ${copied} file(s) -> ${root}`);
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

// The window that covers a first run: unpacking, then 3.4 GB of downloading.
// Without it the app looks hung for several minutes -- the server has not
// started, so there is nothing else to show -- and a user reasonably kills it.
//
// The window is created on the first thing there is to report, not up front, so
// a launch of an already-set-up pack never flashes one. Everything the two
// phases share lives here: the state object the page renders, the throttled
// push, and the fact that closing the window means stop.
function firstRunWindow() {
  const state = {
    head: "Getting ready",
    note: "",
    done: 0,
    total: 0,
    current: "",
    bytes: "",
    log: [],
  };
  const cancels = [];
  let w = null;
  let pending = null;
  let cancelled = false;

  const flush = () => {
    pending = null;
    if (!w || w.isDestroyed()) return;
    w.webContents
      .executeJavaScript(`window.dnUpdate(${JSON.stringify(state)})`)
      .catch(() => {});
  };
  // Coalesced rather than sent per file: several hundred updates a second would
  // spend more time in the renderer than in the copy or the download.
  const push = () => {
    if (pending) return;
    pending = setTimeout(flush, 200);
  };

  const open = () => {
    if (w) return w;
    w = new BrowserWindow({
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
    // The page has to have run its script before an update means anything, and
    // work can start before it has. Re-send once the document is there.
    w.webContents.once("did-finish-load", flush);
    w.on("closed", () => {
      cancelled = true;
      for (const fn of cancels) fn();
    });
    w.loadFile(path.join(__dirname, "first-run.html"));
    return w;
  };

  return {
    state,
    push,
    open,
    get cancelled() {
      return cancelled;
    },
    onCancel(fn) {
      cancels.push(fn);
    },
    phase(head, note) {
      state.head = head;
      state.note = note;
      state.done = 0;
      state.total = 0;
      state.current = "";
      state.bytes = "";
      open();
      push();
    },
    close() {
      if (pending) clearTimeout(pending);
      if (w && !w.isDestroyed()) w.destroy();
    },
  };
}

// Download the payload, reporting progress as it goes.
//
// Returns { ok: true } when the pack is complete enough to serve,
// { ok: false, cancelled: true } when the user closed the progress window, and
// { ok: false, reason } when the download ran and failed. The three are kept
// apart because they want different things afterwards: quit, or an offer to
// retry. Failing the app outright here would make a flaky network -- or a
// machine whose certificate store is out of date -- indistinguishable from a
// broken install.
async function fetchPack(root, py, ui) {
  ui.phase(
    "Fetching the pack",
    "The engine, the IWADs and every mod, each file verified against its own " +
      "sha256 as it lands. It happens once."
  );
  const state = ui.state;

  // -u because stdout is a pipe here, not a console, and Python block-buffers
  // a pipe: without it the whole first run would show nothing until the buffer
  // filled, which is the opposite of progress.
  let child;
  try {
    child = spawn(py.cmd, [...py.args, "-u", path.join(root, "fetcher.py")], {
      cwd: root,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    return {
      ok: false,
      reason: spawnFailure("Python fetcher", py.cmd, error),
    };
  }
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
        ui.push();
        continue;
      }
      m = /^to fetch: (\d+) files, (.+)$/.exec(line);
      if (m) {
        state.total = +m[1];
        state.bytes = m[2];
        ui.push();
        continue;
      }
      m = /^(\S+): ([\d.]+ [A-Z]+) (\d+)%$/.exec(line);
      if (m) {
        state.current = `${m[1]} · ${m[2]} · ${m[3]}%`;
        ui.push();
        continue;
      }
      state.log.push(line);
      if (state.log.length > 24) state.log.shift();
      ui.push();
    }
  };
  for (const stream of [child.stdout, child.stderr]) {
    if (!stream) continue;
    stream.setEncoding("utf8");
    stream.on("data", onData);
  }

  ui.onCancel(() => kill(child));

  const result = await new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    child.once("error", (error) => finish({ error }));
    // `close` follows stdio closure, so all buffered fetcher output is included
    // in the summary before it is parsed.
    child.once("close", (code, signal) => finish({ code, signal }));
  });
  fetcher = null;
  ui.push();

  if (ui.cancelled) return { ok: false, cancelled: true };
  if (result.error) {
    return {
      ok: false,
      reason: spawnFailure("Python fetcher", py.cmd, result.error),
    };
  }
  const { code } = result;

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
    return { ok: true };
  }

  const why = summary
    ? `${summary.failed} file(s) could not be downloaded.`
    : `The fetcher exited with code ${code}.`;
  return { ok: false, reason: `${why}\n\n${text.slice(-700)}` };
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

  try {
    server = spawn(py.cmd, [...py.args, servePy, "--no-open", "--port", String(PORT)], {
      cwd: packRoot,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    fail("The launcher server did not start.", spawnFailure("Python server", py.cmd, error));
    return false;
  }

  const log = [];
  for (const stream of [server.stdout, server.stderr]) {
    if (!stream) continue;
    stream.setEncoding("utf8");
    stream.on("data", (d) => log.push(d.trim()));
  }

  let ready = false;
  let earlyExit = null;
  server.on("error", (error) => {
    log.push(spawnFailure("Python server", py.cmd, error));
    // waitForPort reports startup errors once; only a later error is a runtime
    // failure that needs a dialog here.
    if (ready && !quitting) {
      fail("The launcher server stopped unexpectedly.", log.join("\n").slice(0, 900));
    }
  });
  server.on("exit", (code, signal) => {
    earlyExit = { code, signal };
    // A crash while quitting is expected, and startup exits are reported by
    // waitForPort so the user gets one dialog rather than two.
    if (ready && !quitting) {
      fail(
        "The launcher server stopped unexpectedly.",
        (log.join("\n") || `serve.py exited with code ${code}, signal ${signal || "none"}`).slice(0, 900)
      );
    }
  });

  try {
    await waitForPort(PORT, 30000, server);
  } catch (error) {
    fail(
      "The launcher server did not start.",
      (log.join("\n") || error.message).slice(0, 900)
    );
    return false;
  }
  // The server can exit immediately after opening the port but before this
  // continuation runs. Do not report startup success in that race.
  if (earlyExit || server.exitCode !== null) {
    const ended = earlyExit || { code: server.exitCode, signal: server.signalCode };
    fail(
      "The launcher server stopped unexpectedly.",
      (log.join("\n") || `serve.py exited with code ${ended.code}, signal ${ended.signal || "none"}`).slice(0, 900)
    );
    return false;
  }
  ready = true;
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
    if (!child.pid) return;
    try {
      const killer = spawn(
        "taskkill",
        ["/pid", String(child.pid), "/f", "/t"],
        { windowsHide: true, stdio: "ignore" }
      );
      // Cleanup is best-effort: taskkill may be unavailable or denied, but its
      // spawn error must never become an unhandled ChildProcess 'error' event.
      killer.on("error", (error) => {
        console.warn(`could not stop child ${child.pid}: ${error.message}`);
      });
    } catch (error) {
      console.warn(`could not stop child ${child.pid}: ${error.message}`);
    }
  } else {
    try {
      child.kill("SIGTERM");
    } catch (error) {
      console.warn(`could not stop child ${child.pid || "process"}: ${error.message}`);
    }
  }
}

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);

  const { root: packRoot, managed } = resolvePackRoot();
  const ui = firstRunWindow();

  // The bootstrap first: it contains the fetcher, so it has to be on disk
  // before anything can be downloaded, and serve.py cannot start without it.
  if (managed && !seedPack(packRoot, ui)) return;

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

  // Retry loop rather than a single attempt. Whatever went wrong is usually the
  // network, which is worth a second try, and the fetch is resumable -- nothing
  // already verified is downloaded again.
  let whyNoPack = "";
  while (!ui.cancelled && needsFetch(packRoot, managed)) {
    const got = await fetchPack(packRoot, py, ui);
    if (got.ok) break;
    if (got.cancelled) break;

    whyNoPack = got.reason;
    const pick = dialog.showMessageBoxSync({
      type: "warning",
      title: "DoomNite",
      message: "The pack did not finish downloading.",
      detail:
        `${got.reason}\n\n` +
        "Files already downloaded are kept and re-verified, so trying again " +
        "resumes rather than starting over.",
      buttons: ["Try again", "Open the launcher anyway", "Quit"],
      defaultId: 0,
      cancelId: 2,
      noLink: true,
    });
    if (pick === 1) break;
    if (pick === 2) {
      ui.close();
      return;
    }
  }

  // Read before closing: closing destroys the window, which is the same event
  // as the user closing it, and the two mean opposite things here.
  if (ui.cancelled) return;
  ui.close();

  if (!(await startServer(packRoot, py))) return;
  // The launcher opens with entries missing rather than not opening at all:
  // serve.py reports exactly which ones, and the pack can be completed from
  // here by launching again. Written to the console so a bug report has it.
  if (whyNoPack) console.warn(`pack incomplete:\n${whyNoPack}`);
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