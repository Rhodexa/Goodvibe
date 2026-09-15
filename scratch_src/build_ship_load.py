"""
Additive script: adds a "Ship Load" custom block to the CURRENT
project.json (does not touch/redefine anything that already exists - sync
scratch_src/project.json from the live project.sb3 first, since this is
meant to layer on top of hand-edits made directly in the Scratch/TurboWarp
editor, e.g. "(test) drawWatership").

Unpacks the single combined "ship_data" list (see combine_ship_list.py:
N names, then N x, then N y, then N z) into the vertex processor's
3D_src_x/y/z buffers (indices 1..N) plus a ship-specific "ship_costumes"
list (indices 1..N), and sets ship_point_count = N. Ship-specific data
(costume names) intentionally stays out of the generic "3D_*" namespace -
the vertex processor only ever deals in points.

Run from scratch_src/:
    python3 build_ship_load.py
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

ctx = S.Ctx(blocks, variables, lists, id_prefix="gship_")

ctx.ensure_var("ship_point_count", 0)
ctx.ensure_var("(func) ship load i", 0)
ctx.ensure_var("(func) ship load n", 0)
ctx.ensure_list("ship_data")       # imported by hand: right-click -> import ship_data.txt
ctx.ensure_list("ship_costumes")   # unpacked here, indices 1..N align with 3D_src_x/y/z

n = S.var("(func) ship load n")
i = S.var("(func) ship load i")

Init = S.Proc("3D Init", [], warp=False).attach(ctx)

ShipLoad = S.Proc("Ship Load", [], warp=False)
ShipLoad.define(ctx, S.seq(
    Init.call(),  # guarantees 3D_src_x/y/z are fully (re)allocated before we write into them
    S.setvar("(func) ship load n", S.div(S.listlen("ship_data"), S.num(4))),
    S.setvar("ship_point_count", n),
    S.list_delete_all("ship_costumes"),
    S.setvar("(func) ship load i", S.num(1)),
    S.control_repeat_until(S.gt(i, n), S.seq(
        S.list_add("ship_costumes", S.listitem("ship_data", i)),
        S.list_replace("3D_src_x", i, S.listitem("ship_data", S.add(n, i))),
        S.list_replace("3D_src_y", i, S.listitem("ship_data", S.add(S.mul(n, S.num(2)), i))),
        S.list_replace("3D_src_z", i, S.listitem("ship_data", S.add(S.mul(n, S.num(3)), i))),
        S.changevar("(func) ship load i", S.num(1)),
    )),
), 0, 55000)

print(f"generated {ctx._n} new block ids")

with open(PROJECT_JSON, "w") as f:
    json.dump(proj, f)

print("wrote", PROJECT_JSON)
