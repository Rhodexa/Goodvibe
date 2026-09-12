#!/usr/bin/env python3
"""Extract individual non-overlapping sprites from a sprite-sheet PNG into
separate transparent PNGs - one file per sprite.

Handles the general case where sprites are laid out irregularly and their
tight bounding boxes can overlap even though the shapes themselves never
touch (e.g. a thin wisp of one sprite sitting close to its neighbor). A
plain rectangular crop would leak pixels from the neighboring sprite into
the wrong file, so this script:

  1. Labels connected components of the alpha channel above LABEL_THRESH -
     each sprite body becomes its own component. LABEL_THRESH needs to be
     high enough to see through any ambient glow/haze the source image has
     baked into the alpha channel (which can otherwise bridge two nearby
     sprites into one component).
  2. Splits components into "big" (real sprite bodies) vs "small" (detached
     decorations - e.g. raindrops under a cloud, sparkles) using an
     automatically detected size gap, then reassigns each small fragment to
     its nearest big sprite so it stays attached to the sprite it visually
     belongs to.
  3. Crops each sprite's tight bounding box (plus small padding), blanking
     out (alpha=0) any pixel in that rectangle that belongs to a *different*
     sprite - this is what makes overlapping bounding boxes safe to crop
     from.

Usage:
    python3 extract_sprites.py INPUT.png [OUTPUT_DIR] [options]

Examples:
    python3 extract_sprites.py trees.png
    python3 extract_sprites.py clouds.png clouds --label-thresh 60
    python3 extract_sprites.py icons.png icons --prefix icon --min-size 300
"""

import argparse
import os
from PIL import Image
import numpy as np
from scipy import ndimage


def find_size_gap(sizes_sorted_desc, min_candidate=150):
    """Auto-detect where "real sprite" sizes end and "small fragment"
    (decoration/noise) sizes begin, by finding the largest multiplicative
    drop between consecutive sizes in the sorted list.

    Only gaps where the larger side is >= min_candidate are considered,
    since the deep tail of tiny anti-aliasing specks (areas of just a few
    pixels) is full of huge-looking ratios (e.g. 33 -> 2) that are noise,
    not the real big/small split."""
    if len(sizes_sorted_desc) < 2:
        return 0
    candidates = [i for i in range(len(sizes_sorted_desc) - 1) if sizes_sorted_desc[i] >= min_candidate]
    if not candidates:
        candidates = list(range(len(sizes_sorted_desc) - 1))
    best_idx = max(candidates, key=lambda i: sizes_sorted_desc[i] / max(sizes_sorted_desc[i + 1], 1e-9))
    threshold = (sizes_sorted_desc[best_idx] + sizes_sorted_desc[best_idx + 1]) / 2
    return threshold


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="path to the sprite-sheet PNG (must have an alpha channel)")
    ap.add_argument("output_dir", nargs="?", default=None,
                     help="folder to write sprite files into (default: input basename, no extension)")
    ap.add_argument("--prefix", default=None,
                     help="output filename prefix, e.g. 'tree' -> tree1.png, tree2.png (default: input basename)")
    ap.add_argument("--label-thresh", type=int, default=50,
                     help="alpha threshold used to decide connectivity/grouping (default: 50). "
                          "Raise this if two visually-distinct sprites are getting merged into one file; "
                          "lower it if a single sprite is getting split into pieces.")
    ap.add_argument("--min-size", type=int, default=None,
                     help="pixel-area threshold separating real sprites from small detached "
                          "decorations/noise (default: auto-detected from the size distribution)")
    ap.add_argument("--padding", type=int, default=4, help="transparent pixels of padding around each crop (default: 4)")
    args = ap.parse_args()

    output_dir = args.output_dir or os.path.splitext(os.path.basename(args.input))[0]
    prefix = args.prefix or os.path.splitext(os.path.basename(args.input))[0]

    im = Image.open(args.input).convert("RGBA")
    arr = np.array(im)
    alpha = arr[:, :, 3]
    h, w = alpha.shape

    mask = alpha > args.label_thresh
    lbl, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        raise SystemExit("No non-transparent pixels found - check --label-thresh.")
    sizes = ndimage.sum(mask, lbl, range(1, n + 1))

    if args.min_size is not None:
        min_size = args.min_size
    else:
        min_size = find_size_gap(sorted(sizes, reverse=True))
        print(f"auto-detected --min-size {min_size:.0f} (pass --min-size to override)")

    big_ids = [i + 1 for i, s in enumerate(sizes) if s >= min_size]
    if not big_ids:
        raise SystemExit("No sprite-sized components found - check --label-thresh/--min-size.")

    big_mask = np.isin(lbl, big_ids)
    big_label_grid = np.where(big_mask, lbl, 0)

    # Nearest big-component label for every pixel (a Voronoi fill), applied
    # only to small disconnected fragments so they attach to the sprite they
    # visually belong to. Deliberately NOT applied to background/haze
    # pixels, which would otherwise balloon each sprite's territory across
    # the whole canvas.
    _, (iy, ix) = ndimage.distance_transform_edt(~big_mask, return_indices=True)
    nearest_big_label = big_label_grid[iy, ix]

    group_id = np.zeros_like(lbl)
    group_id[big_mask] = lbl[big_mask]
    small_mask = mask & ~big_mask
    group_id[small_mask] = nearest_big_label[small_mask]

    boxes = {}
    for gid in big_ids:
        ys, xs = np.where(group_id == gid)
        x0, x1 = xs.min(), xs.max() + 1
        y0, y1 = ys.min(), ys.max() + 1
        boxes[gid] = (x0, y0, x1, y1)

    # sort into reading order: row-major (top-to-bottom, left-to-right).
    # Row grouping tolerance adapts to sprite size instead of assuming a
    # fixed image layout.
    heights = [b[3] - b[1] for b in boxes.values()]
    row_span = max(1.0, float(np.median(heights)) * 0.6)

    items = list(boxes.items())
    items.sort(key=lambda kv: (kv[1][1] + kv[1][3]) / 2)
    row_groups = []
    for gid, box in items:
        cy = (box[1] + box[3]) / 2
        placed = False
        for group in row_groups:
            gcy = sum((b[1] + b[3]) / 2 for _, b in group) / len(group)
            if abs(cy - gcy) < row_span:
                group.append((gid, box))
                placed = True
                break
        if not placed:
            row_groups.append([(gid, box)])
    row_groups.sort(key=lambda g: sum((b[1] + b[3]) / 2 for _, b in g) / len(g))
    ordered = []
    for group in row_groups:
        group.sort(key=lambda kv: kv[1][0])
        ordered.extend(group)

    os.makedirs(output_dir, exist_ok=True)
    for idx, (gid, (x0, y0, x1, y1)) in enumerate(ordered, start=1):
        px0 = max(0, x0 - args.padding)
        py0 = max(0, y0 - args.padding)
        px1 = min(w, x1 + args.padding)
        py1 = min(h, y1 + args.padding)

        crop = arr[py0:py1, px0:px1].copy()
        crop_group = group_id[py0:py1, px0:px1]
        crop[crop_group != gid] = 0  # blank out pixels belonging to another sprite

        out_path = os.path.join(output_dir, f"{prefix}{idx}.png")
        Image.fromarray(crop, mode="RGBA").save(out_path)
        print(f"saved {out_path}  ({px1 - px0}x{py1 - py0})")

    print(f"\n{len(ordered)} sprites written to '{output_dir}/'")


if __name__ == "__main__":
    main()
