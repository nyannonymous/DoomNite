## This release fixes a launcher that would not start

2.1.0 was broken. Installing it produced an error dialog saying the launcher
server had stopped, with `ModuleNotFoundError: No module named 'installer'`,
instead of the game grid. Sorry — that one shipped without being tested as a
packaged build rather than from source.

Two separate faults, each fatal on its own:

1. **The pack folder was not importable.** DoomNite runs the launcher server
   with a bundled copy of Python that pins its module search path to three
   fixed locations, which suppresses the normal "look in the script's own
   folder" behaviour. `installer.py` was sitting right there and could not be
   found. The server now sets this up itself, so it does not depend on how
   Python was launched.

   Worth knowing: this was not new in 2.1.0. It has been latent in every
   release so far, which is why you are the first person to hit it — the
   bundled path happened to resolve differently depending on where the app was
   installed.

2. **A required folder was left out of the installer.** Multiplayer's server
   module lives in `tools/`, which was treated as developer-only and never
   packaged. So even with fault 1 fixed, startup failed a moment later on
   `No module named 'mp_http'`. `tools/` is now included.

### How this is prevented now

`tools/selftest_packaged.py` runs against the actual packaged build and checks
that the server really starts under the bundled Python, that the module search
path is set up before the first local import, and that everything the server
imports was actually packaged. Every release gets this run against its own
finished build, not against the source tree.

### Multiplayer wording

The multiplayer panel now says plainly that **the person you invite does not
need to change anything** — no ports, no settings. Only the host needs
anything set up, and only when the game is not on your own network. The
port-forwarding note now appears only when an address that actually needs it is
being offered.

### Verified

`selftest_packaged.py` against the finished 2.1.1 build · `selftest_serve` ·
`selftest_mp` 102/102 · `selftest_packmod_fetch` · `selftest_nn_preset` ·
`verify.mjs` 21/21 · `verify-watch.mjs` 11/11 · `verify-mp-button.mjs` 19/19.

If 2.1.0 gave you an error dialog, uninstall it and install this one.