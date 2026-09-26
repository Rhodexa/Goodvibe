"""
Greetings list -> one centered SVG costume per name, for Scratch.

Each name is converted to outlines (fontTools), so the SVG has no <text>
and doesn't depend on which fonts Scratch/the browser have.

Centering:
    x: the ink bounds of the name are centered, so the rotation center
       sits in the visual middle of the word.
    y: the band between the baseline and the font's cap height is
       centered, NOT the ink bounds. Every name then shares the same
       baseline relative to its center, so descenders (g, y, p, _) don't
       make some names sit higher than others. --vcenter ink switches to
       plain ink-bounds centering.

Like make_tri_sweep_svgs.py, the viewBox starts at 0,0 with an invisible
rect covering it, and the text is placed so its center is the viewBox
center, which is where Scratch puts the default rotation center.

The default fill is a slightly desaturated red (hue 0), so the color
effect in Scratch rotates it cleanly around the hue wheel.

Usage:
    python3 tools/greetings_svg.py greetings.txt OUT_DIR
        [--size 16] [--fill #d65050] [--font PATH] [--pad 2]
        [--vcenter cap|ink] [--prefix hi_] [--only NAME]

Files are named PREFIX + name (hi_KevLeCodeur.svg); a name listed twice
just overwrites its own file.
"""

import argparse
import os
import re

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

DEFAULT_FONT = "/usr/share/fonts/rsms-inter-fonts/Inter-Bold.ttf"


def fmt(v):
    v = round(v, 3)
    if v == 0:
        v = 0.0
    return f"{v:g}"


def text_outline(font, text):
    """Return (glyphs, bounds) in font units, y up. glyphs = [(name, x_offset)]."""
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    gs = font.getGlyphSet()
    glyphs = []
    x = 0
    bp = BoundsPen(gs)
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            raise SystemExit(f"font has no glyph for {ch!r} in {text!r}")
        gs[name].draw(TransformPen(bp, (1, 0, 0, 1, x, 0)))
        glyphs.append((name, x))
        x += hmtx[name][0]
    return glyphs, bp.bounds


def name_svg(font, text, size, fill, pad, vcenter):
    gs = font.getGlyphSet()
    scale = size / font["head"].unitsPerEm
    glyphs, (x0, y0, x1, y1) = text_outline(font, text)

    cx = (x0 + x1) / 2
    if vcenter == "ink":
        cy = (y0 + y1) / 2
    else:
        cap = getattr(font["OS/2"], "sCapHeight", 0) or font["head"].unitsPerEm * 0.7
        cy = cap / 2

    # Half-extents around the center, in px; the canvas is symmetric about it.
    hw = max(cx - x0, x1 - cx) * scale + pad
    hh = max(cy - y0, y1 - cy) * scale + pad
    w, h = 2 * hw, 2 * hh

    # font units (y up, origin at cx,cy) -> SVG px (y down, origin top-left)
    pen = SVGPathPen(gs, ntos=fmt)
    for gname, gx in glyphs:
        t = (scale, 0, 0, -scale, hw + (gx - cx) * scale, hh + cy * scale)
        gs[gname].draw(TransformPen(pen, t))

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        f'width="{fmt(w)}" height="{fmt(h)}" viewBox="0 0 {fmt(w)} {fmt(h)}">\n'
        f'  <rect x="0" y="0" width="{fmt(w)}" height="{fmt(h)}" '
        f'fill="#000000" fill-opacity="0" stroke="none"/>\n'
        f'  <path d="{pen.getCommands()}" fill="{fill}" stroke="none"/>\n'
        f"</svg>\n"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("greetings")
    ap.add_argument("out_dir")
    ap.add_argument("--size", type=float, default=16,
                    help="font size (em) in costume px (default 16)")
    ap.add_argument("--fill", default="#d65050",
                    help="text color (default #d65050, desaturated red)")
    ap.add_argument("--font", default=DEFAULT_FONT, help="TTF/OTF file")
    ap.add_argument("--pad", type=float, default=2,
                    help="empty margin around the ink, in px (default 2)")
    ap.add_argument("--vcenter", choices=["cap", "ink"], default="cap")
    ap.add_argument("--prefix", default="hi_",
                    help="costume file name prefix (default hi_)")
    ap.add_argument("--only", help="render just this one name")
    args = ap.parse_args()

    with open(args.greetings) as f:
        names = [ln.strip() for ln in f if ln.strip()]
    if args.only:
        names = [n for n in names if n == args.only] or [args.only]

    font = TTFont(args.font)
    os.makedirs(args.out_dir, exist_ok=True)
    for name in names:
        fname = args.prefix + re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        with open(os.path.join(args.out_dir, fname + ".svg"), "w") as f:
            f.write(name_svg(font, name, args.size, args.fill, args.pad, args.vcenter))

    print(f"wrote {len(set(names))} svg(s) to {args.out_dir}")


if __name__ == "__main__":
    main()
