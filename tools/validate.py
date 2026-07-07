#!/usr/bin/env python3
"""
HOA rebuild lightweight pre-launch validator.

Catches common crash/parse mistakes in HOI4 mod script without running the game.
It is intentionally conservative: things reported as ERROR are almost always real;
WARNINGs may have false positives (cross-mod / vanilla references) and are for
eyeballing.

Checks:
  1. Encoding        - every .txt/.gui/.gfx/.lua reads as UTF-8 (BOM allowed).
  2. Brace balance   - { and } balance per file (comments and quoted strings stripped).
  3. Focus ids       - duplicate focus ids (ERROR) and dangling references from
                       prerequisite / mutually_exclusive / relative_position_id /
                       shared_focus / load_focus_tree (ERROR).
  4. Event ids       - duplicate event ids (ERROR), repeated namespaces across files
                       (WARN), and *_event = <ns.n> refs to undefined events (WARN).
  5. Localisation    - missing focus/event/tooltip loc keys (WARN), duplicate loc keys
                       (ERROR).
  6. HOA ideologies  - vanilla ideology tokens in script contexts (ERROR).
  7. Scripted syntax - invalid scripted effect / trigger constructs that HOI4 usually
                       reports only at load time.
  8. Runtime anti-patterns - targeted checks for known bad trigger/effect names and
                       malformed constructs that otherwise only surface in HOI4 logs.
  9. Data vocab      - unknown decision categories, opinion modifiers, and idea
                       modifier keys that HOI4 otherwise rejects at load time.
 10. Double-equals   - syntax mistakes like `has_country_flag = X = no` (ERROR).
 11. Decision props  - invalid decision-level keys like `cost_command_power`,
                       `on_remove`, `color` at top level (ERROR).
 12. On-actions wrap - root-level `on_monthly`/`on_weekly` missing `on_actions={}`
                       wrapper (ERROR).
 13. YAML key colon  - embedded colons in localisation key names (ERROR).
 14. Naked variables - bare `var:` / `@var:` tokens outside `check_variable` (ERROR).
 15. Effect/trigger  - unknown effect/trigger names in events, decisions, and focus
                       trees checked against vanilla+mod vocabulary (ERROR).

Usage:
  python tools/validate.py
  python tools/validate.py --path <dir>
  python tools/validate.py --quiet
  python tools/validate.py --hoi4-error-log

Exit code: 0 if no ERRORS, 1 otherwise.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import time

# Dirs whose .txt files use HOI4 script syntax (brace-balanced). Others skipped.
SCRIPT_DIRS = ("common", "events", "history", "map", "gfx", "interface", "tutorial")
SCRIPT_EXT = (".txt",)
TEXT_EXT = (".txt", ".gui", ".gfx", ".lua", ".yml", ".asset")

SCRIPTED_EFFECTS_DIR = "common/scripted_effects"
SCRIPTED_TRIGGERS_DIR = "common/scripted_triggers"
BUILDINGS_DIR = "common/buildings"
IDEAS_DIR = "common/ideas"
DECISION_CATEGORIES_DIR = "common/decisions/categories"
OPINION_MODIFIERS_DIR = "common/opinion_modifiers"
DEFAULT_REFERENCE_ROOTS = (
    r"C:\SteamLibrary\steamapps\common\Hearts of Iron IV",
)
DEFAULT_HOI4_ERROR_LOG = os.path.expanduser(r"~/Documents/Paradox Interactive/Hearts of Iron IV/logs/error.log")
DEFAULT_HOI4_EXE = r"C:\SteamLibrary\steamapps\common\Hearts of Iron IV\hoi4.exe"
DEFAULT_HOI4_SMOKE_ARGS = "-debug"

# Regexes (script is loosely formatted; keep patterns forgiving).
RE_ID = re.compile(r"\bid\s*=\s*([A-Za-z0-9_.']+)")
RE_FOCUS_REF = re.compile(r"\bfocus\s*=\s*([A-Za-z0-9_.']+)")
RE_RELPOS = re.compile(r"\brelative_position_id\s*=\s*([A-Za-z0-9_.']+)")
RE_SHARED = re.compile(r"\bshared_focus\s*=\s*([A-Za-z0-9_.']+)")
RE_FOCUS_TREE_REF = re.compile(r"\bload_focus_tree\s*=\s*([A-Za-z0-9_.']+)")
RE_ADD_NS = re.compile(r"\badd_namespace\s*=\s*([A-Za-z0-9_]+)")
RE_EVENT_ID = re.compile(r"\bid\s*=\s*([A-Za-z0-9_]+\.\d+)")
RE_EVENT_REF = re.compile(
    r"\b(?:country_event|news_event|state_event|unit_leader_event|operative_leader_event)\s*=\s*(?:\{[^}]*\bid\s*=\s*)?([A-Za-z0-9_]+\.\d+)"
)
RE_TOOLTIP_REF = re.compile(r"\bcustom_(?:effect|trigger)_tooltip\s*=\s*([A-Za-z0-9_.']+)")
RE_LOC_KEY = re.compile(r"^\s*([^\s:#][^:]*?)\s*:\d+\s", re.MULTILINE)
RE_IDEOLOGY = re.compile(r"\b(?:ruling_party|ideology)\s*=\s*([A-Za-z_]+)")
RE_FOCUS_ICON = re.compile(r"\bicon\s*=\s*([A-Za-z0-9_]+)")
RE_FOCUS_COORD = re.compile(r"\b(x|y)\s*=\s*(-?\d+)")
RE_FOCUS_PREREQ = re.compile(r"\bprerequisite\s*=\s*\{([^}]*)\}")
RE_BAD_HAS_TECHNOLOGY = re.compile(r"\bhas_technology\s*=")
RE_BAD_LOAD_NAVAL_OOB = re.compile(r"\bload_naval_oob\s*=")
RE_BAD_TRANSFER_EQUIPMENT = re.compile(r"\btransfer_equipment\s*=")
RE_BAD_REMOVE_COUNTRY_LEADER = re.compile(r"\bremove_country_leader\s*=")
RE_BAD_SET_VARIABLE_VALUE = re.compile(r"\bset_variable\s*=\s*\{\s*([A-Za-z0-9_@.:\'-]+)\s+value\s*=")
RE_BAD_IDEA_REMOVAL = re.compile(r"^\s*removal\s*=", re.MULTILINE)
RE_UNIT_RATIO_BLOCK = re.compile(r"\bai_strategy\s*=\s*\{([^{}]*\btype\s*=\s*unit_ratio[^{}]*)\}", re.DOTALL)
RE_AI_STRATEGY_ID = re.compile(r"\bid\s*=\s*([A-Za-z0-9_@.:\'-]+)")
RE_OPINION_MODIFIER_REF = re.compile(
    r"\b(?:add_opinion_modifier|reverse_add_opinion_modifier)\s*=\s*\{[^{}]*?\bmodifier\s*=\s*([A-Za-z0-9_.']+)",
    re.DOTALL,
)
RE_IDEA_REF = re.compile(
    r"\b(?:add_ideas|remove_idea|has_idea|idea)\s*=\s*([A-Za-z0-9_.']+)"
)

# --- New check regexes (checks 10-15) -----------------------------------------

RE_DOUBLE_EQUALS = re.compile(
    r"^\s*([A-Za-z0-9_]+)\s*=\s*([A-Za-z0-9_]+)\s*=\s*(yes|no|true|false|always|never|high|medium|low)\b",
    re.MULTILINE,
)
RE_DECISION_COST_MISTAKE = re.compile(r"\bcost_(command_power|manpower|political_power|stability)\s*=")
RE_ON_ACTION_TOP = re.compile(
    r"^\s*(on_(?:startup|daily|weekly|bi_yearly|monthly|yearly|two_year|five_year|"
    r"actions|peaceconference_ended|civil_war_end|faction_left|faction_joined"
    r"|nuke_dropped|state_changed_owner|unit_captured|unit_destroyed"
    r"|technology_stolen|operative_discovered|naval_combat|air_combat"
    r"|land_combat|supply_node_captured|state_repairing_sabotaged_infrastructure"
    r"|government_change|election|random_event_window|release|release_puppet"
    r"|puppet_level|puppet|lost_puppet|removed_puppet|autonomy_state_change"
    r"|autonomy_level_change|autonomy_set_state|on_army_war|on_civil_war_end"
    r"|on_paradrop|on_capitulation|on_capitulation_start|on_declared_war"
    r"|on_guarantee|on_nation_formed|on_nuke_launched|on_send_volunteers"
    r"|on_volunteer_deployment_start|on_volunteer_deployment_end"
    r"|on_new_term_election|on_annex|on_diplomatic_action|on_focus_completed"
    r"|on_decision|on_building_complete|on_combatant_declared_war"
    r"|on_military_industrial_organization_level_up))\s*=\s*\{",
    re.MULTILINE,
)
RE_YAML_KEY_COLON = re.compile(r"^\s*([^\s:#][^#]*?[A-Za-z_]:[A-Za-z_][^:\n]*):\d+\s", re.MULTILINE)
RE_NAKED_VAR = re.compile(r"\b(?:var:|@var:)([A-Za-z0-9_]+)")
RE_CHECK_VARIABLE = re.compile(r"\bcheck_variable\s*=\s*\{")


EFFECT_BLOCK_NAMES = {
    "effect",
    "hidden_effect",
    "complete_effect",
    "remove_effect",
    "immediate",
    "ai_will_do",
    "on_complete",
    "on_start",
    "on_remove",
    "on_add",
    "after",
    "cancel",
    "on_cancel",
}

INVALID_DECISION_KEYS = {
    "on_remove",
    "color",
    "allowed_civil_war",
}

ON_ACTIONS_DIR = "common/on_actions"

ALLOWED_EFFECT_META_KEYS = {
    "if",
    "else_if",
    "else",
    "add_namespace",
    "country_event",
    "news_event",
    "state_event",
    "unit_leader_event",
    "operative_leader_event",
    "hidden_trigger",
    "custom_effect_tooltip",
    "custom_trigger_tooltip",
    "set_temp_variable",
    "set_variable",
    "add_to_temp_variable",
    "add_to_variable",
    "subtract_from_temp_variable",
    "subtract_from_variable",
    "multiply_variable",
    "divide_variable",
    "multiply_temp_variable",
    "divide_temp_variable",
    "check_variable",
    "random_list",
    "random",
    "random_owned_controlled_state",
    "random_owned_state",
    "random_state",
    "random_country",
    "every_country",
    "every_enemy_country",
    "every_allied_country",
    "every_neighbor_country",
    "every_state",
    "every_owned_state",
    "every_controlled_state",
    "every_core_state",
    "every_neighbor_state",
    "every_unit_leader",
    "every_operative",
    "every_army",
    "every_navy",
    "every_sub_army",
    "every_combatant",
    "random_other_country",
    "random_enemy_country",
    "random_allied_country",
    "any_country",
    "any_state",
    "any_enemy_country",
    "any_allied_country",
    "any_neighbor_country",
    "all_country",
    "all_state",
    "all_enemy_country",
    "all_allied_country",
    "all_neighbor_country",
    "log",
    "save_event_target_as",
    "save_global_event_target_as",
    "clear_saved_event_target",
    "clear_global_event_target",
    "event_target:",
    "clr_country_flag",
    "set_country_flag",
    "exclusive",
    "option",
    "name",
    "ai_chance",
    "add_equipment_to_stockpile",
    "transfer_state",
    "set_state_controller",
    "create_unit",
    "add_manpower",
    "add_political_power",
    "add_stability",
    "add_war_support",
    "add_command_power",
    "army_experience",
    "air_experience",
    "navy_experience",
    "hidden_effect",
} | {'create_country_leader', 'add_country_leader_role', 'set_national_unity',
   'swap_ideas', 'add_timed_idea', 'remove_ideas', 'add_ideas',
   'add_opinion_modifier', 'remove_opinion_modifier', 'reverse_add_opinion_modifier',
   'add_relation_modifier', 'remove_relation_modifier',
   'declare_war_on', 'white_peace', 'add_to_faction', 'remove_from_faction',
   'create_faction', 'leave_faction', 'join_faction',
   'puppet', 'release', 'release_puppet', 'add_autonomy_ratio',
   'set_technology', 'add_tech_bonus', 'add_research_slot',
   'set_politics', 'set_political_party', 'set_rule',
   'start_civil_war', 'add_civil_war', 'remove_unit_leader',
   'create_equipment_variant', 'add_equipment_production',
   'set_country_flag', 'set_global_flag', 'clr_global_flag',
   'set_state_flag', 'clr_state_flag',
   'load_oob', 'create_operative_leader', 'recruit_character',
   'set_focus', 'complete_national_focus', 'unlock_national_focus',
   'add_to_template', 'set_template_name', 'set_division_template_lock',
   'add_extra_state_shared_building_slots', 'set_state_name', 'set_state_category',
   'set_cosmetic_tag', 'drop_cosmetic_tag',
   'annex_country', 'add_core_of', 'remove_core_of',
   'set_capital', 'add_state_core', 'remove_state_core',
   'send_volunteers', 'recall_volunteers', 'send_equipment',
   'add_scaled_equipment', 'damage_building', 'add_building_construction',
   'set_building_level', 'add_offsite_building',
   'spawn_weather', 'end_weather', 'set_province_name', 'set_province_controller',
   'change_terrain', 'create_dynamic_country', 'set_autonomy',
   'add_to_tech_sharing_group', 'remove_from_tech_sharing_group',
   'start_operative_mission', 'set_operative_leader',
   # from existing vocabulary patterns
   'END_OF_CUSTOM_EFFECTS'}

# Remove the sentinel
ALLOWED_EFFECT_META_KEYS.discard('END_OF_CUSTOM_EFFECTS')

BUILTIN_OPINION_MODIFIERS = {
    "small_increase",
    "medium_increase",
    "large_increase",
    "small_decrease",
    "medium_decrease",
    "large_decrease",
}

VALID_IDEOLOGIES = {"alliance", "horde", "death", "fel", "old_gods", "titans", "neutral"}
INVALID_IDEOLOGY_TOKENS = {"democratic", "fascism", "communism", "neutrality", "nazism", "despotic"}
FOCUS_REF_NOISE = {"focus", "yes", "no"}

GENERIC_ICON_PLACEHOLDERS = {
    "GFX_goal_placeholder",
}
GENERIC_ICON_PREFIXES = (
    "GFX_goal_generic_",
    "GFX_focus_generic_",
)
RE_GFX_SPRITE_NAME = re.compile(r'name\s*=\s*"([A-Za-z0-9_]+)"')

ALLOWED_SCOPE_KEYS = {
    "ROOT",
    "FROM",
    "PREV",
    "THIS",
    "owner",
    "controller",
    "overlord",
    "faction_leader",
    "capital_scope",
}
ALLOWED_TRIGGER_META_KEYS = {
    "if",
    "else_if",
    "else",
    "OR",
    "AND",
    "NOT",
    "or",
    "and",
    "not",
    "hidden_trigger",
    "custom_trigger_tooltip",
    "always",
    "count_triggers",
    "all_of",
    "any_of",
    "meta_trigger",
}

TRIGGER_BLOCK_NAMES = {
    "allowed",
    "available",
    "visible",
    "limit",
    "trigger",
    "abort",
    "cancel_trigger",
    "available_if_capitulated",
    "bypass",
    "activation",
    "highlight_states",
    "enable",
}

SCRIPT_RUNTIME_DIR_HINTS = (
    "/events/",
    "/common/decisions/",
    "/common/national_focus/",
)

VALID_UNIT_RATIO_IDS = {
    "fighter",
    "cas",
    "tactical_bomber",
    "naval_bomber",
    "carrier",
    "capital_ship",
    "submarine",
    "screen_ship",
    "convoy",
    "infantry",
    "infantry_special",
    "motorized",
    "artillery",
    "support",
    "cavalry",
    "mountaineers",
    "armor",
}


# --- helpers ---------------------------------------------------------------

def strip_comments_and_strings(text: str) -> str:
    """Remove #comments and double quoted strings so brace counting is accurate."""
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "#":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def iter_files(root: str, exts):
    for dp, _dn, fns in os.walk(root):
        if (
            os.sep + ".git" in dp
            or os.sep + "tools" in dp
            or os.sep + "docs" in dp
            or os.sep + "__pycache__" in dp
        ):
            continue
        for fn in fns:
            if fn.lower().endswith(exts):
                yield os.path.join(dp, fn)


def rel(root: str, path: str) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def load_text(path: str) -> tuple[bytes, str] | None:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    return raw, text


def is_numeric_scope_key(key: str) -> bool:
    return key.isdigit()


def is_dynamic_scope_key(key: str) -> bool:
    return key.startswith("event_target:") or key.startswith("var:") or key.startswith("global.") or "@var:" in key


def is_scope_like_key(key: str) -> bool:
    return key in ALLOWED_SCOPE_KEYS or is_numeric_scope_key(key) or is_dynamic_scope_key(key)


def is_country_tag_like_key(key: str) -> bool:
    return 2 <= len(key) <= 4 and key.isupper() and key.isalpha()


def find_matching_brace(text: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def blank_nested_braces(body: str) -> str:
    """Replace the content of every nested { ... } block with spaces, keeping
    only top-level tokens. Lets us read a focus block's own x/y/id/relpos
    without matching identically-named keys inside effect/trigger sub-blocks
    (e.g. `id =` in create_unit, `x =` in set_variable)."""
    out = []
    depth = 0
    for ch in body:
        if ch == "{":
            depth += 1
            out.append(" ")
        elif ch == "}":
            depth -= 1
            out.append(" ")
        else:
            out.append(ch if depth == 0 else (" " if ch != "\n" else "\n"))
    return "".join(out)


def extract_top_level_definitions(text: str) -> list[tuple[str, str, int]]:
    """
    Return top-level `name = { ... }` blocks as (name, body_without_outer_braces, line).
    The parser is deliberately lightweight and assumes braces are already balanced.
    """
    defs: list[tuple[str, str, int]] = []
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        m = re.match(r"([A-Za-z0-9_@.:\'-]+)\s*=\s*\{", text[i:])
        if not m:
            i += 1
            continue
        name = m.group(1)
        open_idx = i + m.group(0).rfind("{")
        close_idx = find_matching_brace(text, open_idx)
        if close_idx == -1:
            break
        defs.append((name, text[open_idx + 1:close_idx], text.count("\n", 0, i) + 1))
        i = close_idx + 1
    return defs


def extract_named_blocks(text: str, block_name: str) -> list[tuple[str, int]]:
    blocks: list[tuple[str, int]] = []
    pattern = re.compile(rf"\b{re.escape(block_name)}\s*=\s*\{{")
    for m in pattern.finditer(text):
        open_idx = text.find("{", m.start())
        if open_idx == -1:
            continue
        close_idx = find_matching_brace(text, open_idx)
        if close_idx == -1:
            continue
        blocks.append((text[open_idx + 1:close_idx], text.count("\n", 0, m.start()) + 1))
    return blocks


def validate_runtime_antipatterns(
    root: str,
    errors: list[str],
) -> None:
    """
    Catch a short list of high-value anti-patterns that repeatedly caused
    startup/runtime parser failures in this project. This stays deliberately
    narrow to avoid the noise of a fake "full parser".
    """
    for path in iter_files(root, SCRIPT_EXT):
        r = rel(root, path)
        if not any(hint in "/" + r for hint in SCRIPT_RUNTIME_DIR_HINTS):
            continue

        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)

        for m in RE_BAD_HAS_TECHNOLOGY.finditer(clean):
            line = clean.count("\n", 0, m.start()) + 1
            errors.append(
                f"[runtime-antipattern] {r}:{line}: use 'has_tech = ...' instead of unsupported 'has_technology = ...'"
            )

        for m in RE_BAD_LOAD_NAVAL_OOB.finditer(clean):
            line = clean.count("\n", 0, m.start()) + 1
            errors.append(
                f"[runtime-antipattern] {r}:{line}: unsupported 'load_naval_oob'; use 'load_oob = ...'"
            )

        for m in RE_BAD_TRANSFER_EQUIPMENT.finditer(clean):
            line = clean.count("\n", 0, m.start()) + 1
            errors.append(
                f"[runtime-antipattern] {r}:{line}: unsupported 'transfer_equipment' effect in HOI4 1.18.3"
            )

        for m in RE_BAD_REMOVE_COUNTRY_LEADER.finditer(clean):
            line = clean.count("\n", 0, m.start()) + 1
            errors.append(
                f"[runtime-antipattern] {r}:{line}: unsupported 'remove_country_leader' effect; use supported leader-role/retire/kill flow"
            )

        for m in RE_BAD_SET_VARIABLE_VALUE.finditer(clean):
            line = clean.count("\n", 0, m.start()) + 1
            var_name = m.group(1)
            errors.append(
                f"[runtime-antipattern] {r}:{line}: malformed set_variable syntax for '{var_name}' (expected '{var_name} = <value>')"
            )

    ideas_root = os.path.join(root, IDEAS_DIR)
    if os.path.isdir(ideas_root):
        for path in iter_files(ideas_root, SCRIPT_EXT):
            r = rel(root, path)
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)

            for m in RE_BAD_IDEA_REMOVAL.finditer(clean):
                line = clean.count("\n", 0, m.start()) + 1
                errors.append(
                    f"[runtime-antipattern] {r}:{line}: unsupported 'removal = ...' inside idea definitions; use add_timed_idea/add_dynamic_modifier duration on the caller side"
                )

    ai_strategy_root = os.path.join(root, "common", "ai_strategy")
    if os.path.isdir(ai_strategy_root):
        for path in iter_files(ai_strategy_root, SCRIPT_EXT):
            r = rel(root, path)
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)

            for m in RE_UNIT_RATIO_BLOCK.finditer(clean):
                block = m.group(1)
                id_match = RE_AI_STRATEGY_ID.search(block)
                if id_match is None:
                    continue
                unit_id = id_match.group(1)
                if unit_id not in VALID_UNIT_RATIO_IDS:
                    line = clean.count("\n", 0, m.start()) + 1
                    errors.append(
                        f"[runtime-antipattern] {r}:{line}: suspicious unit_ratio id '{unit_id}' (expected vanilla ai ratio bucket such as infantry/cavalry/fighter/screen_ship)"
                    )


def validate_data_vocab(
    root: str,
    errors: list[str],
    known_idea_modifier_keys: set[str],
    known_decision_categories: set[str],
    known_opinion_modifiers: set[str],
    known_ideas: set[str],
) -> None:
    decisions_root = os.path.join(root, "common", "decisions")
    if os.path.isdir(decisions_root):
        for path in iter_files(decisions_root, SCRIPT_EXT):
            r = rel(root, path)
            if "/common/decisions/categories/" in "/" + r:
                continue
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            for name, _body, line in extract_top_level_definitions(clean):
                if name not in known_decision_categories:
                    errors.append(
                        f"[decision-category] {r}:{line}: unknown decision category '{name}' (missing category definition)"
                    )

    ideas_root = os.path.join(root, IDEAS_DIR)
    if os.path.isdir(ideas_root):
        for path in iter_files(ideas_root, SCRIPT_EXT):
            r = rel(root, path)
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            for modifier_body, line in extract_named_blocks(clean, "modifier"):
                for key, rel_line in extract_direct_keys(modifier_body):
                    if key not in known_idea_modifier_keys:
                        errors.append(
                            f"[idea-modifier] {r}:{line + rel_line - 1}: unknown modifier '{key}'"
                        )

    for path in iter_files(root, SCRIPT_EXT):
        r = rel(root, path)
        if not (
            "/events/" in "/" + r
            or "/common/national_focus/" in "/" + r
            or "/common/decisions/" in "/" + r
        ):
            continue
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)
        for m in RE_OPINION_MODIFIER_REF.finditer(clean):
            mod_name = m.group(1)
            if mod_name not in known_opinion_modifiers:
                line = clean.count("\n", 0, m.start(1)) + 1
                errors.append(
                    f"[opinion-modifier] {r}:{line}: unknown opinion modifier '{mod_name}'"
                )
        for m in RE_IDEA_REF.finditer(clean):
            idea_name = m.group(1)
            if idea_name not in known_ideas:
                line = clean.count("\n", 0, m.start(1)) + 1
                errors.append(
                    f"[idea-ref] {r}:{line}: unknown idea '{idea_name}'"
                )


def extract_direct_keys(block_text: str) -> list[tuple[str, int]]:
    """
    Return direct child keys for a block, line-based and depth-aware.
    Good enough for HOA/HOI4 formatting and conservative for validation.
    """
    keys: list[tuple[str, int]] = []
    depth = 0
    for lineno, line in enumerate(block_text.splitlines(), start=1):
        if depth == 0:
            m = re.match(r"^\s*([A-Za-z0-9_@.:\'-]+)\s*(?:=|>|<)", line)
            if m:
                keys.append((m.group(1), lineno))
        depth += line.count("{") - line.count("}")
    return keys


def build_scripted_vocab(mod_root: str) -> tuple[set[str], set[str]]:
    """
    Build conservative vocabularies of known effect and trigger keys.

    Effect keys are sourced from vanilla top-level scripted effect bodies plus
    custom scripted effect names from the mod itself.
    Trigger keys are sourced from vanilla scripted triggers and `limit` blocks
    inside vanilla scripted effects/triggers plus custom scripted trigger names
    from the mod itself.
    """
    effect_keys: set[str] = set()
    trigger_keys: set[str] = set()

    for ref_root in DEFAULT_REFERENCE_ROOTS:
        if not os.path.isdir(ref_root):
            continue
        buildings_root = os.path.join(ref_root, BUILDINGS_DIR)
        if os.path.isdir(buildings_root):
            for path in iter_files(buildings_root, SCRIPT_EXT):
                loaded = load_text(path)
                if loaded is None:
                    continue
                _raw, text = loaded
                clean = strip_comments_and_strings(text)
                for buildings_body, _line in extract_named_blocks(clean, "buildings"):
                    trigger_keys.update(key for key, _ in extract_direct_keys(buildings_body))

    for ref_root in DEFAULT_REFERENCE_ROOTS:
        if not os.path.isdir(ref_root):
            continue

        effects_root = os.path.join(ref_root, SCRIPTED_EFFECTS_DIR)
        if os.path.isdir(effects_root):
            for path in iter_files(effects_root, SCRIPT_EXT):
                loaded = load_text(path)
                if loaded is None:
                    continue
                _raw, text = loaded
                clean = strip_comments_and_strings(text)
                for _name, body, _line in extract_top_level_definitions(clean):
                    effect_keys.update(key for key, _ in extract_direct_keys(body))
                    for limit_body, _limit_line in extract_named_blocks(body, "limit"):
                        trigger_keys.update(key for key, _ in extract_direct_keys(limit_body))

        triggers_root = os.path.join(ref_root, SCRIPTED_TRIGGERS_DIR)
        if os.path.isdir(triggers_root):
            for path in iter_files(triggers_root, SCRIPT_EXT):
                loaded = load_text(path)
                if loaded is None:
                    continue
                _raw, text = loaded
                clean = strip_comments_and_strings(text)
                for _name, body, _line in extract_top_level_definitions(clean):
                    trigger_keys.update(key for key, _ in extract_direct_keys(body))
                    for limit_body, _limit_line in extract_named_blocks(body, "limit"):
                        trigger_keys.update(key for key, _ in extract_direct_keys(limit_body))

    effects_root = os.path.join(mod_root, SCRIPTED_EFFECTS_DIR)
    if os.path.isdir(effects_root):
        for path in iter_files(effects_root, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            for name, _body, _line in extract_top_level_definitions(clean):
                effect_keys.add(name)

    triggers_root = os.path.join(mod_root, SCRIPTED_TRIGGERS_DIR)
    if os.path.isdir(triggers_root):
        for path in iter_files(triggers_root, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            for name, _body, _line in extract_top_level_definitions(clean):
                trigger_keys.add(name)

    return effect_keys, trigger_keys


def build_data_vocab(mod_root: str) -> tuple[set[str], set[str], set[str], set[str]]:
    """
    Build lightweight vocabularies for:
    - idea modifier keys
    - decision category ids
    - opinion modifier ids
    - idea ids
    """
    idea_modifier_keys: set[str] = set()
    decision_categories: set[str] = set()
    opinion_modifiers: set[str] = set()
    ideas: set[str] = set()

    def _load_top_level_names(base_dir: str) -> set[str]:
        names: set[str] = set()
        if not os.path.isdir(base_dir):
            return names
        for path in iter_files(base_dir, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            for name, _body, _line in extract_top_level_definitions(clean):
                names.add(name)
        return names

    def _collect_modifier_keys(base_dir: str) -> None:
        if not os.path.isdir(base_dir):
            return
        for path in iter_files(base_dir, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            for modifier_body, _line in extract_named_blocks(clean, "modifier"):
                idea_modifier_keys.update(key for key, _ in extract_direct_keys(modifier_body))

    def _collect_idea_ids(base_dir: str) -> None:
        if not os.path.isdir(base_dir):
            return
        for path in iter_files(base_dir, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            for ideas_body, _line in extract_named_blocks(clean, "ideas"):
                for _section_name, section_body, _section_line in extract_top_level_definitions(ideas_body):
                    ideas.update(key for key, _ in extract_direct_keys(section_body))

    def _collect_opinion_modifier_ids(base_dir: str) -> None:
        if not os.path.isdir(base_dir):
            return
        for path in iter_files(base_dir, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            for mods_body, _line in extract_named_blocks(clean, "opinion_modifiers"):
                opinion_modifiers.update(key for key, _ in extract_direct_keys(mods_body))

    for ref_root in DEFAULT_REFERENCE_ROOTS:
        if not os.path.isdir(ref_root):
            continue
        _collect_modifier_keys(os.path.join(ref_root, IDEAS_DIR))
        _collect_idea_ids(os.path.join(ref_root, IDEAS_DIR))
        decision_categories.update(_load_top_level_names(os.path.join(ref_root, DECISION_CATEGORIES_DIR)))
        _collect_opinion_modifier_ids(os.path.join(ref_root, OPINION_MODIFIERS_DIR))

    _collect_modifier_keys(os.path.join(mod_root, IDEAS_DIR))
    _collect_idea_ids(os.path.join(mod_root, IDEAS_DIR))
    decision_categories.update(_load_top_level_names(os.path.join(mod_root, DECISION_CATEGORIES_DIR)))
    _collect_opinion_modifier_ids(os.path.join(mod_root, OPINION_MODIFIERS_DIR))
    opinion_modifiers.update(BUILTIN_OPINION_MODIFIERS)

    return idea_modifier_keys, decision_categories, opinion_modifiers, ideas


def build_gfx_sprite_registry(mod_root: str) -> set[str]:
    """Parse all .gfx files (mod + vanilla) and collect SpriteType name= registry."""
    sprites: set[str] = set()
    roots = [mod_root, *DEFAULT_REFERENCE_ROOTS]

    for root in roots:
        iface = os.path.join(root, "interface")
        if not os.path.isdir(iface):
            continue
        for path in iter_files(iface, (".gfx",)):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            sprites.update(m.group(1) for m in RE_GFX_SPRITE_NAME.finditer(text))

    return sprites
def validate_focus_coordinate_collisions(root: str, errors: list[str], warnings: list[str], file_filter: str | None = None) -> None:
    """
    Parse all focus_tree blocks, resolve absolute (x,y) for every focus
    in each tree (including shared_focus subtrees), and report overlaps.
    """
    national_focus_dir = os.path.join(root, "common", "national_focus")
    if not os.path.isdir(national_focus_dir):
        return
    focus_files = list(iter_files(national_focus_dir, SCRIPT_EXT))

    if file_filter is not None:
        _ff_re = re.compile(file_filter.replace("*", ".*").replace("?", "."))
        focus_files = [f for f in focus_files if _ff_re.search(f)]

    focus_data: dict[str, dict] = {}

    for path in focus_files:
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        text = strip_comments_and_strings(text)
        r = rel(root, path)

        for m in re.finditer(r"\b(?:focus|shared_focus)\s*=\s*\{", text):
            open_idx = text.find("{", m.start())
            if open_idx == -1:
                continue
            close_idx = find_matching_brace(text, open_idx)
            if close_idx == -1:
                continue
            body = text[open_idx + 1 : close_idx]
            top = blank_nested_braces(body)

            idm = RE_ID.search(top)
            if not idm:
                continue
            fid = idm.group(1)
            if fid in FOCUS_REF_NOISE:
                continue

            x, y = 0, 0
            relpos = None
            prereqs: list[str] = []

            xm = re.search(r"\bx\s*=\s*(-?\d+)", top)
            if xm:
                x = int(xm.group(1))
            ym = re.search(r"\by\s*=\s*(-?\d+)", top)
            if ym:
                y = int(ym.group(1))
            rm = RE_RELPOS.search(top)
            if rm:
                relpos = rm.group(1)
            pm = re.search(r"\bprerequisite\s*=\s*\{([^}]*)\}", body)
            if pm:
                prereqs = RE_FOCUS_REF.findall(pm.group(1))

            if fid in focus_data:
                continue
            focus_data[fid] = {"x": x, "y": y, "relpos": relpos, "prereqs": prereqs, "file": r}

    def _resolve_abs_positions() -> dict[str, tuple[int, int]]:
        positions: dict[str, tuple[int, int]] = {}
        for fid, data in focus_data.items():
            if data["relpos"] is None:
                positions[fid] = (data["x"], data["y"])
        changed = True
        safety = 20
        while changed and safety > 0:
            safety -= 1
            changed = False
            for fid, data in focus_data.items():
                if fid in positions:
                    continue
                ref = data["relpos"]
                if ref and ref in positions:
                    positions[fid] = (
                        positions[ref][0] + data["x"],
                        positions[ref][1] + data["y"],
                    )
                    changed = True
        return positions

    abs_positions = _resolve_abs_positions()

    children_of: dict[str, set[str]] = {}
    for fid, data in focus_data.items():
        children_of.setdefault(fid, set())
        for other_id, other_data in focus_data.items():
            if other_id == fid:
                continue
            if other_data["file"] != data["file"]:
                continue
            if fid in other_data["prereqs"] or other_data.get("relpos") == fid:
                children_of[fid].add(other_id)

    for path in focus_files:
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        text = strip_comments_and_strings(text)
        r = rel(root, path)

        for tree_m in re.finditer(r"\bfocus_tree\s*=\s*\{", text):
            open_idx = text.find("{", tree_m.start())
            if open_idx == -1:
                continue
            close_idx = find_matching_brace(text, open_idx)
            if close_idx == -1:
                continue
            tree_body = text[open_idx + 1 : close_idx]

            tree_id_m = RE_ID.search(tree_body)
            if not tree_id_m:
                continue
            tree_id = tree_id_m.group(1)

            tree_foci: set[str] = set()

            for fb in extract_named_blocks(tree_body, "focus"):
                fim = RE_ID.search(fb[0])
                if fim:
                    tree_foci.add(fim.group(1))
            for fb in extract_named_blocks(tree_body, "shared_focus"):
                fim = RE_ID.search(fb[0])
                if fim:
                    tree_foci.add(fim.group(1))

            for refm in RE_SHARED.finditer(tree_body):
                ref_id = refm.group(1).strip()
                after = tree_body[refm.end() : refm.end() + 10].strip()
                if after.startswith("{"):
                    continue
                if ref_id in FOCUS_REF_NOISE or ref_id not in focus_data:
                    continue
                tree_foci.add(ref_id)
                queue = [ref_id]
                while queue:
                    parent = queue.pop()
                    for child in children_of.get(parent, set()):
                        if child not in tree_foci:
                            tree_foci.add(child)
                            queue.append(child)

            if len(tree_foci) < 2:
                continue

            tree_foci_list: list[tuple[str, tuple[int, int]]] = []
            for fid in tree_foci:
                if fid in abs_positions:
                    tree_foci_list.append((fid, abs_positions[fid]))

            # Severity model (default HOI4 focus grid: ~90px column / ~100px row,
            # icon roughly one slot wide):
            #   dx==0, dy==0  -> true overlap, icons stacked on the same cell (ERROR)
            #   dx==1, dy==0  -> same row, adjacent columns: icons touch/overlap
            #                    by a few px, usually a layout mistake (WARN)
            #   dx==0, dy==1  -> normal vertical prerequisite spacing (OK)
            #   dx==1, dy==1  -> standard diagonal offset used for sibling /
            #                    mutually_exclusive branches (OK)
            for i in range(len(tree_foci_list)):
                for j in range(i + 1, len(tree_foci_list)):
                    fid_a, (xa, ya) = tree_foci_list[i]
                    fid_b, (xb, yb) = tree_foci_list[j]
                    dx, dy = abs(xa - xb), abs(ya - yb)
                    if dx == 0 and dy == 0:
                        errors.append(
                            f"[focus-collision] {r}: focus tree '{tree_id}' overlapping at "
                            f"(x={xa}, y={ya}) '{fid_a}' and (x={xb}, y={yb}) '{fid_b}'"
                        )
                    elif dx == 1 and dy == 0:
                        warnings.append(
                            f"[focus-nearby] {r}: focus tree '{tree_id}' adjacent in same row at "
                            f"(x={xa}, y={ya}) '{fid_a}' and (x={xb}, y={yb}) '{fid_b}'"
                        )


def validate_scripted_constructs(root: str, errors: list[str], known_effect_keys: set[str], known_trigger_keys: set[str]) -> None:
    effects_root = os.path.join(root, SCRIPTED_EFFECTS_DIR)
    if os.path.isdir(effects_root):
        for path in iter_files(effects_root, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            r = rel(root, path)
            for def_name, body, def_line in extract_top_level_definitions(clean):
                for key, rel_line in extract_direct_keys(body):
                    line = def_line + rel_line - 1
                    if key == "limit":
                        errors.append(
                            f"[scripted-effect] {r}:{line}: top-level 'limit = {{}}' is invalid in scripted effects; wrap it inside if/random/every scope"
                        )
                    elif (
                        key not in known_effect_keys
                        and key not in ALLOWED_TRIGGER_META_KEYS
                        and not is_scope_like_key(key)
                        and key in known_trigger_keys
                    ):
                        errors.append(
                            f"[scripted-effect] {r}:{line}: trigger '{key}' is used as a top-level effect in scripted effect '{def_name}'"
                        )

                for limit_body, limit_line in extract_named_blocks(body, "limit"):
                    for key, rel_line in extract_direct_keys(limit_body):
                        line = def_line + limit_line + rel_line - 2
                        if (
                            key not in known_trigger_keys
                            and key not in ALLOWED_TRIGGER_META_KEYS
                            and not is_scope_like_key(key)
                            and not is_country_tag_like_key(key)
                            and not key.endswith("_target")
                        ):
                            errors.append(
                                f"[scripted-trigger] {r}:{line}: unknown trigger '{key}' inside limit block of scripted effect '{def_name}'"
                            )

    triggers_root = os.path.join(root, SCRIPTED_TRIGGERS_DIR)
    if os.path.isdir(triggers_root):
        for path in iter_files(triggers_root, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            r = rel(root, path)
            for def_name, body, def_line in extract_top_level_definitions(clean):
                for key, rel_line in extract_direct_keys(body):
                    line = def_line + rel_line - 1
                    if (
                        key not in known_trigger_keys
                        and key not in ALLOWED_TRIGGER_META_KEYS
                        and not is_scope_like_key(key)
                        and not is_country_tag_like_key(key)
                        and not key.endswith("_target")
                    ):
                        errors.append(
                            f"[scripted-trigger] {r}:{line}: unknown trigger '{key}' in scripted trigger '{def_name}'"
                        )

                for limit_body, limit_line in extract_named_blocks(body, "limit"):
                    for key, rel_line in extract_direct_keys(limit_body):
                        line = def_line + limit_line + rel_line - 2
                        if (
                            key not in known_trigger_keys
                            and key not in ALLOWED_TRIGGER_META_KEYS
                            and not is_scope_like_key(key)
                            and not is_country_tag_like_key(key)
                            and not key.endswith("_target")
                        ):
                            errors.append(
                                f"[scripted-trigger] {r}:{line}: unknown trigger '{key}' inside limit block of scripted trigger '{def_name}'"
                            )


def validate_runtime_error_log(error_log_path: str, errors: list[str], warnings: list[str]) -> None:
    loaded = load_text(error_log_path)
    if loaded is None:
        errors.append(f"[hoi4-log] {error_log_path}: not valid UTF-8")
        return

    _raw, text = loaded
    collect_runtime_log_issues(text, errors, warnings)


def collect_runtime_log_issues(text: str, errors: list[str], warnings: list[str]) -> None:
    for line in text.splitlines():
        if "Unknown trigger-type:" in line:
            errors.append(f"[hoi4-log] {line.strip()}")
        elif "Unknown effect-type:" in line:
            errors.append(f"[hoi4-log] {line.strip()}")
        elif "Invalid trigger '" in line:
            errors.append(f"[hoi4-log] {line.strip()}")
        elif "Invalid effect '" in line:
            errors.append(f"[hoi4-log] {line.strip()}")
        elif "Missing UTF8 BOM in " in line:
            warnings.append(f"[hoi4-log] {line.strip()}")
        elif "Attempting to set capital state #" in line:
            errors.append(f"[hoi4-log] {line.strip()}")


def split_hoi4_args(raw_args: str) -> list[str]:
    try:
        return shlex.split(raw_args, posix=False)
    except ValueError:
        return raw_args.split()


def snapshot_file(path: str) -> bytes | None:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def extract_new_log_text(error_log_path: str, before_bytes: bytes | None) -> tuple[str | None, str | None]:
    loaded = load_text(error_log_path)
    if loaded is None:
        return None, f"{error_log_path}: not valid UTF-8"

    raw, text = loaded
    if before_bytes is None:
        return text, None

    if raw == before_bytes:
        return "", None

    if raw.startswith(before_bytes):
        delta = raw[len(before_bytes):]
        try:
            return delta.decode("utf-8-sig"), None
        except UnicodeDecodeError:
            return None, f"{error_log_path}: appended log chunk is not valid UTF-8"

    return text, None


def run_hoi4_smoke(
    hoi4_exe: str,
    hoi4_args: str,
    timeout_seconds: int,
    error_log_path: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    if not os.path.isfile(hoi4_exe):
        errors.append(f"[hoi4-smoke] {hoi4_exe}: hoi4.exe not found")
        return

    log_dir = os.path.dirname(error_log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    before_bytes = snapshot_file(error_log_path)
    command = [hoi4_exe, *split_hoi4_args(hoi4_args)]

    creationflags = 0
    startupinfo = None
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    proc = None
    start_ts = time.time()
    try:
        proc = subprocess.Popen(
            command,
            cwd=os.path.dirname(hoi4_exe),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
    except OSError as exc:
        errors.append(f"[hoi4-smoke] failed to launch {' '.join(command)}: {exc}")
        return

    try:
        proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=15)

    # Let HOI4 flush trailing parser lines to error.log after process exit.
    time.sleep(2)
    elapsed = time.time() - start_ts
    warnings.append(
        f"[hoi4-smoke] launched {' '.join(command)} and collected logs after {elapsed:.1f}s"
    )

    new_text, log_error = extract_new_log_text(error_log_path, before_bytes)
    if log_error:
        errors.append(f"[hoi4-smoke] {log_error}")
        return
    if new_text is None:
        warnings.append(f"[hoi4-smoke] {error_log_path}: no readable log output")
        return
    if not new_text.strip():
        warnings.append(f"[hoi4-smoke] {error_log_path}: no new log lines")
        return

    temp_errors: list[str] = []
    temp_warnings: list[str] = []
    collect_runtime_log_issues(new_text, temp_errors, temp_warnings)

    if temp_errors or temp_warnings:
        errors.extend(temp_errors)
        warnings.extend(temp_warnings)
    else:
        warnings.append(f"[hoi4-smoke] {error_log_path}: no tracked parser/capital issues in new lines")


# ---------------------------------------------------------------------------
# Check 10: Double-equals syntax (high priority)
# ---------------------------------------------------------------------------

def validate_double_equals(root: str, errors: list[str]) -> None:
    for path in iter_files(root, SCRIPT_EXT):
        r = rel(root, path)
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)
        for m in RE_DOUBLE_EQUALS.finditer(clean):
            line = clean.count("\n", 0, m.start()) + 1
            errors.append(
                f"[double-equals] {r}:{line}: malformed assign '{m.group(0).strip()}' "
                f"(double-equals pattern 'X = Y = val' detected; did you mean "
                f"NOT = {{ {m.group(1)} = {m.group(2)} }}?)"
            )


# ---------------------------------------------------------------------------
# Check 11: Decision cost mistakes (high priority)
# ---------------------------------------------------------------------------

def validate_decision_costs(root: str, errors: list[str]) -> None:
    decisions_root = os.path.join(root, "common", "decisions")
    if not os.path.isdir(decisions_root):
        return
    for path in iter_files(decisions_root, SCRIPT_EXT):
        r = rel(root, path)
        if "/common/decisions/categories/" in "/" + r:
            continue
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)
        for m in RE_DECISION_COST_MISTAKE.finditer(clean):
            line = clean.count("\n", 0, m.start()) + 1
            errors.append(
                f"[decision-cost] {r}:{line}: invalid '{m.group(0).strip()}' at decision level; "
                f"use '{m.group(1)} = <value>' directly (e.g., 'command_power = 30')"
            )

    # Also catch invalid top-level decision keys
    for path in iter_files(decisions_root, SCRIPT_EXT):
        r = rel(root, path)
        if "/common/decisions/categories/" in "/" + r:
            continue
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)
        for _name, body, def_line in extract_top_level_definitions(clean):
            blank_body = blank_nested_braces(body)
            for key, rel_line in extract_direct_keys(blank_body):
                if key in INVALID_DECISION_KEYS:
                    errors.append(
                        f"[decision-property] {r}:{def_line + rel_line - 1}: "
                        f"invalid decision property '{key}' (not supported in HOI4 1.18.3)"
                    )


# ---------------------------------------------------------------------------
# Check 12: On-actions wrapper (high priority)
# ---------------------------------------------------------------------------

def validate_on_actions_wrapper(root: str, errors: list[str]) -> None:
    on_actions_root = os.path.join(root, ON_ACTIONS_DIR)
    if not os.path.isdir(on_actions_root):
        return
    for path in iter_files(on_actions_root, SCRIPT_EXT):
        r = rel(root, path)
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)
        definitions = extract_top_level_definitions(clean)
        def_names = [n for n, _b, _l in definitions]
        if not def_names:
            continue
        # If the first definition is NOT 'on_actions', or there are root-level
        # on_* blocks alongside on_actions, flag it.
        has_on_actions_wrapper = any(n == "on_actions" for n in def_names)
        has_root_on_blocks = any(
            RE_ON_ACTION_TOP.match(clean[clean.find(n):])
            for n in def_names
            if n != "on_actions"
        )
        bare_on_blocks = []
        for m in RE_ON_ACTION_TOP.finditer(clean):
            candidate = m.group(0).split("=")[0].strip()
            if candidate == "on_actions":
                continue
            if candidate not in bare_on_blocks:
                bare_on_blocks.append(candidate)
        if not has_on_actions_wrapper and bare_on_blocks:
            errors.append(
                f"[on-actions-wrapper] {r}: missing 'on_actions = {{ }}' wrapper "
                f"(root-level blocks found: {', '.join(bare_on_blocks[:4])})"
            )
        elif has_root_on_blocks and has_on_actions_wrapper:
            # Mixed: root-level on_* blocks outside the wrapper
            # Collect top-level def lines that are bare on_* blocks
            for _name, _body, def_line in definitions:
                if _name in bare_on_blocks:
                    errors.append(
                        f"[on-actions-wrapper] {r}:{def_line}: root-level "
                        f"'{_name}' block outside 'on_actions = {{ }}' wrapper"
                    )


# ---------------------------------------------------------------------------
# Check 13: YAML key with embedded colon (high priority)
# ---------------------------------------------------------------------------

def validate_yaml_key_colons(root: str, errors: list[str]) -> None:
    for path in iter_files(root, (".yml",)):
        r = rel(root, path)
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded

        for m in RE_YAML_KEY_COLON.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            full_key = m.group(0).strip().split(":0")[0] if ":0" in m.group(0) else m.group(0).split(":")[0]
            # Extract just the malformed key for the error message
            raw_line = text.splitlines()[line - 1] if line - 1 < len(text.splitlines()) else ""
            errors.append(
                f"[yaml-key-colon] {r}:{line}: localisation key with embedded colon; "
                f"HOA's RE_LOC_KEY silently skips keys containing ':' "
                f"(raw: '{raw_line.strip()[:80]}')"
            )


# ---------------------------------------------------------------------------
# Check 14: Naked variables (medium priority)
# ---------------------------------------------------------------------------

def validate_naked_variables(root: str, errors: list[str]) -> None:
    for path in iter_files(root, SCRIPT_EXT):
        r = rel(root, path)
        if not any(
            hint in "/" + r
            for hint in ("/events/", "/common/decisions/", "/common/national_focus/",
                         "/common/scripted_effects/", "/common/scripted_triggers/")
        ):
            continue
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)

        for m in RE_NAKED_VAR.finditer(clean):
            var_name = m.group(1)
            start_pos = m.start()
            # Find the nearest opening brace before this position
            line = clean.count("\n", 0, start_pos) + 1

            # Check if we're inside a check_variable block by scanning backwards
            prefix = clean[max(0, start_pos - 2000):start_pos]
            # Simple heuristic: count check_variable={ openings and } closings in prefix
            cv_depth = 0
            brace_depth = 0  # overall brace depth
            in_check_variable = False

            i = 0
            while i < len(prefix):
                c = prefix[i]
                if c == "{":
                    brace_depth += 1
                elif c == "}":
                    brace_depth -= 1
                    if cv_depth > 0 and brace_depth < cv_depth:
                        cv_depth -= 1
                # Check if we've entered a check_variable block
                cv_match = re.match(r"\bcheck_variable\s*=\s*\{", prefix[i:])
                if cv_match:
                    cv_depth = brace_depth + 1
                i += 1

            if cv_depth > 0:
                continue  # inside check_variable — OK

            # Also skip if it's inside a set_variable = { var_name = ... } construct
            # or similar variable-value assignment (where var: prefix is the value, not a key)
            setvar_match = re.search(
                r"\bset_(?:temp_)?variable\s*=\s*\{\s*"
                + re.escape(var_name)
                + r"\s*=",
                prefix[-500:],
            )
            if setvar_match:
                continue

            errors.append(
                f"[naked-var] {r}:{line}: bare 'var:{var_name}' "
                f"outside 'check_variable = {{ }}' wrapper"
            )


# ---------------------------------------------------------------------------
# Check 15: Unknown effects/triggers in events, decisions, focus trees (medium)
# ---------------------------------------------------------------------------

def validate_runtime_effects_triggers(
    root: str,
    errors: list[str],
    known_effect_keys: set[str],
    known_trigger_keys: set[str],
) -> None:
    for path in iter_files(root, SCRIPT_EXT):
        r = rel(root, path)
        if not any(
            hint in "/" + r
            for hint in ("/events/", "/common/decisions/", "/common/national_focus/")
        ):
            continue
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)

        # --- Check effects in effect-context blocks ---
        for eff_block_name in EFFECT_BLOCK_NAMES:
            for body, block_line in extract_named_blocks(clean, eff_block_name):
                for key, rel_line in extract_direct_keys(body):
                    if key in known_effect_keys:
                        continue
                    if key in ALLOWED_EFFECT_META_KEYS:
                        continue
                    if is_scope_like_key(key) or is_country_tag_like_key(key):
                        continue
                    if key.endswith("_target") or key.startswith("event_target:"):
                        continue
                    line = block_line + rel_line - 1
                    errors.append(
                        f"[unknown-effect] {r}:{line}: unknown effect '{key}' "
                        f"inside '{eff_block_name}' block"
                    )

        # --- Check triggers in trigger-context blocks ---
        for trig_block_name in TRIGGER_BLOCK_NAMES:
            for body, block_line in extract_named_blocks(clean, trig_block_name):
                for key, rel_line in extract_direct_keys(body):
                    if key in known_trigger_keys:
                        continue
                    if key in ALLOWED_TRIGGER_META_KEYS:
                        continue
                    if is_scope_like_key(key) or is_country_tag_like_key(key):
                        continue
                    if key.endswith("_target"):
                        continue
                    line = block_line + rel_line - 1
                    errors.append(
                        f"[unknown-trigger] {r}:{line}: unknown trigger '{key}' "
                        f"inside '{trig_block_name}' block"
                    )


# --- main ------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument(
        "--summary",
        action="store_true",
        help="condensed report: group findings by check type with counts and a few "
             "examples instead of printing every line (keeps output small)",
    )
    ap.add_argument(
        "--summary-examples",
        type=int,
        default=2,
        metavar="N",
        help="number of example lines to show per check in --summary mode (default: 2)",
    )
    ap.add_argument(
        "--hoi4-error-log",
        nargs="?",
        const=DEFAULT_HOI4_ERROR_LOG,
        default=None,
        help="also parse HOI4 error.log for Unknown trigger/effect and similar runtime parse failures",
    )
    ap.add_argument(
        "--hoi4-smoke",
        action="store_true",
        help="launch hoi4.exe directly, wait briefly for startup parsing, then inspect only newly added error.log lines",
    )
    ap.add_argument(
        "--hoi4-exe",
        default=DEFAULT_HOI4_EXE,
        help=f"path to hoi4.exe (default: {DEFAULT_HOI4_EXE})",
    )
    ap.add_argument(
        "--hoi4-args",
        default=DEFAULT_HOI4_SMOKE_ARGS,
        help=f'launch arguments passed to hoi4.exe during --hoi4-smoke (default: "{DEFAULT_HOI4_SMOKE_ARGS}")',
    )
    ap.add_argument(
        "--hoi4-timeout",
        type=int,
        default=45,
        help="seconds to wait before terminating hoi4.exe during --hoi4-smoke",
    )
    ap.add_argument(
        "--focus-file",
        default=None,
        help="glob pattern to filter focus tree files (e.g. '*second_war*')",
    )
    ap.add_argument(
        "--category",
        nargs="*",
        default=None,
        choices=["loc", "focus-ref", "focus-icon", "collision", "encoding", "braces", "event-ref", "ideology", "scripted", "runtime-script", "data-vocab", "double-equals", "decision-cost", "on-actions", "yaml-key", "naked-var", "runtime-effect-trigger"],
        help="only run specific check categories (default: all)",
    )
    args = ap.parse_args()
    root = args.path

    _active_categories = set(args.category) if args.category else None

    def _cat_active(name: str) -> bool:
        return _active_categories is None or name in _active_categories

    _focus_file_filter: str | None = args.focus_file
    if _focus_file_filter is not None:
        _focus_re = re.compile(
            _focus_file_filter.replace("*", ".*").replace("?", ".")
        )

    def _focus_file_ok(path: str) -> bool:
        if _focus_file_filter is None:
            return True
        return bool(_focus_re.search(path))

    errors: list[str] = []
    warnings: list[str] = []

    focus_defs: dict[str, list[str]] = {}
    focus_tree_defs: dict[str, list[str]] = {}
    focus_refs: list[tuple[str, str, str]] = []
    event_defs: dict[str, list[str]] = {}
    event_refs: list[tuple[str, str]] = []
    event_namespaces: dict[str, list[str]] = {}
    loc_defs: dict[str, list[str]] = {}
    event_loc_expected: dict[str, set[str]] = {}
    focus_loc_expected: dict[str, set[str]] = {}
    tooltip_loc_expected: dict[str, set[str]] = {}

    known_effect_keys, known_trigger_keys = build_scripted_vocab(root)
    known_idea_modifier_keys, known_decision_categories, known_opinion_modifiers, known_ideas = build_data_vocab(root)
    known_gfx_sprites: set[str] = set()
    if _cat_active("focus-icon"):
        known_gfx_sprites = build_gfx_sprite_registry(root)

    for path in iter_files(root, TEXT_EXT):
        r = rel(root, path)
        loaded = load_text(path)
        if loaded is None:
            if _cat_active("encoding"):
                errors.append(f"[encoding] {r}: not valid UTF-8")
            continue
        raw, text = loaded
        clean = strip_comments_and_strings(text)

        if path.lower().endswith(".yml") and _cat_active("loc"):
            if raw[:3] != b"\xef\xbb\xbf":
                errors.append(f"[encoding] {r}: missing UTF-8 BOM (HOI4 requires EF BB BF for localisation files)")
            for key in RE_LOC_KEY.findall(text):
                if key != "l_english":
                    loc_defs.setdefault(key.strip(), []).append(r)

        top = r.split("/", 1)[0]
        if path.lower().endswith(SCRIPT_EXT) and top in SCRIPT_DIRS and _cat_active("braces"):
            o, c = clean.count("{"), clean.count("}")
            if o != c:
                errors.append(f"[braces]   {r}: {{={o} }}={c} (diff {o - c})")

        if "/national_focus/" in "/" + r and _focus_file_ok(r):
            for m in re.finditer(r"\bfocus_tree\s*=\s*\{", text):
                seg = text[m.end():m.end() + 2000]
                idm = RE_ID.search(seg)
                if idm:
                    focus_tree_defs.setdefault(idm.group(1), []).append(r)
            for m in re.finditer(r"\b(?:focus|shared_focus)\s*=\s*\{", text):
                # Skip commented-out focus blocks.
                line_start = text.rfind("\n", 0, m.start()) + 1
                if text[line_start:].lstrip().startswith("#"):
                    continue
                seg = text[m.end():m.end() + 4000]
                idm = RE_ID.search(seg)
                if idm:
                    fid = idm.group(1)
                    focus_defs.setdefault(fid, []).append(r)
                    focus_loc_expected.setdefault(r, set()).update({fid, f"{fid}_desc"})
                if _cat_active("focus-icon"):
                    icon_m = RE_FOCUS_ICON.search(seg)
                    if icon_m:
                        icon_name = icon_m.group(1)
                        if icon_name in GENERIC_ICON_PLACEHOLDERS:
                            warnings.append(
                                f"[focus-icon-missing] {r}: focus '{fid}' has placeholder icon (no art)"
                            )
                        elif icon_name.startswith(GENERIC_ICON_PREFIXES):
                            warnings.append(
                                f"[focus-icon-generic] {r}: focus '{fid}' uses vanilla generic icon '{icon_name}'"
                            )
                        elif icon_name.endswith("_generic"):
                            warnings.append(
                                f"[focus-icon-faction-generic] {r}: focus '{fid}' uses faction-generic placeholder '{icon_name}'"
                            )
                        elif not icon_name.startswith("GFX_goal_") and icon_name not in known_gfx_sprites:
                            errors.append(
                                f"[focus-icon-unknown] {r}: focus '{fid}' references unknown sprite '{icon_name}' (not found in any .gfx registry)"
                            )
            if _cat_active("focus-ref"):
                for m in RE_FOCUS_REF.finditer(text):
                    focus_refs.append((m.group(1), "focus", r))
                for m in RE_RELPOS.finditer(text):
                    focus_refs.append((m.group(1), "relative_position_id", r))
                for m in RE_SHARED.finditer(text):
                    focus_refs.append((m.group(1), "shared_focus", r))
            if _cat_active("loc"):
                for m in RE_TOOLTIP_REF.finditer(text):
                    tooltip_loc_expected.setdefault(r, set()).add(m.group(1))

        if "/history/countries/" in "/" + r and _cat_active("focus-ref"):
            for m in RE_FOCUS_TREE_REF.finditer(clean):
                focus_refs.append((m.group(1), "load_focus_tree", r))

        if "/events/" in "/" + r and _cat_active("event-ref"):
            for m in RE_ADD_NS.finditer(text):
                event_namespaces.setdefault(m.group(1), []).append(r)
            for m in RE_EVENT_ID.finditer(text):
                eid = m.group(1)
                event_defs.setdefault(eid, []).append(r)
                event_loc_expected.setdefault(r, set()).update({f"{eid}.t", f"{eid}.d"})
            for m in re.finditer(r"\boption\s*=\s*\{", text):
                seg = text[m.end():m.end() + 1200]
                name_m = re.search(r"\bname\s*=\s*([A-Za-z0-9_.']+)", seg)
                if name_m:
                    event_loc_expected.setdefault(r, set()).add(name_m.group(1))
            for m in RE_TOOLTIP_REF.finditer(text):
                tooltip_loc_expected.setdefault(r, set()).add(m.group(1))

        for m in RE_EVENT_REF.finditer(text):
            if _cat_active("event-ref"):
                event_refs.append((m.group(1), r))

        if path.lower().endswith(SCRIPT_EXT) and _cat_active("ideology"):
            for ideology in RE_IDEOLOGY.findall(clean):
                if ideology in INVALID_IDEOLOGY_TOKENS:
                    errors.append(
                        f"[ideology] {r}: vanilla ideology token '{ideology}' is not allowed "
                        f"(use HOA ideologies: {', '.join(sorted(VALID_IDEOLOGIES))}; leader ideologies may use *_type)"
                    )

    if _cat_active("scripted"):
        validate_scripted_constructs(root, errors, known_effect_keys, known_trigger_keys)
    if _cat_active("runtime-script"):
        validate_runtime_antipatterns(root, errors)
    if _cat_active("data-vocab"):
        validate_data_vocab(
            root,
            errors,
            known_idea_modifier_keys,
            known_decision_categories,
            known_opinion_modifiers,
            known_ideas,
        )
    if _cat_active("double-equals"):
        validate_double_equals(root, errors)
    if _cat_active("decision-cost"):
        validate_decision_costs(root, errors)
    if _cat_active("on-actions"):
        validate_on_actions_wrapper(root, errors)
    if _cat_active("yaml-key"):
        validate_yaml_key_colons(root, errors)
    if _cat_active("naked-var"):
        validate_naked_variables(root, errors)
    if _cat_active("runtime-effect-trigger"):
        validate_runtime_effects_triggers(root, errors, known_effect_keys, known_trigger_keys)
    if _cat_active("collision"):
        validate_focus_coordinate_collisions(root, errors, warnings, _focus_file_filter)
    if args.hoi4_smoke:
        run_hoi4_smoke(
            hoi4_exe=args.hoi4_exe,
            hoi4_args=args.hoi4_args,
            timeout_seconds=max(args.hoi4_timeout, 1),
            error_log_path=args.hoi4_error_log or DEFAULT_HOI4_ERROR_LOG,
            errors=errors,
            warnings=warnings,
        )
    if args.hoi4_error_log:
        if os.path.isfile(args.hoi4_error_log):
            validate_runtime_error_log(args.hoi4_error_log, errors, warnings)
        else:
            warnings.append(f"[hoi4-log] {args.hoi4_error_log}: file not found")

    if _cat_active("focus-ref"):
        for fid, files in sorted(focus_defs.items()):
            if len(files) > 1:
                errors.append(f"[focus-dup] '{fid}' defined {len(files)}x: {', '.join(sorted(set(files)))}")

        for tid, files in sorted(focus_tree_defs.items()):
            if len(files) > 1:
                errors.append(f"[focus-tree-dup] '{tid}' defined {len(files)}x: {', '.join(sorted(set(files)))}")

        known_focus_ids = set(focus_defs) | set(focus_tree_defs)
        seen_focus_ref = set()
        for fid, kind, file_name in focus_refs:
            if fid in FOCUS_REF_NOISE:
                continue
            if fid not in known_focus_ids and (fid, file_name) not in seen_focus_ref:
                seen_focus_ref.add((fid, file_name))
                errors.append(f"[focus-ref] {file_name}: {kind} -> unknown focus '{fid}'")

    if _cat_active("event-ref"):
        for eid, files in sorted(event_defs.items()):
            if len(files) > 1:
                warnings.append(f"[event-dup] '{eid}' defined {len(files)}x: {', '.join(sorted(set(files)))}")

        for ns, files in sorted(event_namespaces.items()):
            unique_files = sorted(set(files))
            if len(unique_files) > 1:
                warnings.append(f"[namespace] '{ns}' declared in multiple files: {', '.join(unique_files)}")

        seen_event_ref = set()
        for eid, file_name in event_refs:
            if eid not in event_defs and (eid, file_name) not in seen_event_ref:
                seen_event_ref.add((eid, file_name))
                warnings.append(f"[event-ref] {file_name}: -> undefined event '{eid}'")

    if _cat_active("loc"):
        for key, files in sorted(loc_defs.items()):
            unique_files = sorted(set(files))
            if len(files) > len(unique_files):
                warnings.append(f"[loc-dup] '{key}' repeated within file(s): {', '.join(unique_files)}")
            elif len(unique_files) > 1:
                warnings.append(f"[loc-dup] '{key}' defined in multiple files: {', '.join(unique_files)}")

        for file_name, keys in sorted(focus_loc_expected.items()):
            for key in sorted(keys):
                if key not in loc_defs:
                    warnings.append(f"[focus-loc] {file_name}: missing localisation key '{key}'")

        for file_name, keys in sorted(event_loc_expected.items()):
            for key in sorted(keys):
                if key not in loc_defs:
                    warnings.append(f"[event-loc] {file_name}: missing localisation key '{key}'")

        for file_name, keys in sorted(tooltip_loc_expected.items()):
            for key in sorted(keys):
                if key not in loc_defs:
                    warnings.append(f"[tooltip-loc] {file_name}: missing localisation key '{key}'")

    if args.summary:
        def _tag(line: str) -> str:
            m = re.match(r"\s*\[([^\]]+)\]", line)
            return m.group(1) if m else "other"

        def _group(items: list[str]) -> dict[str, list[str]]:
            groups: dict[str, list[str]] = {}
            for it in items:
                groups.setdefault(_tag(it), []).append(it)
            return groups

        rows: list[tuple[str, str, int, list[str]]] = []
        for sev, items in (("ERROR", errors), ("WARN", warnings)):
            if sev == "WARN" and args.quiet:
                continue
            for tag, lst in _group(items).items():
                rows.append((sev, tag, len(lst), lst))
        # errors first, then by count desc
        rows.sort(key=lambda r: (r[0] != "ERROR", -r[2]))
        print("-" * 60)
        print("SUMMARY (grouped by check)")
        for sev, tag, count, lst in rows:
            print(f"  {sev:<5} {tag:<20} {count}")
            for ex in lst[: max(0, args.summary_examples)]:
                print(f"        e.g. {ex}")
            if count > args.summary_examples > 0:
                print(f"        ... +{count - args.summary_examples} more")
    else:
        if not args.quiet:
            for w in warnings:
                print("WARN  " + w)
        for e in errors:
            print("ERROR " + e)

    print("-" * 60)
    print(
        f"focus ids: {len(focus_defs)} | focus trees: {len(focus_tree_defs)} | "
        f"events defined: {len(event_defs)} | loc keys: {len(loc_defs)}"
    )
    print(f"ERRORS: {len(errors)}   WARNINGS: {len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
