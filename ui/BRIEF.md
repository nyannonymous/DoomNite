# Redesign brief (user, verbatim)

Sent during the session before the gateway reset. This is the spec for the
in-progress UI overhaul.

## Role
Expert Senior Frontend Engineer / UI-UX Designer. React, Vite, Tailwind CSS,
Framer Motion.

## Context
"DoomNite," a launcher for Doom mods. Current UI too generic, flat, standard web
dashboard. Overhaul styling and interactions into a **retro-futuristic UAC
terminal**: a modern reimagining of the 1993 Doom UI mixed with the gritty,
fast-paced feel of Doom Eternal.

## Tech stack requirements
- React (Vite)
- Tailwind CSS
- Framer Motion — all micro-animations and transitions
- Lucide React for icons, styled to fit

## Design directives

**1. The "Doom" vibe.** Deep gunmetal greys, industrial rust, toxic waste green,
blood red. High-contrast type. Chunky industrial headers (Oswald / Black Ops One),
body text clean but slightly monospaced (JetBrains Mono / Fira Code) for terminal
feel.

**2. Textures and depth.** No flat colors. Subtle noise, dark gradients, metallic
bevels. CRT scanline overlay and/or vignette across the whole app.

**3. Layout overhaul.**
- Get rid of the rigid uniform grid.
- Make layout dynamic. The **selected** game becomes a "Hero" — its background art
  fills the screen under a dark blurred overlay, cards sit on top.
- Right-hand details pane becomes a UAC terminal readout with animated
  typing effects for the game description.

## Micro-interactions ("the sexy factor")

**Grid cards.** On hover, do not just scale up — *jolt* slightly with Framer Motion
spring physics. Glowing **jagged border** effect (e.g. `clip-path` polygon) that
snaps into place. Slight **glitch / chromatic aberration** on the title text.

**Play button.** The focal point: heavy industrial button. On hover, pulse with a
red/orange glow and a subtle "press down" shadow animation. On click, trigger a
**screen-wide flash or glitch** before launching.

**Details pane.** When switching games, slide/snap in with a mechanical feel.
Animated "data streams" or a loading bar that looks like a UAC boot sequence.

**Cursor.** Custom cursor — classic Doom crosshair or glowing terminal cursor.

## Actionable tasks
1. Tailwind config with the custom Doom palette and fonts.
2. Refactor the grid to `motion.div` with staggered entrance (cards fly in from the
   bottom, like loading into a level).
3. Redesign `ModCard`: jagged hover borders, dynamic drop shadows, glitch text.
4. Redesign `DetailsPane` as a terminal and `PlayButton` as a heavy industrial switch.
5. Add a global CRT/scanline overlay component.

Use `backdrop-filter`, `clip-path`, `mix-blend-mode`, `text-shadow`.