// The first-run window is sandboxed with no Node access, and everything on it
// is pushed from the main process. The one thing the page needs to send back
// is the Skip button, so the preload exposes exactly that -- a function that
// fires one IPC message and nothing else.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("dnSkip", () => {
  ipcRenderer.send("dn-skip");
});
