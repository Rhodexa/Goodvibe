"""Split starfield/universe*.png (2172x724 strips) into 960x720 parallax layer pairs.

Each alpha layer's objects (galaxies, stars, clusters) are extracted as connected
blobs of alpha and scattered at random across two tiles: whole objects only, and
x wraps around so each tile loops seamlessly. y is kept, so objects cut by the
source's top/bottom edge stay flush to that edge. Blobs that the alpha haze
merged into one huge cluster get split at their bright cores, with feathered
alpha at the cut. Objects cut by the source's left/right edge get their cut side
faded out.

The opaque backdrop (universe1) has no alpha to split on, so it's just cut into
two halves.

960x720 = 480x360 stage units at Scratch's bitmap resolution 2.
Usage: python3 split_layers.py [seed]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

SRC = Path(__file__).resolve().parents[2] / "starfield"
OUT = Path(__file__).resolve().parent / "layers"
W, H = 960, 720
ALPHA_THR = 6      # alpha above this seeds an object
MERGE_PX = 6       # dilation so a galaxy's speckled halo stays one object
TRIES = 200        # random x candidates per object; keep the least overlapping
MAX_OBJ_W = 320    # blobs wider than this (haze-merged clusters) get split up...
CORE_THR = 128     # ...at their bright cores,
CORE_OPEN = 4      # ignoring thin star spikes when finding cores,
FEATHER = 10       # with a soft alpha blend this wide across each cut
EDGE_FADE = 48     # fade width for objects the source cut at its left/right edge


def soft_split(a, blob):
    """Split one oversized blob at its bright cores. Returns [(slice, weight)] whose
    weights sum to 1 over the blob, blending across ~FEATHER px at each cut."""
    core = ndimage.binary_opening(a > CORE_THR, iterations=CORE_OPEN) & blob
    seeds, n = ndimage.label(core)
    if n < 2:
        return None
    d = np.stack([ndimage.distance_transform_edt(seeds != i) for i in range(1, n + 1)])
    wts = np.exp(-(d - d.min(0)) / FEATHER) * blob
    wts /= wts.sum(0) + 1e-9
    return list(wts)


def extract_objects(rgba):
    a = rgba[..., 3].astype(np.float32)
    h, w = a.shape
    grown = ndimage.binary_dilation(a > ALPHA_THR, iterations=MERGE_PX)
    labels, _ = ndimage.label(grown)
    # hand every faint leftover pixel to its nearest object so soft edges survive
    _, (iy, ix) = ndimage.distance_transform_edt(labels == 0, return_indices=True)
    labels = np.where(a > 0, labels[iy, ix], 0)

    pieces = []  # (bbox slice, alpha weight within bbox)
    for i, sl in enumerate(ndimage.find_objects(labels), 1):
        if sl is None:
            continue
        blob = labels[sl] == i
        bh, bw = blob.shape
        parts = soft_split(a[sl], blob) if bw > MAX_OBJ_W or bh > H else None
        for wt in parts or [blob.astype(np.float32)]:
            ys, xs = np.nonzero(wt * a[sl] >= 1)
            if len(xs):
                sub = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
                pieces.append(((slice(sl[0].start + sub[0].start, sl[0].start + sub[0].stop),
                                slice(sl[1].start + sub[1].start, sl[1].start + sub[1].stop)),
                               wt[sub]))

    objs = []
    for sl, wt in pieces:
        crop = rgba[sl].copy()
        alpha = crop[..., 3] * wt
        # the source cut this object at its left/right edge: fade the cut instead
        ramp = np.minimum(1, (np.arange(crop.shape[1]) + 1) / EDGE_FADE)
        if sl[1].start == 0:
            alpha *= ramp
        if sl[1].stop == w:
            alpha *= ramp[::-1]
        crop[..., 3] = np.round(alpha).astype(np.uint8)
        if crop.shape[1] > W:
            print(f"  warning: {crop.shape[1]}px-wide object doesn't fit, dropped")
            continue
        objs.append({"img": crop, "y": sl[0].start - (h - H) // 2,
                     "mass": int(crop[..., 3].astype(np.int64).sum())})
    return objs


def place(tiles_alpha, obj, rng):
    """Pick the x (with wraparound) where obj overlaps least with what's there."""
    img = obj["img"]
    oh, ow = img.shape[:2]
    y0 = max(0, min(obj["y"], H - oh))
    obj["y"] = y0
    oa = img[..., 3].astype(np.float32)
    band = tiles_alpha[y0:y0 + oh]
    best, best_x = None, 0
    for x in rng.integers(0, W, TRIES):
        cols = (np.arange(ow) + x) % W
        cost = float((band[:, cols] * oa).sum())
        if best is None or cost < best:
            best, best_x = cost, int(x)
            if cost == 0:
                break
    return best_x


def composite(tile, alpha_acc, obj, x):
    img = Image.fromarray(obj["img"], "RGBA")
    ow = obj["img"].shape[1]
    for dx in (x, x - W):  # second paste covers the wrapped part
        if dx + ow > 0 and dx < W:
            tile.alpha_composite(img, (max(dx, 0), obj["y"]),
                                 (max(-dx, 0), 0, ow, img.height))
    cols = (np.arange(ow) + x) % W
    alpha_acc[obj["y"]:obj["y"] + img.height, cols] += obj["img"][..., 3] / 255.0


def split_alpha(rgba, rng):
    objs = extract_objects(rgba)
    objs.sort(key=lambda o: -o["mass"])  # big ones first, while there's room
    tiles = [Image.new("RGBA", (W, H)) for _ in range(2)]
    accs = [np.zeros((H, W), np.float32) for _ in range(2)]
    masses = [0, 0]
    for o in objs:
        # coin flip, biased toward the emptier tile to keep both balanced
        lo = int(masses[1] < masses[0])
        k = lo if rng.random() < 0.75 else 1 - lo
        x = place(accs[k], o, rng)
        composite(tiles[k], accs[k], o, x)
        masses[k] += o["mass"]
    return tiles, len(objs)


def split_opaque(rgb):
    h, w = rgb.shape[:2]
    y = (h - H) // 2
    half = w // 2
    out = []
    for x0 in (0, half):
        x = x0 + (half - W) // 2
        out.append(Image.fromarray(rgb[y:y + H, x:x + W]).convert("RGBA"))
    return out


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    rng = np.random.default_rng(seed)
    OUT.mkdir(exist_ok=True)
    srcs = sorted(SRC.glob("universe*.png"), key=lambda p: int(p.stem[8:]))
    n = 1
    for p in srcs:
        im = Image.open(p)
        if im.mode == "RGBA":
            tiles, count = split_alpha(np.array(im), rng)
            note = f"{count} objects"
        else:
            tiles = split_opaque(np.array(im.convert("RGB")))
            note = "opaque, cut in half"
        for t in tiles:
            t.save(OUT / f"universe{n}.png")
            n += 1
        print(f"{p.name} -> universe{n - 2}, universe{n - 1} ({note})")


if __name__ == "__main__":
    main()
