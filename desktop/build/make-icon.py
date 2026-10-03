#!/usr/bin/env python
"""Generate the DoomNite application icon.

Produces build/icon.ico (multi-resolution, for electron-builder) and
build/icon.png (1024px master, for the shortcut and docs).

Design rationale -- "doom" and "knight":
- Doom is the red demon; the palette here is the UI's own toxic green
  (#a3e05c) on near-black (#0e1013), not literal blood red, so the icon
  belongs to the launcher rather than to one franchise in its library.
- Knight = the visor slit. One horizontal bar is the whole mark; it reads
  at 16px, which a detailed demon face would not.
- The notched corner profile mirrors the cards' d-jagged clip-path, so the
  icon and the UI share a silhouette.
- Supersampled 4x then LANCZOS-downscaled: 16px is where hand-placed
  pixels fall apart, and this runs at build time so it is cheap.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent

BG = (14, 16, 19, 255)  # --bg, #0e1013
GREEN = (163, 224, 92, 255)  # --accent, #a3e05c
GREEN_DIM = (91, 148, 46, 255)  # --accent-dim, #5b942e
GREEN_HI = (201, 245, 140, 255)  # #c9f58c

S = 1024  # master size
SS = 4  # supersample factor

# Notch geometry, as a fraction of the canvas. Matches d-jagged's ~10/1024
# cut scaled up so the icon has a visible, deliberate corner.
NOTCH = 0.115


def draw_icon(size: int) -> Image.Image:
    """Render one square icon at `size` px."""
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    m = int(s * 0.055)  # outer margin
    box = [m, m, s - m, s - m]
    n = int(s * NOTCH)
    r = int(s * 0.14)  # corner radius

    # Rounded square with two opposite corners notched out, so the silhouette
    # matches the launcher cards' d-jagged border.
    d.rounded_rectangle(box, radius=r, fill=BG)

    # Cut the notches by punching transparent corners. Top-left and
    # bottom-right are chamfered diagonally; top-right and bottom-left keep
    # the radius. Done with a mask so the cut is genuinely transparent
    # rather than painted over.
    mask = Image.new("L", (s, s), 255)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle(box, radius=r, fill=255)
    # top-left chamfer
    md.polygon(
        [(m, m + n), (m + n, m), (m, m)], fill=0
    )
    # bottom-right chamfer
    md.polygon(
        [(s - m, s - m - n), (s - m - n, s - m), (s - m, s - m)], fill=0
    )
    img.putalpha(mask)

    # Recompute the draw layer over the masked base.
    d = ImageDraw.Draw(img)

    # --- The knight's visor: the core mark ---------------------------------
    cx = s / 2
    bar_h = int(s * 0.115)  # bar thickness
    bar_w = int(s * 0.52)  # bar length
    top = int(s * 0.365)

    # Dim "shadow" bar, offset, giving the mark depth without a gradient.
    d.rounded_rectangle(
        [cx - bar_w / 2, top + bar_h * 0.42, cx + bar_w / 2, top + bar_h * 1.42],
        radius=bar_h / 2,
        fill=GREEN_DIM,
    )

    # Bright visor bar.
    d.rounded_rectangle(
        [cx - bar_w / 2, top, cx + bar_w / 2, top + bar_h],
        radius=bar_h / 2,
        fill=GREEN,
    )

    # Hot centre segment -- the glint that makes it read as a lit visor
    # rather than a plain rectangle.
    glint_w = bar_w * 0.30
    d.rounded_rectangle(
        [cx - glint_w / 2, top + bar_h * 0.18, cx + glint_w / 2, top + bar_h * 0.82],
        radius=bar_h * 0.32,
        fill=GREEN_HI,
    )

    # --- Cheek vents: two short bars flanking the visor --------------------
    vent_w = int(s * 0.135)
    vent_h = int(s * 0.052)
    gap = int(s * 0.052)
    vy = top + bar_h * 1.95
    for sign in (-1, 1):
        vx = cx + sign * (bar_w / 2 - vent_w)
        d.rounded_rectangle(
            [vx, vy, vx + vent_w, vy + vent_h], radius=vent_h / 2, fill=GREEN_DIM
        )

    # --- Baseline rule, echoing the UI's divider --------------------------
    rule_w = int(s * 0.46)
    rule_h = int(s * 0.030)
    ry = int(s * 0.70)
    d.rounded_rectangle(
        [cx - rule_w / 2, ry, cx + rule_w / 2, ry + rule_h],
        radius=rule_h / 2,
        fill=GREEN_DIM,
    )

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    master = draw_icon(S)
    png = OUT / "icon.png"
    master.save(png)
    print(f"wrote {png}")

    # electron-builder wants an .ico. Sizes below 256 are the ones that
    # actually matter in a taskbar/Explorer; include the standard ladder.
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [draw_icon(px) for px in sizes]
    ico = OUT / "icon.ico"
    frames[-1].save(
        ico, format="ICO", sizes=[(px, px) for px in sizes], append_images=frames[:-1]
    )
    print(f"wrote {ico} ({len(sizes)} sizes: {sizes})")


if __name__ == "__main__":
    main()