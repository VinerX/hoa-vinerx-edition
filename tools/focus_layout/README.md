# Focus Tree Layout Pipeline

Tools for auditing, previewing, and refactoring HOI4 national focus tree layouts.

## Quick start

```bash
# 1. Generate dependency graph for all trees
python tools/focus_layout/graph.py --all

# 2. Audit a specific tree
python tools/focus_layout/audit.py --tree kultiras_second_war

# 3. Audit all second-war trees (errors only, short summary)
python tools/focus_layout/audit.py --all --errors-only --quiet

# 4. Generate SVG preview
python tools/focus_layout/preview.py --tree kultiras_second_war

# 5. Generate previews for all second-war trees
python tools/focus_layout/preview.py --all
```

## Tools

### `graph.py` — Dependency Graph Extractor

Parses all focus files in `common/national_focus/`, resolves `relative_position_id`
chains to absolute coordinates, and outputs a JSON dependency graph.

| Flag | Description |
|---|---|
| `--all` | Output all trees (default) |
| `--tree <id>` | Output a specific tree |
| `--file <path>` | Output trees from a specific file |
| `--trees` | List all tree IDs with metadata |
| `--output <path>` | Output JSON path (default: `tools/focus_layout/focus_graph.json`) |

Output schema:
```json
{
  "trees": {
    "<tree_id>": {
      "id": "kultiras_second_war",
      "file": "common/national_focus/kultiras_second_war.txt",
      "country_tag": "KUL",
      "continuous_focus_position": {"x": 1300, "y": 0},
      "shared_focus_imports": ["develop_the_country", "arming_the_nation"],
      "node_count": 171,
      "nodes": {
        "<focus_id>": {
          "id": "...",
          "x": 38, "y": 0,
          "relative_position_id": null,
          "prerequisites": ["..."],
          "mutually_exclusive": ["..."],
          "cost": 7,
          "icon": "GFX_...",
          "is_shared": false
        }
      },
      "edges": [
        {"from": "...", "to": "...", "type": "prerequisite"},
        {"from": "...", "to": "...", "type": "mutually_exclusive"},
        {"from": "...", "to": "...", "type": "relative_position"}
      ],
      "bounding_box": {"x_min": 9, "x_max": 56, "y_min": 0, "y_max": 18}
    }
  }
}
```

Coordinates are **absolute** (relative_position_id chains fully resolved). `x` and `y`
are in grid units (x+1 ≈ 96 px, y+1 ≈ 130 px in-game).

### `audit.py` — Layout Audit

Checks focus trees for readability and functional issues.

| Flag | Description |
|---|---|
| `--tree <id>` | Audit a specific tree |
| `--all` | Audit all trees |
| `--errors-only` | Only show ERROR-level issues |
| `--quiet` | Summary only, no issue details |
| `--json` | Output as JSON |

#### Issue levels

| Level | Meaning |
|---|---|
| **ERROR** | Must fix — overlap, broken refs |
| **WARN** | Should fix — anchor mismatch, long edges, backward edges, too many prereqs |
| **INFO** | Review — crossing edges, sibling misalignment, y-gaps, long relpos chains |

#### Check reference

| Code | Level | Description |
|---|---|---|
| `overlap` | ERROR | Two focuses at exact same (x, y) |
| `broken-relpos` | ERROR | `relative_position_id` references non-existent focus |
| `broken-prereq` | ERROR | `prerequisite` references non-existent focus |
| `broken-me` | ERROR | `mutually_exclusive` references non-existent focus |
| `no-root` | WARN | No focus without `relative_position_id` (tree has no anchor) |
| `anchor-mismatch` | WARN | `relative_position_id` differs from all prerequisites |
| `long-edge` | WARN | Prereq edge with Δx > 4 or Δy > 3 |
| `backward-edge` | WARN | Child at or above parent's y (visual confusion) |
| `too-many-prereqs` | WARN | > 2 incoming prereq edges on one focus (should use gateway) |
| `convergence-offset` | WARN | Convergence node not centered between its two prerequisites |
| `empty-cp` | WARN | `continuous_focus_position` empty or missing |
| `edge-crossing` | INFO | Two prerequisite edges cross geometrically |
| `sibling-misalign` | INFO | Sibling focuses on different y rows |
| `large-y-gap` | INFO | y step > 2 without obvious cause |
| `long-relpos-chain` | INFO | `relative_position_id` chain > 4 generations |
| `focus-in-shared-zone` | INFO | Political focus at x < 28 (shared backbone zone) |

### `preview.py` — SVG Preview Generator

Renders focus trees as SVG diagrams.

| Flag | Description |
|---|---|
| `--tree <id>` | Render a specific tree |
| `--all` | Render all trees (default: second-war only) |
| `--graph <path>` | Graph JSON path |
| `--output-dir <dir>` | Output directory for SVGs (default: `tools/focus_layout/preview/`) |

Edge colors:
- **Blue solid** = prerequisite
- **Red dashed** = mutually exclusive
- **Yellow dotted** = relative_position_id

## Workflow

### For new focus trees

```
1. Author mechanics       →  write effects, prerequisites, available
2. Run graph             →  python tools/focus_layout/graph.py --all
3. Run audit            →  python tools/focus_layout/audit.py --tree <tree_id>
4. Fix ERRORs           →  must be zero
5. Generate preview     →  python tools/focus_layout/preview.py --tree <tree_id>
6. Visual review         →  open preview/<tree_id>.svg
7. Layout pass           →  fix WARNs (anchor mismatch, long edges, backward edges)
8. Run validate.py      →  python tools/validate.py --quiet
9. Commit
```

### For refactoring old trees

```
1. Run audit           →  get list of issues
2. Generate preview    →  SVG "before"
3. Apply layout rules  →  fix x/y/relative_position_id (NEVER change effects/prereqs)
4. Re-run audit        →  ERRORS: 0, WARNs minimized
5. Generate preview    →  SVG "after"
6. Run validate.py     →  ERRORS: 0
7. Commit
```

### Layout agent prompt

Use `tools/focus_layout/layout_agent.md` as a prompt template when delegating
layout work to an AI agent. The agent must not change gameplay logic.

## Layout Rules (priority order)

1. **Readability of prerequisites** — player must immediately see the path
2. **Readability of mutually exclusive branches** — obvious where the choice is
3. **Chronology** — early focuses above, late below (standard step: y+1)
4. **Thematic columns** — politics left, main war story center, special mechanics right
5. **Symmetry and aesthetics** — only after the first four

### Hard rules
- `relative_position_id` must be one of the focus's prerequisites (80-90% of cases)
- Standard vertical step: **y +1** (one "story level")
- **y +2** only for act transitions (major new phase)
- Sibling focuses on the same **y row**
- Convergence focus **centered between** its two prerequisites (by x)
- **Gateway focus** for 3+ incoming prereq edges (instead of spaghetti lines)
- Max `relative_position_id` chain: 3-4 generations (beyond that = drift)
- Large sections anchored to stable root focuses with **absolute** x/y
- Political branches must start at **x >= 28** (right of shared backbone)
