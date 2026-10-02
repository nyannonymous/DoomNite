const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("doomnite", {
  browseIwad: (wad) => {
    if (window.location.origin !== "http://127.0.0.1:8765") {
      return Promise.reject(new Error("IWAD browsing is only available in DoomNite."));
    }
    if (!["DOOM.WAD", "DOOM2.WAD"].includes(wad)) {
      return Promise.reject(new Error("Unsupported IWAD selection."));
    }
    return ipcRenderer.invoke("doomnite:browse-iwad", wad);
  },
});
