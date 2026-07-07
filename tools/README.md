# tools/

Helper scripts for the HOA VinerX rebuild. The game never reads this folder.

## crashdump.py - read the minidump when error.log is silent

HOI4's hardest crashes (CTD during load, nothing in `error.log`) still leave a
`minidump.dmp` in the crash folder under
`Documents/Paradox Interactive/Hearts of Iron IV/crashes/hoi4_YYYYMMDD_HHMMSS/`.
No Windows debugger is required — the script parses the dump with pure Python:

```bash
pip install minidump
python tools/crashdump.py "C:/Users/<user>/Documents/Paradox Interactive/Hearts of Iron IV/crashes/hoi4_20260707_214804"
```

How to read the output (this is the whole technique):

1. **Exception params `[op, addr]`** — op `0x0`=read / `0x1`=write, addr = the
   faulting address. If addr is **tiny** (`0x0`–`0x1000`), it is a **null-pointer
   deref reading a member at offset +addr**: some lookup by name returned null.
   That means a broken *data reference* (equipment / tech / variant / idea /
   character), not corruption. If addr is near the stack limit instead, think
   stack overflow → recursion in scripted effects / focus positions.
2. **Crash thread stack strings** — parsers keep the tokens they are currently
   processing on the stack, so the strings name the dying subsystem and often
   the exact token. Example that solved the 596 Second War crash:
   `carrier_equipment_2`, `air_wings`, `task_force`, `fleet`, `units/` →
   the naval OOB loader died on a carrier air wing → grep those tokens in
   `history/units/` → `KUL_596_naval.txt` wing of `organic_fighter_equipment_1`
   which KUL had no tech for (an air wing of un-researched equipment in any
   OOB is a guaranteed silent CTD).
3. **A stable crash address across runs** = same deterministic code path: keep
   hunting one data bug, don't suspect RAM/drivers.
4. **Ignore `exception.txt`'s call stack** (`PHYSFS_swapULE64` etc.). Paradox
   ships no PDB, so those frames are nearest-export guesses and actively
   mislead (they made this crash look like PHYSFS recursion for hours).

Workflow: crashdump.py → classify (null deref vs overflow) → grep the stack
tokens in the mod → fix → add the failure class to validate.py so it can never
come back silently.

## validate.py - pre-launch script linter

## validate.py - pre-launch script linter

Catches common crash and parse mistakes without launching HOI4, which is still the
slow part of the loop here.

```bash
python tools/validate.py            # validate this mod
python tools/validate.py --quiet    # summary + ERRORS only (hide WARNINGs)
python tools/validate.py --path DIR # validate another folder
python tools/validate.py --hoi4-error-log # also fold current HOI4 error.log into the report
python tools/validate.py --hoi4-smoke # launch hoi4.exe, wait for startup parse, inspect new log lines
python tools/validate.py --hoi4-smoke --hoi4-timeout 60
python tools/validate.py --hoi4-smoke --hoi4-args "-debug -nolauncher"
```

Exit code is non-zero if there are ERRORS, so it works as a pre-commit gate.

**ERROR** (almost always a real problem):
- `encoding` - a file is not valid UTF-8.
- `braces` - `{` and `}` do not balance in a script file.
- `focus-dup` - the same focus id is defined twice.
- `focus-tree-dup` - the same focus tree id is defined twice.
- `focus-ref` - a prerequisite / mutually exclusive / relative position / shared focus
  / load focus tree points at an id that no file defines.
- `ideology` - a script uses a vanilla ideology token instead of HOA ideologies.
- `scripted-effect` - invalid scripted effect structure, such as a top-level
  `limit = {}` block or a trigger used where an effect should be.
- `scripted-trigger` - unknown trigger usage in scripted triggers or `limit` blocks
  that HOI4 would otherwise only report in runtime `error.log`.
- `runtime-antipattern` - known bad runtime constructs in normal script files
  (`events/`, `common/decisions/`, `common/national_focus/`) that this project has
  already tripped over, such as `has_technology`, `load_naval_oob`,
  `transfer_equipment`, unsupported `remove_country_leader`, or malformed
  `set_variable = { foo value = ... }`.
- `decision-category` - a file in `common/decisions/` introduces a top-level category
  that is not declared in `common/decisions/categories/` or vanilla category files.
- `idea-modifier` - an idea uses a modifier key that does not exist in the vanilla/mod
  idea modifier vocabulary.
- `opinion-modifier` - `add_opinion_modifier` / `reverse_add_opinion_modifier` points
  at an undefined opinion modifier id.

**WARN** (eyeball; may be a false positive for cross-mod or vanilla references):
- `event-ref` - a `country_event` / `news_event` / etc. points at an event id no file defines.
- `namespace` - the same `add_namespace` appears in multiple event files.
- `focus-loc` / `event-loc` / `tooltip-loc` - a referenced localisation key is missing.
- `loc-dup` - a localisation key is duplicated within one file or across multiple files.

The scripted syntax checks use a conservative vocabulary built from vanilla
`common/scripted_effects` and `common/scripted_triggers`, plus custom scripted
effect and trigger names defined in the mod. That is enough to catch recent startup
regressions like:
- `limit = {}` placed directly at the top level of a scripted effect.
- typos such as `num_of_owned_states` in trigger contexts where HOI4 only accepts
  `num_of_controlled_states`.

There is also a narrower runtime anti-pattern pass for regular script files.
It is intentionally rule-based rather than a fake full parser: the goal is to
catch a short list of high-value mistakes that repeatedly caused startup/parser
crashes in HOA without drowning the output in false positives.

Scope note: this is still a lightweight static check, not a full parser. A clean run
does not guarantee the game loads, but it removes the cheap and common failure
classes before you spend time launching.

If you already launched the game once, `--hoi4-error-log` is a useful follow-up:
it promotes runtime parser failures such as `Unknown trigger-type`,
`Unknown effect-type`, and invalid startup capitals into the same validator output.

If you want the script to do that launch for you, use `--hoi4-smoke`:
- it starts `hoi4.exe` directly instead of going through the Paradox Launcher.
- it passes `-debug` by default so parser/runtime messages land in the usual logs.
- it waits `45` seconds by default, terminates the process, then parses only the
  newly added `error.log` lines so stale earlier crashes do not pollute the result.
- `--hoi4-exe` overrides the game binary path.
- `--hoi4-args` overrides launch flags if you want to add or replace defaults.
- `--hoi4-timeout` controls how long the smoke run is allowed to live before the
  validator kills it.
