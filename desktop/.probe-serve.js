// Throwaway: reproduce exactly how the app starts serve.py, then mirror
// waitForPort, so a failure here is a real one and not buffered output.
const { spawn } = require("node:child_process");
const net = require("node:net");

const py = "C:/Users/Serge/AppData/Local/Temp/dn-verify/win-unpacked/resources/python/python.exe";
const serve = "Z:/DOOM_PACK/serve.py";

const s = spawn(py, [serve, "--no-open", "--port", "8765"], {
  cwd: "Z:/DOOM_PACK",
  windowsHide: true,
  stdio: ["ignore", "pipe", "pipe"],
});

let out = "";
for (const st of [s.stdout, s.stderr]) {
  st.setEncoding("utf8");
  st.on("data", (d) => (out += d));
}
s.on("error", (e) => {
  console.log("SPAWN ERROR", e.code, e.message);
  process.exit(1);
});
s.on("exit", (c) => console.log(`child exited early with code ${c}\n${out || "(no output)"}`));

const started = Date.now();
const attempt = () => {
  const sock = net.connect(8765, "127.0.0.1");
  sock.once("connect", () => {
    console.log(`port open after ${((Date.now() - started) / 1000).toFixed(1)}s`);
    try {
      sock.end();
      s.kill();
    } catch {}
    process.exit(0);
  });
  sock.once("error", () => {
    sock.destroy();
    if (Date.now() - started > 20000) {
      console.log(`NEVER OPENED after 20s\n${out || "(no output)"}`);
      s.kill();
      process.exit(1);
    }
    setTimeout(attempt, 120);
  });
};
attempt();
