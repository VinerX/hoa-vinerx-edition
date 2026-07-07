#!/usr/bin/env python3
"""
Focus tree SVG preview generator.

Renders a focus tree as an SVG diagram with nodes, prerequisite edges,
and mutually exclusive indicators.

Usage:
  # Generate JSON first
  python tools/focus_layout/graph.py --all

  # Render specific tree
  python tools/focus_layout/preview.py --tree kultiras_second_war

  # Render all trees
  python tools/focus_layout/preview.py --all

  # Use a specific graph JSON
  python tools/focus_layout/preview.py --graph my_graph.json --tree kultiras_second_war
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Grid constants (match HOI4 focus tree spacing)
# ---------------------------------------------------------------------------
DX = 96    # pixels per x unit
DY = 130   # pixels per y unit
NODE_W = 86
NODE_H = 100
CORNER_R = 6
FONT_SIZE_TITLE = 9
FONT_SIZE_DETAIL = 7

# Colors
COLOR_BG = "#1a1a2e"
COLOR_GRID = "#252540"
COLOR_NODE_FILL = "#2d2d4a"
COLOR_NODE_STROKE = "#4a4a8a"
COLOR_NODE_TEXT = "#e0e0f0"
COLOR_NODE_SUBTEXT = "#9090b0"
COLOR_EDGE_PREREQ = "#5a5aff"
COLOR_EDGE_ME = "#ff4444"
COLOR_EDGE_RELPOS = "#888844"
COLOR_SHARED_FILL = "#2a3a2a"
COLOR_SHARED_STROKE = "#3a5a3a"
COLOR_ERROR = "#ff3333"
COLOR_WARN = "#ffaa33"


def wrap_text(text: str, max_chars: int = 12) -> list[str]:
    """Wrap long text into multiple lines."""
    if len(text) <= max_chars:
        return [text]
    lines: list[str] = []
    words = text.replace("_", " ").split()
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if len(test) <= max_chars:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines if lines else [text]


def focus_display_name(fid: str) -> str:
    """Convert focus id to a readable short name."""
    # Remove common prefixes
    for prefix in ["_sw_", "sw_"]:
        if prefix in fid:
            parts = fid.split(prefix, 1)
            return parts[1] if len(parts) > 1 else fid
    # Remove tag prefix (ABC_)
    if "_" in fid:
        rest = fid.split("_", 1)[1]
        return rest
    return fid


def node_center(x_abs: int, y_abs: int, origin_x: int, origin_y: int) -> tuple[float, float]:
    """Convert grid coords to SVG pixel center."""
    cx = origin_x + x_abs * DX + DX / 2
    cy = origin_y + y_abs * DY + DY / 2
    return cx, cy


def node_rect(x_abs: int, y_abs: int, origin_x: int, origin_y: int) -> tuple[float, float, float, float]:
    """Convert grid coords to SVG rect top-left."""
    x = origin_x + x_abs * DX + (DX - NODE_W) / 2
    y = origin_y + y_abs * DY + (DY - NODE_H) / 2
    return x, y, NODE_W, NODE_H


def render_tree(tree_data: dict) -> str:
    """Render a single focus tree to SVG string."""
    nodes = tree_data.get("nodes", {})
    edges = tree_data.get("edges", [])
    bb = tree_data.get("bounding_box", {})
    tree_id = tree_data.get("id", "unknown")

    x_min = bb.get("x_min", 0)
    x_max = bb.get("x_max", 0)
    y_min = bb.get("y_min", 0)
    y_max = bb.get("y_max", 0)

    # Padding in grid units
    pad = 2
    x_min -= pad
    y_min -= pad
    x_max += pad
    y_max += pad

    # Padding in pixels
    MARGIN = 60
    svg_w = max(800, (x_max - x_min) * DX + 2 * MARGIN)
    svg_h = max(600, (y_max - y_min) * DY + 2 * MARGIN)

    # Origin offset to shift grid into the visible area
    origin_x = MARGIN - x_min * DX
    origin_y = MARGIN - y_min * DY

    cp = tree_data.get("continuous_focus_position")
    country_tag = tree_data.get("country_tag", "")
    shared_imports = tree_data.get("shared_focus_imports", [])

    svg_parts: list[str] = []
    svg_parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}">')
    svg_parts.append(f'<rect width="100%" height="100%" fill="{COLOR_BG}"/>')

    # Grid
    for x in range(int(x_min) - 1, int(x_max) + 2):
        gx = origin_x + x * DX
        svg_parts.append(f'<line x1="{gx}" y1="{MARGIN}" x2="{gx}" y2="{svg_h - MARGIN}" stroke="{COLOR_GRID}" stroke-width="0.5" stroke-dasharray="4,4"/>')
    for y in range(int(y_min) - 1, int(y_max) + 2):
        gy = origin_y + y * DY
        svg_parts.append(f'<line x1="{MARGIN}" y1="{gy}" x2="{svg_w - MARGIN}" y2="{gy}" stroke="{COLOR_GRID}" stroke-width="0.5" stroke-dasharray="4,4"/>')

    # Legend
    legend_x = svg_w - 200
    legend_y = 10
    svg_parts.append(f'<rect x="{legend_x}" y="{legend_y}" width="190" height="90" rx="4" fill="#00000088" stroke="{COLOR_GRID}"/>')
    svg_parts.append(f'<text x="{legend_x + 10}" y="{legend_y + 18}" fill="{COLOR_NODE_TEXT}" font-size="10" font-family="monospace" font-weight="bold">Legend</text>')
    svg_parts.append(f'<line x1="{legend_x + 10}" y1="{legend_y + 30}" x2="{legend_x + 50}" y2="{legend_y + 30}" stroke="{COLOR_EDGE_PREREQ}" stroke-width="2"/>')
    svg_parts.append(f'<text x="{legend_x + 55}" y="{legend_y + 34}" fill="{COLOR_NODE_TEXT}" font-size="9" font-family="monospace">prerequisite</text>')
    svg_parts.append(f'<line x1="{legend_x + 10}" y1="{legend_y + 48}" x2="{legend_x + 50}" y2="{legend_y + 48}" stroke="{COLOR_EDGE_ME}" stroke-width="2" stroke-dasharray="6,4"/>')
    svg_parts.append(f'<text x="{legend_x + 55}" y="{legend_y + 52}" fill="{COLOR_NODE_TEXT}" font-size="9" font-family="monospace">mut. exclusive</text>')
    svg_parts.append(f'<line x1="{legend_x + 10}" y1="{legend_y + 66}" x2="{legend_x + 50}" y2="{legend_y + 66}" stroke="{COLOR_EDGE_RELPOS}" stroke-width="1" stroke-dasharray="2,3"/>')
    svg_parts.append(f'<text x="{legend_x + 55}" y="{legend_y + 70}" fill="{COLOR_NODE_TEXT}" font-size="9" font-family="monospace">rel_position_id</text>')

    # Continuous focus position marker
    if cp and cp.get("x") and cp.get("y"):
        cpx = cp["x"]
        cpy = cp["y"]
        # CP is in pixels already; show if within view
        svg_parts.append(f'<rect x="{cpx - 5}" y="{cpy - 5}" width="10" height="10" rx="2" fill="none" stroke="{COLOR_WARN}" stroke-width="1"/>')
        svg_parts.append(f'<text x="{cpx + 8}" y="{cpy + 4}" fill="{COLOR_WARN}" font-size="8" font-family="monospace">CP</text>')

    # Shared focus imports indicator
    if shared_imports:
        si_text = ", ".join(shared_imports[:3])
        if len(shared_imports) > 3:
            si_text += f" +{len(shared_imports) - 3}"
        svg_parts.append(f'<text x="{MARGIN + 5}" y="{MARGIN - 10}" fill="{COLOR_SHARED_STROKE}" font-size="8" font-family="monospace">shared: {si_text}</text>')

    # Mutually exclusive edges (draw under everything else)
    for edge in edges:
        if edge["type"] != "mutually_exclusive":
            continue
        fr = edge["from"]
        to = edge["to"]
        if fr not in nodes or to not in nodes:
            continue
        fn = nodes[fr]
        tn = nodes[to]
        if fn.get("x") is None or fn.get("y") is None or tn.get("x") is None or tn.get("y") is None:
            continue
        x1, y1 = node_center(fn["x"], fn["y"], origin_x, origin_y)
        x2, y2 = node_center(tn["x"], tn["y"], origin_x, origin_y)

        # Draw dashed line between the two nodes at same y
        mid_y = y1 + 30
        svg_parts.append(
            f'<path d="M{x1},{mid_y} L{x2},{mid_y}" '
            f'stroke="{COLOR_EDGE_ME}" stroke-width="2.5" stroke-dasharray="8,5" fill="none" opacity="0.7"/>'
        )
        # ME label
        svg_parts.append(
            f'<text x="{(x1 + x2) / 2}" y="{mid_y - 5}" text-anchor="middle" '
            f'fill="{COLOR_EDGE_ME}" font-size="8" font-family="monospace">ME</text>'
        )

    # Prerequisite edges
    for edge in edges:
        if edge["type"] != "prerequisite":
            continue
        fr = edge["from"]
        to = edge["to"]
        if fr not in nodes or to not in nodes:
            continue
        fn = nodes[fr]
        tn = nodes[to]
        if fn.get("x") is None or fn.get("y") is None or tn.get("x") is None or tn.get("y") is None:
            continue

        x1, y1 = node_center(fn["x"], fn["y"], origin_x, origin_y)
        x2, y2 = node_center(tn["x"], tn["y"], origin_x, origin_y)

        # Draw orthogonal path: down from parent, horizontal to child x, down to child
        mid_y = (y1 + y2) / 2

        if abs(x1 - x2) < 5:
            # Nearly vertical — simple straight line
            path = f'M{x1},{y1 + NODE_H / 2} L{x2},{y2 - NODE_H / 2}'
        else:
            # Orthogonal: go down halfway, horizontal, down to child
            path = (f'M{x1},{y1 + NODE_H / 2} '
                    f'L{x1},{mid_y} '
                    f'L{x2},{mid_y} '
                    f'L{x2},{y2 - NODE_H / 2}')

        svg_parts.append(
            f'<path d="{path}" stroke="{COLOR_EDGE_PREREQ}" stroke-width="1.5" fill="none" opacity="0.6"/>'
        )
        # Arrow at end
        svg_parts.append(
            f'<circle cx="{x2}" cy="{y2 - NODE_H / 2}" r="3" fill="{COLOR_EDGE_PREREQ}" opacity="0.6"/>'
        )

    # Relative position edges (subtle, dashed)
    for edge in edges:
        if edge["type"] != "relative_position":
            continue
        fr = edge["from"]
        to = edge["to"]
        if fr not in nodes or to not in nodes:
            continue
        fn = nodes[fr]
        tn = nodes[to]
        if fn.get("x") is None or fn.get("y") is None or tn.get("x") is None or tn.get("y") is None:
            continue

        x1, y1 = node_center(fn["x"], fn["y"], origin_x, origin_y)
        x2, y2 = node_center(tn["x"], tn["y"], origin_x, origin_y)

        svg_parts.append(
            f'<line x1="{x1}" y1="{y1 + NODE_H / 2}" x2="{x2}" y2="{y2 - NODE_H / 2}" '
            f'stroke="{COLOR_EDGE_RELPOS}" stroke-width="0.8" stroke-dasharray="3,4" fill="none" opacity="0.4"/>'
        )

    # Focus nodes
    for nid, node in sorted(nodes.items()):
        if node.get("x") is None or node.get("y") is None:
            continue
        rx, ry, rw, rh = node_rect(node["x"], node["y"], origin_x, origin_y)
        is_shared = node.get("is_shared", False)
        prereq_count = len(node.get("prerequisites", []))

        fill = COLOR_SHARED_FILL if is_shared else COLOR_NODE_FILL
        stroke_c = COLOR_SHARED_STROKE if is_shared else COLOR_NODE_STROKE

        # Highlight issues
        if prereq_count > 2:
            stroke_c = COLOR_WARN

        svg_parts.append(
            f'<rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" rx="{CORNER_R}" '
            f'fill="{fill}" stroke="{stroke_c}" stroke-width="1.5"/>'
        )

        # Focus title
        display = focus_display_name(nid)
        lines = wrap_text(display, 13)
        title_y = ry + rh / 2 - (len(lines) - 1) * 6
        for i, line in enumerate(lines):
            svg_parts.append(
                f'<text x="{rx + rw / 2}" y="{title_y + i * 12}" text-anchor="middle" '
                f'fill="{COLOR_NODE_TEXT}" font-size="{FONT_SIZE_TITLE}" font-family="monospace">{line}</text>'
            )

        # Subtitle with grid coords
        coord_label = f"({node['x']},{node['y']})"
        svg_parts.append(
            f'<text x="{rx + rw / 2}" y="{ry + rh - 8}" text-anchor="middle" '
            f'fill="{COLOR_NODE_SUBTEXT}" font-size="{FONT_SIZE_DETAIL}" font-family="monospace">{coord_label}</text>'
        )

        # Prereq count badge
        if prereq_count > 1:
            badge_x = rx + rw - 2
            badge_y = ry + 2
            svg_parts.append(
                f'<circle cx="{badge_x - 7}" cy="{badge_y + 7}" r="8" fill="{COLOR_EDGE_PREREQ}" opacity="0.8"/>'
            )
            svg_parts.append(
                f'<text x="{badge_x - 7}" y="{badge_y + 10}" text-anchor="middle" '
                f'fill="#fff" font-size="8" font-family="monospace">{prereq_count}</text>'
            )

    # Title
    svg_parts.append(
        f'<text x="20" y="24" fill="{COLOR_NODE_TEXT}" font-size="14" font-family="monospace" font-weight="bold">'
        f'{tree_id} [{country_tag}]</text>'
    )
    svg_parts.append(
        f'<text x="20" y="40" fill="{COLOR_NODE_SUBTEXT}" font-size="9" font-family="monospace">'
        f'nodes: {len(nodes)} | file: {tree_data.get("file", "?")}</text>'
    )

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate SVG preview of focus trees")
    ap.add_argument("--graph", type=str, default="tools/focus_layout/focus_graph.json",
                    help="Path to graph JSON (default: tools/focus_layout/focus_graph.json)")
    ap.add_argument("--tree", type=str, help="Render a specific tree by id")
    ap.add_argument("--all", action="store_true", help="Render all trees")
    ap.add_argument("--output-dir", type=str, default="tools/focus_layout/preview",
                    help="Output directory for SVG files")
    args = ap.parse_args()

    # Find graph file
    graph_path = args.graph
    if not os.path.isfile(graph_path):
        # Try relative to script
        script_dir = Path(__file__).resolve().parent
        graph_path = str(script_dir / "focus_graph.json")

    if not os.path.isfile(graph_path):
        print("ERROR: graph JSON not found. Run graph.py --all first.", file=sys.stderr)
        print(f"       Looked for: {graph_path}", file=sys.stderr)
        return 1

    with open(graph_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    trees = data.get("trees", {})
    if not trees:
        print("ERROR: no trees in graph JSON", file=sys.stderr)
        return 1

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    if args.tree:
        if args.tree in trees:
            trees = {args.tree: trees[args.tree]}
        else:
            print(f"ERROR: tree '{args.tree}' not in graph", file=sys.stderr)
            print(f"Available: {', '.join(sorted(trees))}", file=sys.stderr)
            return 1
    elif not args.all:
        # Default: render second_war trees only
        trees = {k: v for k, v in trees.items() if "second_war" in k or "first_war" in k}

    count = 0
    for tid, td in sorted(trees.items()):
        svg = render_tree(td)
        out_path = os.path.join(output_dir, f"{tid}.svg")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(svg)
        count += 1
        print(f"  {tid}.svg  ({td.get('node_count', 0)} nodes)", file=sys.stderr)

    print(f"\nRendered {count} trees to {output_dir}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
