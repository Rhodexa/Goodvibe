"""
Combine a .obj mesh (point positions) and a sprites.txt (one costume name
per line, same order/count as the mesh's vertices) into ONE flat list:
names, then all x, then all y, then all z - one list = one object, matching
the ship's on-disk identity rather than scattering it across files.

File order is trusted as-is (no auto-sorting) for both inputs - order the
mesh and the sprite list by hand so they agree; this script's only job
after that is to verify they actually DO agree in length and combine them,
not to guess whether they line up.

Output is one plain-text file, N*4 lines: 1..N = names (text), N+1..2N = x,
2N+1..3N = y, 3N+1..4N = z. Import it into ONE Scratch list via right-click
-> import. The unpack block on the Scratch side reads:
    N = (length of the list) / 4
    name(i)     = item i           of the list
    x(i)        = item N + i       of the list
    y(i)        = item 2*N + i     of the list
    z(i)        = item 3*N + i     of the list

Usage:
    python3 combine_ship_list.py ship.obj sprites.txt
        -> writes ship_data.txt next to ship.obj

Axis fixups (Blender is Z-up; adjust once you see real numbers):
    --scale 1.0       multiply every coordinate (e.g. Blender units -> px)
    --swap-yz         swap Y and Z after any negation below
    --negate-x / --negate-y / --negate-z
"""
import argparse
import os

from obj_to_scratch_lists import parse_obj_vertices


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("obj_path")
    ap.add_argument("sprites_path")
    ap.add_argument("--out", default=None, help="default: <obj name>_data.txt next to the obj")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--swap-yz", action="store_true")
    ap.add_argument("--negate-x", action="store_true")
    ap.add_argument("--negate-y", action="store_true")
    ap.add_argument("--negate-z", action="store_true")
    args = ap.parse_args()

    verts = parse_obj_vertices(args.obj_path)
    with open(args.sprites_path) as f:
        names = [ln.strip() for ln in f if ln.strip()]

    if len(names) != len(verts):
        raise SystemExit(
            f"count mismatch: {len(names)} sprite name(s) in {args.sprites_path} "
            f"vs {len(verts)} vertex/vertices in {args.obj_path} - fix one of them "
            f"before combining, a silent mismatch would pair the wrong costume with "
            f"the wrong 3D point."
        )
    n = len(verts)

    fixed = []
    for x, y, z in verts:
        if args.negate_x:
            x = -x
        if args.negate_y:
            y = -y
        if args.negate_z:
            z = -z
        if args.swap_yz:
            y, z = z, y
        fixed.append((x * args.scale, y * args.scale, z * args.scale))

    def fmt(v):
        s = f"{v:.6f}".rstrip("0").rstrip(".")
        return s if s not in ("", "-0") else "0"

    lines = list(names)
    lines += [fmt(v[0]) for v in fixed]
    lines += [fmt(v[1]) for v in fixed]
    lines += [fmt(v[2]) for v in fixed]

    out_path = args.out or os.path.join(
        os.path.dirname(os.path.abspath(args.obj_path)),
        os.path.splitext(os.path.basename(args.obj_path))[0] + "_data.txt",
    )
    with open(out_path, "w") as f:
        f.write("\n".join(lines))

    print(f"N = {n} points, wrote {len(lines)} lines to {out_path}")
    print(f"  names: [1..{n}]")
    print(f"  x:     [{n + 1}..{2 * n}]")
    print(f"  y:     [{2 * n + 1}..{3 * n}]")
    print(f"  z:     [{3 * n + 1}..{4 * n}]")
    print("Import this one file into a single Scratch list (right-click -> import).")
    print("Sanity check:")
    for i, (name, v) in enumerate(zip(names, fixed), 1):
        print(f"  [{i}] {name:10s} x={v[0]:.3f} y={v[1]:.3f} z={v[2]:.3f}")


if __name__ == "__main__":
    main()
