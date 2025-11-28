#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tools/inspect_workflow.py

用途：
- 可视化/打印 JSON 中的 OT-Flex 甲板布局（A1..D4），以及每个槽位被哪些节点/函数使用
- 打印推导的执行顺序（考虑 parallel/ sequential）以便核对是否符合实验步骤

使用：
  python tools/inspect_workflow.py --json /path/to/completeflexelectrodep_workflow-FILLED.json [--gui]

说明：
- --gui 可选，弹出一个简单 Tkinter 视图网格 A..D x 1..4。若运行环境不支持 GUI，则仅打印到控制台。
"""

import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set, Optional

def load_wf(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

FLEX_ROWS = ['A','B','C','D']
FLEX_COLS = ['1','2','3','4']

def norm_deck(deck: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    slots = (deck or {}).get('slots', {}) or {}
    out: Dict[str, Dict[str, Any]] = {}
    def is_label(s: str) -> bool:
        return isinstance(s, str) and len(s) == 2 and s[0].upper() in FLEX_ROWS and s[1] in FLEX_COLS
    # 1..16 column-major
    num2label = {
        1:'A1',2:'B1',3:'C1',4:'D1', 5:'A2',6:'B2',7:'C2',8:'D2', 9:'A3',10:'B3',11:'C3',12:'D3', 13:'A4',14:'B4',15:'C4',16:'D4'
    }
    for k, rec in slots.items():
        lbl = None
        if is_label(k):
            lbl = k.upper()
        else:
            try:
                n = int(k)
                lbl = num2label.get(n)
            except Exception:
                lbl = None
        out[str(k)] = {**(rec or {}), 'slot_label': lbl}
    return out

def reverse_labware_mapping(deck_norm: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    """labware alias/name -> slot_label"""
    m: Dict[str, str] = {}
    for k, rec in deck_norm.items():
        lbl = rec.get('slot_label')
        if not lbl:
            continue
        # Prefer explicit name if given, else labware model id
        alias = rec.get('name') or ''
        lw = rec.get('labware') or ''
        if alias:
            m[alias] = lbl
        if lw:
            m[lw] = lbl
    return m

def collect_slot_usage(wf: Dict[str, Any], name2slot: Dict[str, str]) -> Dict[str, List[str]]:
    """Return mapping: slot_label -> list of node type/labels that reference that labware name."""
    usage: Dict[str, List[str]] = {}
    for node in wf['workflow']['nodes']:
        ntype = node.get('type','')
        label = node.get('data',{}).get('label', ntype)
        params = node.get('params') or node.get('data', {}).get('params') or {}

        def add(name: Optional[str]):
            if not name:
                return
            slot = name2slot.get(name)
            if not slot:
                return
            usage.setdefault(slot, []).append(f"{label} :: {ntype}")

        # Common patterns
        if isinstance(params.get('from'), dict):
            add(params['from'].get('labware'))
        if isinstance(params.get('to'), dict):
            add(params['to'].get('labware'))
        # Other node types may directly reference labware names
        for key in ('labware','source_labware','dest_labware','plate','target_labware'):
            if key in params and isinstance(params[key], str):
                add(params[key])

    return usage

def build_graph(wf: Dict[str, Any]):
    nodes = {n['id']: n for n in wf['workflow']['nodes']}
    edges = wf['workflow']['edges']
    parents = {nid: set() for nid in nodes}
    children = {nid: [] for nid in nodes}
    emode = {}
    for e in edges:
        s, t = e['source'], e['target']
        parents[t].add(s)
        children[s].append(t)
        emode[(s,t)] = (e.get('data',{}) or {}).get('mode') or e.get('mode','sequential')
    return nodes, parents, children, emode

def topo_order(wf: Dict[str, Any]) -> List[List[str]]:
    """Return a list of execution groups; inner list may be parallel nodes."""
    nodes, parents, children, emode = build_graph(wf)
    ready = [nid for nid, ps in parents.items() if not ps]
    done: Set[str] = set()
    order: List[List[str]] = []

    def par_group(curr: str) -> List[List[str]]:
        seq, par = [], []
        for ch in children.get(curr, []):
            if emode.get((curr,ch),'sequential') == 'parallel':
                par.append(ch)
            else:
                seq.append(ch)
        groups = []
        if par:
            groups.append(par)
        for s in seq:
            groups.append([s])
        return groups

    while ready:
        curr = ready.pop()
        if curr in done:
            continue
        order.append([curr])
        done.add(curr)
        for grp in par_group(curr):
            can = [n for n in grp if parents[n].issubset(done)]
            if len(grp) == 1:
                if can:
                    ready.append(can[0])
            else:
                if set(can) == set(grp):
                    order.append(grp)
                    done.update(grp)
        for nid, ps in parents.items():
            if nid not in done and ps.issubset(done):
                ready.append(nid)
    return order

def print_deck(deck_norm, usage):
    print("\n[Deck Mapping] (A..D x 1..4)")
    grid = {f"{r}{c}": '' for r in FLEX_ROWS for c in FLEX_COLS}
    for k, rec in deck_norm.items():
        lbl = rec.get('slot_label')
        if not lbl:
            continue
        alias = rec.get('display') or rec.get('name') or ''
        model = rec.get('labware') or ''
        grid[lbl] = alias or model or '(empty)'
    for r in FLEX_ROWS:
        row_vals = [grid[f"{r}{c}"] or '-' for c in FLEX_COLS]
        print(f" {r}: ", " | ".join(f"{v:20.20s}" for v in row_vals))
    print("\n[Per-slot Usage]")
    for rc in [f"{r}{c}" for r in FLEX_ROWS for c in FLEX_COLS]:
        items = usage.get(rc, [])
        if items:
            print(f"  {rc}: ")
            for it in items:
                print(f"    - {it}")

def maybe_gui(deck_norm, usage):
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        print("[GUI] Tkinter not available. Skipping GUI.")
        return
    root = tk.Tk()
    root.title('OT-Flex Deck Mapping (A..D x 1..4)')
    for j,c in enumerate(['']+FLEX_COLS):
        ttk.Label(root, text=c, font=('Arial', 10, 'bold')).grid(row=0, column=j, padx=6, pady=6)
    # build cell text
    grid = {f"{r}{c}": '' for r in FLEX_ROWS for c in FLEX_COLS}
    for k, rec in deck_norm.items():
        lbl = rec.get('slot_label')
        if not lbl:
            continue
        alias = rec.get('display') or rec.get('name') or ''
        model = rec.get('labware') or ''
        use = usage.get(lbl, [])
        cell = alias or model or '(empty)'
        if use:
            cell += "\n" + "\n".join(f"- {x}" for x in use[:5])
            if len(use) > 5:
                cell += f"\n(+{len(use)-5} more)"
        grid[lbl] = cell
    for i,r in enumerate(FLEX_ROWS, start=1):
        ttk.Label(root, text=r, font=('Arial', 10, 'bold')).grid(row=i, column=0, padx=6, pady=6)
        for j,c in enumerate(FLEX_COLS, start=1):
            txt = grid[f"{r}{c}"] or '-'
            lab = ttk.Label(root, text=txt, relief=tk.GROOVE, padding=8, anchor='w', justify='left')
            lab.grid(row=i, column=j, sticky='nsew', padx=4, pady=4)
            root.grid_columnconfigure(j, weight=1)
    root.mainloop()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', required=True, help='Path to FILLED workflow JSON')
    ap.add_argument('--gui', action='store_true', help='Show GUI window (Tkinter)')
    ap.add_argument('--friendly', action='store_true', help='Print friendly step list with deck slots')
    args = ap.parse_args()

    wf = load_wf(Path(args.json))

    devices = (wf.get('devices', {}) or {})
    deck_cfg = devices.get('otflex', {}).get('deck', {})
    ref = devices.get('otflex_file')
    if ref:
        try:
            ref_path = (Path(args.json).parent / ref).resolve()
            deck_cfg = json.loads(ref_path.read_text(encoding='utf-8')).get('deck', {})
            print(f"[Inspector] Loaded otflex deck from {ref}")
        except Exception as e:
            print(f"[Inspector][WARN] Failed to load otflex_file {ref}: {e}")
    deck_norm = norm_deck(deck_cfg)
    name2slot = reverse_labware_mapping(deck_norm)
    usage = collect_slot_usage(wf, name2slot)
    order = topo_order(wf)

    print_deck(deck_norm, usage)

    nodes = {n['id']: n for n in wf['workflow']['nodes']}

    def node_slots(n: Dict[str, Any]) -> List[str]:
        params = n.get('params') or n.get('data', {}).get('params') or {}
        slots: List[str] = []
        def slot_of(name: Optional[str]) -> Optional[str]:
            if not name:
                return None
            return name2slot.get(name)
        # transfer: from/to
        if isinstance(params.get('from'), dict) or isinstance(params.get('to'), dict):
            f = (params.get('from') or {}).get('labware')
            t = (params.get('to') or {}).get('labware')
            fs = slot_of(f); ts = slot_of(t)
            pair = []
            if fs: pair.append(fs)
            if ts and ts != fs: pair.append(ts)
            if pair:
                slots.append('→'.join(pair))
        # single labware keys
        for key in ('labware','source_labware','dest_labware','plate','target_labware'):
            if key in params and isinstance(params[key], str):
                s = slot_of(params[key])
                if s and s not in slots:
                    slots.append(s)
        return slots

    if args.friendly:
        print("\n[Plain-Language Execution Order]")
        friendly = {
            'input': '开始（输入参数）',
            'output': '结束',
            'otflexMyxArmPosition': '机械臂移动到位',
            'otflexMyxArmGripper': '机械臂夹爪动作',
            'otflexGripper': 'Flex夹爪动作',
            'otflexArduinoReactor': '反应器控制',
            'otflexTransfer': '移液（吸/吐）',
            'otflexArduinoElectrode': '电极切换/选择',
            'sdl1ElectrodeManipulation': '电极定位/插拔',
            'sdl1ElectrodeSetup': '电极安装/设置',
            'sdl1ElectrochemicalMeasurement': '电化学测量',
            'otflexElectrodeWash': '电极清洗',
            'otflexArduinoPump': '液路泵动作',
            'otflexArduinoFurnace': '加热炉动作',
        }
        step = 1
        for grp in order:
            if len(grp) == 1:
                n = nodes.get(grp[0]);
                if not n: continue
                typ = n.get('type','')
                label = n.get('data',{}).get('label') or friendly.get(typ) or typ
                slots = node_slots(n)
                suffix = f" [Deck: {', '.join(slots)}]" if slots else ""
                print(f"- Step {step}: {label}{suffix}")
                step += 1
            else:
                names = []
                for nid in grp:
                    n = nodes.get(nid)
                    if not n: continue
                    typ = n.get('type','')
                    label = n.get('data',{}).get('label') or friendly.get(typ) or typ
                    slots = node_slots(n)
                    suffix = f" (Deck: {', '.join(slots)})" if slots else ""
                    names.append(label + suffix)
                if names:
                    print(f"- Parallel: " + " | ".join(names))
    else:
        print("\n[Derived Execution Order]")
        for grp in order:
            if len(grp) == 1:
                n = nodes.get(grp[0])
                if n:
                    print(f"  -> {grp[0]} :: {n.get('type')} :: {n.get('data',{}).get('label', n.get('type'))}")
            else:
                labels = []
                for nid in grp:
                    n = nodes.get(nid)
                    if n:
                        labels.append(f"{nid}::{n.get('type')}")
                print("  || PARALLEL:", ", ".join(labels))

    if args.gui:
        maybe_gui(deck_norm, usage)

if __name__ == '__main__':
    main()
