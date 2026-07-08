#!/usr/bin/env python3
"""
SRC focus tree layout fix.

Fixes backward prereq edges by re-computing y-levels from the prereq graph.
SRC uses absolute coordinates — just adjust x,y. No gameplay changes.
"""
import re, sys, json
from collections import defaultdict

def find_matching_brace(text, open_idx):
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == '{': depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0: return i
    return -1

def blank_nested_braces(body):
    out = []; depth = 0
    for ch in body:
        if ch == '{': depth += 1; out.append(' ')
        elif ch == '}': depth -= 1; out.append(' ')
        else: out.append(ch if depth == 0 else (' ' if ch != '\n' else '\n'))
    return ''.join(out)

def parse_src(path):
    with open(path, 'r', encoding='utf-8-sig') as f:
        text = f.read()

    RE_FOCUS = re.compile(r'\bfocus\s*=\s*\{')
    RE_ID = re.compile(r'\bid\s*=\s*([A-Za-z0-9_.]+)')
    RE_X = re.compile(r'\bx\s*=\s*(-?\d+)')
    RE_Y = re.compile(r'\by\s*=\s*(-?\d+)')
    RE_PREREQ = re.compile(r'\bprerequisite\s*=\s*\{([^}]*)\}')
    RE_FOCUS_REF = re.compile(r'\bfocus\s*=\s*([A-Za-z0-9_.]+)')

    focuses = []
    for m in RE_FOCUS.finditer(text):
        oi = text.find('{', m.start())
        if oi == -1: continue
        ci = find_matching_brace(text, oi)
        if ci == -1: continue
        body = text[oi+1:ci]
        top = blank_nested_braces(body)
        id_m = RE_ID.search(top)
        if not id_m: continue
        fid = id_m.group(1)
        if not fid.startswith('SRC_sw_'): continue

        xm = RE_X.search(top)
        ym = RE_Y.search(top)
        prereqs = []
        for pm in RE_PREREQ.finditer(body):
            for fm in RE_FOCUS_REF.finditer(pm.group(1)):
                prereqs.append(fm.group(1))

        focuses.append({
            'id': fid, 'x': int(xm.group(1)) if xm else 0,
            'y': int(ym.group(1)) if ym else 0,
            'prereqs': prereqs,
            'block': text[oi:ci+1],
        })

    return text, focuses

def compute_y(focuses):
    """Recompute y so every child is below all its parents."""
    id_map = {f['id']: f for f in focuses}
    all_ids = set(id_map)

    # Compute depth = longest path from any root
    def depth(fid, visited=None):
        if visited is None: visited = set()
        if fid in visited: return 0
        if fid not in id_map: return 0
        visited.add(fid)
        prs = [p for p in id_map[fid]['prereqs'] if p in all_ids]
        if not prs: return 0
        return 1 + max(depth(p, set(visited)) for p in prs)

    # Assign y = depth
    for f in focuses:
        d = depth(f['id'])
        f['y_new'] = d

    # Build layer map for convergence spacing
    layers = defaultdict(list)
    for f in focuses:
        layers[f['y_new']].append(f['id'])

    # Ensure children are below parents (resolve convergence)
    changed = True
    while changed:
        changed = False
        for f in focuses:
            for pr in f['prereqs']:
                if pr in id_map and f['y_new'] <= id_map[pr]['y_new']:
                    f['y_new'] = id_map[pr]['y_new'] + 1
                    changed = True

def compute_x(focuses):
    """Adjust x: center convergence nodes between parents, keep others."""
    id_map = {f['id']: f for f in focuses}
    all_ids = set(id_map)

    for f in focuses:
        f['x_new'] = f['x']  # default: keep current x

        prs = [p for p in f['prereqs'] if p in all_ids]
        if len(prs) == 2:
            # Convergence: center between parents
            x0 = id_map[prs[0]]['x']
            x1 = id_map[prs[1]]['x']
            mid = (x0 + x1) // 2
            if abs(f['x'] - mid) > 2:
                f['x_new'] = mid
        elif len(prs) >= 3:
            # Gateway: center between all parents
            xs = [id_map[p]['x'] for p in prs]
            mid = sum(xs) // len(xs)
            f['x_new'] = mid

def resolve_collisions(focuses):
    """Shift overlapping focuses at same (x,y)."""
    pos = defaultdict(list)
    for f in focuses:
        pos[(f['x_new'], f['y_new'])].append(f['id'])

    for _ in range(20):
        changed = False
        for (x, y), ids in list(pos.items()):
            if len(ids) <= 1: continue
            ids.sort()
            for offset, fid in enumerate(ids):
                new_x = x + offset
                pos[(x, y)].remove(fid)
                if not pos.get((x, y)): del pos[(x, y)]
                pos[(new_x, y)].append(fid)
                for f in focuses:
                    if f['id'] == fid: f['x_new'] = new_x
            changed = True
        if not changed: break

def apply_changes(text, focuses):
    result = text
    for f in focuses:
        old_block = f['block']
        if f['y'] == f['y_new'] and f['x'] == f['x_new']:
            continue
        
        new_block = old_block
        new_block = re.sub(r'\bx\s*=\s*-?\d+', f'x = {f["x_new"]}', new_block)
        new_block = re.sub(r'\by\s*=\s*-?\d+', f'y = {f["y_new"]}', new_block)
        
        idx = result.find(old_block)
        if idx >= 0:
            result = result[:idx] + new_block + result[idx+len(old_block):]
    return result

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'common/national_focus/stormreaver_second_war.txt'
    text, focuses = parse_src(path)
    print(f'Parsed {len(focuses)} SRC focuses')

    compute_y(focuses)
    compute_x(focuses)
    resolve_collisions(focuses)

    changes = 0
    for f in sorted(focuses, key=lambda f: (f['y_new'], f['x_new'])):
        old = (f['x'], f['y'])
        new = (f['x_new'], f['y_new'])
        marker = ' **' if old != new else ''
        pr = ', '.join(f['prereqs']) or '-'
        print(f"  {f['id']:45s}  ({old[0]:2d},{old[1]:2d}) -> ({new[0]:2d},{new[1]:2d}){marker}  [{pr}]")
        if old != new: changes += 1

    print(f'\n{changes} coordinates changed')

    ys = [f['y_new'] for f in focuses]
    xs = [f['x_new'] for f in focuses]
    print(f'New bbox: x=[{min(xs)},{max(xs)}] y=[{min(ys)},{max(ys)}]')

    if '--dry' in sys.argv:
        print('[dry-run] no changes written')
        return

    new_text = apply_changes(text, focuses)
    with open(path, 'w', encoding='utf-8-sig') as f:
        f.write(new_text)
    print(f'Written: {path}')

main()
