"""
Additive script: adds the "TriPlayer" object to Sprite1 of the CURRENT
project.json (sync scratch_src/project.json from the live project.sb3 first).

TriPlayer plays animations pre-baked by export_visible_tri_frames.py in its
"stamps" format: every face already carries its half-tri stamps (direction,
costume offset, size per half) and its Scratch effect color, so drawing a
frame is just list reads + stamps, no math.

Safe to re-run: costumes and (with --data) list contents are replaced,
blocks are only added if "TriPlayer Init" doesn't exist yet.

Adds:
  - costumes tri_1 .. tri_N (the half-tri set from trianglefiller.sb3),
    APPENDED to Sprite1 so no other costume number moves; a re-run swaps
    the old set for the current one
  - lists (model) TriPlayer vertices / faces / face colors / frames -
    import <prefix>_vertices.txt / _faces.txt / _face_colors.txt /
    _frames.txt into them (right-click -> import), or pass --data PREFIX
    here to prefill them
  - TriPlayer Init            finds tri_1's costume number; call once
  - TriPlayer Draw Frame (frame)
                              stamps frame 1..N on top of whatever is on
                              the pen layer (clearing is the caller's job),
                              then clears graphic effects
  - when t key pressed        dev test: Init, then loops every frame

Run from scratch_src/:
    python3 build_tri_player.py [--data ../assets/minuta/tri_frames/minuta] [--costumes ../trianglefiller.sb3]
Then validate.py + pack.py.
"""
import argparse
import json
import os
import zipfile

import sb3dsl as S

PROJECT_JSON = "project.json"

ap = argparse.ArgumentParser()
ap.add_argument("--costumes", default="../trianglefiller.sb3",
                help="the triangle filler project whose tri_N costumes get copied in")
ap.add_argument("--data", default=None,
                help="exporter output prefix, e.g. ../anims/spin/spin - prefills the lists")
args = ap.parse_args()

with open(PROJECT_JSON) as f:
    proj = json.load(f)

stage = next(t for t in proj["targets"] if t["isStage"])
sprite = next(t for t in proj["targets"] if t["name"] == "Sprite1")

# ---- costumes ------------------------------------------------------------

filler_sb3 = zipfile.ZipFile(args.costumes)
filler = json.loads(filler_sb3.read("project.json"))
filler_costumes = next(t for t in filler["targets"] if t["name"] == "Sprite1")["costumes"]
half_tris = {c["name"]: c for c in filler_costumes
             if c["name"].startswith("tri_") and c["name"][4:].isdigit()}
half_tri_count = len(half_tris)


def is_half_tri(costume):
    return costume["name"].startswith("tri_") and costume["name"][4:].isdigit()


removed = [c for c in sprite["costumes"] if is_half_tri(c)]
sprite["costumes"] = [c for c in sprite["costumes"] if not is_half_tri(c)]
if sprite["currentCostume"] >= len(sprite["costumes"]):
    sprite["currentCostume"] = 0
for n in range(1, half_tri_count + 1):
    costume = half_tris[f"tri_{n}"]
    with open(costume["md5ext"], "wb") as f:
        f.write(filler_sb3.read(costume["md5ext"]))
    sprite["costumes"].append(dict(costume))
still_used = {c["md5ext"] for t in proj["targets"] for c in t["costumes"]}
for md5ext in {c["md5ext"] for c in removed} - still_used:
    os.remove(md5ext)                                 # pack.py zips every file in here

# ---- data ----------------------------------------------------------------

blocks = sprite["blocks"]
ctx = S.Ctx(blocks, stage["variables"], stage["lists"], id_prefix="gtrip_")

LIST_FILES = {
    "(model) TriPlayer vertices": "vertices",
    "(model) TriPlayer faces": "faces",
    "(model) TriPlayer face colors": "face_colors",
    "(model) TriPlayer frames": "frames",
}
for list_name, suffix in LIST_FILES.items():
    lid = ctx.ensure_list(list_name)
    if args.data:
        with open(f"{args.data}_{suffix}.txt") as f:
            stage["lists"][lid][1] = [float(v) if "." in v else int(v) for v in f.read().split()]

VERTICES, FACES, COLORS, FRAMES = LIST_FILES

ctx.ensure_var("tri_player_costume_base", 0)
face = S.var("(func) tri_player face")
record = S.var("(func) tri_player record")
brightness = S.var("(func) tri_player brightness")
ghost = S.var("(func) tri_player ghost")


def face_item(offset):
    return S.listitem(FACES, S.add(record, S.num(offset)))


# ---- blocks --------------------------------------------------------------

already_built = any(isinstance(b, dict) and b.get("opcode") == "procedures_prototype"
                    and b["mutation"]["proccode"] == "TriPlayer Init" for b in blocks.values())
if already_built:
    print(f"TriPlayer blocks already present, swapped in {half_tri_count} costumes (was {len(removed)})")
    with open(PROJECT_JSON, "w") as f:
        json.dump(proj, f)
    raise SystemExit(0)

Init = S.Proc("TriPlayer Init", [], warp=True)
Init.define(ctx, S.seq(
    S.switch_costume(S.text("tri_1")),
    S.setvar("tri_player_costume_base", S.costume_number()),
), 0, 60000)

StampHalf = S.Proc("(child) TriPlayer Stamp Half %s %s %s", ["vertex", "costume", "size"], warp=True)
vertex = StampHalf.arg("vertex")
StampHalf.define(ctx, S.seq(
    S.goto_xy(S.listitem(VERTICES, S.sub(S.mul(vertex, S.num(2)), S.num(1))),
              S.listitem(VERTICES, S.mul(vertex, S.num(2)))),
    S.switch_costume(S.add(S.var("tri_player_costume_base"), StampHalf.arg("costume"))),
    S.set_size(StampHalf.arg("size")),
    S.set_effect("BRIGHTNESS", brightness),
    S.set_effect("GHOST", S.num(0)),
    S.pen_stamp(),
    # overlay: same shape in black, ghost = how much of the color survives
    S.control_if(S.lt(ghost, S.num(100)), S.seq(
        S.set_effect("BRIGHTNESS", S.num(-100)),
        S.set_effect("GHOST", ghost),
        S.pen_stamp(),
    )),
), 0, 60400)

DrawFrame = S.Proc("TriPlayer Draw Frame %s", ["frame"], warp=True)
frame = DrawFrame.arg("frame")
DrawFrame.define(ctx, S.seq(
    S.setvar("(func) tri_player face", S.listitem(FRAMES, S.sub(S.mul(frame, S.num(2)), S.num(1)))),
    S.control_repeat(S.listitem(FRAMES, S.mul(frame, S.num(2))), S.seq(
        S.setvar("(func) tri_player record", S.mul(S.sub(face, S.num(1)), S.num(7))),
        S.setvar("(func) tri_player brightness", S.listitem(COLORS, S.sub(S.mul(face, S.num(3)), S.num(1)))),
        S.setvar("(func) tri_player ghost", S.listitem(COLORS, S.mul(face, S.num(3)))),
        S.set_effect("COLOR", S.listitem(COLORS, S.sub(S.mul(face, S.num(3)), S.num(2)))),
        S.point_in_direction(face_item(3)),
        StampHalf.call(vertex=face_item(1), costume=face_item(4), size=face_item(5)),
        StampHalf.call(vertex=face_item(2), costume=face_item(6), size=face_item(7)),
        S.changevar("(func) tri_player face", S.num(1)),
    )),
    S.clear_graphic_effects(),
), 0, 60900)

dev_frame = S.var("(func) tri_player dev frame")
S.place_top(ctx, S.hat_keypressed("t"), S.seq(
    Init.call(),
    S.setvar("(func) tri_player dev frame", S.num(1)),
    S.control_forever(S.seq(
        S.pen_clear(),
        DrawFrame.call(frame=dev_frame),
        S.setvar("(func) tri_player dev frame",
                 S.add(S.mod(dev_frame, S.div(S.listlen(FRAMES), S.num(2))), S.num(1))),
    )),
), 0, 61500)

print(f"added {half_tri_count} costumes, generated {ctx._n} new block ids")

with open(PROJECT_JSON, "w") as f:
    json.dump(proj, f)

print("wrote", PROJECT_JSON)
