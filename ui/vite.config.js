import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built assets go to ../app, NOT ../dist.
//
// dist/ is what Cloudflare Pages publishes, and it should be nothing but the
// download page. Two earlier layouts put the launcher in dist/ and both were
// wrong: publishing the launcher at the public root just gives a browser full of
// failed /api/entries fetches and an empty page, and nesting it at dist/app/ was
// no better because Pages rewrites *every* unmatched path -- including .js and
// .css -- to index.html. Requests for /app/assets/*.js came back as HTML.
//
// Keeping the launcher out of the published tree removes the problem instead of
// working around it: dist/ holds one file, there is nothing for a rewrite rule
// to catch, and serve.py still finds everything under the pack root.
//
// base is relative so the bundle works from /app without rewriting asset URLs.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../app",
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