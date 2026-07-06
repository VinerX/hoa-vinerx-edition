# Hearts of Azeroth — Rebuild Diagnosis (target HOI4 1.18.3.0)

Analysis of 27 crash folders in `C:\Games\Hoi4\source\crashes` (game build
`Case Green v1.18.3.0.7709`, some `Operation Postern v1.19.2`). The user plays the
**Second War bookmark** (`common/bookmarks/the_second_war.txt`, start `596.1.1.12`).

## Two distinct crash families

### Crash A — `EXCEPTION_INT_DIVIDE_BY_ZERO` (address 0x…113F116D), ~date 595.09  [FIXED]
Always preceded by a storm of `AI tried to post an invalid command: set_as_reserve_fleet_command`
(gameidler.cpp:1604). **100% correlated with the separate mod "Naval Domination Rework" (3734272971).**
HOA-only runs have ZERO `set_as_reserve_fleet_command` lines.

Root cause: Naval Domination Rework ships a **full 1.17-era `common/defines/00_defines.lua`**
that overrides 1.18.3's defines and is MISSING newer naval defines (e.g.
`NAVY_REPAIR_BASE_SEARCH_NON_OPERATIONAL_STR`, `CAPITAL_SHIP_COMBAT_RETREAT_MULT`).
The 1.18.3 naval AI reads those as 0 → divide by zero.

Fix applied: do NOT import that mod's files. Its meaningful naval intent (6 defines,
diffed vs vanilla 1.18.3) is added **additively** to `common/defines/HOA_defines.lua`:
- `DOMINANCE_CONTROLLED_THRESHOLD_RATIO` 0.60→0.51 (key: fewer ships to control a sea zone)
- `SHIP_SUPPORT_NEED_FACTOR` 0.10→0.12, `NAVAL_DOMINANCE_SPOTTING_BONUS` 0.05→0.08,
  `COMBAT_MIN_HIT_CHANCE` 0.005→0.02, `NAVAL_INVASION_PREPARE_DAYS` 60→35,
  `BASE_NAVAL_INVASION_DIVISION_CAP` 4→5.

### Crash B — `EXCEPTION_ACCESS_VIOLATION`, at/just after Second War start  [NOT REPRODUCED on rebuild build]
UPDATE: after switching to the clean single-mod rebuild build (workshop HOA + the three
outdated submods disabled, naval intent folded in), the user confirmed surviving the
**Second War start** — no new crash dump produced. Not root-caused, but no longer
reproducing; likely the incompatible submod stack (esp. the naval defines override) was
the real trigger. Watch for it recurring later in the campaign.

Original observation (pre-fix):
Fresh game on the Second War bookmark (596.1.1.12). Runs ~16 real-time minutes into
596.1.1–596.1.2, then AV. Reproduces across 4 HOA-only runs. The text logs do NOT
name a file/line for the AV (it is a runtime memory fault). HOI4 ships no PDB symbols,
so the minidump/exception stack is only `hoi4.exe+offset` — not localizable statically.
**Needs a `-debug` run to surface the assert/context.** This is the crash that blocks
actually playing the Second War.

## Non-fatal issues found (degrade balance/AI, do NOT crash — game runs past them)
- `common/terrain/00_terrain.txt`: every `type =` ref in the graphical `terrain = {}`
  block (lines 828-916) logs "Malformed token" on 1.18.3, cascading to thousands of
  "Unexpected token: city/forest/marsh/…" in `common/units/*` and `common/technologies/*`.
  The file is internally consistent (44 categories, all graphical `type=` values defined,
  braces balanced, ASCII, no BOM) yet the terrain-type table isn't honored at apply time.
  Cause not yet root-caused; unproven whether it contributes to Crash B (theory: broken
  terrain combat modifiers at war start). Do NOT mass-rename terrain ids (prior agent's
  advice) — `city`/`gateway`/`outpost` are validly declared by the mod.
- `common/weather.txt`: same "Malformed token" cascade from line 8 (same mechanism as terrain).
- `common/doctrines/grand_doctrines/special_forces_grand_doctrines.txt`: 928× `has_tech: Invalid tech`.
- `game rules/ww1 random.txt`: `invalid rule id: AUH/ENG/GER/…_ai_behavior` (vanilla/Great-War
  tags leaking in; not HOA tags).
- `common/ai_navy/goals/goals_JAP.txt`: `Invalid country tag: available_for`.
- Runtime `Invalid subunit: none` at 596.01.01 (unit creation at Second War setup) — suspect for Crash B.
- Many missing textures / GUI faceplates (cosmetic).

## Integration decisions (per user)
- Merge into a single HOA mod (no load order). Target 1.18.3.
- Integrate INTENT of: AI Wars (2956996260), Simple Peace Deals (3711217109),
  Naval Domination Rework (3734272971 — done, see Crash A). Do NOT use VinerX's Azeroth (outdated).
