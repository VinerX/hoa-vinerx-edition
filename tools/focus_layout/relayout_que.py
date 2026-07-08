#!/usr/bin/env python3
"""
QUE Second War focus tree BRC-style re-layout.

Applies BRC layout principles to Quel'Thalas:
  - y+1 for simple children (not y+2)
  - Convergence nodes anchor to spine ancestors (not immediate prereqs)
  - ME pairs on same row, horizontal left/right
  - Victory spine: last N focuses in single column
  - Thematic x columns
  - Short relpos chains, key breakpoints at absolute x/y

Only modifies x, y, relative_position_id. Zero gameplay changes.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------
RE_FOCUS_BLOCK = re.compile(r'\bfocus\s*=\s*\{')
RE_SHARED_IMPORT = re.compile(r'\bshared_focus\s*=\s*([A-Za-z0-9_.]+)')
RE_ID = re.compile(r'\bid\s*=\s*([A-Za-z0-9_.]+)')
RE_RELPOS = re.compile(r'\brelative_position_id\s*=\s*([A-Za-z0-9_.]+)')
RE_X = re.compile(r'\bx\s*=\s*(-?\d+)')
RE_Y = re.compile(r'\by\s*=\s*(-?\d+)')
RE_PREREQ_BLOCK = re.compile(r'\bprerequisite\s*=\s*\{([^}]*)\}')
RE_ME_BLOCK = re.compile(r'\bmutually_exclusive\s*=\s*\{([^}]*)\}')
RE_FOCUS_REF = re.compile(r'\bfocus\s*=\s*([A-Za-z0-9_.]+)')


def find_matching_brace(text, open_idx):
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    return -1


def blank_nested_braces(body):
    out = []
    depth = 0
    for ch in body:
        if ch == '{':
            depth += 1
            out.append(' ')
        elif ch == '}':
            depth -= 1
            out.append(' ')
        else:
            out.append(ch if depth == 0 else (' ' if ch != '\n' else '\n'))
    return ''.join(out)


def parse_focus_file(filepath):
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        text = f.read()

    focuses = []
    for m in RE_FOCUS_BLOCK.finditer(text):
        open_idx = text.find('{', m.start())
        if open_idx == -1:
            continue
        close_idx = find_matching_brace(text, open_idx)
        if close_idx == -1:
            continue
        body = text[open_idx + 1 : close_idx]
        top = blank_nested_braces(body)

        id_m = RE_ID.search(top)
        if not id_m:
            continue
        fid = id_m.group(1)
        if not fid.startswith('QUE_sw_'):
            continue  # skip shared-backbone focuses

        relpos_m = RE_RELPOS.search(top)
        xm = RE_X.search(top)
        ym = RE_Y.search(top)

        prereqs = []
        for pm in RE_PREREQ_BLOCK.finditer(body):
            for fm in RE_FOCUS_REF.finditer(pm.group(1)):
                prereqs.append(fm.group(1))

        me_list = []
        for mm in RE_ME_BLOCK.finditer(body):
            for fm in RE_FOCUS_REF.finditer(mm.group(1)):
                me_list.append(fm.group(1))

        focuses.append({
            'id': fid,
            'x_old': int(xm.group(1)) if xm else 0,
            'y_old': int(ym.group(1)) if ym else 0,
            'relpos_old': relpos_m.group(1) if relpos_m else None,
            'prereqs': prereqs,
            'me': me_list,
            'body_start': open_idx + 1,
            'body_end': close_idx,
            'original_text': text[open_idx:close_idx+1],  # includes braces
            'top': top,
        })

    return text, focuses


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------
def build_graph(focuses):
    all_ids = {f['id'] for f in focuses}
    children = defaultdict(list)
    parents = defaultdict(list)
    me_pairs = defaultdict(set)
    for f in focuses:
        for pr in f['prereqs']:
            if pr in all_ids:
                children[pr].append(f['id'])
                parents[f['id']].append(pr)
        for me in f['me']:
            me_pairs[f['id']].add(me)
            me_pairs[me].add(f['id'])

    roots = [f['id'] for f in focuses if not f['prereqs']]

    def depth(nid, visited=None):
        if visited is None:
            visited = set()
        if nid in visited:
            return 0
        visited.add(nid)
        prs = parents.get(nid, [])
        if not prs:
            return 0
        return 1 + max(depth(p, set(visited)) for p in prs if p in all_ids)

    depths = {f['id']: depth(f['id']) for f in focuses}
    max_depth = max(depths.values()) if depths else 0

    return children, parents, me_pairs, roots, depths, max_depth


# ---------------------------------------------------------------------------
# Column assignment
# ---------------------------------------------------------------------------
# QUE thematic zones (BRC-style: clear horizontal bands)
# x=40-44: Diplomacy (Stromgarde, Alliance, Dwarves, Gnomish)
# x=45-47: Kael'thas personal story (prince, reform, dalaran ties)
# x=48-49: Military modernization (dragonhawks, heavy inf, armories)
# x=50   : CENTRAL SPINE (anasterians → pragmatism → shared_sacrifice → destiny)
# x=51-52: Arcane/Spellbreaker (arcane doctrine, spellbreakers, sunwell)
# x=53-54: Defense/Amani (runestones, reinforce, burning, repel)
# x=55-56: Rangers (alleria, windrunner, elrendar, farstriders)
# x=44-46: Naval (token_fleet, full_fleet, shipyards, marines)
# x=40-42: Post-war left (scars, rebuild)
# x=48-50: Post-war right (place_in_alliance, guarantor)
# x=50-52: Victory spine (destiny → phoenix → sunwell_warning)

def assign_column(fid, parents_dict, children_dict):
    """Assign base x-column. Returns integer."""
    # CENTRAL SPINE
    spine = {
        'QUE_sw_anasterians_reticence', 'QUE_sw_council_of_silvermoon',
        'QUE_sw_kaelthas_pragmatism', 'QUE_sw_shared_sacrifice',
        'QUE_sw_kaelthas_destiny', 'QUE_sw_the_phoenix_prince',
        'QUE_sw_sunwell_warning', 'QUE_sw_the_princes_council',
        'QUE_sw_scholar_of_dalaran', 'QUE_sw_united_leadership',
        'QUE_sw_kirin_tor_path',
    }
    # Starting boosts (independent roots)
    start_boosts = {
        'QUE_sw_farstrider_legacy', 'QUE_sw_queldanas_trade',
        'QUE_sw_monitoring_the_border',
    }

    if fid in spine:
        return 50
    if fid in start_boosts:
        # Place starting boosts around the spine
        if fid == 'QUE_sw_farstrider_legacy':
            return 46
        if fid == 'QUE_sw_queldanas_trade':
            return 48
        if fid == 'QUE_sw_monitoring_the_border':
            return 54
        return 50

    # Thematic overrides by ID prefix/pattern
    if fid == 'QUE_sw_old_oath_to_thoradin':
        return 46
    if fid == 'QUE_sw_the_debt_of_arathor':
        return 44
    if fid == 'QUE_sw_alliance_membership':
        return 44
    if fid == 'QUE_sw_stromgardes_legacy':
        return 40
    if fid == 'QUE_sw_dwarven_engineering':
        return 42
    if fid == 'QUE_sw_gnomish_technology':
        return 40
    if fid == 'QUE_sw_token_fleet':
        return 44
    if fid == 'QUE_sw_full_fleet_mobilization':
        return 46
    if fid == 'QUE_sw_elves_on_the_front':
        return 45
    if fid == 'QUE_sw_shipyards_of_queldanas':
        return 43
    if fid == 'QUE_sw_elven_battlefleet':
        return 43
    if fid == 'QUE_sw_thalassian_marines':
        return 47

    if fid == 'QUE_sw_silvermoons_isolation':
        return 54
    if fid == 'QUE_sw_houses_of_silvermoon':
        return 54
    if fid == 'QUE_sw_sunstrider_ascendancy':
        return 52
    if fid == 'QUE_sw_balance_of_houses':
        return 56
    if fid == 'QUE_sw_runestone_debate':
        return 54
    if fid == 'QUE_sw_power_ban_dinoriel':
        return 52
    if fid == 'QUE_sw_shatter_isolation':
        return 56

    if fid == 'QUE_sw_detect_the_amani_threat':
        return 54
    if fid == 'QUE_sw_reinforce_the_runestones':
        return 54
    if fid == 'QUE_sw_burning_of_the_borderlands':
        return 54
    if fid == 'QUE_sw_repel_the_amani':
        return 54
    if fid == 'QUE_sw_counter_raid_zul_aman':
        return 52
    if fid == 'QUE_sw_loa_hunting':
        return 56
    if fid == 'QUE_sw_purge_forest_trolls':
        return 52
    if fid == 'QUE_sw_end_of_zul_aman':
        return 56
    if fid == 'QUE_sw_secure_quelthalas':
        return 54

    if fid == 'QUE_sw_allerias_defiance':
        return 56
    if fid == 'QUE_sw_windrunner_rangers':
        return 56
    if fid == 'QUE_sw_ranger_defense_network':
        return 56
    if fid == 'QUE_sw_lorthemar_secures_pass':
        return 56
    if fid == 'QUE_sw_hold_the_elrendar':
        return 56
    if fid == 'QUE_sw_farstriders_glory':
        return 56

    if fid == 'QUE_sw_prince_of_the_sun':
        return 46
    if fid == 'QUE_sw_princes_reform':
        return 46
    if fid == 'QUE_sw_kaelthas_dalaran_ties':
        return 42
    if fid == 'QUE_sw_modernize_convocation':
        return 46
    if fid == 'QUE_sw_sunwell_guardianship':
        return 44
    if fid == 'QUE_sw_sideline_magisters':
        return 48
    if fid == 'QUE_sw_princes_regency':
        return 48
    if fid == 'QUE_sw_kirin_tor_exchange':
        return 40
    if fid == 'QUE_sw_silver_covenant':
        return 42
    if fid == 'QUE_sw_arcane_innovation':
        return 38
    if fid == 'QUE_sw_dalaran_magisters':
        return 44

    if fid == 'QUE_sw_modernize_elven_army':
        return 50
    if fid == 'QUE_sw_dragonhawk_riders':
        return 48
    if fid == 'QUE_sw_elven_heavy_infantry':
        return 52
    if fid == 'QUE_sw_aerial_superiority':
        return 48
    if fid == 'QUE_sw_silvermoon_armories':
        return 52
    if fid == 'QUE_sw_spellbreaker_corps':
        return 52
    if fid == 'QUE_sw_arcane_warfare_doctrine':
        return 52
    if fid == 'QUE_sw_sunwells_blessing':
        return 52

    if fid == 'QUE_sw_scars_of_the_war':
        return 40
    if fid == 'QUE_sw_rebuild_the_guard':
        return 40
    if fid == 'QUE_sw_place_in_the_alliance':
        return 46
    if fid == 'QUE_sw_guarantor_of_lordaeron':
        return 46

    # Fallback: inherit from parent
    prs = parents_dict.get(fid, [])
    if prs:
        parent_cols = [assign_column(p, parents_dict, children_dict) for p in prs if p.startswith('QUE_sw_')]
        if parent_cols:
            return sum(parent_cols) // len(parent_cols)
    return 50


# ---------------------------------------------------------------------------
# Row (y) assignment
# ---------------------------------------------------------------------------
def compute_y(fid, depths, parents_dict, focus_map):
    """Assign y based on depth + convergence rules (BRC-style: y+1 standard, y+2 convergence)."""
    depth = depths.get(fid, 0)
    prs = parents_dict.get(fid, [])

    # Roots at y=0
    if not prs:
        return 0

    # Convergence nodes (2+ prereqs): add visual space
    queen_prereqs = [p for p in prs if p.startswith('QUE_sw_')]
    if len(queen_prereqs) >= 2:
        return depth + (len(queen_prereqs) - 1)  # y = depth + extra for each additional branch

    return depth


# ---------------------------------------------------------------------------
# Main layout function
# ---------------------------------------------------------------------------
def compute_layout(focuses):
    children, parents, me_pairs, roots, depths, max_depth = build_graph(focuses)
    focus_map = {f['id']: f for f in focuses}

    # Build depth→focuses map for layer assignment
    depth_nodes = defaultdict(list)
    for fid, d in depths.items():
        depth_nodes[d].append(fid)

    # --- Narrative y-layer overrides (BRC-style chapter pacing) ---
    # Some focuses need to be at specific story levels regardless of prereq depth.
    Y_LAYER = {
        # 0: Starting position
        'QUE_sw_farstrider_legacy': 0, 'QUE_sw_queldanas_trade': 0,
        'QUE_sw_anasterians_reticence': 0, 'QUE_sw_silvermoons_isolation': 0,
        'QUE_sw_monitoring_the_border': 0,
        # 1: First reactions
        'QUE_sw_old_oath_to_thoradin': 1, 'QUE_sw_council_of_silvermoon': 1,
        'QUE_sw_allerias_defiance': 1, 'QUE_sw_houses_of_silvermoon': 1,
        'QUE_sw_runestone_debate': 1,
        # 2: Direction
        'QUE_sw_the_debt_of_arathor': 2, 'QUE_sw_kaelthas_pragmatism': 2,
        'QUE_sw_detect_the_amani_threat': 2, 'QUE_sw_windrunner_rangers': 2,
        'QUE_sw_sunstrider_ascendancy': 2, 'QUE_sw_power_ban_dinoriel': 2,
        'QUE_sw_shatter_isolation': 2, 'QUE_sw_balance_of_houses': 2,
        # 3: Commitment
        'QUE_sw_alliance_membership': 3, 'QUE_sw_prince_of_the_sun': 3,
        'QUE_sw_stromgardes_legacy': 3, 'QUE_sw_reinforce_the_runestones': 3,
        'QUE_sw_ranger_defense_network': 3, 'QUE_sw_modernize_elven_army': 3,
        # 4: War preparation
        'QUE_sw_token_fleet': 4, 'QUE_sw_full_fleet_mobilization': 4,
        'QUE_sw_princes_reform': 4, 'QUE_sw_dwarven_engineering': 4,
        'QUE_sw_kaelthas_dalaran_ties': 4, 'QUE_sw_dragonhawk_riders': 4,
        'QUE_sw_elven_heavy_infantry': 4, 'QUE_sw_burning_of_the_borderlands': 4,
        'QUE_sw_lorthemar_secures_pass': 4,
        # 5: War intensifies
        'QUE_sw_kirin_tor_exchange': 5, 'QUE_sw_gnomish_technology': 5,
        'QUE_sw_silver_covenant': 5, 'QUE_sw_modernize_convocation': 5,
        'QUE_sw_sideline_magisters': 5, 'QUE_sw_aerial_superiority': 5,
        'QUE_sw_elves_on_the_front': 5, 'QUE_sw_silvermoon_armories': 5,
        'QUE_sw_arcane_warfare_doctrine': 5, 'QUE_sw_repel_the_amani': 5,
        'QUE_sw_hold_the_elrendar': 5,
        # 6: War execution
        'QUE_sw_arcane_innovation': 6, 'QUE_sw_dalaran_magisters': 6,
        'QUE_sw_sunwell_guardianship': 6, 'QUE_sw_princes_regency': 6,
        'QUE_sw_shipyards_of_queldanas': 6, 'QUE_sw_spellbreaker_corps': 6,
        'QUE_sw_counter_raid_zul_aman': 6, 'QUE_sw_secure_quelthalas': 6,
        'QUE_sw_loa_hunting': 6, 'QUE_sw_farstriders_glory': 6,
        'QUE_sw_thalassian_marines': 6,
        # 7: Gateway - shared sacrifice
        'QUE_sw_shared_sacrifice': 7, 'QUE_sw_sunwells_blessing': 7,
        'QUE_sw_elven_battlefleet': 7,
        # 8: Post-war consequences
        'QUE_sw_scars_of_the_war': 8, 'QUE_sw_place_in_the_alliance': 8,
        'QUE_sw_purge_forest_trolls': 8, 'QUE_sw_end_of_zul_aman': 8,
        'QUE_sw_kaelthas_destiny': 8,
        # 9: Victory
        'QUE_sw_rebuild_the_guard': 9, 'QUE_sw_guarantor_of_lordaeron': 9,
        'QUE_sw_the_phoenix_prince': 9, 'QUE_sw_the_princes_council': 9,
        'QUE_sw_scholar_of_dalaran': 9,
        # 10: Epilogue
        'QUE_sw_sunwell_warning': 10, 'QUE_sw_united_leadership': 10,
        'QUE_sw_kirin_tor_path': 10,
    }

    # Assign columns
    columns = {}
    for f in focuses:
        fid = f['id']
        columns[fid] = assign_column(fid, parents, children)

    # Assign rows: use Y_LAYER override if available, else depth-based
    final_y = {}
    final_x = {}
    for f in focuses:
        fid = f['id']
        final_x[fid] = columns.get(fid, 50)
        if fid in Y_LAYER:
            final_y[fid] = Y_LAYER[fid]
        else:
            # Fallback: depth-based
            final_y[fid] = depths.get(fid, 0)

    # --- collision resolution pass ---
    # Group focuses by (x, y) and shift overlapping ones
    pos_map = defaultdict(list)
    for f in focuses:
        fid = f['id']
        pos_map[(final_x[fid], final_y[fid])].append(fid)

    # Simple greedy: shift right by 1 if collision
    max_iter = 20
    for _ in range(max_iter):
        collisions = 0
        for (x, y), ids in list(pos_map.items()):
            if len(ids) <= 1:
                continue
            collisions += 1
            ids.sort()
            for offset, fid in enumerate(ids):
                new_x = x + offset
                pos_map[(x, y)].remove(fid)
                if not pos_map[(x, y)]:
                    del pos_map[(x, y)]
                pos_map[(new_x, y)].append(fid)
                final_x[fid] = new_x
        if collisions == 0:
            break

    # --- children-below-parents constraint ---
    # Ensure child.y > parent.y when anchor IS a prerequisite
    changed = True
    while changed:
        changed = False
        for f in focuses:
            fid = f['id']
            for pr in f['prereqs']:
                if pr in final_y and final_y[fid] <= final_y[pr]:
                    final_y[fid] = final_y[pr] + 1
                    changed = True

    # --- convergence center adjustment ---
    # For focuses with 2 prereqs, center x between prereqs
    for f in focuses:
        prs = [p for p in f['prereqs'] if p.startswith('QUE_sw_') and p in final_x]
        if len(prs) == 2:
            x0 = final_x[prs[0]]
            x1 = final_x[prs[1]]
            mid = (x0 + x1) // 2
            if abs(final_x[f['id']] - mid) > 2:
                final_x[f['id']] = mid

    # --- ME pair alignment ---
    # Ensure ME pairs share the same y row
    for f in focuses:
        for me_target in f['me']:
            if me_target in final_y and f['id'] in final_y:
                me_y = max(final_y[f['id']], final_y[me_target])
                final_y[f['id']] = me_y
                final_y[me_target] = me_y

    # --- anchor assignment ---
    spine_ancestors = {
        'QUE_sw_anasterians_reticence', 'QUE_sw_kaelthas_pragmatism',
        'QUE_sw_shared_sacrifice', 'QUE_sw_kaelthas_destiny',
    }

    # Special anchor overrides for critical convergence nodes
    ANCHOR_OVERRIDE = {
        'QUE_sw_kaelthas_destiny': 'QUE_sw_shared_sacrifice',
        'QUE_sw_elves_on_the_front': 'QUE_sw_token_fleet',
        'QUE_sw_arcane_warfare_doctrine': 'QUE_sw_modernize_elven_army',
        'QUE_sw_detect_the_amani_threat': 'QUE_sw_monitoring_the_border',
        'QUE_sw_modernize_elven_army': 'QUE_sw_kaelthas_pragmatism',
        'QUE_sw_princes_reform': 'QUE_sw_prince_of_the_sun',
    }

    anchors = {}
    for f in focuses:
        fid = f['id']
        prs = [p for p in parents.get(fid, []) if p.startswith('QUE_sw_')]

        if fid in ANCHOR_OVERRIDE:
            anchor_id = ANCHOR_OVERRIDE[fid]
            ax = final_x.get(anchor_id, 50)
            ay = final_y.get(anchor_id, 0)
            anchors[fid] = (anchor_id, final_x[fid] - ax, final_y[fid] - ay)
        elif not prs:
            anchors[fid] = (None, final_x[fid], final_y[fid])
        elif len(prs) >= 2:
            spine_prereq = None
            for sa in spine_ancestors:
                if sa in prs:
                    spine_prereq = sa
                    break
            if spine_prereq is None:
                spine_prereq = max(prs, key=lambda p: depths.get(p, 0))
            ax = final_x.get(spine_prereq, 50)
            ay = final_y.get(spine_prereq, 0)
            anchors[fid] = (spine_prereq, final_x[fid] - ax, final_y[fid] - ay)
        else:
            parent_id = prs[0]
            px = final_x.get(parent_id, 50)
            py = final_y.get(parent_id, 0)
            anchors[fid] = (parent_id, final_x[fid] - px, final_y[fid] - py)

    return final_x, final_y, anchors


# ---------------------------------------------------------------------------
# Write back
# ---------------------------------------------------------------------------
def apply_layout(filepath, focuses, final_x, final_y, anchors, original_text):
    """Rewrite focus file: only change x, y, relative_position_id."""
    # Build replacement maps
    replacements = {}  # focus_id -> new coordinate block

    for f in focuses:
        fid = f['id']
        relpos_id, new_x, new_y = anchors[fid]

        if relpos_id is None:
            # Absolute
            new_block = f'x = {new_x}\n\t\ty = {new_y}'
        else:
            new_block = f'relative_position_id = {relpos_id}\n\t\tx = {new_x}\n\t\ty = {new_y}'

        # Build old text: the part we need to replace
        # Find the coordinate/relpos section in the focus block
        body = f['top']

        # Remove old relpos, x, y lines and replace with new ones
        # Strategy: find the focus block start in the original text, then
        # find the "id = FOO" line, then the next line with x/y/relpos
        # We'll rebuild the focus block text

        old_block = f['original_text']
        # Replace coordinate lines inside the block
        # Remove old relative_position_id line if present
        new_block_text = old_block

        # Replace x = <old> with x = <new_x>
        new_block_text = re.sub(
            r'\bx\s*=\s*-?\d+',
            f'x = {new_x}',
            new_block_text
        )
        # Replace y = <old> with y = <new_y>
        new_block_text = re.sub(
            r'\by\s*=\s*-?\d+',
            f'y = {new_y}',
            new_block_text
        )
        # Handle relative_position_id
        if relpos_id is not None:
            # If there's already a relpos line, replace its value
            if RE_RELPOS.search(new_block_text):
                new_block_text = re.sub(
                    r'\brelative_position_id\s*=\s*[A-Za-z0-9_.]+',
                    f'relative_position_id = {relpos_id}',
                    new_block_text
                )
            else:
                # Insert relpos before x
                new_block_text = re.sub(
                    r'(\bx\s*=\s*-?\d+)',
                    f'relative_position_id = {relpos_id}\n\t\t\\1',
                    new_block_text
                )
        else:
            # Remove relpos line if present (absolute positioning)
            new_block_text = re.sub(
                r'\brelative_position_id\s*=\s*[A-Za-z0-9_.]+\s*\n\s*',
                '',
                new_block_text
            )

        replacements[fid] = new_block_text

    # Apply replacements to the full file
    result = original_text
    for f in focuses:
        fid = f['id']
        old = f['original_text']
        new = replacements[fid]
        if old != new:
            # Find and replace (first occurrence only)
            idx = result.find(old)
            if idx >= 0:
                result = result[:idx] + new + result[idx + len(old):]

    return result


# ---------------------------------------------------------------------------
# Diagnostic dump
# ---------------------------------------------------------------------------
def dump_layout(focuses, final_x, final_y, anchors, depths):
    print(f"\n{'ID':45s} {'x':>3s} {'y':>2s} {'d':>2s} {'anchor':40s} {'prereqs'}")
    print('-' * 120)
    for f in sorted(focuses, key=lambda f: (final_y[f['id']], final_x[f['id']])):
        fid = f['id']
        relpos_id, rx, ry = anchors[fid]
        anchor = relpos_id if relpos_id else 'ABSOLUTE'
        pr = ', '.join(f['prereqs']) if f['prereqs'] else '-'
        print(f'{fid:45s} {final_x[fid]:3d} {final_y[fid]:2d} {depths[fid]:2d} {anchor:40s} [{pr}]')

    # Stats
    ys = [final_y[f['id']] for f in focuses]
    xs = [final_x[f['id']] for f in focuses]
    print(f'\nBounding box: x=[{min(xs)},{max(xs)}] y=[{min(ys)},{max(ys)}]')
    print(f'Nodes: {len(focuses)}')


def main():
    ap = argparse.ArgumentParser(description='QUE second war focus tree BRC-style re-layout')
    ap.add_argument('file', nargs='?', default='common/national_focus/quelthalas_second_war.txt',
                    help='Path to the focus file')
    ap.add_argument('--dry-run', action='store_true', help='Print layout without writing')
    args = ap.parse_args()

    filename = args.file
    if '/' not in filename and '\\' not in filename:
        filename = 'common/national_focus/' + filename

    print(f'Parsing {filename}...')
    text, focuses = parse_focus_file(filename)
    print(f'  Found {len(focuses)} QUE focuses')

    print('Computing layout...')
    final_x, final_y, anchors = compute_layout(focuses)

    dump_layout(focuses, final_x, final_y, anchors,
                {f['id']: 0 for f in focuses})  # depths handled internally

    if args.dry_run:
        print('\n[dry-run] No changes written.')
        return 0

    print('\nApplying layout...')
    result = apply_layout(filename, focuses, final_x, final_y, anchors, text)

    with open(filename, 'w', encoding='utf-8-sig') as f:
        f.write(result)

    print(f'Written: {filename}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
