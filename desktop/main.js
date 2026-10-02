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
// this file in a dev checkout. In a packaged build they are not bundled -- the
// pack stays on disk and the app points at wherever it is installed.
const DEV_PACK = path.resolve(__dirname, "..");

let server = null;
let win = null;
let quitting = false;

// Which Python to use, and whether there is one at all. Checked before we make
// a window, so the user gets a dialog naming the actual problem instead of a
// window that loads forever.
function findPython(packRoot) {
  const candidates = [];

  if (process.env.DOOMNITE_PYTHON) candidates.push(process.env.DOOMNITE_PYTHON);

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

function resolvePackRoot() {
  if (process.env.DOOMNITE_PACK) return process.env.DOOMNITE_PACK;
  if (!app.isPackaged) return DEV_PACK;

  // Packaged: the app was installed into its own directory, and the pack sits
  // alongside it. Walk up until serve.py shows up.
  let dir = path.dirname(app.getPath("exe"));
  for (let i = 0; i < 4; i++) {
    if (fs.existsSync(path.join(dir, "serve.py"))) return dir;
    const up = path.dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  return null;
}

function fail(message, detail) {
  dialog.showErrorBox("DoomNite can't start", message + (detail ? `\n\n${detail}` : ""));
  app.quit();
}

async function startServer(packRoot) {
  const servePy = path.join(packRoot, "serve.py");
  if (!fs.existsSync(servePy)) {
    fail(
      "Couldn't find serve.py.",
      `Looked in:\n${packRoot}\n\nSet DOOMNITE_PACK to the pack directory if it lives somewhere else.`
    );
    return false;
  }

  const py = findPython(packRoot);
  if (!py) {
    fail(
      "No Python found.",
      "DoomNite's server is Python and needs Python 3.11 or newer.\n\n" +
        "Install it from python.org, or set DOOMNITE_PYTHON to a python.exe."
    );
    return false;
  }

  // --no-open: we are the window now, so serve.py must not also open a browser.
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

app.whenReady().then(async () => {
  const packRoot = resolvePackRoot();
  if (!packRoot) {
    fail(
      "Couldn't locate the DoomNite pack.",
      "Set DOOMNITE_PACK to the folder containing serve.py."
    );
    return;
  }

  Menu.setApplicationMenu(null);
  if (!(await startServer(packRoot))) return;
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", () => {
  quitting = true;
  // Kill the server with us. Without this, closing the window leaves an
  // invisible python holding port 8765 and the next launch reports EADDRINUSE.
  if (server && !server.killed) {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(server.pid), "/f", "/t"], { windowsHide: true });
    } else {
      server.kill("SIGTERM");
    }
  }
});

app.on("window-all-closed", () => app.quit());