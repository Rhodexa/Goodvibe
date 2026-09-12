#!/usr/bin/env python3
"""Extract individual cloud sprites from clouds.png into separate transparent PNGs.

Unlike a regular grid of non-overlapping bounding boxes (see extract_trees.py),
these clouds are laid out irregularly: two clouds can sit close enough that
their tight bounding boxes overlap even though the shapes themselves never
touch. A plain rectangular crop would therefore leak pixels of a neighboring
cloud into the wrong file.

Approach:
  1. Label connected components of the alpha channel - each real cloud body
     is its own component.
  2. Small components (raindrops, snowflakes, sparkles, thin wisps that are
     disconnected from their parent cloud by a few transparent pixels) are
     reassigned to whichever big cloud is nearest, so they stay attached to
     the sprite they visually belong to.
  3. For each big cloud, crop its bounding box, but blank out (alpha=0) any
     pixel in that rectangle that was assigned to a *different* cloud - this
     is what makes overlapping bounding boxes safe to crop from.
"""

import os
from PIL import Image
import numpy as np
from scipy import ndimage

SRC = "clouds.png"
OUT_DIR = "clouds"
# clouds.png carries a soft ambient haze in the alpha channel that covers
# most of the canvas at low values (>50% of pixels have alpha <= 30), so a
# low threshold would Voronoi-fill the whole image when attaching small
# fragments to their parent cloud. LABEL_THRESH must clear that haze.
LABEL_THRESH = 60       # alpha threshold for connectivity/grouping decisions
BIG_MIN_SIZE = 1200      # components at/above this size (at LABEL_THRESH) are real cloud bodies
PADDING = 4              # extra transparent pixels around each cropped cloud


def main():
    im = Image.open(SRC).convert("RGBA")
    arr = np.array(im)
    alpha = arr[:, :, 3]
    h, w = alpha.shape

    mask = alpha > LABEL_THRESH
    lbl, n = ndimage.label(mask, structure=np.ones((3, 3)))
    sizes = ndimage.sum(mask, lbl, range(1, n + 1))

    big_ids = [i + 1 for i, s in enumerate(sizes) if s >= BIG_MIN_SIZE]
    if not big_ids:
        raise SystemExit("No cloud-sized components found - check LABEL_THRESH/BIG_MIN_SIZE.")

    big_mask = np.isin(lbl, big_ids)
    big_label_grid = np.where(big_mask, lbl, 0)

    # Find the nearest big-component label for every pixel (a Voronoi fill),
    # but only apply it to small disconnected fragments (rain, snow,
    # sparkles) so they attach to the cloud they visually belong to. This is
    # deliberately NOT applied to background/haze pixels, which would
    # otherwise balloon each cloud's assigned territory across the whole
    # canvas.
    _, (iy, ix) = ndimage.distance_transform_edt(~big_mask, return_indices=True)
    nearest_big_label = big_label_grid[iy, ix]

    group_id = np.zeros_like(lbl)
    group_id[big_mask] = lbl[big_mask]
    small_mask = mask & ~big_mask
    group_id[small_mask] = nearest_big_label[small_mask]

    objects = ndimage.find_objects(lbl)
    boxes = {}
    for gid in big_ids:
        ys, xs = np.where(group_id == gid)
        x0, x1 = xs.min(), xs.max() + 1
        y0, y1 = ys.min(), ys.max() + 1
        boxes[gid] = (x0, y0, x1, y1)

    # sort into reading order: row-major (top-to-bottom, left-to-right)
    items = list(boxes.items())
    items.sort(key=lambda kv: (kv[1][1] + kv[1][3]) / 2)
    row_span = h / 6  # loose bucket to separate visually distinct rows
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

    os.makedirs(OUT_DIR, exist_ok=True)
    for idx, (gid, (x0, y0, x1, y1)) in enumerate(ordered, start=1):
        px0 = max(0, x0 - PADDING)
        py0 = max(0, y0 - PADDING)
        px1 = min(w, x1 + PADDING)
        py1 = min(h, y1 + PADDING)

        crop = arr[py0:py1, px0:px1].copy()
        crop_group = group_id[py0:py1, px0:px1]
        # blank out any pixel in this rectangle that belongs to another cloud
        crop[crop_group != gid] = 0

        out_path = os.path.join(OUT_DIR, f"cloud{idx}.png")
        Image.fromarray(crop, mode="RGBA").save(out_path)
        print(f"saved {out_path}  ({px1 - px0}x{py1 - py0})")

    print(f"\n{len(ordered)} clouds written to '{OUT_DIR}/'")


if __name__ == "__main__":
    main()
