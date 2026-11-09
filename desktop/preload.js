const { contextBridge, ipcRenderer } = require("electron");

// The launcher's port is chosen at startup (first free one at or above 8765),
// so it cannot be a constant here: hardcoding 8765 both rejected the real app
// and accepted whatever else happened to be on that port. main.js passes the
// port it actually bound through additionalArguments.
const ORIGIN =
  (process.argv.find((a) => a.startsWith("--doomnite-origin=")) || "").split("=")[1] ||
  "http://127.0.0.1:8765";

contextBridge.exposeInMainWorld("doomnite", {
  browseIwad: (wad) => {
    if (window.location.origin !== ORIGIN) {
      return Promise.reject(new Error("IWAD browsing is only available in DoomNite."));
    }
    if (!["DOOM.WAD", "DOOM2.WAD"].includes(wad)) {
      return Promise.reject(new Error("Unsupported IWAD selection."));
    }
    return ipcRenderer.invoke("doomnite:browse-iwad", wad);
  },
});
