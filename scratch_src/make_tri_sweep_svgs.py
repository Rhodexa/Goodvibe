"""
Right-triangle sweep costumes for Scratch.

Writes N SVG costumes of a right triangle whose hypotenuse is a radius-100
spoke rotated by angle a, sampled evenly over 0..180 degrees (both ends
included):

    P0 = (0, 0)                      always, the costume's rotation center
    P1 = (100*cos a, 0)              right-angle corner, on the x axis
    P2 = (100*cos a, 100*sin a)      on the circle

    a =   0  ->  0,0  100,0     100,0     (degenerate, empty)
    a =  90  ->  0,0    0,0       0,100   (degenerate, empty)
    a = 180  ->  0,0 -100,0    -100,0     (degenerate, empty)

Coordinates above are Scratch-style (y up); the SVG flips y so the triangle
points up on stage.

Every file has a fixed 0..200 viewBox plus an invisible 200x200 rect covering
it, so the bounds never depend on the triangle. The drawing is shifted by
+100 on both axes so P0 sits at (100, 100), the image center, which is where
Scratch puts the default rotation center. (A -100..100 viewBox doesn't work:
Scratch measures the center from the viewBox origin, not from its min corner,
so it lands on the bottom-right corner instead.)

--seam W strokes the triangle in its own fill color with a W-wide round-joined
stroke, growing it by W/2 on every side so neighbouring triangles overlap
instead of leaving hairline gaps. Degenerate frames (0/90/180 deg) then show
as a thin W-wide line instead of nothing, and at 0/180 the half-stroke past
the tip is clipped by the image edge.

Costume i (1-based in Scratch) is angle 180 * (i-1) / (N-1).

Usage:
    python3 make_tri_sweep_svgs.py OUT_DIR [-n 181] [--fill #ffffff] [--seam 0]
"""

import argparse
import math
import os

R = 100


def fmt(v):
    # Round away float noise (cos 90 = 6e-15) and drop "-0".
    v = round(v, 4)
    if v == 0:
        v = 0.0
    return f"{v:g}"


def tri_svg(angle_deg, fill, seam):
    a = math.radians(angle_deg)
    x = R + R * math.cos(a)
    y = R - R * math.sin(a)  # SVG y points down
    pts = f"{R},{R} {fmt(x)},{R} {fmt(x)},{fmt(y)}"
    if seam > 0:
        stroke = (f'stroke="{fill}" stroke-width="{fmt(seam)}" '
                  f'stroke-linejoin="round" stroke-linecap="round"')
    else:
        stroke = 'stroke="none"'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        f'width="{2 * R}" height="{2 * R}" viewBox="0 0 {2 * R} {2 * R}">\n'
        f'  <rect x="0" y="0" width="{2 * R}" height="{2 * R}" '
        f'fill="#000000" fill-opacity="0" stroke="none"/>\n'
        f'  <polygon points="{pts}" fill="{fill}" {stroke}/>\n'
        f"</svg>\n"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("-n", "--count", type=int, default=181,
                    help="number of costumes over 0..180 deg (default 181 = 1 deg steps)")
    ap.add_argument("--fill", default="#ffffff")
    ap.add_argument("--seam", type=float, default=0,
                    help="same-color round-joined stroke width, in costume px (default 0 = off)")
    args = ap.parse_args()

    n = args.count
    if n < 1:
        ap.error("--count must be >= 1")

    os.makedirs(args.out_dir, exist_ok=True)
    for i in range(n):
        angle = 0.0 if n == 1 else 180.0 * i / (n - 1)
        path = os.path.join(args.out_dir, f"tri_{i + 1}.svg")
        with open(path, "w") as f:
            f.write(tri_svg(angle, args.fill, args.seam))

    step = 0 if n == 1 else 180.0 / (n - 1)
    print(f"wrote {n} costumes to {args.out_dir} ({step:g} deg/step)")


if __name__ == "__main__":
    main()
