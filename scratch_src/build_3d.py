"""
Builds the "3D vertex processor" into project.json (Sprite1 + Stage), removing
the old dead 3D_* prototype scaffold first. Run from scratch_src/:

    python3 build_3d.py

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

# ---------------------------------------------------------------------------
# 1. Remove the dead 3D_* prototype scaffold (confirmed unused/dead with the
#    user). Removes: the custom blocks themselves, the two green-flag scripts
#    that seeded/called them, and the now-superseded globals. Leaves
#    unit_cube_edges_start/end alone (still useful, already correctly
#    populated from the old dev script's last saved run).
# ---------------------------------------------------------------------------

DEAD_PROCCODES = {
    "3D AllocateDest",
    "3D ApplyMatrix %s",
    "3D ApplyMatrixAll",
    "3D ApplyProjection %s %s",
    "(dev) watershipRenderer Test",
}


def _collect_stack(bid, into):
    while bid and bid not in into:
        b = blocks.get(bid)
        if b is None:
            return
        into.add(bid)
        for v in b.get("inputs", {}).values():
            if isinstance(v, list) and len(v) >= 2 and isinstance(v[1], str) and v[1] in blocks:
                _collect_stack(v[1], into)
            if isinstance(v, list) and len(v) >= 3 and isinstance(v[2], str) and v[2] in blocks:
                _collect_stack(v[2], into)
        _collect_stack(b.get("next"), into)


to_delete = set()

# custom block defs (prototype + definition + full body)
for bid, b in list(blocks.items()):
    if isinstance(b, dict) and b.get("opcode") == "procedures_prototype":
        if b.get("mutation", {}).get("proccode") in DEAD_PROCCODES:
            def_id = b["parent"]
            to_delete.add(bid)
            _collect_stack(def_id, to_delete)

# the two disconnected dev green-flag scripts (seed 3D_gmat identity; seed
# 3D_src_x/y/z + unit_cube_edges + call 3D AllocateDest), plus two more
# fully orphaned (no hat, never runs) leftover blocks found by validate.py:
# a lone "3D ApplyMatrixAll" call sitting alone in the workspace, and a
# detached "forever [pen clear; call (dev) watershipRenderer Test]" loop.
GMAT_SEED_TOP = "nX8ZWEI)X/^rwDpBLdGk"
CUBE_SEED_TOP = "{h!iuHoX5,h.jLhGsnat"
ORPHAN_APPLYMATRIXALL_CALL = "2fbK;ulh+`po%z(TYG20"
ORPHAN_WATERSHIP_TEST_FOREVER = "!|I21YtfZ-[I~5~gLS)/"
_collect_stack(GMAT_SEED_TOP, to_delete)
_collect_stack(CUBE_SEED_TOP, to_delete)
_collect_stack(ORPHAN_APPLYMATRIXALL_CALL, to_delete)
_collect_stack(ORPHAN_WATERSHIP_TEST_FOREVER, to_delete)

for bid in to_delete:
    blocks.pop(bid, None)

print(f"removed {len(to_delete)} dead blocks")

DEAD_VARS = {
    "3D_projected_x",
    "3D_projected_y",
    "(func) 3D AllocateDest idx counter",
    "(func) 3D ApplyMatrixAll Index",
}
DEAD_LISTS = {"3D_dest_x", "3D_dest_y", "3D_dest_z", "3D_gmat"}

for vid, v in list(variables.items()):
    if v[0] in DEAD_VARS:
        del variables[vid]
for lid, l in list(lists.items()):
    if l[0] in DEAD_LISTS:
        del lists[lid]

print("removed dead vars/lists")

# ---------------------------------------------------------------------------
# 2. New globals, with sane defaults baked in.
# ---------------------------------------------------------------------------

ctx = S.Ctx(blocks, variables, lists, id_prefix="g3d_")

DEFAULT_VARS = {
    "3D_vertex_capacity": 512,
    "3D_camera_x": 0,
    "3D_camera_y": 0,
    "3D_camera_z": -400,
    "3D_camera_yaw": 0,
    "3D_camera_pitch": 0,
    "3D_camera_roll": 0,
    "3D_camera_fov": 300,
    "3D_camera_near": 10,
    "3D_camera_screen_bound": 1.5,
    "(return) 3D Matrix Get": 0,
    "(func) 3D range i": 0,
    "(func) 3D mat base": 0,
    "(func) 3D mat base l": 0,
    "(func) 3D mat base r": 0,
    "(func) 3D mat base o": 0,
    "(func) 3D mat base from": 0,
    "(func) 3D mat base to": 0,
    "(func) 3D mat c": 0,
    "(func) 3D mat s": 0,
    "(func) 3D proj z": 0,
    "(func) 3D proj sx": 0,
    "(func) 3D proj sy": 0,
    "(func) 3D la dx": 0,
    "(func) 3D la dy": 0,
    "(func) 3D la dz": 0,
    "(func) 3D la h": 0,
    "(func) 3D cube angle": 0,
    "(func) 3D cube edge i": 0,
    "(func) 3D cube vs": 0,
    "(func) 3D cube ve": 0,
}
for name, default in DEFAULT_VARS.items():
    ctx.ensure_var(name, default)

NEW_LISTS = [
    "3D_src_x", "3D_src_y", "3D_src_z",
    "3D_cam_x", "3D_cam_y", "3D_cam_z",
    "3D_screen_x", "3D_screen_y", "3D_visible",
]
for name in NEW_LISTS:
    ctx.ensure_list(name)
ctx.ensure_list("3D_mat_ram")
ctx.ensure_list("unit_cube_edges_start")  # pre-existing, reused as-is
ctx.ensure_list("unit_cube_edges_end")

# matrix RAM slot conventions (documentation only, not enforced by blocks):
SLOT_ACTIVE = 0        # the matrix Apply/Project read
SLOT_A = 1              # general-purpose scratch for composition
SLOT_B = 2              # general-purpose scratch for composition
# 3-5 free for future use (e.g. per-object matrices)
SLOT_TMP1 = 6           # internal scratch, used by CameraView
SLOT_TMP2 = 7           # internal scratch, used by Multiply and CameraView
MAT_SLOTS = 8
MAT_RAM_LEN = MAT_SLOTS * 16
MULT_SCRATCH_BASE = SLOT_TMP2 * 16  # 112

X0 = 2000  # workspace column for all new scripts, clear of existing content
Y_STEP = 260
y = 0


def next_y():
    global y
    y += Y_STEP
    return y


# ---------------------------------------------------------------------------
# 3. Matrix builders
# ---------------------------------------------------------------------------

def mat_cells(base_var, cells):
    """cells: list of 16 exprs, row-major, 1-indexed position k -> cells[k-1]."""
    return S.seq(*[
        S.list_replace("3D_mat_ram", S.add(S.var(base_var), S.num(k)), cells[k - 1])
        for k in range(1, 17)
    ])


Identity = S.Proc("3D Matrix Identity %s", ["slot"], warp=True)
_diag = {1, 6, 11, 16}
Identity.define(ctx, S.seq(
    S.setvar("(func) 3D mat base", S.mul(Identity.arg("slot"), S.num(16))),
    mat_cells("(func) 3D mat base", [S.num(1) if k in _diag else S.num(0) for k in range(1, 17)]),
), X0, next_y())

Translation = S.Proc("3D Matrix Translation %s %s %s %s", ["slot", "x", "y", "z"], warp=True)
Translation.define(ctx, S.seq(
    S.setvar("(func) 3D mat base", S.mul(Translation.arg("slot"), S.num(16))),
    mat_cells("(func) 3D mat base", [
        S.num(1), S.num(0), S.num(0), Translation.arg("x"),
        S.num(0), S.num(1), S.num(0), Translation.arg("y"),
        S.num(0), S.num(0), S.num(1), Translation.arg("z"),
        S.num(0), S.num(0), S.num(0), S.num(1),
    ]),
), X0, next_y())

Scale = S.Proc("3D Matrix Scale %s %s %s %s", ["slot", "x", "y", "z"], warp=True)
Scale.define(ctx, S.seq(
    S.setvar("(func) 3D mat base", S.mul(Scale.arg("slot"), S.num(16))),
    mat_cells("(func) 3D mat base", [
        Scale.arg("x"), S.num(0), S.num(0), S.num(0),
        S.num(0), Scale.arg("y"), S.num(0), S.num(0),
        S.num(0), S.num(0), Scale.arg("z"), S.num(0),
        S.num(0), S.num(0), S.num(0), S.num(1),
    ]),
), X0, next_y())


def _rot_common(proc):
    c, s = S.var("(func) 3D mat c"), S.var("(func) 3D mat s")
    return S.seq(
        S.setvar("(func) 3D mat base", S.mul(proc.arg("slot"), S.num(16))),
        S.setvar("(func) 3D mat c", S.cos(proc.arg("deg"))),
        S.setvar("(func) 3D mat s", S.sin(proc.arg("deg"))),
    ), c, s


RotationX = S.Proc("3D Matrix Rotation X %s %s", ["slot", "deg"], warp=True)
_pre, c, s = _rot_common(RotationX)
RotationX.define(ctx, S.seq(
    _pre,
    mat_cells("(func) 3D mat base", [
        S.num(1), S.num(0), S.num(0), S.num(0),
        S.num(0), c, S.neg(s), S.num(0),
        S.num(0), s, c, S.num(0),
        S.num(0), S.num(0), S.num(0), S.num(1),
    ]),
), X0, next_y())

RotationY = S.Proc("3D Matrix Rotation Y %s %s", ["slot", "deg"], warp=True)
_pre, c, s = _rot_common(RotationY)
RotationY.define(ctx, S.seq(
    _pre,
    mat_cells("(func) 3D mat base", [
        c, S.num(0), s, S.num(0),
        S.num(0), S.num(1), S.num(0), S.num(0),
        S.neg(s), S.num(0), c, S.num(0),
        S.num(0), S.num(0), S.num(0), S.num(1),
    ]),
), X0, next_y())

RotationZ = S.Proc("3D Matrix Rotation Z %s %s", ["slot", "deg"], warp=True)
_pre, c, s = _rot_common(RotationZ)
RotationZ.define(ctx, S.seq(
    _pre,
    mat_cells("(func) 3D mat base", [
        c, S.neg(s), S.num(0), S.num(0),
        s, c, S.num(0), S.num(0),
        S.num(0), S.num(0), S.num(1), S.num(0),
        S.num(0), S.num(0), S.num(0), S.num(1),
    ]),
), X0, next_y())

Multiply = S.Proc("3D Matrix Multiply %s %s %s", ["slot", "left", "right"], warp=True)


def _mult_cell(r, c_):
    bl, br = S.var("(func) 3D mat base l"), S.var("(func) 3D mat base r")
    terms = []
    for k in range(1, 5):
        li = (r - 1) * 4 + k
        ri = (k - 1) * 4 + c_
        terms.append(S.mul(
            S.listitem("3D_mat_ram", S.add(bl, S.num(li))),
            S.listitem("3D_mat_ram", S.add(br, S.num(ri))),
        ))
    return S.add(S.add(terms[0], terms[1]), S.add(terms[2], terms[3]))


_mult_write_scratch = S.seq(*[
    S.list_replace("3D_mat_ram", S.num(MULT_SCRATCH_BASE + (r - 1) * 4 + c_), _mult_cell(r, c_))
    for r in range(1, 5) for c_ in range(1, 5)
])
_mult_copy_out = S.seq(*[
    S.list_replace(
        "3D_mat_ram", S.add(S.var("(func) 3D mat base o"), S.num(k)),
        S.listitem("3D_mat_ram", S.num(MULT_SCRATCH_BASE + k)),
    ) for k in range(1, 17)
])
Multiply.define(ctx, S.seq(
    S.setvar("(func) 3D mat base l", S.mul(Multiply.arg("left"), S.num(16))),
    S.setvar("(func) 3D mat base r", S.mul(Multiply.arg("right"), S.num(16))),
    S.setvar("(func) 3D mat base o", S.mul(Multiply.arg("slot"), S.num(16))),
    _mult_write_scratch,
    _mult_copy_out,
), X0, next_y())

Copy = S.Proc("3D Matrix Copy %s %s", ["from", "to"], warp=True)
Copy.define(ctx, S.seq(
    S.setvar("(func) 3D mat base from", S.mul(Copy.arg("from"), S.num(16))),
    S.setvar("(func) 3D mat base to", S.mul(Copy.arg("to"), S.num(16))),
    S.seq(*[
        S.list_replace(
            "3D_mat_ram", S.add(S.var("(func) 3D mat base to"), S.num(k)),
            S.listitem("3D_mat_ram", S.add(S.var("(func) 3D mat base from"), S.num(k))),
        ) for k in range(1, 17)
    ]),
), X0, next_y())

MatrixGet = S.Proc("3D Matrix Get %s %s %s", ["slot", "row", "col"], warp=True)
MatrixGet.define(ctx, S.seq(
    S.setvar("(func) 3D mat base", S.mul(MatrixGet.arg("slot"), S.num(16))),
    S.setvar("(return) 3D Matrix Get", S.listitem(
        "3D_mat_ram",
        S.add(S.var("(func) 3D mat base"),
              S.add(S.mul(S.sub(MatrixGet.arg("row"), S.num(1)), S.num(4)), MatrixGet.arg("col"))),
    )),
), X0, next_y())

CameraView = S.Proc("3D Matrix Camera View %s", ["slot"], warp=True)
CameraView.define(ctx, S.seq(
    RotationZ.call(slot=S.num(SLOT_TMP1), deg=S.neg(S.var("3D_camera_roll"))),
    RotationX.call(slot=S.num(SLOT_TMP2), deg=S.neg(S.var("3D_camera_pitch"))),
    Multiply.call(slot=S.num(SLOT_TMP1), left=S.num(SLOT_TMP2), right=S.num(SLOT_TMP1)),
    RotationY.call(slot=S.num(SLOT_TMP2), deg=S.neg(S.var("3D_camera_yaw"))),
    Multiply.call(slot=S.num(SLOT_TMP1), left=S.num(SLOT_TMP2), right=S.num(SLOT_TMP1)),
    Translation.call(
        slot=S.num(SLOT_TMP2),
        x=S.neg(S.var("3D_camera_x")), y=S.neg(S.var("3D_camera_y")), z=S.neg(S.var("3D_camera_z")),
    ),
    Multiply.call(slot=CameraView.arg("slot"), left=S.num(SLOT_TMP1), right=S.num(SLOT_TMP2)),
), X0, next_y())

LookAt = S.Proc("3D Camera Look At %s %s %s", ["x", "y", "z"], warp=True)
dx, dy, dz = S.var("(func) 3D la dx"), S.var("(func) 3D la dy"), S.var("(func) 3D la dz")
h = S.var("(func) 3D la h")
LookAt.define(ctx, S.seq(
    S.setvar("(func) 3D la dx", S.sub(LookAt.arg("x"), S.var("3D_camera_x"))),
    S.setvar("(func) 3D la dy", S.sub(LookAt.arg("y"), S.var("3D_camera_y"))),
    S.setvar("(func) 3D la dz", S.sub(LookAt.arg("z"), S.var("3D_camera_z"))),
    S.setvar("(func) 3D la h", S.sqrt(S.add(S.mul(dx, dx), S.mul(dz, dz)))),
    S.control_if_else(
        S.gt(dz, S.num(0)),
        S.seq(S.setvar("3D_camera_yaw", S.atan(S.div(dx, dz)))),
        S.seq(S.control_if_else(
            S.lt(dz, S.num(0)),
            S.seq(S.control_if_else(
                S.gte(dx, S.num(0)),
                S.seq(S.setvar("3D_camera_yaw", S.add(S.atan(S.div(dx, dz)), S.num(180)))),
                S.seq(S.setvar("3D_camera_yaw", S.sub(S.atan(S.div(dx, dz)), S.num(180)))),
            )),
            S.seq(S.control_if_else(
                S.gt(dx, S.num(0)),
                S.seq(S.setvar("3D_camera_yaw", S.num(90))),
                S.seq(S.control_if_else(
                    S.lt(dx, S.num(0)),
                    S.seq(S.setvar("3D_camera_yaw", S.num(-90))),
                    S.seq(S.setvar("3D_camera_yaw", S.num(0))),
                )),
            )),
        )),
    ),
    S.control_if_else(
        S.gt(h, S.num(0)),
        S.seq(S.setvar("3D_camera_pitch", S.atan(S.div(dy, h)))),
        S.seq(S.control_if_else(
            S.gt(dy, S.num(0)),
            S.seq(S.setvar("3D_camera_pitch", S.num(90))),
            S.seq(S.control_if_else(
                S.lt(dy, S.num(0)),
                S.seq(S.setvar("3D_camera_pitch", S.num(-90))),
                S.seq(S.setvar("3D_camera_pitch", S.num(0))),
            )),
        )),
    ),
), X0, next_y())

# ---------------------------------------------------------------------------
# 4. Setup, Apply, Project
# ---------------------------------------------------------------------------

Init = S.Proc("3D Init", [], warp=False)
_all_bufs = NEW_LISTS
Init.define(ctx, S.seq(
    S.seq(*[S.list_delete_all(n) for n in _all_bufs]),
    S.list_delete_all("3D_mat_ram"),
    S.control_repeat(S.var("3D_vertex_capacity"), S.seq(*[
        S.list_add(n, S.num(0)) for n in _all_bufs
    ])),
    S.control_repeat(S.num(MAT_RAM_LEN), S.seq(S.list_add("3D_mat_ram", S.num(0)))),
), X0, next_y())


def _affine_row(base1):
    i = S.var("(func) 3D range i")
    m = lambda k: S.listitem("3D_mat_ram", S.num(base1 + k - 1))
    return S.add(
        S.add(S.mul(m(1), S.listitem("3D_src_x", i)), S.mul(m(2), S.listitem("3D_src_y", i))),
        S.add(S.mul(m(3), S.listitem("3D_src_z", i)), m(4)),
    )


ApplyRange = S.Proc("3D Apply Range %s %s", ["s", "e"], warp=True)
i = S.var("(func) 3D range i")
ApplyRange.define(ctx, S.seq(
    S.setvar("(func) 3D range i", ApplyRange.arg("s")),
    S.control_repeat_until(S.gt(i, ApplyRange.arg("e")), S.seq(
        S.list_replace("3D_cam_x", i, _affine_row(1)),
        S.list_replace("3D_cam_y", i, _affine_row(5)),
        S.list_replace("3D_cam_z", i, _affine_row(9)),
        S.changevar("(func) 3D range i", S.num(1)),
    )),
), X0, next_y())

ApplyAll = S.Proc("3D Apply All", [], warp=True)
ApplyAll.define(ctx, S.seq(
    ApplyRange.call(s=S.num(1), e=S.var("3D_vertex_capacity")),
), X0, next_y())

projz = S.var("(func) 3D proj z")
projsx = S.var("(func) 3D proj sx")
projsy = S.var("(func) 3D proj sy")

ProjectRange = S.Proc("3D Project Range %s %s", ["s", "e"], warp=True)
i = S.var("(func) 3D range i")
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
                S.list_replace("3D_visible", i, S.num(0)),
            ),
        ),
        S.changevar("(func) 3D range i", S.num(1)),
    )),
), X0, next_y())

ProjectAll = S.Proc("3D Project All", [], warp=True)
ProjectAll.define(ctx, S.seq(
    ProjectRange.call(s=S.num(1), e=S.var("3D_vertex_capacity")),
), X0, next_y())

# ---------------------------------------------------------------------------
# 5. Dev demo: rotating unit cube, drawn with the pen, wired to "d" key.
# ---------------------------------------------------------------------------

CUBE_X = [-1, 1, -1, 1, -1, 1, -1, 1]
CUBE_Y = [1, 1, -1, -1, 1, 1, -1, -1]
CUBE_Z = [-1, -1, -1, -1, 1, 1, 1, 1]

DrawTestCube = S.Proc("3D Dev Draw Test Cube", [], warp=False)
_seed = S.seq(*[
    stmt
    for idx in range(8)
    for stmt in (
        S.list_replace("3D_src_x", S.num(idx + 1), S.num(CUBE_X[idx] * 100)),
        S.list_replace("3D_src_y", S.num(idx + 1), S.num(CUBE_Y[idx] * 100)),
        S.list_replace("3D_src_z", S.num(idx + 1), S.num(CUBE_Z[idx] * 100)),
    )
])

vs = S.var("(func) 3D cube vs")
ve = S.var("(func) 3D cube ve")
ei = S.var("(func) 3D cube edge i")

_edge_loop = S.seq(
    S.setvar("(func) 3D cube edge i", S.num(1)),
    S.control_repeat_until(S.gt(ei, S.num(12)), S.seq(
        S.setvar("(func) 3D cube vs", S.listitem("unit_cube_edges_start", ei)),
        S.setvar("(func) 3D cube ve", S.listitem("unit_cube_edges_end", ei)),
        S.control_if(
            S.AND(
                S.eq(S.listitem("3D_visible", vs), S.num(1)),
                S.eq(S.listitem("3D_visible", ve), S.num(1)),
            ),
            S.seq(
                S.pen_up(),
                S.goto_xy(S.listitem("3D_screen_x", vs), S.listitem("3D_screen_y", vs)),
                S.pen_down(),
                S.goto_xy(S.listitem("3D_screen_x", ve), S.listitem("3D_screen_y", ve)),
                S.pen_up(),
            ),
        ),
        S.changevar("(func) 3D cube edge i", S.num(1)),
    )),
)

DrawTestCube.define(ctx, S.seq(
    _seed,
    RotationY.call(slot=S.num(SLOT_A), deg=S.var("(func) 3D cube angle")),
    RotationX.call(slot=S.num(SLOT_B), deg=S.mul(S.var("(func) 3D cube angle"), S.num(0.5))),
    Multiply.call(slot=S.num(SLOT_A), left=S.num(SLOT_B), right=S.num(SLOT_A)),
    CameraView.call(slot=S.num(SLOT_B)),
    Multiply.call(slot=S.num(SLOT_ACTIVE), left=S.num(SLOT_B), right=S.num(SLOT_A)),
    ApplyRange.call(s=S.num(1), e=S.num(8)),
    ProjectRange.call(s=S.num(1), e=S.num(8)),
    S.pen_clear(),
    S.pen_color(S.color("#39ff6a")),
    _edge_loop,
    S.changevar("(func) 3D cube angle", S.num(2)),
    S.setvar("(func) 3D cube angle", S.mod(S.var("(func) 3D cube angle"), S.num(360))),
), X0, next_y())

demo_hat = S.place_top(
    ctx,
    S.hat_keypressed("d"),
    S.seq(
        Init.call(),
        S.control_forever(S.seq(DrawTestCube.call())),
    ),
    X0, next_y(),
)

print(f"generated {ctx._n} new block ids")

with open(PROJECT_JSON, "w") as f:
    json.dump(proj, f)

print("wrote", PROJECT_JSON)
