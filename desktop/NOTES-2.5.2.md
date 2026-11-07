# v2.5.2 — Duke multiplayer stops lying about being broken

Duke multiplayer worked, and the panel said it didn't. Opening the
multiplayer dialog on a Duke game ran the Zandronum/NukemNet setup step —
junctions, then a scan of NukemNet's doom/doom2 file lists — and printed
`DOOM2.WAD <- MISSING` into the log of a game that uses none of those
things. EDuke32 ships inside the pack; Duke host/join is a plain IP
address and no setup. The panel now says exactly that for Duke entries
and skips the NukemNet machinery entirely.

Also covered, for the record: Zandronum itself ships inside the pack
(`runtime/zandronum/zandronum.exe`) and the multiplayer path prefers the
bundled copy over an installed one — no separate Zandronum install is
needed on any machine running v2.5.1+.
