# Layout Agent Prompt Template

Use this as the instruction prompt when delegating focus tree layout work to an AI agent.
Copy it verbatim and append the specific tree information (audit output + graph data).

---

Audit and rebuild the visual layout of the national focus tree.

Primary goal: **FUNCTIONAL READABILITY.**

The player must be able to understand the prerequisite structure immediately from the tree layout.
Every prerequisite line must be visually traceable from parent to child without crossing
unrelated branches or spanning half the screen.

## What you may change

Only layout coordinates and relative positioning:
- `x`, `y` values
- `relative_position_id` references

## What you must NOT change

- Focus effects (`completion_reward`, `available`, `bypass`, `ai_will_do`)
- Prerequisite logic (`prerequisite = { focus = ... }`)
- Mutually exclusive relationships (`mutually_exclusive = { focus = ... }`)
- Focus IDs, costs, icons, localisation
- `shared_focus` imports
- Any scripted effects, triggers, or game logic

## Layout rules

### Absolute priority: readability over symmetry
1. Readable prerequisites > beautiful symmetry
2. Chronology (top to bottom) > compactness  
3. Thematic columns > space efficiency

### Prerequisite visual rules
1. A focus **must** be visually positioned relative to one of its actual prerequisites (`relative_position_id` ∈ `prerequisite` set). The only exception is a pure convergence node where both prereqs are equidistant and the relpos can be a third anchor that makes geometric sense.
2. Standard vertical step: **y + 1** (one "story level" = one row down).
3. **y + 2** only for major act transitions (e.g. "The War Reaches the Front").
4. Sibling focuses (sharing a prerequisite) must be on the **same y row**.
5. A convergence focus with 2 prerequisites must be **centered between them** by x.
6. Prerequisite edges must **not cross** unrelated branches. If a line would cross 3+ columns of another branch, restructure.
7. Avoid prerequisite edges longer than 4 columns (Δx ≤ 4) or 3 rows (Δy ≤ 3).
8. A child must always be **visually below** its parent (child.y > parent.y), unless it is part of a deliberate convergence diamond.

### Gateway pattern
When a focus has 3+ incoming prerequisites from different parts of the tree:
- Create a **gateway focus** that collects them
- The gateway becomes the single prerequisite for the complex focus
- This adds 1 focus but makes the tree readable

### Mutually exclusive rules
1. Mutually exclusive siblings must be visually **balanced around their parent** by x.
2. They must be on the **same y row**.
3. If one branch is fundamentally longer, use intermediate mini-gateways rather than asymmetry.

### Structural rules
1. Avoid chains of `relative_position_id` longer than 3-4 generations. Anchor large sections to stable root focuses with **absolute** x/y.
2. Political branches start at **x >= 28** (right of `develop_the_country` shared backbone).
3. Thematic zones: x = 28-34 (internal politics), x = 35-44 (main war story), x = 45-55 (special mechanics / side content).
4. Major story spine focuses should form the **visual center** of the tree.
5. `continuous_focus_position` should be set to a pixel position that does not overlap the tree visually.

### x spacing guidelines
- Between independent major branches: **Δx = 2-3**
- Between left/right alternatives of a mutually exclusive choice: **Δx = 2-4** (symmetric)
- Between a parent and a single child: **Δx = 0** (directly below)

### y spacing guidelines
- Standard: **y + 1** per focus level
- Act breaks: **y + 2** for major story transitions
- Convergence: the converging node should be **y + 1** below the lower of its two prerequisites

## Process

1. Read the audit output to identify specific issues (anchor mismatches, long edges, backward edges, overlaps).
2. Read the graph JSON to understand the current topology.
3. Plan the new layout: define thematic columns and the central story spine.
4. Apply coordinate changes — one focus at a time, working from root down.
5. Verify: re-run audit → ERRORS: 0, WARNs minimized.
6. Generate preview SVG to visually confirm readability.

## Report format

After making changes, report:
```
Files changed: <list>
Layout-only changes: <count>
Errors fixed: <list of codes>
Anchor mismatches fixed: <count>
Long edges fixed: <count>
Crossing edges fixed: <count>
Remaining intentional exceptions: <list with justification>
```
