# v2.5.5 — a smaller payload, same games

**418 MB of payload is gone, and nothing you can launch changed.** The pack
carried a second copy of the Total Chaos data file under `mods\total-chaos\` —
byte-for-byte identical to the one the *Total Chaos (Retro)* card already runs
out of its own folder, and referenced by no card, launcher or shortcut. It was
left over from when Total Chaos was only a Doom mod; both TC entries have been
standalone builds for a while, so the loose copy was dead weight every new
install downloaded.

First run is now 11,834 files / ~10.9 GB instead of 11,835 / ~11.3 GB. The
Retro and Standalone cards are untouched: Retro still streams its 418 MB data
file from the Internet Archive, Standalone its 1.5 GB build from the release.

Existing installs need nothing — the file they already downloaded is simply
never asked for again, and it is not flagged as missing, because the manifest no
longer lists it. No update is required; this one is only worth reinstalling for
if you were short on disk.
