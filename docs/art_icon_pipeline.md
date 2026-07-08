# Art icon pipeline

How to generate focus icons and similar UI art in HOA VinerX Edition with a coding agent.
This is a **workflow contract**, not a one-off prompt. Use it before asking an agent to
generate a batch of icons.

Read `AGENTS.md` first for the general repo rules. For focus icons, also read
`docs/FOCUS_CHECKLIST.md`.

## Goal

Generate icons that are:

- readable at small size (`140x140` for focus icons)
- visually consistent with Warcraft / WoW-adjacent fantasy UI art
- grounded in the right faction / house / character symbolism
- easy to cut out into alpha and convert to `.dds`

This pipeline is intentionally split into analysis, reference selection, generation, and
post-processing. Do not jump straight to image generation without doing the classification
step first.

## What the agent must decide first

For each icon, the agent must write a short spec with these fields:

```txt
id:
subject_type:
visual_family:
canon_strictness:
must_have:
avoid:
cutout_strategy:
```

Field meanings:

- `id`: target asset / focus id / icon name.
- `subject_type`: `symbol`, `character`, `scene`, `object`, `location`, or `hybrid`.
- `visual_family`: `heraldry`, `portrait`, `battle_action`, `architecture`, `artifact`,
  `ritual_magic`, or another short descriptive family.
- `canon_strictness`: `strict`, `guided`, or `inspired`.
- `must_have`: 2-5 required visual elements.
- `avoid`: composition traps or canon mistakes to avoid.
- `cutout_strategy`: `alpha_direct`, `chroma_green`, `chroma_magenta`, or
  `dark_isolation`.

If the agent cannot fill this spec confidently, it should stop and gather references
before generating.

## Canon levels

Use one of these three canon levels for every icon.

### `strict`

Use when the icon depends on a known emblem, named character, or established prop.

Examples:

- faction / kingdom symbols
- house symbols
- named leaders (`Daelin`, `Jaina`, etc.)
- recognisable buildings or orders

Rules:

- do not rely on model memory alone if local references are missing
- collect at least 1-3 visual references first
- preserve colours, silhouette, heraldic motifs, props, and costume cues

### `guided`

Use when the icon should feel canonical but composition can be original.

Examples:

- councils
- shipyards
- military schools
- trade agreements
- docks / infrastructure

Rules:

- use known materials, colours, and motifs from the faction
- stylise the composition freely as long as the icon still reads as belonging to that group

### `inspired`

Use when only the broader Warcraft-adjacent aesthetic matters.

Examples:

- generic military buildup
- generic bombardment
- generic watchtower or convoy scene

Rules:

- still match the project's art direction
- do not accidentally drift into another faction's identity

## Reference gathering

Do not ask the model to "remember Warcraft correctly" for strict-canon subjects.

Preferred reference structure:

```txt
refs/
  shared/
    style/
  factions/
    <faction>/
      symbols/
      characters/
      ships/
      architecture/
      materials/
```

If the repo does not have a `refs/` tree yet, the agent should still behave as if the
reference step exists:

- use local screenshots / pasted images from the user when available
- use existing in-repo art as a local style reference
- identify which icons are unsafe to finalise without an external canon reference

For strict-canon work, references should answer:

- what colours are canonical?
- what motifs are canonical?
- what props or silhouettes define the subject?
- what details are non-negotiable?

## Choose the right icon family

Different icon families need different composition rules.

### Heraldry

Best for:

- nations
- houses
- councils
- institutions

Rules:

- one large central symbol
- symmetric or near-symmetric composition
- clear silhouette
- minimal scene background

### Portrait

Best for:

- named characters
- faction leaders
- personal arcs

Rules:

- bust or close mid-shot
- one iconic prop is better than many
- avoid crowd scenes
- face and silhouette must still read at small size

### Battle action

Best for:

- naval battles
- landings
- bombardments
- crises

Rules:

- one frozen moment, not a panorama
- one primary action
- strong directional lighting
- avoid clutter and tiny units

### Architecture

Best for:

- docks
- forts
- shrines
- manors
- lighthouses

Rules:

- one landmark
- push silhouette over fine detail
- keep the horizon / background simple

### Artifact / table / document

Best for:

- trade charters
- doctrine
- naval school
- contracts

Rules:

- tabletop still life is acceptable
- 2-4 objects max
- readable shape language matters more than realism

## Choose the cutout strategy

There is no single mandatory background colour for every batch. The agent must choose a
cutout strategy deliberately.

### `alpha_direct`

Use when the image tool reliably returns a clean transparent background.

Pros:

- simplest pipeline

Cons:

- often inconsistent across batches

### `chroma_green`

Use when the subject does **not** contain dominant green tones.

Pros:

- easiest to key automatically

Cons:

- bad choice for green banners, fel subjects, forests, jade, druidic or sea-green assets

### `chroma_magenta`

Use when the subject contains lots of green but little magenta / pink.

Pros:

- good fallback when green conflicts with the faction palette

Cons:

- bad choice for arcane / void / pink spell effects

### `dark_isolation`

Use a flat black or near-black background when chroma would collide with the subject or
when spell / smoke edges are hard to key.

Pros:

- robust for many fantasy subjects

Cons:

- often needs thresholding or manual mask cleanup

### Selection rule

Pick the background based on the subject, not habit:

- lots of green in the subject -> avoid `chroma_green`
- lots of magenta / violet in the subject -> avoid `chroma_magenta`
- magical haze / smoke / translucent effects -> prefer `dark_isolation`
- hard-edged emblems, props, portraits -> chroma is usually fine

## Composition rules for small icons

The agent must optimise for icon readability, not for splash art.

Hard rules:

- one dominant subject
- subject should occupy roughly 65-80% of the frame
- leave safe empty margin so the in-game frame does not clip the subject
- avoid wide panorama scenes
- avoid tiny background figures
- avoid more than 2-3 secondary objects
- bias toward strong silhouette and contrast

If an image looks good only at large size, it failed the icon test.

## Batch generation rules

Do not generate one huge mixed sheet unless the subjects are from the same visual family.

Preferred batch structure:

- `heraldry` sheet
- `portrait` sheet
- `battle_action` sheet
- `architecture` sheet
- `ritual_magic` sheet

Recommended batch size:

- 4-6 icons per sheet when fidelity matters
- 8-12 only for exploratory ideation

When a batch mixes portraits, ships, heraldry, and cityscapes together, composition quality
usually drops.

## Prompt construction

Use a shared project style block plus a family-specific block.

Shared style block should usually include:

- Warcraft-inspired fantasy UI icon
- readable at `140x140`
- one centered subject
- crisp silhouette
- strong contrast / rim light
- no text
- no decorative frame baked into the art
- plain isolated background chosen by `cutout_strategy`

Then append a family-specific block:

- heraldry -> "single emblematic object, symmetric composition"
- portrait -> "bust portrait, iconic prop, no crowd"
- battle -> "single frozen action moment, not a panorama"
- architecture -> "single landmark, strong silhouette"

## Post-generation review

After generation, the agent must evaluate each icon before calling it usable.

Suggested labels:

- `ready`
- `needs_recrop`
- `good_idea_bad_silhouette`
- `non_canon_drift`
- `bad_cutout_background`
- `too_busy_for_140`

Checklist:

- does the subject read at thumbnail size?
- is the silhouette clean?
- are the canon markers present?
- is the background easy to key or mask?
- does it look like an icon rather than a splash illustration?

## Post-processing

Target pipeline:

1. generate source image
2. remove background according to chosen `cutout_strategy`
3. crop to the useful silhouette
4. fit into `140x140` with safe margin
5. light contrast / cleanup if needed
6. export `.png` with alpha
7. convert to `.dds`

If the project later standardises a specific conversion script, document it here instead of
letting each agent improvise.

## Recommended agent workflow

Use this exact order:

1. Read this file and `docs/FOCUS_CHECKLIST.md`.
2. Build a spec table for the requested batch.
3. Mark which icons are `strict`, `guided`, or `inspired`.
4. Gather or request references for `strict` icons.
5. Group icons by visual family.
6. Choose a cutout strategy per group.
7. Generate exploratory sheets.
8. Self-review and rank the outputs.
9. Regenerate only the weak icons with tighter prompts.
10. Prepare final cutout / crop / export assets.

## What to ask the user for

Ask only for information that materially changes the outcome:

- canon references for named characters or symbols
- preferred cutout mode if they have a strong downstream tooling preference
- whether the batch is exploratory or final-use

Do not ask vague questions that the agent can answer from classification and references.

## Minimal output contract for an agent

When handling an icon batch, the agent should produce:

- a spec table
- one or more grouped sheets
- a short review of which results are usable
- any flagged canon-risk items

This keeps the process reproducible and prevents the agent from silently drifting into
"pretty art" that is hard to use in-game.
