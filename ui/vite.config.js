import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built assets go to ../dist/app so serve.py can serve them from the pack root.
//
// Why a subdirectory: ../dist is what Cloudflare Pages publishes, and its
// index.html is the download page. The launcher UI cannot be the root of that
// deploy -- it calls /api/entries and /api/launch, which only exist when the
// user's own Python server is running. Serving it at the public root just
// produces a browser console full of failed fetches and an empty launcher.
//
// So: dist/index.html is the download page, dist/app/index.html is the launcher.
// One tree satisfies both -- Pages gets the page at the root with no dashboard
// configuration change, and serve.py serves the launcher from the subpath.
//
// base is relative so the bundle works from /app without rewriting asset URLs.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../dist/app",
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