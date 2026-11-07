# v2.5.1 — updates actually download

v2.5.0 shipped the Duke games but never installed them on a machine that
already had DoomNite: the app decided "pack complete" from a single marker
file, so the ~6,100 new manifest entries never triggered a fetch. Fresh
installs were fine; everyone else got Duke cards with no files behind them.

The fetch trigger now checks the manifest against disk — anything
`sources.json` lists that is missing gets downloaded on next launch (the
fetcher is resumable, so it downloads exactly the gap). `no_host` files
are excluded so a vetoed IWAD can't put the app in a permanent
fetch-loop-at-startup state.
