// Arrange Scripts — TurboWarp dev-only extension.
// Load via Extensions → Custom Extension → Files, with "Run without sandbox" checked.
// Adds a palette button; no blocks are ever placed, so nothing gets saved into
// the project and the .sb3 stays vanilla-compatible.
//
// Layout: one top-down column (survives Scratch's own "Clean up").
//   1. entry hats that call custom blocks (most reachable procs first)
//   2. un-namespaced procs, in call order (DFS from the entries)
//   3. libraries (namespace prefix: "3D ...", "Ball::...", "(child) TriPlayer ..."),
//      callers before callees, each library in its own call order
//   4. loose fragments
// Hats with no custom-block calls (pure init: set var / fill list) sit directly
// above the first proc that uses one of their variables or lists.

(function (Scratch) {
  'use strict';

  function namespace(proccode) {
    const s = proccode.replace(/^\(child\)\s*/, '');
    const m = s.match(/^([^\s:]+)::?/);
    if (m) return m[1];
    const words = s.split(' ').filter(w => w && !/^%[sbn]$/.test(w));
    return words.length > 1 ? words[0] : '';
  }

  // blocks: VM-format map {id: {opcode, next, parent, topLevel, x, y, inputs:{k:{block}}, fields:{k:{id}}, mutation}}
  // Returns [{ids: [...topIds]}] groups in display order.
  function computeOrder(blocks) {
    const tops = Object.keys(blocks).filter(id => blocks[id].topLevel)
      .sort((a, b) => (blocks[a].y - blocks[b].y) || (blocks[a].x - blocks[b].x));

    // Script-ordered walk: calls (in order) and variable/list ids touched.
    function scan(topId) {
      const calls = [], vars = new Set();
      const visit = id => {
        while (id) {
          const b = blocks[id];
          if (!b) return;
          if (b.opcode === 'procedures_call') calls.push(b.mutation.proccode);
          for (const f of Object.values(b.fields || {})) {
            if ((f.name === 'VARIABLE' || f.name === 'LIST') && f.id) vars.add(f.id);
          }
          for (const inp of Object.values(b.inputs || {})) visit(inp.block);
          id = b.next;
        }
      };
      visit(topId);
      return {calls, vars};
    }

    const procTop = {}; // proccode -> top id
    const info = {};    // top id -> {kind, proccode?, calls, vars}
    for (const id of tops) {
      const b = blocks[id];
      const s = scan(id);
      if (b.opcode === 'procedures_definition') {
        const proto = blocks[b.inputs.custom_block.block];
        const pc = proto.mutation.proccode;
        procTop[pc] = id;
        info[id] = {kind: 'proc', proccode: pc, ns: namespace(pc), ...s};
      } else if (b.opcode.startsWith('event_when') || b.opcode.startsWith('control_start_as_clone')) {
        info[id] = {kind: s.calls.length ? 'entry' : 'init', ...s};
      } else {
        info[id] = {kind: 'loose', ...s};
      }
    }
    const callees = id => info[id].calls.map(pc => procTop[pc]).filter(Boolean);

    function reach(id, seen = new Set()) {
      for (const c of callees(id)) if (!seen.has(c)) { seen.add(c); reach(c, seen); }
      return seen;
    }
    const entries = tops.filter(id => info[id].kind === 'entry')
      .map(id => [id, reach(id).size])
      .sort((a, b) => b[1] - a[1])
      .map(e => e[0]);

    // Global discovery order of procs: DFS preorder from entries, then loose, then the rest.
    const disc = [], seen = new Set();
    const dfs = id => {
      for (const c of callees(id)) if (!seen.has(c)) { seen.add(c); disc.push(c); dfs(c); }
    };
    entries.forEach(dfs);
    tops.filter(id => info[id].kind === 'loose').forEach(dfs);
    for (const id of tops) {
      if (info[id].kind === 'proc' && !seen.has(id)) { seen.add(id); disc.push(id); dfs(id); }
    }

    // Library order: topo sort on cross-namespace calls, ties by discovery.
    const libs = [];
    for (const id of disc) { const ns = info[id].ns; if (ns && !libs.includes(ns)) libs.push(ns); }
    const deps = {}; // ns -> set of namespaces that call it
    libs.forEach(ns => { deps[ns] = new Set(); });
    for (const id of disc) {
      const from = info[id].ns;
      if (!from) continue;
      for (const c of callees(id)) {
        const to = info[c].ns;
        if (to && to !== from) deps[to].add(from);
      }
    }
    const libOrder = [];
    while (libOrder.length < libs.length) {
      const left = libs.filter(ns => !libOrder.includes(ns));
      const ready = left.find(ns => [...deps[ns]].every(d => libOrder.includes(d)));
      libOrder.push(ready || left[0]); // cycle: fall back to discovery order
    }

    // Init hats: bind to the proc sharing the most variables/lists with it; ties go
    // to the most specific proc (fewest vars overall), so orchestrators that merely
    // read a scene's timer don't steal that scene's init.
    const initsFor = {}, unbound = [];
    for (const id of tops.filter(id => info[id].kind === 'init')) {
      let target = null, best = [0, 0];
      for (const p of disc) {
        const shared = [...info[id].vars].filter(v => info[p].vars.has(v)).length;
        const score = [shared, -info[p].vars.size];
        if (shared && (score[0] > best[0] || (score[0] === best[0] && score[1] > best[1]))) {
          target = p; best = score;
        }
      }
      if (target) (initsFor[target] = initsFor[target] || []).push(id);
      else unbound.push(id);
    }
    const withInits = ids => ids.flatMap(p => [...(initsFor[p] || []), p]);

    const groups = [
      {name: 'entry', ids: [...entries, ...unbound]},
      {name: '(app)', ids: withInits(disc.filter(id => !info[id].ns))},
      ...libOrder.map(ns => ({name: ns, ids: withInits(disc.filter(id => info[id].ns === ns))})),
      {name: 'loose', ids: tops.filter(id => info[id].kind === 'loose')},
    ].filter(g => g.ids.length);
    return {groups, info};
  }

  if (typeof module !== 'undefined') module.exports = {computeOrder, namespace};
  if (!Scratch) return;

  class ArrangeScripts {
    getInfo() {
      return {
        id: 'rhodexaArrange',
        name: 'Arrange Scripts',
        blocks: [
          {blockType: Scratch.BlockType.BUTTON, text: 'Arrange scripts', func: 'arrange'},
        ],
      };
    }

    async arrange() {
      const vm = Scratch.vm;
      const SB = await Scratch.gui.getBlockly();
      const ws = SB.getMainWorkspace();
      const target = vm.editingTarget;
      if (!ws || !target) return;

      const {groups} = computeOrder(target.blocks._blocks);
      const gap = SB.BlockSvg.MIN_BLOCK_Y || 48;
      const groupGap = gap * 3;

      SB.Events.setGroup(true); // one Ctrl+Z undoes the whole arrange
      try {
        let y = 0;
        for (const g of groups) {
          for (const id of g.ids) {
            const block = ws.getBlockById(id);
            if (!block) continue;
            const xy = block.getRelativeToSurfaceXY();
            block.moveBy(-xy.x, y - xy.y);
            y += block.getHeightWidth().height + gap;
          }
          y += groupGap - gap;
        }
      } finally {
        SB.Events.setGroup(false);
      }
      ws.scrollbar && ws.scrollbar.set(0, 0);
    }
  }

  Scratch.extensions.register(new ArrangeScripts());
})(typeof Scratch !== 'undefined' ? Scratch : undefined);
