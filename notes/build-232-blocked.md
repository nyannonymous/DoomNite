# 2.3.2 build — blocked note (2026-10-16)

Not attempted: `npm run build` empties `app/` on failure (vitest/vite OOM) and needs RAM free (Bitwig uses ~25 GB of 32 GB). The `copyTree` fix lives in source; building just produces a new bundle/index. Blocked on: free RAM (close Bitwig) and owner confirming a build is needed (v2.3.1 is live; 2.3.2 has no new feature beyond that fix which is already committed but unreleased).
