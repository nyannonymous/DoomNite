import { readFileSync } from "node:fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The launcher UI shows the pack version in the topbar, under the logo.
// Baked at build time from the Electron app's package.json -- the single
// place the version lives -- so dev, the packaged app and the served bundle
// can never disagree about what is running.
const desktopPkg = JSON.parse(
  readFileSync(new URL("../desktop/package.json", import.meta.url), "utf8"));

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
  define: {
    __APP_VERSION__: JSON.stringify(desktopPkg.version),
  },
  base: "./",
  build: {
    outDir: "../app",
    emptyOutDir: true,
    assetsDir: "assets",
    sourcemap: false,
  },
  server: {
    port: 5173,
    // Bind IPv4 as well as IPv6. Without this Vite listens on [::1] only, so
    // http://localhost:5173/ works but http://127.0.0.1:5173/ gets connection
    // refused -- and the IP form is the one the rest of this project uses
    // (serve.py on 127.0.0.1:8765, the Electron window, the download page).
    // `host: true` would also expose it on the LAN, which is not wanted.
    host: "127.0.0.1",
    // During `npm run dev`, proxy to the Python server so the UI talks to the
    // real /api/entries, /api/launch and /art/ instead of dying on CORS.
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/art": "http://127.0.0.1:8765",
    },
  },
});