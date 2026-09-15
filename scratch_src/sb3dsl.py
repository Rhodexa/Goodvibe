"""
Minimal DSL for programmatically authoring Scratch 3 (.sb3) block JSON.

Block shapes were reverse engineered directly from this project's own
project.json (see dump.py) rather than assumed, with the following
exceptions which are standard, well-documented scratch-vm sb3 shapes not
otherwise present anywhere in this file: control_repeat_until,
event_whenkeypressed.

Core idea: an "expr" is a python callable `f(ctx, parent_id) -> input_array`
that, given the id of the block that will contain it, creates whatever
child blocks it needs (with that parent) and returns the value to put in
the parent's `inputs[KEY]`. A "stmt" is a callable `f(ctx, parent_id) ->
block_id` that creates exactly one command block with the given parent and
returns its id (next/parent wiring across a sequence is handled by seq()).
"""
import json


class Ctx:
    def __init__(self, blocks, variables, lists, id_prefix):
        self.blocks = blocks
        self.variables = variables
        self.lists = lists
        self.var_by_name = {v[0]: k for k, v in variables.items()}
        self.list_by_name = {v[0]: k for k, v in lists.items()}
        self._n = 0
        self._prefix = id_prefix

    def new_id(self):
        self._n += 1
        return f"{self._prefix}{self._n:05d}"

    def ensure_var(self, name, default=0):
        if name in self.var_by_name:
            return self.var_by_name[name]
        vid = self.new_id()
        self.variables[vid] = [name, default]
        self.var_by_name[name] = vid
        return vid

    def ensure_list(self, name, default=None):
        if name in self.list_by_name:
            return self.list_by_name[name]
        vid = self.new_id()
        self.lists[vid] = [name, default if default is not None else []]
        self.list_by_name[name] = vid
        return vid


def _fmt(v):
    return str(v)


# ---- expressions (reporters) -------------------------------------------

def num(value):
    def f(ctx, parent):
        return [1, [4, _fmt(value)]]
    return f


def text(value):
    def f(ctx, parent):
        return [1, [10, _fmt(value)]]
    return f


def var(name):
    def f(ctx, parent):
        vid = ctx.ensure_var(name)
        return [3, [12, name, vid], [10, ""]]
    return f


def arg(name):
    def f(ctx, parent):
        bid = ctx.new_id()
        ctx.blocks[bid] = {
            "opcode": "argument_reporter_string_number",
            "next": None, "parent": parent,
            "inputs": {}, "fields": {"VALUE": [name, None]},
            "shadow": False, "topLevel": False,
        }
        return [2, bid]
    return f


def listitem(listname, index_expr):
    def f(ctx, parent):
        bid = ctx.new_id()
        lid = ctx.ensure_list(listname)
        idx_in = index_expr(ctx, bid)
        ctx.blocks[bid] = {
            "opcode": "data_itemoflist", "next": None, "parent": parent,
            "inputs": {"INDEX": idx_in},
            "fields": {"LIST": [listname, lid]},
            "shadow": False, "topLevel": False,
        }
        return [2, bid]
    return f


def listlen(listname):
    def f(ctx, parent):
        bid = ctx.new_id()
        lid = ctx.ensure_list(listname)
        ctx.blocks[bid] = {
            "opcode": "data_lengthoflist", "next": None, "parent": parent,
            "inputs": {}, "fields": {"LIST": [listname, lid]},
            "shadow": False, "topLevel": False,
        }
        return [2, bid]
    return f


def _binop(opcode, a, b, k1="NUM1", k2="NUM2"):
    def f(ctx, parent):
        bid = ctx.new_id()
        i1 = a(ctx, bid)
        i2 = b(ctx, bid)
        ctx.blocks[bid] = {
            "opcode": opcode, "next": None, "parent": parent,
            "inputs": {k1: i1, k2: i2}, "fields": {},
            "shadow": False, "topLevel": False,
        }
        return [2, bid]
    return f


def add(a, b): return _binop("operator_add", a, b)
def sub(a, b): return _binop("operator_subtract", a, b)
def mul(a, b): return _binop("operator_multiply", a, b)
def div(a, b): return _binop("operator_divide", a, b)
def mod(a, b): return _binop("operator_mod", a, b)
def gt(a, b): return _binop("operator_gt", a, b, "OPERAND1", "OPERAND2")
def lt(a, b): return _binop("operator_lt", a, b, "OPERAND1", "OPERAND2")
def eq(a, b): return _binop("operator_equals", a, b, "OPERAND1", "OPERAND2")
def AND(a, b): return _binop("operator_and", a, b, "OPERAND1", "OPERAND2")
def OR(a, b): return _binop("operator_or", a, b, "OPERAND1", "OPERAND2")


def lte(a, b): return NOT(gt(a, b))
def gte(a, b): return NOT(lt(a, b))
def neg(a): return sub(num(0), a)


def NOT(a):
    def f(ctx, parent):
        bid = ctx.new_id()
        i = a(ctx, bid)
        ctx.blocks[bid] = {
            "opcode": "operator_not", "next": None, "parent": parent,
            "inputs": {"OPERAND": i}, "fields": {},
            "shadow": False, "topLevel": False,
        }
        return [2, bid]
    return f


def mathop(op, a):
    def f(ctx, parent):
        bid = ctx.new_id()
        i = a(ctx, bid)
        ctx.blocks[bid] = {
            "opcode": "operator_mathop", "next": None, "parent": parent,
            "inputs": {"NUM": i}, "fields": {"OPERATOR": [op, None]},
            "shadow": False, "topLevel": False,
        }
        return [2, bid]
    return f


def sin(a): return mathop("sin", a)
def cos(a): return mathop("cos", a)
def atan(a): return mathop("atan", a)
def sqrt(a): return mathop("sqrt", a)
def absv(a): return mathop("abs", a)


def color(hexstr):
    def f(ctx, parent):
        return [1, [9, hexstr]]
    return f


def join(a, b):
    def f(ctx, parent):
        bid = ctx.new_id()
        i1 = a(ctx, bid)
        i2 = b(ctx, bid)
        ctx.blocks[bid] = {
            "opcode": "operator_join", "next": None, "parent": parent,
            "inputs": {"STRING1": i1, "STRING2": i2}, "fields": {},
            "shadow": False, "topLevel": False,
        }
        return [2, bid]
    return f


# ---- statements (commands) ----------------------------------------------

def seq(*stmts):
    def f(ctx, owner_parent):
        prev_id = None
        first_id = None
        for s in stmts:
            this_parent = owner_parent if prev_id is None else prev_id
            bid = s(ctx, this_parent)
            if first_id is None:
                first_id = bid
            if prev_id is not None:
                ctx.blocks[prev_id]["next"] = bid
            # `s` may itself be a multi-statement seq(...): bid is then only
            # the *first* block of an already-internally-chained run. Walk to
            # its actual tail so the next sibling gets appended after the
            # whole run, instead of overwriting that internal chain's own
            # first .next link (which silently truncated it to one statement).
            tail = bid
            while ctx.blocks[tail].get("next") is not None:
                tail = ctx.blocks[tail]["next"]
            prev_id = tail
        return first_id
    return f


def setvar(name, value_expr):
    def f(ctx, parent):
        bid = ctx.new_id()
        vid = ctx.ensure_var(name)
        val_in = value_expr(ctx, bid)
        ctx.blocks[bid] = {
            "opcode": "data_setvariableto", "next": None, "parent": parent,
            "inputs": {"VALUE": val_in}, "fields": {"VARIABLE": [name, vid]},
            "shadow": False, "topLevel": False,
        }
        return bid
    return f


def changevar(name, value_expr):
    def f(ctx, parent):
        bid = ctx.new_id()
        vid = ctx.ensure_var(name)
        val_in = value_expr(ctx, bid)
        ctx.blocks[bid] = {
            "opcode": "data_changevariableby", "next": None, "parent": parent,
            "inputs": {"VALUE": val_in}, "fields": {"VARIABLE": [name, vid]},
            "shadow": False, "topLevel": False,
        }
        return bid
    return f


def list_replace(listname, index_expr, value_expr):
    def f(ctx, parent):
        bid = ctx.new_id()
        lid = ctx.ensure_list(listname)
        idx_in = index_expr(ctx, bid)
        val_in = value_expr(ctx, bid)
        ctx.blocks[bid] = {
            "opcode": "data_replaceitemoflist", "next": None, "parent": parent,
            "inputs": {"INDEX": idx_in, "ITEM": val_in},
            "fields": {"LIST": [listname, lid]},
            "shadow": False, "topLevel": False,
        }
        return bid
    return f


def list_add(listname, value_expr):
    def f(ctx, parent):
        bid = ctx.new_id()
        lid = ctx.ensure_list(listname)
        val_in = value_expr(ctx, bid)
        ctx.blocks[bid] = {
            "opcode": "data_addtolist", "next": None, "parent": parent,
            "inputs": {"ITEM": val_in}, "fields": {"LIST": [listname, lid]},
            "shadow": False, "topLevel": False,
        }
        return bid
    return f


def list_delete_all(listname):
    def f(ctx, parent):
        bid = ctx.new_id()
        lid = ctx.ensure_list(listname)
        ctx.blocks[bid] = {
            "opcode": "data_deletealloflist", "next": None, "parent": parent,
            "inputs": {}, "fields": {"LIST": [listname, lid]},
            "shadow": False, "topLevel": False,
        }
        return bid
    return f


def control_if(cond_expr, body_seq):
    def f(ctx, parent):
        bid = ctx.new_id()
        cond_in = cond_expr(ctx, bid)
        blk = {
            "opcode": "control_if", "next": None, "parent": parent,
            "inputs": {"CONDITION": cond_in}, "fields": {},
            "shadow": False, "topLevel": False,
        }
        ctx.blocks[bid] = blk
        if body_seq is not None:
            first = body_seq(ctx, bid)
            blk["inputs"]["SUBSTACK"] = [2, first]
        return bid
    return f


def control_if_else(cond_expr, then_seq, else_seq):
    def f(ctx, parent):
        bid = ctx.new_id()
        cond_in = cond_expr(ctx, bid)
        blk = {
            "opcode": "control_if_else", "next": None, "parent": parent,
            "inputs": {"CONDITION": cond_in}, "fields": {},
            "shadow": False, "topLevel": False,
        }
        ctx.blocks[bid] = blk
        then_first = then_seq(ctx, bid)
        else_first = else_seq(ctx, bid)
        blk["inputs"]["SUBSTACK"] = [2, then_first]
        blk["inputs"]["SUBSTACK2"] = [2, else_first]
        return bid
    return f


def control_forever(body_seq):
    def f(ctx, parent):
        bid = ctx.new_id()
        blk = {
            "opcode": "control_forever", "next": None, "parent": parent,
            "inputs": {}, "fields": {}, "shadow": False, "topLevel": False,
        }
        ctx.blocks[bid] = blk
        first = body_seq(ctx, bid)
        blk["inputs"]["SUBSTACK"] = [2, first]
        return bid
    return f


def control_repeat(times_expr, body_seq):
    def f(ctx, parent):
        bid = ctx.new_id()
        times_in = times_expr(ctx, bid)
        blk = {
            "opcode": "control_repeat", "next": None, "parent": parent,
            "inputs": {"TIMES": times_in}, "fields": {},
            "shadow": False, "topLevel": False,
        }
        ctx.blocks[bid] = blk
        first = body_seq(ctx, bid)
        blk["inputs"]["SUBSTACK"] = [2, first]
        return bid
    return f


def control_repeat_until(cond_expr, body_seq):
    def f(ctx, parent):
        bid = ctx.new_id()
        cond_in = cond_expr(ctx, bid)
        blk = {
            "opcode": "control_repeat_until", "next": None, "parent": parent,
            "inputs": {"CONDITION": cond_in}, "fields": {},
            "shadow": False, "topLevel": False,
        }
        ctx.blocks[bid] = blk
        first = body_seq(ctx, bid)
        blk["inputs"]["SUBSTACK"] = [2, first]
        return bid
    return f


def pen_clear():
    def f(ctx, parent):
        bid = ctx.new_id()
        ctx.blocks[bid] = {
            "opcode": "pen_clear", "next": None, "parent": parent,
            "inputs": {}, "fields": {}, "shadow": False, "topLevel": False,
        }
        return bid
    return f


def pen_down():
    def f(ctx, parent):
        bid = ctx.new_id()
        ctx.blocks[bid] = {
            "opcode": "pen_penDown", "next": None, "parent": parent,
            "inputs": {}, "fields": {}, "shadow": False, "topLevel": False,
        }
        return bid
    return f


def pen_up():
    def f(ctx, parent):
        bid = ctx.new_id()
        ctx.blocks[bid] = {
            "opcode": "pen_penUp", "next": None, "parent": parent,
            "inputs": {}, "fields": {}, "shadow": False, "topLevel": False,
        }
        return bid
    return f


def pen_color(color_expr):
    def f(ctx, parent):
        bid = ctx.new_id()
        c_in = color_expr(ctx, bid)
        ctx.blocks[bid] = {
            "opcode": "pen_setPenColorToColor", "next": None, "parent": parent,
            "inputs": {"COLOR": c_in}, "fields": {}, "shadow": False, "topLevel": False,
        }
        return bid
    return f


def goto_xy(x_expr, y_expr):
    def f(ctx, parent):
        bid = ctx.new_id()
        x_in = x_expr(ctx, bid)
        y_in = y_expr(ctx, bid)
        ctx.blocks[bid] = {
            "opcode": "motion_gotoxy", "next": None, "parent": parent,
            "inputs": {"X": x_in, "Y": y_in}, "fields": {},
            "shadow": False, "topLevel": False,
        }
        return bid
    return f


class Proc:
    """A custom block ("procedure") definition + call-site factory."""

    def __init__(self, proccode, params, warp):
        assert proccode.count("%s") == len(params), proccode
        self.proccode = proccode
        self.params = params
        self.warp = warp
        self.def_id = None
        self.proto_id = None
        self.argids = None

    def define(self, ctx, body_seq, x, y):
        def_id = ctx.new_id()
        proto_id = ctx.new_id()
        # Scratch binds a call's argument VALUES to the callee by argid, not
        # by name or position - the call block's own inputs dict is keyed by
        # argid, and the interpreter looks those ids up directly against the
        # CURRENT prototype's argumentids. So if this proccode already has
        # call sites elsewhere (we're deleting+regenerating an existing
        # block, e.g. to add a feature) and we hand out fresh random argids
        # here, every one of those existing calls silently starts passing
        # empty-string defaults instead of its real arguments - no error,
        # just wrong output. Reuse the existing call sites' argids instead,
        # so old calls keep working against the new definition.
        existing_argids = None
        for b in ctx.blocks.values():
            if isinstance(b, dict) and b.get("opcode") == "procedures_call" \
                    and b.get("mutation", {}).get("proccode") == self.proccode:
                existing_argids = json.loads(b["mutation"]["argumentids"])
                break
        if existing_argids is not None:
            assert len(existing_argids) == len(self.params), (
                f"{self.proccode}: existing call sites pass {len(existing_argids)} "
                f"argument(s) but this Proc declares {len(self.params)} param(s)"
            )
            argids = existing_argids
        else:
            argids = [ctx.new_id() for _ in self.params]
        ctx.blocks[def_id] = {
            "opcode": "procedures_definition", "next": None, "parent": None,
            "inputs": {"custom_block": [2, proto_id]}, "fields": {},
            "shadow": False, "topLevel": True, "x": x, "y": y,
        }
        ctx.blocks[proto_id] = {
            "opcode": "procedures_prototype", "next": None, "parent": def_id,
            "inputs": {}, "fields": {}, "shadow": False, "topLevel": False,
            "mutation": {
                "tagName": "mutation", "children": [],
                "proccode": self.proccode,
                "argumentids": json.dumps(argids),
                "argumentnames": json.dumps(self.params),
                "argumentdefaults": json.dumps([""] * len(self.params)),
                "warp": "true" if self.warp else "false",
            },
        }
        self.def_id, self.proto_id, self.argids = def_id, proto_id, argids
        if body_seq is not None:
            first = body_seq(ctx, def_id)
            ctx.blocks[def_id]["next"] = first
        return def_id

    def arg(self, name):
        assert name in self.params
        return arg(name)

    def attach(self, ctx):
        """Bind to an already-defined custom block with this proccode
        (e.g. from an earlier build script's run), instead of defining a
        new one. Lets a fresh script .call() into existing blocks without
        redefining/duplicating them."""
        for bid, b in ctx.blocks.items():
            if isinstance(b, dict) and b.get("opcode") == "procedures_prototype" \
                    and b.get("mutation", {}).get("proccode") == self.proccode:
                self.proto_id = bid
                self.def_id = b["parent"]
                self.argids = json.loads(b["mutation"]["argumentids"])
                return self
        raise ValueError(f"no existing definition found for proccode {self.proccode!r}")

    def call(self, **kwargs):
        assert self.argids is not None, "call() used before define()"
        for k in kwargs:
            assert k in self.params, f"unknown param {k!r} for {self.proccode}"

        def f(ctx, parent):
            bid = ctx.new_id()
            inputs = {}
            for pname, aid in zip(self.params, self.argids):
                expr = kwargs.get(pname)
                inputs[aid] = expr(ctx, bid) if expr is not None else [1, [10, ""]]
            ctx.blocks[bid] = {
                "opcode": "procedures_call", "next": None, "parent": parent,
                "inputs": inputs, "fields": {}, "shadow": False, "topLevel": False,
                "mutation": {
                    "tagName": "mutation", "children": [],
                    "proccode": self.proccode,
                    "argumentids": json.dumps(self.argids),
                    "warp": "true" if self.warp else "false",
                },
            }
            return bid
        return f


def hat_flag():
    def f(ctx, parent):
        bid = ctx.new_id()
        ctx.blocks[bid] = {
            "opcode": "event_whenflagclicked", "next": None, "parent": None,
            "inputs": {}, "fields": {}, "shadow": False, "topLevel": True,
        }
        return bid
    return f


def hat_keypressed(key):
    def f(ctx, parent):
        bid = ctx.new_id()
        ctx.blocks[bid] = {
            "opcode": "event_whenkeypressed", "next": None, "parent": None,
            "inputs": {}, "fields": {"KEY_OPTION": [key, None]},
            "shadow": False, "topLevel": True,
        }
        return bid
    return f


def place_top(ctx, hat_stmt, body_seq, x, y):
    hat_id = hat_stmt(ctx, None)
    ctx.blocks[hat_id]["x"] = x
    ctx.blocks[hat_id]["y"] = y
    if body_seq is not None:
        first = body_seq(ctx, hat_id)
        ctx.blocks[hat_id]["next"] = first
    return hat_id
