"""
Convert a .obj mesh (exported from Blender, one mesh = one ordered point
set) into three plain-text files, one per axis, ready for Scratch's list
right-click -> "import" (which expects a .txt with exactly one value per
line, in list order).

Only "v x y z" lines are read; faces/normals/UVs/comments are ignored.

By default, file order is trusted as-is and preserved exactly - order the
mesh however you like in Blender (Mesh > Sort Elements, manual placement,
sorted by billboard type, whatever) and it comes through unchanged. Pass
--sort-axis to opt into an automatic depth sort instead, for cases where
you'd rather not order it by hand (e.g. a quick procedural point set).

Model separate kinds of points (e.g. a ship's fuselage-slice line vs. its
propeller hubs) as SEPARATE mesh objects in Blender, export/convert each
one separately, rather than packing both into one mesh - keeps each file's
order unambiguous instead of needing this script to guess which points are
which kind.

Usage:
    python3 obj_to_scratch_lists.py ship_hull.obj
        -> writes ship_hull_x.txt, ship_hull_y.txt, ship_hull_z.txt, in
           exactly the vertex order the .obj file has
    python3 obj_to_scratch_lists.py ship_props.obj --sort-axis x
        -> opts into auto-sort: left-to-right instead of file order

Axis fixups (Blender is Z-up; adjust once you see real numbers - defaults
below do nothing). --sort-axis runs AFTER these, i.e. against the
already-remapped coordinates:
    --scale 1.0       multiply every coordinate (e.g. Blender units -> px)
    --swap-yz         swap Y and Z after any negation below
    --negate-x / --negate-y / --negate-z
"""
import argparse
import os


def parse_obj_vertices(path):
    verts = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line.startswith("v "):
                continue
            parts = line.split()
            # "v x y z" (a trailing w is rare/ignored if present)
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            verts.append((x, y, z))
    return verts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("obj_path")
    ap.add_argument("--out-dir", default=None, help="default: alongside the input file")
    ap.add_argument("--prefix", default=None, help="default: input filename without extension")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--swap-yz", action="store_true")
    ap.add_argument("--negate-x", action="store_true")
    ap.add_argument("--negate-y", action="store_true")
    ap.add_argument("--negate-z", action="store_true")
    ap.add_argument("--sort-axis", choices=["x", "y", "z"], default=None,
                     help="opt into auto-sorting by this axis; default is to keep file order as-is")
    ap.add_argument("--reverse", action="store_true", help="reverse the sort direction")
    args = ap.parse_args()

    raw_verts = parse_obj_vertices(args.obj_path)
    if not raw_verts:
        raise SystemExit(f"no 'v x y z' lines found in {args.obj_path}")

    out_dir = args.out_dir or os.path.dirname(os.path.abspath(args.obj_path))
    prefix = args.prefix or os.path.splitext(os.path.basename(args.obj_path))[0]

    fixed = []
    for x, y, z in raw_verts:
        if args.negate_x:
            x = -x
        if args.negate_y:
            y = -y
        if args.negate_z:
            z = -z
        if args.swap_yz:
            y, z = z, y
        fixed.append((x * args.scale, y * args.scale, z * args.scale))

    if args.sort_axis is None:
        ordered = fixed
        print(f"{len(ordered)} point(s), kept in file order:")
    else:
        axis_idx = {"x": 0, "y": 1, "z": 2}[args.sort_axis]
        ordered = sorted(fixed, key=lambda v: v[axis_idx], reverse=args.reverse)
        print(f"{len(ordered)} point(s), sorted by {args.sort_axis}"
              f"{' (reversed)' if args.reverse else ''}:")
    for i, v in enumerate(ordered, 1):
        print(f"  [{i}] x={v[0]:.2f} y={v[1]:.2f} z={v[2]:.2f}")

    xs = [v[0] for v in ordered]
    ys = [v[1] for v in ordered]
    zs = [v[2] for v in ordered]

    def fmt(n):
        # trim to a sane number of decimals; Scratch just reads text
        s = f"{n:.6f}".rstrip("0").rstrip(".")
        return s if s not in ("", "-0") else "0"

    paths = {}
    for axis, values in (("x", xs), ("y", ys), ("z", zs)):
        path = os.path.join(out_dir, f"{prefix}_{axis}.txt")
        with open(path, "w") as f:
            f.write("\n".join(fmt(v) for v in values))
        paths[axis] = path

    print(f"wrote {len(ordered)} points from {args.obj_path}:")
    for axis, path in paths.items():
        print(f"  {axis}: {path}")
    print("Import each into its matching Scratch list via right-click -> import on the list monitor.")


if __name__ == "__main__":
    main()
