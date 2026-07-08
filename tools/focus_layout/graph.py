#!/usr/bin/env python3
"""
Focus tree graph extractor.

Parses all national-focus files, resolves relative_position_id chains to
absolute coordinates, and outputs a JSON dependency graph per tree.

Usage:
  python tools/focus_layout/graph.py --all              # all trees -> focus_graph.json
  python tools/focus_layout/graph.py --tree <tree_id>   # single tree
  python tools/focus_layout/graph.py --file <focus_file> # trees from one file
  python tools/focus_layout/graph.py --trees             # list all tree ids
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
RE_FOCUS_START = re.compile(r"\b(?:focus|shared_focus)\s*=\s*\{")
RE_FOCUS_TREE_START = re.compile(r"\bfocus_tree\s*=\s*\{")
RE_ID = re.compile(r"\bid\s*=\s*([A-Za-z0-9_.]+)")
RE_RELPOS = re.compile(r"\brelative_position_id\s*=\s*([A-Za-z0-9_.]+)")
RE_SHARED = re.compile(r"\bshared_focus\s*=\s*([A-Za-z0-9_.]+)")
RE_X = re.compile(r"\bx\s*=\s*(-?\d+)")
RE_Y = re.compile(r"\by\s*=\s*(-?\d+)")
RE_COST = re.compile(r"\bcost\s*=\s*(-?\d+)")
RE_ICON = re.compile(r"\bicon\s*=\s*([A-Za-z0-9_]+)")
RE_PREREQ_BLOCK = re.compile(r"\bprerequisite\s*=\s*\{([^}]*)\}")
RE_ME_BLOCK = re.compile(r"\bmutually_exclusive\s*=\s*\{([^}]*)\}")
RE_FOCUS_REF = re.compile(r"\bfocus\s*=\s*([A-Za-z0-9_.]+)")
RE_COUNTRY_TAG = re.compile(r"\btag\s*=\s*([A-Z]{3})")
RE_CP = re.compile(r"\bcontinuous_focus_position\s*=\s*\{\s*x\s*=\s*(-?\d+)\s*y\s*=\s*(-?\d+)\s*\}")


# ---------------------------------------------------------------------------
# Brace handling
# ---------------------------------------------------------------------------
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


def blank_nested_braces(body: str) -> str:
    """Blank nested { ... } content, preserving length + newlines."""
    out = []
    depth = 0
    for ch in body:
        if ch == "{":
            depth += 1
            out.append(" ")
        elif ch == "}":
            depth -= 1
            out.append(" ")
        else:
            out.append(ch if depth == 0 else (" " if ch != "\n" else "\n"))
    return "".join(out)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class FocusNode:
    id: str
    x_abs: int | None = None
    y_abs: int | None = None
    x_rel: int | None = None
    y_rel: int | None = None
    relative_position_id: str | None = None
    prerequisites: list[str] = field(default_factory=list)
    mutually_exclusive: list[str] = field(default_factory=list)
    cost: int = 0
    icon: str = "GFX_goal_placeholder"
    is_shared: bool = False
    tree_id: str | None = None
    file: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": self.x_abs,
            "y": self.y_abs,
            "x_rel": self.x_rel,
            "y_rel": self.y_rel,
            "relative_position_id": self.relative_position_id,
            "prerequisites": self.prerequisites,
            "mutually_exclusive": self.mutually_exclusive,
            "cost": self.cost,
            "icon": self.icon,
            "is_shared": self.is_shared,
        }


@dataclass
class FocusTree:
    id: str
    file: str
    country_tag: str = ""
    continuous_focus_position: dict | None = None
    shared_focus_imports: list[str] = field(default_factory=list)
    nodes: dict[str, FocusNode] = field(default_factory=dict)

    def bounding_box(self) -> dict:
        xs = [n.x_abs for n in self.nodes.values() if n.x_abs is not None]
        ys = [n.y_abs for n in self.nodes.values() if n.y_abs is not None]
        if not xs:
            return {"x_min": 0, "x_max": 0, "y_min": 0, "y_max": 0}
        return {
            "x_min": min(xs), "x_max": max(xs),
            "y_min": min(ys), "y_max": max(ys),
        }

    def edges(self) -> list[dict]:
        edges: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for node in self.nodes.values():
            for prereq in node.prerequisites:
                key = (prereq, node.id, "prerequisite")
                if key not in seen:
                    seen.add(key)
                    edges.append({"from": prereq, "to": node.id, "type": "prerequisite"})
            for me in node.mutually_exclusive:
                key = (node.id, me, "mutually_exclusive")
                if key not in seen:
                    seen.add(key)
                    edges.append({"from": node.id, "to": me, "type": "mutually_exclusive"})
            if node.relative_position_id:
                key = (node.relative_position_id, node.id, "relative_position")
                if key not in seen:
                    seen.add(key)
                    edges.append({"from": node.relative_position_id, "to": node.id, "type": "relative_position"})
        return edges

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file": self.file,
            "country_tag": self.country_tag,
            "continuous_focus_position": self.continuous_focus_position,
            "shared_focus_imports": self.shared_focus_imports,
            "node_count": len(self.nodes),
            "nodes": {nid: n.to_dict() for nid, n in sorted(self.nodes.items())},
            "edges": self.edges(),
            "bounding_box": self.bounding_box(),
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_focus_block(body: str, full_text: str, body_start: int, body_end: int) -> FocusNode | None:
    """Parse a single focus = { ... } or shared_focus = { ... } block."""
    top = blank_nested_braces(body)

    id_m = RE_ID.search(top)
    if not id_m:
        return None
    fid = id_m.group(1)

    relpos_m = RE_RELPOS.search(top)
    xm = RE_X.search(top)
    ym = RE_Y.search(top)
    cm = RE_COST.search(top)
    icon_m = RE_ICON.search(top)

    node = FocusNode(
        id=fid,
        x_rel=int(xm.group(1)) if xm else None,
        y_rel=int(ym.group(1)) if ym else None,
        relative_position_id=relpos_m.group(1) if relpos_m else None,
        cost=int(cm.group(1)) if cm else 0,
        icon=icon_m.group(1) if icon_m else "GFX_goal_placeholder",
    )

    # Prerequisites — find all prerequisite = { ... } blocks in body
    for pm in RE_PREREQ_BLOCK.finditer(body):
        for fm in RE_FOCUS_REF.finditer(pm.group(1)):
            node.prerequisites.append(fm.group(1))

    # Mutually exclusive
    for mm in RE_ME_BLOCK.finditer(body):
        for fm in RE_FOCUS_REF.finditer(mm.group(1)):
            node.mutually_exclusive.append(fm.group(1))

    return node


def parse_focus_tree_block(body: str) -> tuple[str, str, dict | None, list[str]]:
    """Parse a focus_tree = { ... } block. Returns (tree_id, country_tag, cp, shared_imports)."""
    top = blank_nested_braces(body)

    id_m = RE_ID.search(top)
    tree_id = id_m.group(1) if id_m else ""

    tag = ""
    tag_m = RE_COUNTRY_TAG.search(body)
    if tag_m:
        tag = tag_m.group(1)

    cp: dict | None = None
    cp_m = RE_CP.search(body)
    if cp_m:
        cp = {"x": int(cp_m.group(1)), "y": int(cp_m.group(2))}

    shared_imports: list[str] = []
    for sm in RE_SHARED.finditer(top):
        sid = sm.group(1)
        if sid not in ("focus",):  # skip "shared_focus = focus" which is not an import
            shared_imports.append(sid)

    return tree_id, tag, cp, shared_imports


def parse_file(filepath: str) -> tuple[list[FocusNode], list[FocusTree]]:
    """Parse one focus file. Returns (all_focuses, all_trees)."""
    try:
        with open(filepath, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
    except (FileNotFoundError, UnicodeDecodeError):
        return [], []

    relpath = os.path.relpath(filepath).replace("\\", "/")
    focuses: list[FocusNode] = []
    trees: list[FocusTree] = []

    # Find all focus_tree blocks
    tree_positions: list[tuple[int, int]] = []
    for m in RE_FOCUS_TREE_START.finditer(text):
        open_idx = text.find("{", m.start())
        if open_idx == -1:
            continue
        close_idx = find_matching_brace(text, open_idx)
        if close_idx == -1:
            continue
        tree_positions.append((open_idx + 1, close_idx))

    # Parse each focus_tree
    for t_start, t_end in tree_positions:
        tree_body = text[t_start:t_end]
        tree_id, tag, cp, shared = parse_focus_tree_block(tree_body)
        tree = FocusTree(id=tree_id, file=relpath, country_tag=tag,
                         continuous_focus_position=cp, shared_focus_imports=shared)

        # Find focus blocks within this tree's body
        for fm in RE_FOCUS_START.finditer(tree_body):
            open_idx = tree_body.find("{", fm.start())
            if open_idx == -1:
                continue
            close_idx = find_matching_brace(tree_body, open_idx)
            if close_idx == -1:
                continue
            fbody = tree_body[open_idx + 1 : close_idx]
            node = parse_focus_block(fbody, tree_body, open_idx + 1, close_idx)
            if node:
                node.tree_id = tree_id
                node.file = relpath
                node.is_shared = tree_body[fm.start():fm.start()+6] == "shared"
                tree.nodes[node.id] = node
                focuses.append(node)

        trees.append(tree)

    # Also find top-level focus/shared_focus blocks (outside any tree)
    # These are typically shared_focus definitions in generic_shared_focus.txt
    for fm in RE_FOCUS_START.finditer(text):
        open_idx = text.find("{", fm.start())
        if open_idx == -1:
            continue
        # Check if this block is inside a tree we already parsed
        in_tree = any(t_start <= open_idx < t_end for t_start, t_end in tree_positions)
        if in_tree:
            continue
        close_idx = find_matching_brace(text, open_idx)
        if close_idx == -1:
            continue
        fbody = text[open_idx + 1 : close_idx]
        node = parse_focus_block(fbody, text, open_idx + 1, close_idx)
        if node:
            node.file = relpath
            node.is_shared = text[fm.start():fm.start()+6] == "shared"
            focuses.append(node)

    return focuses, trees


def collect_shared_dependents(shared_root_id: str, all_focuses: list[FocusNode]) -> list[FocusNode]:
    """Collect all focuses that transitively depend on a shared_focus root via relative_position_id."""
    # Build a map from focus id -> list of focuses that reference it via relative_position_id
    children: dict[str, list[FocusNode]] = defaultdict(list)
    for f in all_focuses:
        if f.relative_position_id:
            children[f.relative_position_id].append(f)

    result: list[FocusNode] = []
    visited: set[str] = set()
    queue = [shared_root_id]
    while queue:
        fid = queue.pop(0)
        if fid in visited:
            continue
        visited.add(fid)
        for child in children.get(fid, []):
            if child.id not in visited:
                result.append(child)
                queue.append(child.id)
    return result


def resolve_absolute_coords(tree: FocusTree, global_focuses: dict[str, FocusNode]) -> dict[str, FocusNode]:
    """Resolve absolute coordinates for all nodes in a tree.

    Follows relative_position_id chains. For imported shared_focus blocks,
    the chain starts at the shared_focus root which has absolute x/y.
    Returns a dict of id -> FocusNode with x_abs/y_abs populated.
    """
    resolved: dict[str, FocusNode] = {}

    def resolve_one(fid: str, resolving: set[str] | None = None) -> tuple[int, int] | None:
        if resolving is None:
            resolving = set()
        if fid in resolving:
            return None  # cycle detected
        if fid in resolved:
            n = resolved[fid]
            if n.x_abs is not None:
                return (n.x_abs, n.y_abs)
            return None
        resolving.add(fid)

        node = global_focuses.get(fid)
        if node is None:
            resolving.discard(fid)
            return None

        if node.relative_position_id is None:
            # Absolute coordinates
            if node.x_rel is not None and node.y_rel is not None:
                node.x_abs = node.x_rel
                node.y_abs = node.y_rel
                resolved[fid] = node
                resolving.discard(fid)
                return (node.x_abs, node.y_abs)
            resolving.discard(fid)
            return None

        # Relative — resolve parent first
        parent = resolve_one(node.relative_position_id, resolving)
        if parent is None:
            resolving.discard(fid)
            return None

        node.x_abs = parent[0] + (node.x_rel or 0)
        node.y_abs = parent[1] + (node.y_rel or 0)
        resolved[fid] = node
        resolving.discard(fid)
        return (node.x_abs, node.y_abs)

    for nid in tree.nodes:
        resolve_one(nid)

    return resolved


def build_global_registry(all_focuses: list[FocusNode]) -> dict[str, FocusNode]:
    """Build a global id -> FocusNode registry with deduplication (first occurrence wins)."""
    registry: dict[str, FocusNode] = {}
    for f in all_focuses:
        if f.id not in registry:
            registry[f.id] = f
    return registry


def expand_tree(tree: FocusTree, global_focuses: dict[str, FocusNode]) -> FocusTree:
    """Expand a tree by resolving shared_focus imports — pull in dependent nodes."""
    imported_ids: set[str] = set()

    for sid in tree.shared_focus_imports:
        if sid in global_focuses:
            imported_ids.add(sid)
            # Collect all focuses that are dependents of this shared root
            all_focuses_list = list(global_focuses.values())
            deps = collect_shared_dependents(sid, all_focuses_list)
            for dep in deps:
                imported_ids.add(dep.id)

    for fid in imported_ids:
        if fid not in tree.nodes:
            node = global_focuses[fid]
            tree.nodes[fid] = node

    return tree


def build_graphs(focus_dir: str) -> dict[str, FocusTree]:
    """Main entry: parse all files, build tree graphs, resolve coordinates."""
    all_focuses: list[FocusNode] = []
    all_trees: list[FocusTree] = []

    # Parse all .txt files in the focus directory
    focus_path = Path(focus_dir)
    if not focus_path.is_dir():
        print(f"ERROR: not a directory: {focus_dir}", file=sys.stderr)
        return {}

    for filepath in sorted(focus_path.glob("*.txt")):
        focuses, trees = parse_file(str(filepath))
        all_focuses.extend(focuses)
        all_trees.extend(trees)

    # Build global registry
    global_registry = build_global_registry(all_focuses)

    # Expand each tree with shared_focus imports and resolve coordinates
    result: dict[str, FocusTree] = {}
    for tree in all_trees:
        if not tree.id:
            continue
        tree = expand_tree(tree, global_registry)
        resolve_absolute_coords(tree, global_registry)
        result[tree.id] = tree

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def find_focus_dir() -> str:
    """Find common/national_focus relative to this script's location."""
    script_dir = Path(__file__).resolve().parent.parent.parent  # tools/focus_layout -> tools -> root
    focus_dir = script_dir / "common" / "national_focus"
    if focus_dir.is_dir():
        return str(focus_dir)
    # Fallback: try cwd
    focus_dir = Path("common/national_focus")
    if focus_dir.is_dir():
        return str(focus_dir)
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract focus tree dependency graphs")
    ap.add_argument("--all", action="store_true", help="Output all trees")
    ap.add_argument("--tree", type=str, help="Output a specific tree by id")
    ap.add_argument("--file", type=str, help="Output trees from a specific focus file")
    ap.add_argument("--trees", action="store_true", help="List all tree ids")
    ap.add_argument("--output", type=str, default="tools/focus_layout/focus_graph.json",
                    help="Output JSON file path (default: tools/focus_layout/focus_graph.json)")
    ap.add_argument("--focus-dir", type=str, help="Path to common/national_focus/")
    args = ap.parse_args()

    focus_dir = args.focus_dir or find_focus_dir()
    if not focus_dir:
        print("ERROR: could not find common/national_focus/", file=sys.stderr)
        return 1

    print(f"Parsing focus files from: {focus_dir}", file=sys.stderr)
    trees = build_graphs(focus_dir)

    if not trees:
        print("ERROR: no focus trees found", file=sys.stderr)
        return 1

    if args.trees:
        for tid in sorted(trees):
            t = trees[tid]
            print(f"  {tid:40s}  tag={t.country_tag:4s}  nodes={len(t.nodes):3d}  file={t.file}")
        return 0

    # Select trees to output
    selected: dict[str, FocusTree] = {}
    if args.tree:
        if args.tree in trees:
            selected[args.tree] = trees[args.tree]
        else:
            print(f"ERROR: tree '{args.tree}' not found", file=sys.stderr)
            print(f"Available: {', '.join(sorted(trees))}", file=sys.stderr)
            return 1
    elif args.file:
        target_file = args.file.replace("\\", "/")
        for tid, t in trees.items():
            if t.file == target_file or t.file.endswith(target_file):
                selected[tid] = t
        if not selected:
            print(f"ERROR: no trees found in file '{args.file}'", file=sys.stderr)
            return 1
    else:
        selected = trees  # --all (default)

    # Build output
    output_data = {
        "trees": {tid: t.to_dict() for tid, t in selected.items()},
    }

    output_path = args.output
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output_data, fh, indent=2)

    total_nodes = sum(len(t.nodes) for t in selected.values())
    print(f"Wrote {len(selected)} trees, {total_nodes} nodes -> {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
