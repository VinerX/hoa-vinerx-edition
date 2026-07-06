# HOA VinerX Edition

A personal rebuild of **Hearts of Azeroth** (a Warcraft total-conversion for
**Hearts of Iron IV**), fixed and extended for **HOI4 1.18.3.0**. For me and friends.

This repository is the **live, playable mod** and a full restorable backup (binary
game assets included). Private.

## Status

- ✅ Naval crash (`INT_DIVIDE_BY_ZERO`, ~595.09) — fixed; Naval Domination Rework's intent
  folded into `common/defines/HOA_defines.lua` (no separate mod needed).
- ✅ Second War start crash — no longer reproduces on this single-mod build.
- ✅ AI Wars + Simple Peace Deals — integrated (world keeps fighting; separate peace deals).
- ✅ Blackrock focuses `journey_north` / `hunt_the_shadow_council` gated on the fall of
  Stormwind (control of Stormwind Keep), not the whole Alliance.
- ⏳ Second War events — in progress.

See **`DIAGNOSIS.md`** for the full crash analysis (27 crash logs) and **`AGENTS.md`**
for how to work on the mod.

## Play it

The launcher descriptor lives at
`Documents/Paradox Interactive/Hearts of Iron IV/mod/hoa_vinerx_edition.mod` (points at
this folder, all 57 `replace_path`s). In the HOI4 launcher enable **"HOA VinerX Edition
(rebuild)"** and disable the workshop HOA + the AI Wars / Simple Peace Deals / Naval
Domination Rework mods (their intents are already merged in). A full game restart re-reads
files from disk after edits.

## Develop it

```bash
python tools/validate.py            # pre-launch script linter (must show ERRORS: 0)
```

- Target engine: **1.18.3.0**. Single merged mod (no load order).
- Custom ideologies: `alliance / horde / death / fel / old_gods / titans / neutral`.
- Branch: `rebuild`. Backup remote: `github.com/VinerX/hoa-vinerx-edition` (private).
- Read `AGENTS.md` before editing — it has the conventions, domain facts, and pitfalls.

## Credits

Derivative work built on *Hearts of Azeroth* by its original authors, in the Warcraft
setting (Blizzard). Kept private for personal use.
