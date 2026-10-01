import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built assets go to ../dist so serve.py can serve them from the pack root.
// base is relative so the bundle works whether it is served from / or a
// subpath without rewriting asset URLs.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../dist",
    emptyOutDir: true,
    assetsDir: "assets",
    sourcemap: false,
  },
  server: {
    port: 5173,
    // During `npm run dev`, proxy to the Python server so the UI talks to the
    // real /api/entries, /api/launch and /art/ instead of dying on CORS.
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/art": "http://127.0.0.1:8765",
    },
  },
});