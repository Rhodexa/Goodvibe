#!/usr/bin/env python3
"""Extract individual tree sprites from trees.png into separate transparent PNGs."""

import os
import sys
from PIL import Image
import numpy as np
from scipy import ndimage

SRC = "trees.png"
OUT_DIR = "trees"
ALPHA_THRESH = 30      # ignore near-zero anti-aliasing noise when finding blobs
MIN_COMPONENT_SIZE = 100  # drop stray noise specks, keep real tree silhouettes
PADDING = 4            # extra transparent pixels around each cropped tree


def main():
    im = Image.open(SRC).convert("RGBA")
    arr = np.array(im)
    alpha = arr[:, :, 3]
    h, w = alpha.shape

    mask = alpha > ALPHA_THRESH
    labels, n = ndimage.label(mask)
    sizes = ndimage.sum(mask, labels, range(1, n + 1))
    keep = [i + 1 for i, s in enumerate(sizes) if s > MIN_COMPONENT_SIZE]

    objects = ndimage.find_objects(labels)
    boxes = []
    for i in keep:
        sl = objects[i - 1]
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        boxes.append((x0, y0, x1, y1))

    if not boxes:
        sys.exit("No tree components found - check ALPHA_THRESH/MIN_COMPONENT_SIZE.")

    # sort into reading order: row-major (top-to-bottom, left-to-right),
    # grouping into rows by vertical center
    boxes.sort(key=lambda b: (b[1] + b[3]) / 2)
    row_groups = []
    row_span = h / 4  # loose bucket, just needs to separate the 3 rows
    for b in boxes:
        placed = False
        cy = (b[1] + b[3]) / 2
        for group in row_groups:
            gcy = sum((gb[1] + gb[3]) / 2 for gb in group) / len(group)
            if abs(cy - gcy) < row_span:
                group.append(b)
                placed = True
                break
        if not placed:
            row_groups.append([b])
    row_groups.sort(key=lambda g: sum((b[1] + b[3]) / 2 for b in g) / len(g))
    ordered = []
    for group in row_groups:
        group.sort(key=lambda b: b[0])
        ordered.extend(group)

    os.makedirs(OUT_DIR, exist_ok=True)
    for idx, (x0, y0, x1, y1) in enumerate(ordered, start=1):
        px0 = max(0, x0 - PADDING)
        py0 = max(0, y0 - PADDING)
        px1 = min(w, x1 + PADDING)
        py1 = min(h, y1 + PADDING)
        crop = im.crop((px0, py0, px1, py1))
        out_path = os.path.join(OUT_DIR, f"tree{idx}.png")
        crop.save(out_path)
        print(f"saved {out_path}  ({px1 - px0}x{py1 - py0})")

    print(f"\n{len(ordered)} trees written to '{OUT_DIR}/'")


if __name__ == "__main__":
    main()
