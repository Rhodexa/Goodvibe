import json, sys

with open("project.json") as f:
    proj = json.load(f)

errors = []
warnings = []

for target in proj["targets"]:
    blocks = target.get("blocks", {})
    variables = target.get("variables", {})
    lists = target.get("lists", {})
    name = target["name"]

    var_ids = set(variables.keys())
    list_ids = set(lists.keys())
    # also global stage vars/lists are visible to sprites
    stage = next(t for t in proj["targets"] if t["isStage"])
    if not target["isStage"]:
        var_ids |= set(stage["variables"].keys())
        list_ids |= set(stage["lists"].keys())

    block_ids = set(blocks.keys())

    def check_ref(bid, v, path):
        if not isinstance(v, list):
            return
        if len(v) >= 2 and isinstance(v[1], str) and v[1] not in block_ids:
            # could be a compact var/list ref that's actually a list, not str; already guarded
            pass

    for bid, b in blocks.items():
        if not isinstance(b, dict):
            continue
        op = b.get("opcode")
        # parent/next existence
        if b.get("parent") is not None and b["parent"] not in block_ids:
            errors.append(f"{name}/{bid}: parent {b['parent']} missing")
        if b.get("next") is not None and b["next"] not in block_ids:
            errors.append(f"{name}/{bid}: next {b['next']} missing")
        for key, v in b.get("inputs", {}).items():
            if not isinstance(v, list):
                errors.append(f"{name}/{bid}: input {key} malformed {v!r}")
                continue
            kind = v[0]
            if kind in (2, 3):
                ref = v[1]
                if isinstance(ref, str):
                    if ref not in block_ids:
                        errors.append(f"{name}/{bid}: input {key} -> missing block {ref}")
                elif isinstance(ref, list):
                    # compact var/list reporter [12,name,id] or [13,name,id]
                    if ref[0] == 12 and ref[2] not in var_ids:
                        errors.append(f"{name}/{bid}: input {key} var id {ref[2]} missing")
                    if ref[0] == 13 and ref[2] not in list_ids:
                        errors.append(f"{name}/{bid}: input {key} list id {ref[2]} missing")
                elif ref is None:
                    pass
                else:
                    errors.append(f"{name}/{bid}: input {key} weird ref {ref!r}")
        for key, v in b.get("fields", {}).items():
            if key == "VARIABLE" and isinstance(v, list) and len(v) > 1 and v[1] not in var_ids:
                errors.append(f"{name}/{bid}: field VARIABLE id {v[1]} missing")
            if key == "LIST" and isinstance(v, list) and len(v) > 1 and v[1] not in list_ids:
                errors.append(f"{name}/{bid}: field LIST id {v[1]} missing")
        if op == "procedures_call":
            mut = b.get("mutation", {})
            argids = json.loads(mut.get("argumentids", "[]"))
            for aid in argids:
                if aid not in b.get("inputs", {}):
                    errors.append(f"{name}/{bid}: call {mut.get('proccode')} missing input for argid {aid}")

    # every procedures_call's proccode must have a matching prototype somewhere in this target
    protos = {
        b["mutation"]["proccode"]
        for b in blocks.values()
        if isinstance(b, dict) and b.get("opcode") == "procedures_prototype"
    }
    for bid, b in blocks.items():
        if isinstance(b, dict) and b.get("opcode") == "procedures_call":
            pc = b["mutation"]["proccode"]
            if pc not in protos:
                errors.append(f"{name}/{bid}: call to undefined proc {pc!r}")

    # cycle check via next-chains from all topLevel blocks
    visited_global = set()
    for bid, b in blocks.items():
        if not isinstance(b, dict) or not b.get("topLevel"):
            continue
        seen = set()
        cur = bid
        while cur:
            if cur in seen:
                errors.append(f"{name}: cycle detected starting near {bid} at {cur}")
                break
            seen.add(cur)
            visited_global.add(cur)
            b2 = blocks.get(cur)
            if b2 is None:
                errors.append(f"{name}: dangling next from {cur}")
                break
            cur = b2.get("next")

if errors:
    print(f"FOUND {len(errors)} ERRORS:")
    for e in errors[:200]:
        print(" -", e)
    sys.exit(1)
else:
    print("OK: no structural errors found")
