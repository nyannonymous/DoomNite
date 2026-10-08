## The interface stops looking cheap

This release is about how the UI is put together, not what is in it. Nothing
about the launcher, the mods or multiplayer changes here.

### The cause

Two things, both structural.

**Nine full-screen translucent layers were stacked over your content.** The CRT
effect is four of them — scanlines, a moving sweep, a vignette and colour
fringing — plus a hero veil, a blurred hero backdrop, film grain, an ember
canvas and two more. Together they multiplied down to roughly 60% black across
the whole interface before a single pixel of text was legible.

That is why everything looked dim and muddy. The panels were not dark because
they were styled dark; they were dark because six black layers were sitting on
top of them.

**The surfaces had almost no value range.** The panel background sat at 5%
lightness on a page at 3%. A 2% difference is not a surface, it is a slightly
different black — so the only thing separating a panel from the page was a 1px
border. The entire interface read as thin outlines on black, which is what
"cheap" looks like.

### What changed

- **Scanlines are edge-weighted now.** They used to run at full strength across
  the centre 45% of the screen — exactly where the text is. They now fade out by
  52% radius and only read at the far edges, where they look like a screen
  instead of stripes over your type.
- **The vignette is one corner-weighted shadow** instead of two stacked insets.
  The inner 50px ring was darkening the middle of the screen as well as the
  edges.
- **The hero veil dropped from 82% black to a 16–22% band**, weighted to the top
  and bottom where the header and status bar sit, and near-zero across the
  middle. The hero image is already blurred to 14px at 42% brightness, so it is
  low-contrast by construction and never needed a heavy veil.
- **A real surface ramp.** Panels, raised panels and the page are now three
  distinct values instead of three shades of the same black, so nesting reads
  without leaning on borders. Borders and shadows are refinement now, not basic
  legibility.
- **One surface colour instead of three.** The panel header was painted
  `rgba(8, 14, 8)` — a *green* — under a purple panel, because `.panel` had
  drifted into three separate rules that disagreed. They are consolidated, and
  the sidebar now reads as one object instead of two mismatched pieces.

### Also in this release

- The fake `LOADING` bar is gone. It was a 520ms timer covering an already
  rendered panel, and it sat directly above PLAY so it read as progress toward
  pressing the button — then the button was still there after 100%.
- Card titles have a contrast scrim, so a white title on a white logo no longer
  disappears.
- The multiplayer address field is the first control in the panel, not a second
  screen behind a Join button. It is pinned so it cannot be scrolled out of
  view.
- Active Mods and the command line are folded away. The command line is the
  least-used thing in a launcher whose whole job is running games for you.
- Filter chips explain themselves on hover. "Combos" is more than one mod;
  "Multi-config" is more than one build.
- The falling green streaks are gone from the sidebar, where they were crossing
  the mod list several times a second.

### Verified

`selftest_packaged.py` against the finished 2.2.0 build · `selftest_serve` ·
`selftest_mp` 102/102 · `selftest_packmod_fetch` · `selftest_nn_preset` ·
`verify.mjs` 21/21 · `verify-watch.mjs` 11/11 · `verify-mp-button.mjs` 29/29.

Every colour change above was checked in the *compiled* stylesheet, not just the
source — the minifier rewrites `rgba(8,9,11,0.62)` to `#08090b9e`, and an earlier
round of assertions passed or failed on that serialisation rather than on the
design.