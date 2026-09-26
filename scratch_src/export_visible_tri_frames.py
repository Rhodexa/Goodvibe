"""
Blender -> ST-NICCC-style "visible triangle" animation for Scratch.

Runs INSIDE Blender. For every frame of the scene's animation it projects all
renderable meshes through the scene camera onto the 480x360 Scratch stage,
throws away everything that can't be seen, and writes what's left as a list
of flat-colored 2D triangles in back-to-front order - so a plain triangle
filler can paint each frame with the painter's algorithm, no depth logic at
runtime.

Four plain-text files come out, one value per line (Scratch list right-click
-> "import"):

    <prefix>_vertices.txt      x, y pairs - shared by ALL frames (a vertex that
                               sits still is stored once). Vertex n = items
                               2n-1, 2n.
    <prefix>_faces.txt         one geometry record per face, see --format.
    <prefix>_face_colors.txt   hue, brightness, ghost per face, parallel to the
                               faces list: face n = items 3n-2 .. 3n.
    <prefix>_frames.txt        first face, face count - per frame (frame f =
                               items 2f-1, 2f). Faces within a frame are in draw
                               order: first = farthest back, last = frontmost.

Face records (--format):
    faces   (default) v1, v2, v3 - face n = items 3n-2 .. 3n
            for the generic TriangleRenderer - drawTriangle, which works the
            longest edge / costume / size out itself. Wound the way it expects:
            (x1-x0)*(y2-y0) - (y1-y0)*(x2-x0) < 0.
    stamps  base1, base2, direction, costume1, size1, costume2, size2
            - face n = items 7n-6 .. 7n
            the same filler's math already done: point in direction, go to
            vertex base1, costume (tri_1 + costume1), size size1, stamp; go to
            vertex base2, costume (tri_1 + costume2), size size2, stamp.

  - x/y are integer Scratch stage coordinates (-240..240, -180..180), already
    clipped to the stage, so no vertex ever gets fenced.
  - costume1/costume2 are 0-based offsets from the tri_1 costume.

Color = Scratch effects on the red half-tri costumes, solved exactly against
the Scratch 3 sprite shader (hue rotate, then brightness added and clamped):
    hue         color effect
    brightness  brightness effect (> 0 desaturates toward white, < 0 darkens)
    ghost       ghost of the black overlay stamp (brightness -100) that
                scales the color down; 100 = invisible = skip the overlay.
Colors whose brightest channel is ~100% or darkest is ~0% need one stamp
(ghost 100); anything else needs the overlay. Per half-tri: color stamp,
then its overlay, THEN the next half - never both colors then both overlays.

How visibility works: every triangle (after near-plane + stage clipping and
backface culling) is rasterized into a 480x360 ID/z-buffer. Triangles that
own no pixel are dropped. Draw order is then read off that same buffer: if
triangle A covers a pixel that B wins, A must be drawn before B; a
topological sort of those constraints gives an order whose painter's result
matches the z-buffer. Interpenetrating faces (A in front of B in some
pixels, behind it in others) have no valid order, so they get split along
each other's plane and the pass is redone; any leftover cycles are broken
using depth.

Colors (--color):
    render    (default) render each frame with the scene's engine and average
              the pixels each face owns - picks up lighting and textures.
              Only "interior" pixels are sampled (all 4 neighbours belong to
              the same face) to avoid anti-aliased edge bleed. The view
              transform is forced to Standard so flat colors come out as
              picked, unless --keep-view-transform.
    material  unlit flat Base Color / Color of the face's material (or its
              viewport display color); no render needed, much faster.

The scene's output resolution is set to 480x360 for the export (nothing is
saved back to the .blend) - set it in your file too so the camera frame you
see in Blender matches what gets exported.

For seamless loops, end the frame range one frame BEFORE the pose repeats.

Usage, from the UI: Edit > Preferences > Add-ons > Install from Disk, pick
this file; the "Scratch Tri Frames" panel shows up in Output Properties and
its settings are saved in the .blend. (Or open it in the Text Editor and Run
Script to register it for this session only.)

Usage, headless:
    blender -b anim.blend -P scratch_src/export_visible_tri_frames.py -- \\
        --prefix spinner --out-dir anim_out --preview-dir anim_out/preview

Options (after the "--"):
    --prefix NAME          default: the .blend's filename
    --out-dir DIR          default: next to the .blend
    --frames A-B           default: the scene's frame range
    --color render|material
    --min-pixels N         drop faces owning fewer than N pixels (default 1)
    --double-sided         keep back faces (draws the far side of open meshes)
    --keep-view-transform  don't force the Standard view transform
    --format faces|stamps
    --preview-dir DIR      also write a PNG per frame, painted from the
                           exported data the way the Scratch filler does it:
                           1-degree stroked half-tri costumes, effect colors
"""
import argparse
import colorsys
import heapq
import math
import os
import sys
import tempfile
from types import SimpleNamespace

import bpy
import numpy as np

STAGE_WIDTH = 480
STAGE_HEIGHT = 360
MAX_SPLIT_PASSES = 4
DEPTH_EPSILON = 1e-9    # NDC z difference below this is a tie (shared edges), not an occlusion
HALF_TRI_COSTUME_STEP = 1             # degrees between tri_1 .. tri_181
HALF_TRI_STROKE = 4                   # costume units; round-joined outline that closes seams
EFFECT_SNAP = 0.02                    # channel within this of 0 / 1 counts as 0 / 1 (skips the overlay)
MESHLIKE_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}

# homogeneous clip-space planes, inside when dot(plane, v) >= 0:
# near (z >= -w), left, right, bottom, top. No far plane.
CLIP_PLANES = np.array([
    [0, 0, 1, 1],
    [1, 0, 0, 1],
    [-1, 0, 0, 1],
    [0, 1, 0, 1],
    [0, -1, 0, 1],
], dtype=np.float64)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="export_visible_tri_frames.py")
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--frames", default=None, help="A-B, inclusive")
    ap.add_argument("--color", choices=["render", "material"], default="render")
    ap.add_argument("--min-pixels", type=int, default=1)
    ap.add_argument("--double-sided", action="store_true")
    ap.add_argument("--keep-view-transform", action="store_true")
    ap.add_argument("--format", choices=["faces", "stamps"], default="faces")
    ap.add_argument("--preview-dir", default=None)
    return ap.parse_args(argv)


# ---------------------------------------------------------------- colors

def linear_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def material_flat_color(mat):
    """Linear RGB of a material's unlinked Base Color / Color input, falling
    back to its viewport display color."""
    if mat is None:
        return (0.8, 0.8, 0.8)
    if mat.node_tree is not None:
        output = next((n for n in mat.node_tree.nodes
                       if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
        if output is not None and output.inputs["Surface"].is_linked:
            shader = output.inputs["Surface"].links[0].from_node
            for name in ("Base Color", "Color"):
                socket = shader.inputs.get(name)
                if socket is not None and not socket.is_linked:
                    return tuple(socket.default_value[:3])
    return tuple(mat.diffuse_color[:3])


def rgb_to_effects(rgb):
    """sRGB 0..1 -> (hue, brightness, ghost) for the red costume + black overlay.
    The shader turns the red into a pure hue P (max 1, min 0, mid m), then adds
    brightness b to every channel and clamps - so max/min land exactly and the
    mid channel is solved for: m = target_mid - b."""
    rgb = np.clip(np.asarray(rgb, dtype=np.float64), 0.0, 1.0)
    hi, lo = rgb.max(), rgb.min()
    ghost = 100.0
    if hi <= EFFECT_SNAP:
        return 0.0, -100.0, ghost
    if hi >= 1 - EFFECT_SNAP:
        rgb = rgb / hi
        brightness = rgb.min()                        # lift toward white
    elif lo <= EFFECT_SNAP:
        brightness = hi - 1                           # pull down toward black
    else:
        ghost = hi * 100                              # overlay scales it down
        rgb = rgb / hi
        brightness = rgb.min()
    low, mid, high = np.argsort(rgb, kind="stable")
    pure = np.zeros(3)
    pure[high] = 1.0
    pure[mid] = np.clip(rgb[mid] - brightness, 0.0, 1.0)
    hue = colorsys.rgb_to_hsv(*pure)[0]
    return hue * 200, brightness * 100, ghost


def effects_to_rgb(hue, brightness, ghost):
    """What the Scratch shader + overlay actually paint (for previews)."""
    pure = np.array(colorsys.hsv_to_rgb((hue / 200) % 1.0, 1.0, 1.0))
    return np.clip(pure + brightness / 100, 0.0, 1.0) * (ghost / 100)


def fmt(n):
    s = f"{n:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


# ---------------------------------------------------------------- half-tri filler

def scratch_atan2(y, x):
    """Math::atan2 from the filler: Scratch direction of the vector (x, y)."""
    if y > 0:
        return math.degrees(math.atan(x / y))
    if y < 0:
        return math.degrees(math.atan(x / y)) + 180
    return 90 if x > 0 else -90


def half_tri_stamps(p0, p1, p2):
    """TriangleRenderer - drawTriangle (longest-edge tree) + its Raster child,
    for a triangle already in the filler's winding. Returns (base1, base2,
    direction, costume1, size1, costume2, size2) with base1/base2 as indices
    into (p0, p1, p2) and 0-based costume offsets."""
    def dist2(a, b):
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
    p = (p0, p1, p2)
    ab, bc, ca = dist2(p0, p1), dist2(p1, p2), dist2(p2, p0)
    if ab > bc:
        apex, b1, b2 = (2, 0, 1) if ab > ca else (1, 2, 0)
    else:
        apex, b1, b2 = (0, 1, 2) if bc > ca else (1, 2, 0)
    (x0, y0), (x1, y1), (x2, y2) = p[apex], p[b1], p[b2]
    direction = scratch_atan2(y1 - y2, x1 - x2)
    costume1 = math.ceil(((direction - scratch_atan2(y0 - y1, x0 - x1)) % 360) / HALF_TRI_COSTUME_STEP)
    costume2 = math.floor(((direction - scratch_atan2(y0 - y2, x0 - x2)) % 360) / HALF_TRI_COSTUME_STEP)
    size1 = math.sqrt(dist2(p[apex], p[b1]))
    size2 = math.sqrt(dist2(p[apex], p[b2]))
    return b1, b2, direction, costume1, size1, costume2, size2


def half_tri_shape(pivot, direction, costume, size):
    """Stage-space corners of costume tri_(costume+1) stamped at pivot: a right
    triangle whose hypotenuse (100 px at size 100) sits `costume` steps
    counter-clockwise from the pointing direction, right angle on that line."""
    angle = math.radians(costume * HALF_TRI_COSTUME_STEP)
    d = math.radians(direction)
    forward = np.array([math.sin(d), math.cos(d)])
    side = np.array([-forward[1], forward[0]])
    foot = np.asarray(pivot, dtype=np.float64) + forward * size * math.cos(angle)
    return np.array([pivot, foot, foot + side * size * math.sin(angle)], dtype=np.float64)


# ---------------------------------------------------------------- geometry

def gather_frame_triangles(depsgraph, view_proj):
    """All renderable triangles in homogeneous clip space.
    Returns (tris (N,3,4), material sRGB colors (N,3))."""
    all_tris = []
    all_colors = []
    for inst in depsgraph.object_instances:
        ob = inst.object
        if ob.type not in MESHLIKE_TYPES or ob.original.hide_render:
            continue
        mesh = ob.to_mesh()
        if mesh is None:
            continue
        mesh.calc_loop_triangles()
        vert_count = len(mesh.vertices)
        tri_count = len(mesh.loop_triangles)
        if tri_count:
            co = np.empty(vert_count * 3, dtype=np.float32)
            mesh.vertices.foreach_get("co", co)
            tri_verts = np.empty(tri_count * 3, dtype=np.int32)
            mesh.loop_triangles.foreach_get("vertices", tri_verts)
            tri_mats = np.empty(tri_count, dtype=np.int32)
            mesh.loop_triangles.foreach_get("material_index", tri_mats)

            to_clip = np.array(view_proj @ inst.matrix_world, dtype=np.float64)
            co_h = np.c_[co.reshape(-1, 3), np.ones(vert_count)] @ to_clip.T
            all_tris.append(co_h[tri_verts.reshape(-1, 3)])

            slot_colors = [material_flat_color(slot.material) for slot in ob.material_slots]
            slot_colors = linear_to_srgb(slot_colors or [(0.8, 0.8, 0.8)])
            all_colors.append(slot_colors[np.clip(tri_mats, 0, len(slot_colors) - 1)])
        ob.to_mesh_clear()

    if not all_tris:
        return np.zeros((0, 3, 4)), np.zeros((0, 3))
    return np.concatenate(all_tris), np.concatenate(all_colors)


def clip_polygon(poly, planes=CLIP_PLANES):
    """Sutherland-Hodgman, poly = list of homogeneous 4-vectors."""
    for plane in planes:
        if not poly:
            break
        clipped = []
        for i, a in enumerate(poly):
            b = poly[(i + 1) % len(poly)]
            da, db = a @ plane, b @ plane
            if da >= 0:
                clipped.append(a)
            if (da >= 0) != (db >= 0):
                clipped.append(a + (b - a) * (da / (da - db)))
        poly = clipped
    return poly


def clip_triangles(tris):
    """Clip to near plane + stage. Returns (pieces (M,3,4), source index (M,))."""
    dist = tris @ CLIP_PLANES.T                       # (N, 3 verts, 5 planes)
    fully_inside = (dist >= 0).all(axis=(1, 2))
    fully_outside = (dist < 0).all(axis=1).any(axis=1)

    pieces = [tris[fully_inside]]
    sources = [np.nonzero(fully_inside)[0]]
    for t in np.nonzero(~fully_inside & ~fully_outside)[0]:
        poly = clip_polygon(list(tris[t]))
        for i in range(1, len(poly) - 1):             # fan
            pieces.append(np.array([[poly[0], poly[i], poly[i + 1]]]))
            sources.append(np.array([t]))
    return np.concatenate(pieces), np.concatenate(sources)


def split_by_plane(tri, plane):
    """Split a clip-space triangle (3,4) along a clip-space plane. Returns the
    pieces (K,3,4), or None if the triangle lies on one side of it."""
    plane = plane / np.linalg.norm(plane)
    dist = tri @ plane
    eps = 1e-9 * np.abs(tri).max()
    if (dist >= -eps).all() or (dist <= eps).all():
        return None
    pieces = []
    for side in (plane, -plane):
        poly = clip_polygon(list(tri), [side])
        pieces += [[poly[0], poly[i], poly[i + 1]] for i in range(1, len(poly) - 1)]
    return np.array(pieces)


def split_interpenetrating(tris, sources, pairs):
    """Split one face of each mutually-occluding pair along the other's plane
    (a plane through 3 homogeneous points = null space of the 3x4 matrix;
    projection preserves planes, so this is the same cut as in 3D)."""
    replaced = {}
    for a, b in pairs:
        if a in replaced or b in replaced:
            continue
        for cut, by in ((a, b), (b, a)):
            pieces = split_by_plane(tris[cut], np.linalg.svd(tris[by])[2][-1])
            if pieces is not None:
                replaced[cut] = pieces
                break
    if not replaced:
        return tris, sources, 0
    keep = np.array([t not in replaced for t in range(len(tris))])
    new_tris = [tris[keep]] + list(replaced.values())
    new_sources = [sources[keep]] + [np.full(len(p), sources[t]) for t, p in replaced.items()]
    return np.concatenate(new_tris), np.concatenate(new_sources), len(replaced)


def project_to_stage(tris):
    """Clip space (M,3,4) -> stage xy (M,3,2) and NDC depth (M,3)."""
    ndc = tris[:, :, :3] / tris[:, :, 3:4]
    return ndc[:, :, :2] * [STAGE_WIDTH / 2, STAGE_HEIGHT / 2], ndc[:, :, 2]


def signed_area2(xy):
    """Twice the signed area of (M,3,2) triangles; > 0 = counter-clockwise (y up)."""
    a, b, c = xy[:, 0], xy[:, 1], xy[:, 2]
    return (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])


# ---------------------------------------------------------------- raster

def triangle_pixels(xy):
    """Pixels whose centers fall inside a stage-space triangle (3,2).
    Returns (flat pixel indices, barycentric weights (K,3))."""
    u = xy[:, 0] + STAGE_WIDTH / 2
    v = STAGE_HEIGHT / 2 - xy[:, 1]
    col0 = max(int(np.ceil(u.min() - 0.5)), 0)
    col1 = min(int(np.floor(u.max() - 0.5)), STAGE_WIDTH - 1)
    row0 = max(int(np.ceil(v.min() - 0.5)), 0)
    row1 = min(int(np.floor(v.max() - 0.5)), STAGE_HEIGHT - 1)
    if col0 > col1 or row0 > row1:
        return np.zeros(0, dtype=np.int64), np.zeros((0, 3))
    cols, rows = np.meshgrid(np.arange(col0, col1 + 1), np.arange(row0, row1 + 1))
    pu, pv = cols + 0.5, rows + 0.5
    area = (u[1] - u[0]) * (v[2] - v[0]) - (u[2] - u[0]) * (v[1] - v[0])
    if area == 0:
        return np.zeros(0, dtype=np.int64), np.zeros((0, 3))
    w0 = ((u[1] - pu) * (v[2] - pv) - (u[2] - pu) * (v[1] - pv)) / area
    w1 = ((u[2] - pu) * (v[0] - pv) - (u[0] - pu) * (v[2] - pv)) / area
    w2 = 1.0 - w0 - w1
    inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    pixels = rows[inside].astype(np.int64) * STAGE_WIDTH + cols[inside]
    return pixels, np.stack([w0[inside], w1[inside], w2[inside]], axis=1)


def rasterize_id_buffer(xy, depth):
    """Z-buffered ID buffer. depth = NDC z (affine in screen space, smaller = nearer).
    Returns (id buffer (H*W,), z buffer, per-triangle (pixels, depths))."""
    ids = np.full(STAGE_WIDTH * STAGE_HEIGHT, -1, dtype=np.int64)
    zbuf = np.full(STAGE_WIDTH * STAGE_HEIGHT, np.inf)
    covered = []
    for t in range(len(xy)):
        pixels, bary = triangle_pixels(xy[t])
        z = bary @ depth[t]
        nearer = z < zbuf[pixels]
        zbuf[pixels[nearer]] = z[nearer]
        ids[pixels[nearer]] = t
        covered.append((pixels, z))
    return ids, zbuf, covered


def draw_before_constraints(kept, ids, zbuf, covered):
    """{t: {owner: pixel count}} - t covers pixels that `owner` wins while being
    genuinely behind it there, so t must be drawn before owner."""
    kept_set = set(kept.tolist())
    successors = {t: {} for t in kept}
    for t in kept:
        pixels, z = covered[t]
        owners = ids[pixels]
        behind = (owners != t) & (owners >= 0) & (z > zbuf[pixels] + DEPTH_EPSILON)
        owners, counts = np.unique(owners[behind], return_counts=True)
        for owner, count in zip(owners.tolist(), counts.tolist()):
            if owner in kept_set:
                successors[t][owner] = count
    return successors


def mutual_pairs(successors):
    return [(a, b) for a in successors for b in successors[a]
            if a < b and a in successors.get(b, {})]


def painter_order(kept, successors, mean_depth):
    """Topological sort of the draw-before constraints. Farther triangles come
    first among free choices; leftover cycles are broken at the triangle with
    the fewest pixels' worth of violated constraints."""
    in_count = {t: 0 for t in kept}
    in_weight = {t: 0 for t in kept}
    for t in kept:
        for owner, count in successors[t].items():
            in_count[owner] += 1
            in_weight[owner] += count

    heap = [(-mean_depth[t], t) for t in kept if in_count[t] == 0]
    heapq.heapify(heap)
    done = set()
    order = []
    cycles_broken = 0
    while len(order) < len(kept):
        if not heap:
            stuck = min((t for t in kept if t not in done),
                        key=lambda t: (in_weight[t], -mean_depth[t]))
            in_count[stuck] = 0
            heap.append((-mean_depth[stuck], stuck))
            cycles_broken += 1
        _, t = heapq.heappop(heap)
        if t in done:
            continue
        done.add(t)
        order.append(t)
        for succ, count in successors[t].items():
            if succ in done:
                continue
            in_count[succ] -= 1
            in_weight[succ] -= count
            if in_count[succ] == 0:
                heapq.heappush(heap, (-mean_depth[succ], succ))
    return order, cycles_broken


# ---------------------------------------------------------------- render sampling

def render_frame_rgb(tmp_path):
    """Render the current frame; returns (H,W,3) display-referred sRGB, row 0 = top."""
    bpy.context.scene.render.filepath = tmp_path
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(tmp_path, check_existing=False)
    pixels = np.empty(STAGE_WIDTH * STAGE_HEIGHT * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    return pixels.reshape(STAGE_HEIGHT, STAGE_WIDTH, 4)[::-1, :, :3]


def sample_source_colors(render_rgb, source_ids, source_count, fallback):
    """Mean render color per source face over its interior pixels (all 4
    neighbours owned by the same face), else over all its pixels."""
    grid = source_ids.reshape(STAGE_HEIGHT, STAGE_WIDTH)
    padded = np.pad(grid, 1, constant_values=-2)
    interior = ((padded[:-2, 1:-1] == grid) & (padded[2:, 1:-1] == grid) &
                (padded[1:-1, :-2] == grid) & (padded[1:-1, 2:] == grid)).ravel()
    rgb = render_rgb.reshape(-1, 3)
    colors = fallback.copy()
    for mask in (source_ids >= 0, interior & (source_ids >= 0)):
        counts = np.bincount(source_ids[mask], minlength=source_count)
        have = counts > 0
        for ch in range(3):
            sums = np.bincount(source_ids[mask], weights=rgb[mask, ch], minlength=source_count)
            colors[have, ch] = sums[have] / counts[have]
    return colors


# ---------------------------------------------------------------- per frame

def export_frame(scene, depsgraph, args, tmp_render_path, vertex_numbers, vertices):
    """Appends this frame's new vertices to the shared vertex list; returns
    (face records, face colors, stats) in draw order."""
    vertex_count_before = len(vertices)
    cam = scene.camera.evaluated_get(depsgraph)
    view_proj = cam.calc_matrix_camera(depsgraph, x=STAGE_WIDTH, y=STAGE_HEIGHT) @ cam.matrix_world.inverted()
    source_tris, source_colors = gather_frame_triangles(depsgraph, view_proj)
    source_count = len(source_tris)

    tris, sources = clip_triangles(source_tris) if source_count else (np.zeros((0, 3, 4)), np.zeros(0, int))
    area = signed_area2(project_to_stage(tris)[0])
    facing = area > 0 if not args.double_sided else area != 0
    tris, sources = tris[facing], sources[facing]
    clipped_count = len(tris)

    splits = 0
    for split_pass in range(MAX_SPLIT_PASSES + 1):
        xy, depth = project_to_stage(tris)
        ids, zbuf, covered = rasterize_id_buffer(xy, depth)
        owned = np.bincount(ids[ids >= 0], minlength=len(xy))
        kept = np.nonzero(owned >= max(args.min_pixels, 1))[0]
        successors = draw_before_constraints(kept, ids, zbuf, covered)
        pairs = mutual_pairs(successors)
        if not pairs or split_pass == MAX_SPLIT_PASSES:
            break
        tris, sources, split_count = split_interpenetrating(tris, sources, pairs)
        if split_count == 0:
            break
        splits += split_count
    order, cycles_broken = painter_order(kept, successors, depth.mean(axis=1))

    if args.color == "render":
        source_ids = np.where(ids >= 0, sources[np.maximum(ids, 0)], -1)
        colors = sample_source_colors(render_frame_rgb(tmp_render_path), source_ids,
                                      source_count, source_colors)
    else:
        colors = source_colors

    faces = []
    face_colors = []
    for t in order:
        corners = [tuple(int(round(c)) for c in p) for p in xy[t]]
        rounded = np.array([corners], dtype=np.float64)
        area = signed_area2(rounded)[0]
        if area == 0:
            continue                                  # collapsed when snapped to pixels
        if area > 0:
            corners = [corners[0], corners[2], corners[1]]    # filler wants clockwise
        numbers = []
        for corner in corners:
            if corner not in vertex_numbers:
                vertices.append(corner)
                vertex_numbers[corner] = len(vertices)
            numbers.append(vertex_numbers[corner])
        if args.format == "stamps":
            b1, b2, *rest = half_tri_stamps(*corners)
            faces.append((numbers[b1], numbers[b2], *rest))
        else:
            faces.append(tuple(numbers))
        face_colors.append(rgb_to_effects(colors[sources[t]]))

    stats = dict(source=source_count, clipped=clipped_count, splits=splits, visible=len(kept),
                 written=len(faces), vertices=len(vertices) - vertex_count_before, cycles=cycles_broken)
    return faces, face_colors, stats


def half_tri_pixels(corners, size):
    """Pixels a stamped half-tri covers: the triangle plus its round-joined
    stroke, which reaches HALF_TRI_STROKE/2 costume units (scaled by size)
    past every edge."""
    radius = HALF_TRI_STROKE / 2 * size / 100
    u = corners[:, 0] + STAGE_WIDTH / 2
    v = STAGE_HEIGHT / 2 - corners[:, 1]
    col0 = max(int(math.ceil(u.min() - radius - 0.5)), 0)
    col1 = min(int(math.floor(u.max() + radius - 0.5)), STAGE_WIDTH - 1)
    row0 = max(int(math.ceil(v.min() - radius - 0.5)), 0)
    row1 = min(int(math.floor(v.max() + radius - 0.5)), STAGE_HEIGHT - 1)
    if col0 > col1 or row0 > row1:
        return np.zeros(0, dtype=np.int64)
    cols, rows = np.meshgrid(np.arange(col0, col1 + 1), np.arange(row0, row1 + 1))
    pu, pv = cols + 0.5, rows + 0.5
    covered = np.zeros(pu.shape, dtype=bool)
    area = (u[1] - u[0]) * (v[2] - v[0]) - (u[2] - u[0]) * (v[1] - v[0])
    if area != 0:
        w0 = ((u[1] - pu) * (v[2] - pv) - (u[2] - pu) * (v[1] - pv)) / area
        w1 = ((u[2] - pu) * (v[0] - pv) - (u[0] - pu) * (v[2] - pv)) / area
        covered |= (w0 >= 0) & (w1 >= 0) & (1 - w0 - w1 >= 0)
    for i in range(3):
        au, av, bu, bv = u[i], v[i], u[(i + 1) % 3], v[(i + 1) % 3]
        length2 = (bu - au) ** 2 + (bv - av) ** 2
        t = np.clip(((pu - au) * (bu - au) + (pv - av) * (bv - av)) / length2, 0, 1) if length2 else 0
        covered |= (pu - au - t * (bu - au)) ** 2 + (pv - av - t * (bv - av)) ** 2 <= radius ** 2
    return rows[covered].astype(np.int64) * STAGE_WIDTH + cols[covered]


def write_preview(path, vertices, faces, face_colors, record_format):
    canvas = np.zeros((STAGE_WIDTH * STAGE_HEIGHT, 3))
    for record, effects in zip(faces, face_colors):
        if record_format == "stamps":
            base1, base2, direction, costume1, size1, costume2, size2 = record
        else:
            corners = [vertices[n - 1] for n in record]
            b1, b2, direction, costume1, size1, costume2, size2 = half_tri_stamps(*corners)
            base1, base2 = record[b1], record[b2]
        color = effects_to_rgb(*effects)
        for base, costume, size in ((base1, costume1, size1), (base2, costume2, size2)):
            canvas[half_tri_pixels(half_tri_shape(vertices[base - 1], direction, costume, size), size)] = color
    rgba = np.ones((STAGE_HEIGHT, STAGE_WIDTH, 4), dtype=np.float32)
    rgba[:, :, :3] = canvas.reshape(STAGE_HEIGHT, STAGE_WIDTH, 3)
    image = bpy.data.images.new("tri_frame_preview", STAGE_WIDTH, STAGE_HEIGHT)
    image.pixels.foreach_set(rgba[::-1].ravel())
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


# ---------------------------------------------------------------- export

SCRATCH_LIST_LIMIT = 200000


def run_export(scene, opts, report=print, on_frame=None):
    """Export opts.first..opts.last. opts: prefix, out_dir, first, last, color,
    format, min_pixels, double_sided, keep_view_transform, preview_dir (or None).
    The render / color settings it needs are restored afterwards."""
    if scene.camera is None:
        raise RuntimeError("scene has no active camera")
    os.makedirs(opts.out_dir, exist_ok=True)
    if opts.preview_dir:
        os.makedirs(opts.preview_dir, exist_ok=True)

    render = scene.render
    image_settings = render.image_settings
    saved = dict(
        resolution=(render.resolution_x, render.resolution_y, render.resolution_percentage),
        pixel_aspect=(render.pixel_aspect_x, render.pixel_aspect_y),
        image=(image_settings.file_format, image_settings.color_mode, image_settings.color_depth),
        filepath=render.filepath,
        view=(scene.view_settings.view_transform, scene.view_settings.look),
        frame=scene.frame_current,
    )
    if render.resolution_x * STAGE_HEIGHT != render.resolution_y * STAGE_WIDTH:
        report(f"WARNING: scene resolution is {render.resolution_x}x{render.resolution_y}, "
               f"not 4:3 - the exported framing will differ from Blender's camera view")

    vertex_numbers = {}
    vertices = []
    faces = []
    face_colors = []
    frames = []
    try:
        render.resolution_x, render.resolution_y = STAGE_WIDTH, STAGE_HEIGHT
        render.resolution_percentage = 100
        render.pixel_aspect_x = render.pixel_aspect_y = 1.0
        image_settings.file_format = "PNG"
        image_settings.color_mode = "RGB"
        image_settings.color_depth = "8"
        if not opts.keep_view_transform:
            scene.view_settings.view_transform = "Standard"
            scene.view_settings.look = "None"
        tmp_render_path = os.path.join(tempfile.mkdtemp(prefix="tri_frames_"), "frame.png")

        for frame in range(opts.first, opts.last + 1):
            scene.frame_set(frame)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            frame_faces, frame_colors, stats = export_frame(scene, depsgraph, opts, tmp_render_path,
                                                            vertex_numbers, vertices)
            frames.append((len(faces) + 1, len(frame_faces)))
            faces += frame_faces
            face_colors += frame_colors

            report(f"frame {frame}: {stats['source']} faces -> {stats['clipped']} after clip/cull "
                   f"-> {stats['visible']} visible -> {stats['written']} tris, "
                   f"{stats['vertices']} new verts"
                   + (f", {stats['splits']} face(s) split" if stats["splits"] else "")
                   + (f", {stats['cycles']} cycle(s) broken" if stats["cycles"] else ""))
            if opts.preview_dir:
                write_preview(os.path.join(opts.preview_dir, f"{opts.prefix}_{frame:04d}.png"),
                              vertices, frame_faces, frame_colors, opts.format)
            if on_frame:
                on_frame(frame)
    finally:
        render.resolution_x, render.resolution_y, render.resolution_percentage = saved["resolution"]
        render.pixel_aspect_x, render.pixel_aspect_y = saved["pixel_aspect"]
        image_settings.file_format, image_settings.color_mode, image_settings.color_depth = saved["image"]
        render.filepath = saved["filepath"]
        scene.view_settings.view_transform, scene.view_settings.look = saved["view"]
        scene.frame_set(saved["frame"])

    lists = {
        "vertices": [n for vertex in vertices for n in vertex],
        "faces": [fmt(n) for face in faces for n in face],
        "face_colors": [fmt(n) for color in face_colors for n in color],
        "frames": [n for frame in frames for n in frame],
    }
    report(f"wrote {len(frames)} frame(s), {len(faces)} faces, {len(vertices)} vertices:")
    for name, items in lists.items():
        path = os.path.join(opts.out_dir, f"{opts.prefix}_{name}.txt")
        with open(path, "w") as f:
            f.write("\n".join(str(n) for n in items))
        report(f"  {path} ({len(items)} items)")
        if len(items) > SCRATCH_LIST_LIMIT:
            report(f"WARNING: {name} is over Scratch's {SCRATCH_LIST_LIMIT}-item list limit")
    return len(frames), len(faces)


def blend_name():
    return os.path.splitext(os.path.basename(bpy.data.filepath))[0] or "untitled"


def main():
    args = parse_args()
    scene = bpy.context.scene
    first, last = (int(n) for n in args.frames.split("-")) if args.frames else (scene.frame_start, scene.frame_end)
    opts = SimpleNamespace(
        prefix=args.prefix or blend_name(),
        out_dir=args.out_dir or os.path.dirname(bpy.data.filepath) or os.getcwd(),
        first=first, last=last, color=args.color, format=args.format,
        min_pixels=args.min_pixels, double_sided=args.double_sided,
        keep_view_transform=args.keep_view_transform, preview_dir=args.preview_dir,
    )
    try:
        run_export(scene, opts)
    except RuntimeError as e:
        raise SystemExit(str(e))


# ---------------------------------------------------------------- UI

bl_info = {
    "name": "Scratch Tri Frames",
    "description": "Export an animation as visible, back-to-front flat triangles for a Scratch filler",
    "blender": (4, 2, 0),
    "category": "Import-Export",
    "location": "Properties > Output > Scratch Tri Frames",
}


class TriFrameExportSettings(bpy.types.PropertyGroup):
    prefix: bpy.props.StringProperty(name="Prefix", description="File name prefix; empty = .blend name")
    out_dir: bpy.props.StringProperty(name="Folder", subtype="DIR_PATH", default="//")
    use_scene_range: bpy.props.BoolProperty(name="Scene Frame Range", default=True)
    frame_first: bpy.props.IntProperty(name="Start", default=1)
    frame_last: bpy.props.IntProperty(name="End", default=24)
    color: bpy.props.EnumProperty(name="Color", items=[
        ("render", "Render", "Average each face's rendered pixels (lighting, textures)"),
        ("material", "Material", "Unlit flat material color, no render"),
    ])
    record_format: bpy.props.EnumProperty(name="Format", items=[
        ("faces", "Faces", "v1, v2, v3 for the generic triangle filler"),
        ("stamps", "Stamps", "Half-tri stamps precomputed: base1, base2, direction, costume/size x2"),
    ])
    min_pixels: bpy.props.IntProperty(name="Min Pixels", default=1, min=1,
                                      description="Drop faces owning fewer visible pixels")
    double_sided: bpy.props.BoolProperty(name="Double Sided", description="Keep back faces")
    keep_view_transform: bpy.props.BoolProperty(name="Keep View Transform",
                                                description="Don't force Standard while rendering colors")
    write_preview: bpy.props.BoolProperty(name="Preview PNGs", default=True)
    preview_dir: bpy.props.StringProperty(name="Preview Folder", subtype="DIR_PATH", default="//preview/")


class EXPORT_OT_scratch_tri_frames(bpy.types.Operator):
    bl_idname = "export_scene.scratch_tri_frames"
    bl_label = "Export Tri Frames"
    bl_description = "Export the animation as Scratch triangle lists"

    def execute(self, context):
        scene = context.scene
        settings = scene.scratch_tri_frames
        first, last = ((scene.frame_start, scene.frame_end) if settings.use_scene_range
                       else (settings.frame_first, settings.frame_last))
        opts = SimpleNamespace(
            prefix=settings.prefix or blend_name(),
            out_dir=bpy.path.abspath(settings.out_dir),
            first=first, last=last, color=settings.color, format=settings.record_format,
            min_pixels=settings.min_pixels, double_sided=settings.double_sided,
            keep_view_transform=settings.keep_view_transform,
            preview_dir=bpy.path.abspath(settings.preview_dir) if settings.write_preview else None,
        )
        wm = context.window_manager
        wm.progress_begin(first, last)
        try:
            frame_count, face_count = run_export(scene, opts, on_frame=wm.progress_update)
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        finally:
            wm.progress_end()
        self.report({"INFO"}, f"Exported {frame_count} frames, {face_count} faces to {opts.out_dir}")
        return {"FINISHED"}


class RENDER_PT_scratch_tri_frames(bpy.types.Panel):
    bl_label = "Scratch Tri Frames"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "output"

    def draw(self, context):
        settings = context.scene.scratch_tri_frames
        layout = self.layout
        layout.use_property_split = True
        layout.prop(settings, "out_dir")
        layout.prop(settings, "prefix")
        layout.prop(settings, "use_scene_range")
        if not settings.use_scene_range:
            row = layout.row(align=True)
            row.prop(settings, "frame_first")
            row.prop(settings, "frame_last")
        layout.prop(settings, "record_format")
        layout.prop(settings, "color")
        if settings.color == "render":
            layout.prop(settings, "keep_view_transform")
        layout.prop(settings, "min_pixels")
        layout.prop(settings, "double_sided")
        layout.prop(settings, "write_preview")
        if settings.write_preview:
            layout.prop(settings, "preview_dir")
        layout.operator(EXPORT_OT_scratch_tri_frames.bl_idname, icon="EXPORT")


UI_CLASSES = (TriFrameExportSettings, EXPORT_OT_scratch_tri_frames, RENDER_PT_scratch_tri_frames)


def register():
    for cls in UI_CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.scratch_tri_frames = bpy.props.PointerProperty(type=TriFrameExportSettings)


def unregister():
    del bpy.types.Scene.scratch_tri_frames
    for cls in reversed(UI_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    if bpy.app.background:
        main()
    else:
        if hasattr(bpy.types.Scene, "scratch_tri_frames"):
            unregister()                              # re-run from the Text Editor
        register()
