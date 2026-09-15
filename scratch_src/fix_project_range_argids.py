"""
Fixes the argid-mismatch bug: build_screen_scale.py deleted and regenerated
"3D Project Range %s %s" with fresh random argids, but every existing call
site (inside drawWatership, the cube demo, 3D Project All, manual test
stacks) still references the ORIGINAL argids from build_3d.py. Scratch
binds call arguments by id, so every one of those calls has been silently
passing empty-string defaults ever since - not a logic bug, an id mismatch.

sb3dsl.py's Proc.define() now auto-detects and reuses existing call-site
argids when regenerating an already-called proccode, so simply deleting
and rebuilding this one block (same body as build_screen_scale.py) fixes
every call site at once, with no changes needed at any call site.

Run from scratch_src/ against a project.json freshly synced from the live
project.sb3:
    python3 fix_project_range_argids.py
Then repack with pack.py.
"""
import json
import sb3dsl as S

PROJECT_JSON = "project.json"

with open(PROJECT_JSON) as f:
    proj = json.load(f)

stage = next(t for t in proj["targets"] if t["isStage"])
sprite = next(t for t in proj["targets"] if t["name"] == "Sprite1")
blocks = sprite["blocks"]
variables = stage["variables"]
lists = stage["lists"]


def _collect_stack(bid, into):
    while bid and bid not in into:
        b = blocks.get(bid)
        if b is None:
            return
        into.add(bid)
        for v in b.get("inputs", {}).values():
            if isinstance(v, list) and len(v) >= 2 and isinstance(v[1], str) and v[1] in blocks:
                _collect_stack(v[1], into)
        _collect_stack(b.get("next"), into)


to_delete = set()
for bid, b in list(blocks.items()):
    if isinstance(b, dict) and b.get("opcode") == "procedures_prototype":
        if b.get("mutation", {}).get("proccode") == "3D Project Range %s %s":
            to_delete.add(bid)
            _collect_stack(b["parent"], to_delete)
for bid in to_delete:
    blocks.pop(bid, None)
print(f"removed {len(to_delete)} blocks (broken 3D Project Range %s %s)")

ctx = S.Ctx(blocks, variables, lists, id_prefix="gpr_")

i = S.var("(func) 3D range i")
projz = S.var("(func) 3D proj z")
projsx = S.var("(func) 3D proj sx")
projsy = S.var("(func) 3D proj sy")

ProjectRange = S.Proc("3D Project Range %s %s", ["s", "e"], warp=True)
ProjectRange.define(ctx, S.seq(
    S.setvar("(func) 3D range i", ProjectRange.arg("s")),
    S.control_repeat_until(S.gt(i, ProjectRange.arg("e")), S.seq(
        S.setvar("(func) 3D proj z", S.listitem("3D_cam_z", i)),
        S.control_if_else(
            S.gt(projz, S.var("3D_camera_near")),
            S.seq(
                S.setvar("(func) 3D proj sx", S.mul(S.div(S.listitem("3D_cam_x", i), projz), S.var("3D_camera_fov"))),
                S.setvar("(func) 3D proj sy", S.mul(S.div(S.listitem("3D_cam_y", i), projz), S.var("3D_camera_fov"))),
                S.list_replace("3D_screen_x", i, projsx),
                S.list_replace("3D_screen_y", i, projsy),
                S.list_replace("3D_screen_scale", i, S.div(S.var("3D_camera_fov"), projz)),
                S.control_if_else(
                    S.AND(
                        S.lte(S.absv(projsx), S.mul(S.var("3D_camera_screen_bound"), S.num(240))),
                        S.lte(S.absv(projsy), S.mul(S.var("3D_camera_screen_bound"), S.num(180))),
                    ),
                    S.seq(S.list_replace("3D_visible", i, S.num(1))),
                    S.seq(S.list_replace("3D_visible", i, S.num(0))),
                ),
            ),
            S.seq(
                S.list_replace("3D_screen_x", i, S.num(0)),
                S.list_replace("3D_screen_y", i, S.num(0)),
                S.list_replace("3D_screen_scale", i, S.num(0)),
                S.list_replace("3D_visible", i, S.num(0)),
            ),
        ),
        S.changevar("(func) 3D range i", S.num(1)),
    )),
), 0, 56600)

print(f"regenerated 3D Project Range %s %s with argids {ProjectRange.argids}, {ctx._n} new block ids")

with open(PROJECT_JSON, "w") as f:
    json.dump(proj, f)
print("wrote", PROJECT_JSON)
