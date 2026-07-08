#!/usr/bin/env python3
"""
Focus tree layout auditor.

Analyzes the dependency graph of focus trees and checks for:
  - Coordinate overlaps
  - Anchor mismatches (relative_position_id != prerequisite)
  - Long prerequisite edges
  - Backward edges (child above parent)
  - Too many incoming prerequisites (non-gateway nodes with > 2)
  - Convergence nodes not centered between prerequisites
  - Crossing edges
  - Sibling misalignment
  - Large y-gaps
  - Empty continuous_focus_position
  - Long relative_position_id chains

Returns ERROR (must fix), WARN (should fix), or INFO (review).

Usage:
  python tools/focus_layout/graph.py --all               # generate graph first
  python tools/focus_layout/audit.py --all                # audit all trees
  python tools/focus_layout/audit.py --tree kultiras_second_war
  python tools/focus_layout/audit.py --tree kultiras_second_war --json  # JSON output
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Audit issue types
# ---------------------------------------------------------------------------
LEVEL_ERROR = "ERROR"
LEVEL_WARN = "WARN"
LEVEL_INFO = "INFO"

# Thresholds
MAX_PREREQ_DX = 4
MAX_PREREQ_DY = 3
MAX_PREREQ_INCOMING = 2
MAX_RELPOS_CHAIN = 4
CONVERGENCE_OFFSET_THRESHOLD = 2


def load_graph(graph_path: str) -> dict:
    if not os.path.isfile(graph_path):
        print(f"ERROR: graph file not found: {graph_path}", file=sys.stderr)
        sys.exit(1)
    with open(graph_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_overlap(tree: dict) -> list[dict]:
    """Check for two focuses at the exact same (x, y)."""
    issues: list[dict] = []
    nodes = tree.get("nodes", {})
    pos_map: dict[tuple[int, int], list[str]] = defaultdict(list)
    for nid, node in nodes.items():
        x, y = node.get("x"), node.get("y")
        if x is not None and y is not None:
            pos_map[(x, y)].append(nid)
    for (x, y), ids in pos_map.items():
        if len(ids) > 1:
            issues.append({
                "level": LEVEL_ERROR,
                "code": "overlap",
                "focuses": ids,
                "pos": [x, y],
                "message": f"Overlap: {', '.join(ids)} at ({x}, {y})",
            })
    return issues


def check_broken_refs(tree: dict) -> list[dict]:
    """Check that relative_position_id, prerequisite, and mutually_exclusive refs resolve."""
    issues: list[dict] = []
    nodes = tree.get("nodes", {})
    all_ids = set(nodes.keys())

    for nid, node in nodes.items():
        rpid = node.get("relative_position_id")
        if rpid and rpid not in all_ids:
            issues.append({
                "level": LEVEL_ERROR,
                "code": "broken-relpos",
                "focus": nid,
                "target": rpid,
                "message": f"relative_position_id references non-existent focus: {nid} -> {rpid}",
            })

        for prereq in node.get("prerequisites", []):
            if prereq not in all_ids:
                issues.append({
                    "level": LEVEL_ERROR,
                    "code": "broken-prereq",
                    "focus": nid,
                    "target": prereq,
                    "message": f"prerequisite references non-existent focus: {nid} requires {prereq}",
                })

        for me in node.get("mutually_exclusive", []):
            if me not in all_ids:
                issues.append({
                    "level": LEVEL_ERROR,
                    "code": "broken-me",
                    "focus": nid,
                    "target": me,
                    "message": f"mutually_exclusive references non-existent focus: {nid} excludes {me}",
                })

    # Also check if any prerequisite/ME edges are dangling (target exists in data but not in this tree's nodes)
    edges = tree.get("edges", [])
    for edge in edges:
        fr = edge.get("from", "")
        to = edge.get("to", "")
        if fr not in nodes and fr in all_ids:
            pass  # shared_focus may reference nodes outside the tree; skip
        if to not in nodes and to in all_ids:
            pass

    return issues


def check_no_root(tree: dict) -> list[dict]:
    """Check that the tree has at least one root focus (no relative_position_id, y=0)."""
    issues: list[dict] = []
    nodes = tree.get("nodes", {})

    # A root focus has no relative_position_id AND (y == 0 or is at minimal y)
    shared_imports = tree.get("shared_focus_imports", [])
    roots = []
    for nid, node in nodes.items():
        if node.get("relative_position_id") is None and node.get("is_shared", False) is False:
            roots.append(nid)

    if not roots and not shared_imports:
        issues.append({
            "level": LEVEL_WARN,
            "code": "no-root",
            "message": "No root focus found (no focus without relative_position_id)",
        })
    return issues


def check_anchor_mismatch(tree: dict) -> list[dict]:
    """Check that relative_position_id is among prerequisites (for nodes with prereqs)."""
    issues: list[dict] = []
    nodes = tree.get("nodes", {})

    for nid, node in nodes.items():
        rpid = node.get("relative_position_id")
        prereqs = node.get("prerequisites", [])
        if rpid and prereqs and rpid not in prereqs:
            # Exception: convergence nodes with 2 prereqs — the relpos may be a third
            # anchor that is structurally sensible but not a prereq
            if len(prereqs) > 2:
                continue  # skip complex convergence
            issues.append({
                "level": LEVEL_WARN,
                "code": "anchor-mismatch",
                "focus": nid,
                "relpos": rpid,
                "prereqs": prereqs,
                "message": f"relative_position_id ({rpid}) differs from prerequisites ({', '.join(prereqs)}) for {nid}",
            })
    return issues


def check_long_edges(tree: dict) -> list[dict]:
    """Check for prerequisite edges with large dx or dy."""
    issues: list[dict] = []
    nodes = tree.get("nodes", {})

    for nid, node in nodes.items():
        nx, ny = node.get("x"), node.get("y")
        if nx is None or ny is None:
            continue
        for prereq in node.get("prerequisites", []):
            pn = nodes.get(prereq)
            if pn is None:
                continue
            px, py = pn.get("x"), pn.get("y")
            if px is None or py is None:
                continue
            dx = abs(nx - px)
            dy = abs(ny - py)
            if dx > MAX_PREREQ_DX or dy > MAX_PREREQ_DY:
                issues.append({
                    "level": LEVEL_WARN,
                    "code": "long-edge",
                    "from": prereq,
                    "to": nid,
                    "dx": dx,
                    "dy": dy,
                    "message": f"Long edge: {prereq} -> {nid} spans dx={dx}, dy={dy}",
                })
    return issues


def check_backward_edges(tree: dict) -> list[dict]:
    """Check for prerequisite edges where child is at or above parent's y."""
    issues: list[dict] = []
    nodes = tree.get("nodes", {})

    for nid, node in nodes.items():
        nx, ny = node.get("x"), node.get("y")
        if nx is None or ny is None:
            continue
        for prereq in node.get("prerequisites", []):
            pn = nodes.get(prereq)
            if pn is None:
                continue
            py = pn.get("y")
            if py is None:
                continue
            if ny <= py:
                # Check if this is a deliberate convergence (child between two parents)
                incoming = [n for n in nodes.values() if prereq in n.get("prerequisites", [])]
                if len(node.get("prerequisites", [])) >= 2:
                    continue  # convergence nodes are allowed to have one parent at same/lower y
                issues.append({
                    "level": LEVEL_WARN,
                    "code": "backward-edge",
                    "from": prereq,
                    "to": nid,
                    "parent_y": py,
                    "child_y": ny,
                    "message": f"Backward edge: {prereq} (y={py}) -> {nid} (y={ny}), child at or above parent",
                })
    return issues


def check_too_many_prereqs(tree: dict) -> list[dict]:
    """Check for nodes with > 2 incoming prerequisites (should use gateway)."""
    issues: list[dict] = []
    nodes = tree.get("nodes", {})

    for nid, node in nodes.items():
        prereqs = node.get("prerequisites", [])
        if len(prereqs) > MAX_PREREQ_INCOMING:
            issues.append({
                "level": LEVEL_WARN,
                "code": "too-many-prereqs",
                "focus": nid,
                "count": len(prereqs),
                "prereqs": prereqs,
                "message": f"Too many incoming prereqs ({len(prereqs)}) on {nid}: {', '.join(prereqs)}. Consider a gateway focus.",
            })
    return issues


def check_convergence_offset(tree: dict) -> list[dict]:
    """Check convergence nodes (2 prereqs) are centered between them by x."""
    issues: list[dict] = []
    nodes = tree.get("nodes", {})

    for nid, node in nodes.items():
        prereqs = node.get("prerequisites", [])
        if len(prereqs) != 2:
            continue
        nx = node.get("x")
        if nx is None:
            continue
        p0 = nodes.get(prereqs[0])
        p1 = nodes.get(prereqs[1])
        if p0 is None or p1 is None:
            continue
        x0 = p0.get("x")
        x1 = p1.get("x")
        if x0 is None or x1 is None:
            continue
        mid = (x0 + x1) / 2
        offset = abs(nx - mid)
        if offset > CONVERGENCE_OFFSET_THRESHOLD:
            issues.append({
                "level": LEVEL_WARN,
                "code": "convergence-offset",
                "focus": nid,
                "prereqs": prereqs,
                "x": nx,
                "mid_x": mid,
                "offset": offset,
                "message": f"Convergence offset: {nid} at x={nx}, mid of prereqs is {mid} (offset={offset:.1f})",
            })
    return issues


def check_empty_cp(tree: dict) -> list[dict]:
    """Check for empty or missing continuous_focus_position."""
    issues: list[dict] = []
    cp = tree.get("continuous_focus_position")
    if cp is None or (cp.get("x") is None and cp.get("y") is None):
        issues.append({
            "level": LEVEL_WARN,
            "code": "empty-cp",
            "tree": tree["id"],
            "message": f"continuous_focus_position is empty or not set for {tree['id']}",
        })
    return issues


def _segment_intersection(
    ax1: float, ay1: float, ax2: float, ay2: float,
    bx1: float, by1: float, bx2: float, by2: float,
) -> bool:
    """Check if two line segments intersect."""
    def ccw(x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> float:
        return (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)

    d1 = ccw(ax1, ay1, ax2, ay2, bx1, by1)
    d2 = ccw(ax1, ay1, ax2, ay2, bx2, by2)
    d3 = ccw(bx1, by1, bx2, by2, ax1, ay1)
    d4 = ccw(bx1, by1, bx2, by2, ax2, ay2)

    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    return d1 == 0 or d2 == 0 or d3 == 0 or d4 == 0


def check_crossing_edges(tree: dict) -> list[dict]:
    """Check for crossing prerequisite edges."""
    issues: list[dict] = []
    nodes = tree.get("nodes", {})

    prereq_edges: list[tuple[str, str, float, float, float, float]] = []
    for nid, node in nodes.items():
        nx, ny = node.get("x"), node.get("y")
        if nx is None or ny is None:
            continue
        for prereq in node.get("prerequisites", []):
            pn = nodes.get(prereq)
            if pn is None:
                continue
            px, py = pn.get("x"), pn.get("y")
            if px is None or py is None:
                continue
            prereq_edges.append((prereq, nid, float(px), float(py), float(nx), float(ny)))

    for i in range(len(prereq_edges)):
        for j in range(i + 1, len(prereq_edges)):
            a = prereq_edges[i]
            b = prereq_edges[j]
            if a[0] == b[0] or a[1] == b[1] or a[0] == b[1] or a[1] == b[0]:
                continue  # share a node, skip
            if _segment_intersection(a[2], a[3], a[4], a[5], b[2], b[3], b[4], b[5]):
                issues.append({
                    "level": LEVEL_INFO,
                    "code": "edge-crossing",
                    "edge1": [a[0], a[1]],
                    "edge2": [b[0], b[1]],
                    "message": f"Crossing edges: {a[0]}->{a[1]} crosses {b[0]}->{b[1]}",
                })
    return issues


def check_sibling_misalign(tree: dict) -> list[dict]:
    """Check siblings (share a prerequisite) are on the same y row."""
    issues: list[dict] = []
    nodes = tree.get("nodes", {})

    # Build parent -> children map
    parent_children: dict[str, list[tuple[str, int | None]]] = defaultdict(list)
    for nid, node in nodes.items():
        for prereq in node.get("prerequisites", []):
            parent_children[prereq].append((nid, node.get("y")))

    for parent, children in parent_children.items():
        if len(children) < 2:
            continue
        y_values = [c[1] for c in children if c[1] is not None]
        if not y_values:
            continue
        if len(set(y_values)) > 1:
            child_strs = [f"{c[0]}(y={c[1]})" for c in children]
            issues.append({
                "level": LEVEL_INFO,
                "code": "sibling-misalign",
                "parent": parent,
                "children": [c[0] for c in children],
                "y_values": y_values,
                "message": f"Siblings on different rows under {parent}: {', '.join(child_strs)}",
            })
    return issues


def check_large_y_gaps(tree: dict) -> list[dict]:
    """Check for y gaps > 2 without obvious reason."""
    issues: list[dict] = []
    nodes = tree.get("nodes", {})

    for nid, node in nodes.items():
        ny = node.get("y")
        if ny is None:
            continue
        for prereq in node.get("prerequisites", []):
            pn = nodes.get(prereq)
            if pn is None:
                continue
            py = pn.get("y")
            if py is None:
                continue
            dy = ny - py
            if dy > 2:
                issues.append({
                    "level": LEVEL_INFO,
                    "code": "large-y-gap",
                    "from": prereq,
                    "to": nid,
                    "dy": dy,
                    "message": f"Large y-gap: {prereq} (y={py}) -> {nid} (y={ny}), dy={dy}",
                })
    return issues


def check_long_relpos_chain(tree: dict) -> list[dict]:
    """Check for relative_position_id chains > MAX_RELPOS_CHAIN generations."""
    issues: list[dict] = []
    nodes = tree.get("nodes", {})

    # Build relpos map
    relpos_map: dict[str, str] = {}
    for nid, node in nodes.items():
        rpid = node.get("relative_position_id")
        if rpid:
            relpos_map[nid] = rpid

    # For each node, compute chain length
    for nid in nodes:
        chain = 0
        cur = nid
        while cur in relpos_map:
            chain += 1
            cur = relpos_map[cur]
            if chain > MAX_RELPOS_CHAIN * 2:  # safety break
                break
        if chain > MAX_RELPOS_CHAIN:
            issues.append({
                "level": LEVEL_INFO,
                "code": "long-relpos-chain",
                "focus": nid,
                "chain_length": chain,
                "message": f"Long relative_position_id chain from {nid}: length {chain}",
            })

    # Deduplicate — only report the longest chains
    seen_chains: set[str] = set()
    unique: list[dict] = []
    for issue in issues:
        fid = issue["focus"]
        if fid not in seen_chains:
            seen_chains.add(fid)
            unique.append(issue)
    return unique


def check_focus_in_shared_zone(tree: dict) -> list[dict]:
    """Check that political focuses start at x >= 28 (shared backbone zone)."""
    issues: list[dict] = []
    nodes = tree.get("nodes", {})

    for nid, node in nodes.items():
        x = node.get("x")
        is_shared = node.get("is_shared", False)
        prereqs = node.get("prerequisites", [])
        if x is not None and x < 28 and not is_shared and prereqs:
            # This is a political focus in the shared backbone zone
            issues.append({
                "level": LEVEL_INFO,
                "code": "focus-in-shared-zone",
                "focus": nid,
                "x": x,
                "message": f"Focus {nid} at x={x} in shared backbone zone (x < 28). May overlap with develop_the_country.",
            })
    return issues


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

ALL_CHECKS = [
    ("overlap", check_overlap),
    ("broken-refs", check_broken_refs),
    ("no-root", check_no_root),
    ("anchor-mismatch", check_anchor_mismatch),
    ("long-edges", check_long_edges),
    ("backward-edges", check_backward_edges),
    ("too-many-prereqs", check_too_many_prereqs),
    ("convergence-offset", check_convergence_offset),
    ("empty-cp", check_empty_cp),
    ("crossing-edges", check_crossing_edges),
    ("sibling-misalign", check_sibling_misalign),
    ("large-y-gaps", check_large_y_gaps),
    ("long-relpos-chain", check_long_relpos_chain),
    ("focus-in-shared-zone", check_focus_in_shared_zone),
]


def audit_tree(tree: dict) -> dict:
    """Run all checks on one tree, return summary."""
    all_issues: list[dict] = []
    for name, check_fn in ALL_CHECKS:
        try:
            issues = check_fn(tree)
            all_issues.extend(issues)
        except Exception as e:
            all_issues.append({
                "level": LEVEL_ERROR,
                "code": f"check-error:{name}",
                "message": f"Check '{name}' failed: {e}",
            })

    errors = [i for i in all_issues if i["level"] == LEVEL_ERROR]
    warns = [i for i in all_issues if i["level"] == LEVEL_WARN]
    infos = [i for i in all_issues if i["level"] == LEVEL_INFO]

    return {
        "tree": tree["id"],
        "file": tree.get("file", ""),
        "node_count": tree.get("node_count", 0),
        "errors": len(errors),
        "warns": len(warns),
        "infos": len(infos),
        "issues": all_issues,
    }


def format_issue(issue: dict) -> str:
    level = issue["level"]
    code = issue.get("code", "?")
    msg = issue.get("message", str(issue))
    return f"  [{level:5s}] {code:22s} {msg}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit focus tree layout for readability issues")
    ap.add_argument("--graph", type=str, default="tools/focus_layout/focus_graph.json",
                    help="Path to graph JSON")
    ap.add_argument("--tree", type=str, help="Audit a specific tree")
    ap.add_argument("--all", action="store_true", help="Audit all trees")
    ap.add_argument("--json", action="store_true", help="Output results as JSON")
    ap.add_argument("--errors-only", action="store_true", help="Only show ERROR-level issues")
    ap.add_argument("--quiet", action="store_true", help="Summary only, no issue details")
    args = ap.parse_args()

    graph_path = args.graph
    if not os.path.isfile(graph_path):
        script_dir = Path(__file__).resolve().parent
        graph_path = str(script_dir / "focus_graph.json")
    if not os.path.isfile(graph_path):
        print("ERROR: graph JSON not found. Run graph.py --all first.", file=sys.stderr)
        return 1

    data = load_graph(graph_path)
    trees = data.get("trees", {})

    if args.tree:
        if args.tree in trees:
            trees = {args.tree: trees[args.tree]}
        else:
            print(f"ERROR: tree '{args.tree}' not found", file=sys.stderr)
            return 1
    elif not args.all:
        # Default: second_war + first_war trees
        trees = {k: v for k, v in trees.items() if "second_war" in k or "first_war" in k}

    results = {}
    total_errors = 0
    total_warns = 0
    total_infos = 0

    for tid in sorted(trees):
        td = trees[tid]
        result = audit_tree(td)
        results[tid] = result
        total_errors += result["errors"]
        total_warns += result["warns"]
        total_infos += result["infos"]

        if args.json:
            continue

        # Print per-tree summary
        e = result["errors"]
        w = result["warns"]
        i = result["infos"]
        if args.errors_only and e == 0:
            continue
        if e + w + i == 0:
            if not args.quiet:
                print(f"  {tid:35s}  OK")
            continue

        print(f"\n{'='*80}")
        print(f"  {tid}  ({result['file']})")
        print(f"  nodes: {result['node_count']}  |  errors: {e}  warns: {w}  infos: {i}")
        print(f"{'='*80}")

        if not args.quiet:
            for issue in result["issues"]:
                if args.errors_only and issue["level"] != LEVEL_ERROR:
                    continue
                print(format_issue(issue))

    # Final summary
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"\n{'='*80}")
        print(f"  TOTAL: {total_errors} errors, {total_warns} warns, {total_infos} infos across {len(trees)} trees")
        print(f"{'='*80}")

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
