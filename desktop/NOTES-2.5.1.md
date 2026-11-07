# v2.5.1 — updates actually download, full roster restored

Two fixes over v2.5.0, both found the hard way:

**Updates download.** v2.5.0 shipped the Duke games but never installed
them on a machine that already had DoomNite: the app decided "pack
complete" from a single marker file, so the ~6,100 new manifest entries
never triggered a fetch. Fresh installs were fine; everyone else got
Duke cards with no files behind them. The fetch trigger now checks the
manifest against disk — anything `sources.json` lists that is missing
gets downloaded on next launch (resumable; downloads exactly the gap).
`no_host` files are excluded so a vetoed IWAD can't put the app in a
permanent fetch-loop-at-startup state.

**All 16 Doom games restored.** The v2.5.0 manifest was built with only
4 of 16 games: the build treated the operator's original folders as the
source of truth, and those had been emptied — every mod-based game
(Brutal Doom, Brutal Doom Black Edition, Aliens: Eradication, The Bikini
Bottom Massacre, DukeBoomem, QuakinDoom, Shadow Warrior, DBP37, MoonMan,
MyHouse, DN3DooM...) silently dropped off its card. The build now falls
back to the pack's own copies, which are the same files the bucket
serves. SRB2 is the one casualty: it launched from an operator folder
that no longer exists and was never in the pack or bucket — point a
v2.2 install at the pack and it can come back as a bundled title.

Engine logs (e.g. `eduke32.log`) are no longer tracked in the manifest;
they are rewritten on every launch and made the manifest drift constantly.
