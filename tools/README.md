# tools/

Helper scripts for the HOA VinerX rebuild. The game never reads this folder.

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
