# AGENTS.md — working guide for coding agents

You are editing **HOA VinerX Edition**, a personal rebuild of the *Hearts of Azeroth*
(Warcraft total conversion) mod for **Hearts of Iron IV, targeting exactly 1.18.3.0**.
This working directory **is** the live playable mod (the launcher loads it directly),
so edits here take effect on the next game launch. Read this whole file before writing.

## Golden rules (read first)

1. **Validate before every commit:** `python tools/validate.py --quiet`. It must print
   `ERRORS: 0`. Fix any brace/encoding/duplicate-id/dangling-focus errors first. See
   `tools/README.md`. A clean run doesn't guarantee the game loads, but it removes the
   cheap, common crash classes (the game can't be launched from here to test).
2. **Additive only — never drag whole vanilla files.** The mod already broke once because
   a submod shipped a full 1.17 `common/defines/00_defines.lua`. Add small files / append
   to existing ones; don't replace an entire vanilla subsystem.
3. **HOA has its own ideologies** — `alliance, horde, death, fel, old_gods, titans,
   neutral` (leader ideologies add `_type`, e.g. `alliance_type`). There is **no**
   `democratic/fascism/communism/neutrality/nazism`. Never use vanilla ideology tokens.
4. **Don't mass-rename terrain ids** (`city`, `gateway`, `outpost`… are validly declared
   by the mod). See `DIAGNOSIS.md` for why the old "rename city→urban" advice is wrong.
5. **Match the surrounding code style** (tabs, brace placement, `immediate = { log = ... }`
   idiom). Don't reformat files you touch.
6. Keep changes scoped and commit with a clear message (see Git below).

## Project facts

- Engine target: **1.18.3.0** (`Case Green`). Vanilla for reference lives at
  `C:/SteamLibrary/steamapps/common/Hearts of Iron IV`.
- It is a **single merged mod** (no load order). Integrated intents: Naval Domination
  Rework (naval defines in `HOA_defines.lua`), AI Wars (`common/on_actions/ai_wars_on_actions.txt`),
  Simple Peace Deals (diplomatic action + support files). Do not re-add those as separate mods.
- Calendar / bookmarks (`common/bookmarks/`):
  | bookmark | start date |
  |---|---|
  | Rise of the Horde (grand campaign) | 581.1.1.12 |
  | The First War | 592.1.1.12 |
  | **The Second War** | **596.1.1.12** |
  | The Third War | 610.1.1.12 |
- A game started at a later bookmark applies that date's `history/` blocks at startup;
  earlier events/on_actions do NOT fire. So Second-War content must not assume the First
  War was played in-session (e.g. Stormwind is already refugees at 596 — see below).

## Domain reference (Second War essentials)

Key country tags (`common/country_tags/01_HoA_countries.txt`):
`BRC` Blackrock Clan · `STO` Stormwind · `LOR` Lordaeron · `TSC` The Shadow Council ·
`SRC` Stormreaver Clan · `BHC` Bleeding Hollow Clan · `DMC` Dragonmaw Clan ·
`IRO` Ironforge · `QUE` Quel'Thalas · `GIL` Gilneas · `DAL` Dalaran · `STR` Stromgarde.

Stormwind mechanics (worth knowing before scripting the Second War):
- On defeat Stormwind does **not** get annexed/stay capitulated — it white-peaces and
  reforms in the north as **refugees**, keeping tag `STO` (cosmetic `STO_REF`, idea
  `STO_government_in_exile`, puppet of `LOR`). So `has_capitulated`/annexation checks are
  unreliable. To test "Stormwind fell", prefer control of **Stormwind Keep = state 22**
  (`NOT = { 22 = { is_controlled_by = STO } }`) or the `fall_of_stormwind` flag (set on
  BRC) / `STO_REF` country flag (set via the First-War capitulation event, not at 596 start).
- At the 596 bookmark, state 22 is already held by `SRC` (Horde); STO is already refugees.

Existing Second War content to extend / not collide with:
- `events/hoa_second_war_events.txt` — namespace **`second_war`** (ids 1–50 used).
- `events/stormwind_war_1_capitulation.txt` — namespace **`stormwind_capitulation`**.
- `events/stormwind_events.txt`, `common/national_focus/*first_and_second_war.txt`,
  `common/national_focus/stormwind_second_war.txt`, `common/bookmarks/the_second_war.txt`.

## Where things live

```
common/            events/            history/            localisation/english/
  national_focus/     *.txt (events)     countries/          *_l_english.yml
  decisions/                              states/
  scripted_effects/  common/on_actions/  units/ (OOBs)      map/
  scripted_triggers/ common/ideas/       general/
  ideologies/        common/bookmarks/
```

`descriptor.mod` `replace_path`s many `common/` subfolders (units, technologies,
on_actions, scripted_effects/triggers, national_focus, events, history/*, …). Inside a
replace_path'd dir the mod's files fully replace vanilla's, so **add new files there**
(don't expect vanilla content in that dir). Dirs NOT replace_path'd (e.g.
`common/scripted_diplomatic_actions`, `common/game_rules`) merge with vanilla — additive.

## Writing events (the common task)

Template (country event), matching house style:

```txt
add_namespace = my_second_war_batch      # once per file; pick a UNIQUE namespace

country_event = {
    id = my_second_war_batch.1
    title = my_second_war_batch.1.t
    desc  = my_second_war_batch.1.d
    picture = GFX_report_event_german_parade_paris

    is_triggered_only = yes              # fired by focus/decision/on_action/other event
    fire_only_once = yes                 # if it should happen once
    # hidden = yes                       # for silent effect-only events

    immediate = { log = "[GetDateText]: [Root.GetName]: event my_second_war_batch.1" }

    option = {
        name = my_second_war_batch.1.option.1
        # effects...
    }
}
```

Conventions:
- **Namespace + ids:** `add_namespace = X` at top; ids are `X.<n>`. Namespaces are global —
  pick a unique one per batch/agent to avoid collisions (see Parallel work).
- **Firing:** events don't fire themselves. Trigger via `country_event = X.n` from a focus
  `completion_reward`, a decision, an `on_actions` block, or another event. Dated `X.n` with
  `mean_time_to_happen`/`trigger` also works but is less used here.
- **Localisation:** every `title/desc/option name` needs a key in
  `localisation/english/*_l_english.yml`. Existing Second War strings are in
  `hoa_events_l_english.yml`. YAML format (note leading space + `:0`):
  ```yml
  l_english:
   my_second_war_batch.1.t:0 "Title text"
   my_second_war_batch.1.d:0 "Body. Use \n for newlines and [BRC.GetLeader] scopes."
   my_second_war_batch.1.option.1:0 "For the Horde!"
  ```
  You may add a new `*_l_english.yml` file for your batch. The user plays in Russian but
  Russian falls back to English, so English is enough to be functional.
- Prefer existing `GFX_*` event pictures unless art is provided (you can't add sprites).

## Validate, then commit (git)

- Branch is **`rebuild`**. Stay on it unless told otherwise.
- Workflow: edit → `python tools/validate.py --quiet` (ERRORS: 0) → `git add -A` →
  `git commit` → `git push origin rebuild` (HTTPS via the `gh` credential helper).
- Commit message: short imperative subject + why, and end with:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- The remote is a **private** backup: `github.com/VinerX/hoa-vinerx-edition`.

## Parallel-agent etiquette

Multiple agents may build Second War content at once. To avoid stepping on each other:
- **One new file per batch** under `events/` and a **unique `add_namespace`** — don't append
  to `hoa_second_war_events.txt` (shared file = merge conflicts). Same for a per-batch
  `localisation/english/<yourbatch>_l_english.yml`.
- Wiring that touches a shared file (e.g. adding `country_event` calls to an existing focus
  or `common/on_actions/00_hoa_on_actions.txt`) is the collision-prone part — keep those
  edits minimal and note them in your commit.
- Never edit `common/defines/*`, `common/terrain/*`, `descriptor.mod`, or `tools/` unless
  that is your explicit task.

## Before you finish

- `python tools/validate.py` shows `ERRORS: 0` (24 pre-existing event WARNINGs are OK).
- No vanilla ideology tokens, no full-file vanilla overrides.
- Localisation keys exist for every new string.
- Read `DIAGNOSIS.md` if anything crash-related is in scope.
```
