#!/usr/bin/env python3
"""Create a resized copy of a folder of sprite PNGs.

Usage:
    python3 resize_sprites.py INPUT_DIR [OUTPUT_DIR] [--scale 0.5]

Examples:
    python3 resize_sprites.py trees                  # -> trees_50pct/, half size
    python3 resize_sprites.py trees trees_small       # explicit output folder
    python3 resize_sprites.py clouds --scale 0.25     # -> clouds_25pct/, quarter size
"""

import argparse
import os
from PIL import Image


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_dir", help="folder of sprite PNGs to resize")
    ap.add_argument("output_dir", nargs="?", default=None,
                     help="folder to write resized copies into (default: '<input_dir>_<N>pct')")
    ap.add_argument("--scale", type=float, default=0.5, help="scale factor, e.g. 0.5 for half size (default: 0.5)")
    args = ap.parse_args()

    if args.scale <= 0:
        raise SystemExit("--scale must be positive")

    output_dir = args.output_dir or f"{args.input_dir.rstrip('/')}_{round(args.scale * 100)}pct"
    os.makedirs(output_dir, exist_ok=True)

    count = 0
    for fname in sorted(os.listdir(args.input_dir)):
        if not fname.lower().endswith(".png"):
            continue
        im = Image.open(os.path.join(args.input_dir, fname))
        new_size = (max(1, round(im.width * args.scale)), max(1, round(im.height * args.scale)))
        resized = im.resize(new_size, Image.LANCZOS)
        resized.save(os.path.join(output_dir, fname))
        print(f"{fname}: {im.size} -> {resized.size}")
        count += 1

    if count == 0:
        raise SystemExit(f"No PNG files found in '{args.input_dir}'")
    print(f"\n{count} sprites written to '{output_dir}/'")


if __name__ == "__main__":
    main()
