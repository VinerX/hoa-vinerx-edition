#!/usr/bin/env python3
"""
Shift a focus subtree to the right by a given x offset.

Traverses the dependency graph from root_focus_id forward (BFS), collects
all transitive dependents (focuses that directly or indirectly require the
root), and adds the offset to their x coordinate.

Focuses that use relative_position_id are skipped — they derive position
from their reference and will shift automatically when the reference moves.

Usage:
  python tools/shift_focus_subtree.py <focus_file> <root_focus_id> <x_offset>
  python tools/shift_focus_subtree.py <focus_file> <root_focus_id> <x_offset> --root  # also shift root
  python tools/shift_focus_subtree.py <focus_file> <root_focus_id> <x_offset> --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys


RE_FOCUS_START = re.compile(r"\b(?:focus|shared_focus)\s*=\s*\{")
RE_ID = re.compile(r"\bid\s*=\s*([A-Za-z0-9_.]+)")
RE_PREREQ = re.compile(r"\bprerequisite\s*=\s*\{([^}]*)\}")
RE_FOCUS_REF = re.compile(r"\bfocus\s*=\s*([A-Za-z0-9_.]+)")
RE_RELPOS = re.compile(r"\brelative_position_id\s*=\s*([A-Za-z0-9_.]+)")
RE_X_IN_BODY = re.compile(r"\bx\s*=\s*(-?\d+)")


def find_matching_brace(text: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def parse_focuses(text: str) -> list[dict]:
    focuses: list[dict] = []
    for m in RE_FOCUS_START.finditer(text):
        open_idx = text.find("{", m.start())
        if open_idx == -1:
            continue
        close_idx = find_matching_brace(text, open_idx)
        if close_idx == -1:
            continue
        body = text[open_idx + 1 : close_idx]

        id_m = RE_ID.search(body)
        if not id_m:
            continue
        fid = id_m.group(1)

        relpos_m = RE_RELPOS.search(body)
        relpos = relpos_m.group(1) if relpos_m else None

        prereqs: list[str] = []
        pm = RE_PREREQ.search(body)
        if pm:
            prereqs = RE_FOCUS_REF.findall(pm.group(1))

        focuses.append({
            "id": fid,
            "relpos": relpos,
            "prereqs": prereqs,
            "body": body,
            "body_start": open_idx + 1,  # position after opening '{'
            "body_end": close_idx,       # position of closing '}'
        })
    return focuses


def build_graph(focuses: list[dict]) -> tuple[dict[str, list[str]], dict[str, dict]]:
    children: dict[str, list[str]] = {}
    id_to_data: dict[str, dict] = {}
    for f in focuses:
        id_to_data[f["id"]] = f
        children.setdefault(f["id"], [])
        for prereq in f["prereqs"]:
            if prereq in id_to_data:
                children.setdefault(prereq, []).append(f["id"])
    return children, id_to_data


def collect_dependents(root_id: str, children: dict[str, list[str]], include_root: bool) -> set[str]:
    visited: set[str] = set()
    queue = [root_id]
    while queue:
        fid = queue.pop(0)
        if fid in visited:
            continue
        visited.add(fid)
        for child in children.get(fid, []):
            if child not in visited:
                queue.append(child)
    if not include_root:
        visited.discard(root_id)
    return visited


def shift_subtree(text: str, dependent_ids: set[str], id_to_data: dict[str, dict], offset: int) -> str:
    """
    Find and modify x coordinates for focuses in dependent_ids.
    Focuses with relative_position_id are skipped (they derive position from their reference).
    Returns modified text.
    """
    modifications: list[tuple[int, int, str]] = []

    for fid in dependent_ids:
        if fid not in id_to_data:
            continue
        f = id_to_data[fid]
        if f["relpos"] is not None:
            continue

        # Find x = <num> within the body, searching line by line
        xm = RE_X_IN_BODY.search(f["body"])
        if not xm:
            continue

        old_x = int(xm.group(1))
        new_x = old_x + offset

        # Position in the full text: body_start + position of x inside body
        abs_pos = f["body_start"] + xm.start(1)
        abs_end = f["body_start"] + xm.end(1)

        modifications.append((abs_pos, abs_end, str(new_x)))

    # Apply from right to left to preserve positions
    modifications.sort(key=lambda m: m[0], reverse=True)
    result = list(text)
    for start, end, new_val in modifications:
        result[start:end] = new_val

    return "".join(result)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Shift a focus subtree to the right by a given x offset"
    )
    ap.add_argument("file", help="path to the national_focus .txt file")
    ap.add_argument("root", help="root focus id")
    ap.add_argument("offset", type=int, help="x offset to add (positive = right)")
    ap.add_argument("--root", dest="include_root", action="store_true",
                    help="also shift the root focus itself")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would change without writing")
    args = ap.parse_args()

    try:
        with open(args.file, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
    except FileNotFoundError:
        print(f"ERROR: file not found: {args.file}")
        return 1

    focuses = parse_focuses(text)
    children, id_to_data = build_graph(focuses)

    if args.root not in children:
        print(f"ERROR: focus '{args.root}' not found in any focus block in {args.file}")
        print(f"Available focus ids ({len(focuses)}):")
        for f in focuses:
            print(f"  {f['id']}")
        return 1

    dependents = collect_dependents(args.root, children, args.include_root)

    if not dependents:
        print(f"Focus '{args.root}' has no dependents. Nothing to shift.")
        return 0

    modified = shift_subtree(text, dependents, id_to_data, args.offset)

    changes = 0
    for fid in sorted(dependents):
        if fid not in id_to_data:
            continue
        f = id_to_data[fid]
        if f["relpos"] is not None:
            print(f"  SKIP {fid} (uses relative_position_id = {f['relpos']})")
            continue
        xm = RE_X_IN_BODY.search(f["body"])
        if xm:
            old_x = int(xm.group(1))
            print(f"  SHIFT {fid}: x {old_x} -> {old_x + args.offset}")
            changes += 1

    print(f"\nTotal: {len(dependents)} dependents, {changes} x-coords to shift by +{args.offset}")

    if args.dry_run:
        print("[dry-run] no changes written.")
        return 0

    with open(args.file, "w", encoding="utf-8-sig") as fh:
        fh.write(modified)

    print(f"Written: {args.file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
