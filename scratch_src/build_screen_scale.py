"""
Adds a 3D_screen_scale output (the fov/z factor already computed inside
Project Range for screen_x/y, but previously discarded) so billboard
drawers can scale sprite size to match projected depth - 100% = the
costume's native pixel size, matching mesh-unit scale 1:1 at fov/z=1.

Surgically replaces "3D Init" and "3D Project Range %s %s" (delete +
regenerate, same as build_3d.py's own dead-code removal - safe because
every caller elsewhere references them by proccode string, not block id,
so they keep working unchanged). "3D Project All" is untouched: it already
calls "3D Project Range %s %s" by proccode, so it picks up the new
behavior automatically.

Also directly patches the one looks_setsizeto inside drawWatership that
was reading raw 3D_cam_z (a depth, not a scale factor) as its SIZE, to
instead read 3D_screen_scale * 100.

Run from scratch_src/ against a project.json freshly synced from the live
project.sb3 (unzip -p ../project.sb3 project.json > project.json first):
    python3 build_screen_scale.py
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
        if b.get("mutation", {}).get("proccode") in ("3D Init", "3D Project Range %s %s"):
            to_delete.add(bid)
            _collect_stack(b["parent"], to_delete)
for bid in to_delete:
    blocks.pop(bid, None)
print(f"removed {len(to_delete)} blocks from 3D Init + 3D Project Range %s %s (regenerating)")

ctx = S.Ctx(blocks, variables, lists, id_prefix="gss_")
ctx.ensure_list("3D_screen_scale")

BUFS = [
    "3D_src_x", "3D_src_y", "3D_src_z",
    "3D_cam_x", "3D_cam_y", "3D_cam_z",
    "3D_screen_x", "3D_screen_y", "3D_visible", "3D_screen_scale",
]
for n in BUFS:
    ctx.ensure_list(n)

X0, Y0 = 0, 56000

Init = S.Proc("3D Init", [], warp=False)
Init.define(ctx, S.seq(
    S.seq(*[S.list_delete_all(n) for n in BUFS]),
    S.list_delete_all("3D_mat_ram"),
    S.control_repeat(S.var("3D_vertex_capacity"), S.seq(*[
        S.list_add(n, S.num(0)) for n in BUFS
    ])),
    S.control_repeat(S.num(128), S.seq(S.list_add("3D_mat_ram", S.num(0)))),
), X0, Y0)

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
), X0, Y0 + 260)

print(f"regenerated 3D Init + 3D Project Range %s %s, {ctx._n} new block ids")

# ---------------------------------------------------------------------------
# patch drawWatership's looks_setsizeto: was reading raw 3D_cam_z (a depth,
# not a scale factor); should read 3D_screen_scale * 100.
# ---------------------------------------------------------------------------

SETSIZE_BID = "pM?kno.fdv}J1-Dd1Z!a"
OLD_CHILD_BID = "/caN`(OnDOKFhR$q}!e%"

setsize_block = blocks.get(SETSIZE_BID)
if setsize_block is None or setsize_block.get("opcode") != "looks_setsizeto":
    raise SystemExit(f"expected looks_setsizeto at {SETSIZE_BID!r} inside drawWatership, "
                      f"found {setsize_block!r} - block ids shifted, re-locate it by hand")

new_size_input = S.mul(
    S.listitem("3D_screen_scale", S.var("(func) watership draw i")),
    S.num(100),
)(ctx, SETSIZE_BID)
setsize_block["inputs"]["SIZE"] = new_size_input
blocks.pop(OLD_CHILD_BID, None)
print(f"patched {SETSIZE_BID} (looks_setsizeto in drawWatership) to use 3D_screen_scale * 100")

with open(PROJECT_JSON, "w") as f:
    json.dump(proj, f)
print("wrote", PROJECT_JSON)
