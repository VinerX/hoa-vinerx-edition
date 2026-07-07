# Focus tree authoring checklist

How to add a nation focus tree in HOA VinerX Edition. **Reuse the generic non-political
branches** for the economy/military backbone and only hand-author the political/story part.
Read `AGENTS.md` first for the general rules.

## The generic backbone (reuse this, don't rewrite it)

The default tree `generic_focus` (in `common/national_focus/generic_focus.txt`) is built
from four shared-focus roots defined in `common/national_focus/generic_shared_focus.txt`:

| shared root | kind | covers |
|---|---|---|
| `our_nation` | political base | `our_people`, `how_we_fight` (early identity focuses) |
| `the_path_forward` | political | `pick_a_side` -> ideology/alignment branch (Alliance/Horde/...) |
| **`develop_the_country`** | **non-political (economy)** | `blacksmith_1`, `build_roads`->`prospect_the_soil`, `workshop_1`, `improved_forges` - industry, infrastructure, resources, research bonuses |
| **`arming_the_nation`** | **non-political (military)** | `army_training`->`infantry/cavalry_training`->`train_archers/knights/spellcasters/mounted_footmen`->`support_units` - army/navy/air XP, unit tech bonuses, doctrine cost |

**Rule of thumb:** a new nation tree should pull in `develop_the_country` and
`arming_the_nation` (and usually `our_nation`) via `shared_focus = ...`, so every nation gets
a consistent non-political base for free. Then author the nation's own political/story
branch. Only fork a shared branch if this nation genuinely needs different economy/military
focuses.

## Skeleton (copy-paste, then fill the political branch)

```txt
#!gfx:interface\hoa_focus.gfx
focus_tree = {
    id = XXX_focus                       # unique; convention: <TAG>_focus
    country = { factor = 0 modifier = { add = 10 tag = XXX } }
    default = no
    reset_on_civilwar = no

    continuous_focus_position = { x = 1300 y = 0 }

    # --- non-political backbone (reused) ---
    shared_focus = our_nation
    shared_focus = develop_the_country   # economy / industry / research
    shared_focus = arming_the_nation     # army / navy / air buildup

    # --- nation-specific political / story branch (author below) ---
    focus = {
        id = XXX_first_focus
        icon = GFX_goal_generic_...
        cost = 10                        # 10 = ~70 days
        x = 5  y = 0                     # or relative_position_id + x/y
        available = { }                  # optional gate
        completion_reward = {
            # add_political_power / add_ideas / country_event = ns.n / create_wargoal / ...
        }
    }
}
```

## Per-tree checklist

- [ ] `focus_tree` has a **unique `id`** and a `country = { ... }` rule that selects your TAG.
- [ ] `default = no` (only `generic_focus` is `default = yes`).
- [ ] Included the non-political shared branches you want (`develop_the_country`,
      `arming_the_nation`, and usually `our_nation`) instead of re-authoring economy/army focuses.
- [ ] Nation's political/story focuses authored (leader/ideology, war goals, unique mechanics).
- [ ] The tree loads for the nation: either it wins the `country` factor, or history uses
      `load_focus_tree = XXX_focus` (some HOA nations swap trees by date/flag).

## Per-focus checklist

- [ ] Unique `id` (globally unique across ALL focus files - the validator flags dups).
- [ ] `icon = GFX_...` that exists.
- [ ] `cost` (in weeks*... ; 10 ~= 70 days) and a position: `x`/`y`, or
      `relative_position_id = <other focus>` + `x`/`y`.
- [ ] Links resolve: every `prerequisite = { focus = ... }`, `mutually_exclusive`,
      `relative_position_id`, `shared_focus` points at a **defined** focus id.
- [ ] Gating as needed: `available = { }`, `bypass = { }`, `will_lead_to_war_with = TAG`.
- [ ] `completion_reward = { }` present (effects, and/or `country_event = ns.n`).
- [ ] War focuses: prefer robust triggers (e.g. control of a state) over `has_capitulated`
      for nations that reform as refugees - see the Stormwind note in `AGENTS.md`.

## Focus art spec

For this project, new custom focus icons should currently target:

- `140x140` canvas for focus icons
- final file format: `.dds`
- scripted tree placement still uses the normal focus grid:
  `x +1 = 96 px`, `y +1 = 130 px`

Practical art rules:

- keep one centered subject
- do not bake a decorative border into the icon itself
- leave enough empty margin so the in-game frame does not visually clip the subject

## Placeholder icons (fine for now - no art needed)

A focus `icon` just needs to reference an existing `GFX_*` sprite. A wrong/missing icon is
non-fatal - the game shows a blank square and logs a texture warning, nothing crashes - so
never block on icons if you are only scripting. Known-good keys (defined in
`interface/hoa_focus.gfx` or vanilla):

- `GFX_goal_placeholder` - explicit placeholder (safest default).
- Military: `GFX_focus_generic_golden_sword`, `GFX_focus_generic_orc_warrior`.
- Economy/build: `GFX_focus_generic_construction_green` (`_blue` / `_brown` variants exist).
- Nation flavour: `GFX_focus_stormwind_generic`.
- Any vanilla `GFX_goal_generic_*` (e.g. `GFX_goal_generic_political_pressure`,
  `GFX_goal_generic_construct_infrastructure`, `GFX_goal_generic_major_war`).

To find more, grep existing sprites: `grep -rhoE 'name = "GFX_(goal|focus)_[a-z_0-9]+"' interface/*.gfx`.

## Localisation checklist

For every focus id, add to a `localisation/english/<yourbatch>_l_english.yml`:

```yml
l_english:
 XXX_first_focus:0 "Focus Title"
 XXX_first_focus_desc:0 "Tooltip/flavour. \n for newlines, [XXX.GetLeader] scopes."
```

- [ ] Title (`<id>:0`) and description (`<id>_desc:0`) for each new focus.
- [ ] Any `custom_effect_tooltip`/`custom_trigger_tooltip` keys used are defined too.

## Visual Layout Rules

Focus tree layout must prioritise **functional readability** over symmetry. The player
must immediately understand prerequisites from the tree layout. Use the layout pipeline
(`tools/focus_layout/`) to audit and preview.

### Priority order (highest first)

1. **Readability of prerequisite edges** — player must see what leads to what
2. **Readability of mutually exclusive choices** — obvious where the fork is
3. **Chronology** — early above, late below. Standard step: **y + 1**
4. **Thematic columns** — politics left, war story centre, special mechanics right
5. **Symmetry and aesthetics** — only after the first four

### Hard rules

- [ ] **Anchor rule**: `relative_position_id` must be one of the focus's `prerequisite`
      entries (the visual anchor should trace the logical dependency). Exception: pure
      convergence nodes where a third anchor makes geometric sense.
- [ ] **Standard step**: **y + 1** between consecutive focuses. Use **y + 2** only for
      major act transitions (new phase of the war).
- [ ] **Sibling row**: focuses sharing a prerequisite must be on the **same y row**.
- [ ] **Convergence centring**: a focus with exactly 2 prerequisites must be **x-centred**
      between them (offset <= 2 columns).
- [ ] **Gateway pattern**: a focus with 3+ incoming prerequisite edges should be
      preceded by a gateway focus that collects them. Avoid spaghetti.
- [ ] **No backward edges**: child.y must be > parent.y (except deliberate convergence
      diamonds).
- [ ] **Max edge span**: prerequisite edges should not exceed Δx=4 or Δy=3.
- [ ] **Max relpos chain**: no more than 3-4 generations of `relative_position_id`
      before anchoring to absolute x/y.
- [ ] **Political zone**: hand-authored political/story focuses must start at
      **x >= 28** (to the right of `develop_the_country` and `arming_the_nation`).
- [ ] **Continuous focus position**: set to a pixel position that does not overlap the
      focus tree visually. Must not be empty.

### Thematic column guidelines

| x range | Zone |
|---|---|
| x < 9 | Reserved for `arming_the_nation` shared backbone |
| x = 9-27 | Reserved for `develop_the_country` shared backbone |
| x = 28-34 | Internal politics / diplomacy |
| x = 35-44 | **Main war story spine** (central narrative axis) |
| x = 45-55 | Special mechanics / side content / economic branches |

### Pipeline tools

```bash
# Audit a tree for layout issues
python tools/focus_layout/audit.py --tree <tree_id>

# Generate SVG preview
python tools/focus_layout/preview.py --tree <tree_id>

# Full pipeline: graph -> audit -> preview
python tools/focus_layout/graph.py --all
python tools/focus_layout/audit.py --tree <tree_id>
python tools/focus_layout/preview.py --tree <tree_id>
```

See `tools/focus_layout/README.md` for full documentation.

### Pre-commit layout check

- [ ] `python tools/focus_layout/audit.py --tree <tree_id> --errors-only --quiet`
      → no ERRORs (0 overlaps, 0 broken refs).
- [ ] Anchor mismatches fixed or intentionally justified.
- [ ] No prerequisite lines crossing unrelated branches (check preview SVG).

## Before commit

- [ ] `python tools/validate.py --quiet` -> `ERRORS: 0` (catches dup ids + dangling focus refs).
- [ ] `python tools/focus_layout/audit.py --tree <tree_id> --errors-only` -> 0 errors.
- [ ] No vanilla ideology tokens; no full-file vanilla overrides (see `AGENTS.md`).
- [ ] New file + unique namespace if you also added events (parallel-agent etiquette).
