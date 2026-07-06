# tools/

Helper scripts for the HOA VinerX rebuild. The game never reads this folder.

## validate.py — pre-launch script linter

Catches the most common crash/parse mistakes without launching HOI4 (the slow part
of the loop, since the game can't be run headless here).

```bash
python tools/validate.py            # validate this mod
python tools/validate.py --quiet    # summary + ERRORS only (hide WARNINGs)
python tools/validate.py --path DIR # validate another folder
```

Exit code is non-zero if there are ERRORS, so it works as a pre-commit gate.

**ERROR** (almost always a real problem):
- `encoding` — a file isn't valid UTF-8.
- `braces` — `{`/`}` don't balance in a script file (a hard parse error in-game).
- `focus-dup` — the same focus id is defined twice.
- `focus-ref` — a prerequisite / mutually_exclusive / relative_position_id / shared_focus
  points at a focus id that no file defines.

**WARN** (eyeball; may be a false positive for cross-mod/vanilla references):
- `event-ref` — a `country_event`/`news_event`/… points at an event id no file defines.
  Not a crash (HOI4 just logs "event not found"), but usually a dead button/effect.

Scope note: this is a lightweight static check, not a full parser. A clean run does
NOT guarantee the game loads — it just removes the cheap, common failure classes
before you spend time launching.
