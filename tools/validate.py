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
BOOKMARKS_DIR = "common/bookmarks"
CHARACTERS_DIR = "common/characters"
SCIENTIST_TRAITS_DIR = "common/scientist_traits"
UNIT_LEADER_DIR = "common/unit_leader"
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
RE_FOCUS_COORD = re.compile(r"\b(x|y)\s*=\s*(-?\d+)")
RE_FOCUS_PREREQ = re.compile(r"\bprerequisite\s*=\s*\{([^}]*)\}")
RE_BAD_HAS_TECHNOLOGY = re.compile(r"\bhas_technology\s*=")
RE_BAD_LOAD_NAVAL_OOB = re.compile(r"\bload_naval_oob\s*=")
RE_BAD_TRANSFER_EQUIPMENT = re.compile(r"\btransfer_equipment\s*=")
RE_BAD_REMOVE_COUNTRY_LEADER = re.compile(r"\bremove_country_leader\s*=")
RE_BAD_SET_VARIABLE_VALUE = re.compile(r"\bset_variable\s*=\s*\{\s*([A-Za-z0-9_@.:\'-]+)\s+value\s*=")
RE_BAD_IDEA_REMOVAL = re.compile(r"^\s*removal\s*=", re.MULTILINE)
RE_BAD_LEADER_ROLE_MILITARY = re.compile(
    r"\badd_country_leader_role\s*=\s*\{(?:[^{}]|\{[^{}]*\})*?\b(corps_commander|field_marshal|navy_leader)\s*=",
    re.DOTALL,
)
RE_UNIT_RATIO_BLOCK = re.compile(r"\bai_strategy\s*=\s*\{([^{}]*\btype\s*=\s*unit_ratio[^{}]*)\}", re.DOTALL)
RE_AI_STRATEGY_ID = re.compile(r"\bid\s*=\s*([A-Za-z0-9_@.:\'-]+)")
RE_OPINION_MODIFIER_REF = re.compile(
    r"\b(?:add_opinion_modifier|reverse_add_opinion_modifier)\s*=\s*\{[^{}]*?\bmodifier\s*=\s*([A-Za-z0-9_.']+)",
    re.DOTALL,
)
RE_IDEA_REF = re.compile(
    r"\b(?:add_ideas|remove_idea|has_idea|idea)\s*=\s*([A-Za-z0-9_.']+)"
)
RE_HISTORY_VARIANT_TYPE = re.compile(r"\btype\s*=\s*([A-Za-z0-9_.']+)")
RE_HISTORY_VARIANT_PARENT = re.compile(r"\bparent\s*=\s*([A-Za-z0-9_.']+)")
RE_HISTORY_VARIANT_UPGRADE = re.compile(r"\bupgrade\s*=\s*\{")
RE_HISTORY_VARIANT_UPGRADES_BLOCK = re.compile(r"\bupgrades\s*=\s*\{")
RE_SET_NAVAL_OOB = re.compile(r"\bset_naval_oob\s*=\s*([A-Za-z0-9_.']+|\"[^\"]+\")")
RE_OOB_EQUIPMENT = re.compile(
    r"\bequipment\s*=\s*\{\s*([A-Za-z0-9_.']+)\s*=\s*\{[^{}]*?\bowner\s*=\s*([A-Z0-9]{2,4})\b",
    re.DOTALL,
)
RE_OOB_CARRIER_EQUIPMENT = re.compile(
    r"\bequipment\s*=\s*\{\s*(carrier_equipment_[0-9]+)\s*=\s*\{[^{}]*?\bowner\s*=\s*([A-Z0-9]{2,4})\b",
    re.DOTALL,
)
RE_OOB_AIR_WING = re.compile(
    r"\b([A-Za-z0-9_.']+)\s*=\s*\{[^{}]*?\bowner\s*=\s*\"?([A-Z0-9]{2,4})\"?[^{}]*?\bamount\s*=",
    re.DOTALL,
)
RE_HISTORY_CHARACTER_REF = re.compile(r"\b(?:recruit_character|retire_character|kill_character)\s*=\s*([A-Za-z0-9_.']+)")
RE_DIRECT_CAPITAL = re.compile(r"^\s*capital\s*=\s*(\d+)", re.MULTILINE)
RE_DIRECT_SET_CAPITAL = re.compile(r"\bset_capital\s*=\s*\{\s*state\s*=\s*(\d+)\s*\}")
RE_BOOKMARK_DATE = re.compile(r"\bdate\s*=\s*(\d+\.\d+\.\d+(?:\.\d+)?)")
RE_SCRIPT_DATE = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)?$")
RE_REQUIRED_PROVINCES = re.compile(r"\brequired_provinces\s*=\s*\{([^}]*)\}", re.DOTALL)

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

        for m in RE_BAD_LEADER_ROLE_MILITARY.finditer(clean):
            line = clean.count("\n", 0, m.start()) + 1
            role = m.group(1)
            errors.append(
                f"[runtime-antipattern] {r}:{line}: '{role}' is not a valid effect inside add_country_leader_role "
                f"(add_country_leader_role only takes a country_leader block); to add a general use recruit_character on a character that defines a {role} block"
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


def country_tag_from_history_path(path: str) -> str | None:
    base = os.path.basename(path)
    if " - " in base:
        tag = base.split(" - ", 1)[0]
    else:
        tag = os.path.splitext(base)[0]
    if 2 <= len(tag) <= 4 and tag.isupper() and tag.isalpha():
        return tag
    return None


def parse_script_date(raw: str) -> tuple[int, int, int, int]:
    parts = [int(p) for p in raw.split(".")]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def build_state_owner_timelines(root: str) -> dict[int, list[tuple[tuple[int, int, int, int], str]]]:
    state_root = os.path.join(root, "history", "states")
    timelines: dict[int, list[tuple[tuple[int, int, int, int], str]]] = {}
    if not os.path.isdir(state_root):
        return timelines

    for path in iter_files(state_root, SCRIPT_EXT):
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)
        state_id_match = re.search(r"\bid\s*=\s*(\d+)", clean)
        if not state_id_match:
            continue

        state_id = int(state_id_match.group(1))
        timeline: list[tuple[tuple[int, int, int, int], str]] = []
        for history_body, _line in extract_named_blocks(clean, "history"):
            top_history = blank_nested_braces(history_body)
            owner_match = re.search(r"\bowner\s*=\s*([A-Z0-9]{2,4})", top_history)
            if owner_match:
                timeline.append(((0, 0, 0, 0), owner_match.group(1)))

            for block_name, block_body, _block_line in extract_top_level_definitions(history_body):
                if not RE_SCRIPT_DATE.match(block_name):
                    continue
                top_block = blank_nested_braces(block_body)
                owner_match = re.search(r"\bowner\s*=\s*([A-Z0-9]{2,4})", top_block)
                if owner_match:
                    timeline.append((parse_script_date(block_name), owner_match.group(1)))

        timelines[state_id] = sorted(timeline)

    return timelines


def owner_for_state_on_date(
    state_owner_timelines: dict[int, list[tuple[tuple[int, int, int, int], str]]],
    state_id: int,
    date_value: tuple[int, int, int, int],
) -> str | None:
    owner = None
    for owner_date, owner_tag in state_owner_timelines.get(state_id, []):
        if owner_date <= date_value:
            owner = owner_tag
        else:
            break
    return owner


def collect_bookmark_dates(root: str) -> list[tuple[str, tuple[int, int, int, int]]]:
    bookmarks_root = os.path.join(root, BOOKMARKS_DIR)
    results: list[tuple[str, tuple[int, int, int, int]]] = []
    if not os.path.isdir(bookmarks_root):
        return results

    for path in iter_files(bookmarks_root, SCRIPT_EXT):
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)
        r = rel(root, path)
        for match in RE_BOOKMARK_DATE.finditer(clean):
            raw_date = match.group(1)
            results.append((f"{r}:{clean.count(chr(10), 0, match.start()) + 1}", parse_script_date(raw_date)))

    return sorted(results, key=lambda item: item[1])


def build_character_ids(root: str) -> set[str]:
    characters_root = os.path.join(root, CHARACTERS_DIR)
    character_ids: set[str] = set()
    if not os.path.isdir(characters_root):
        return character_ids

    for path in iter_files(characters_root, SCRIPT_EXT):
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)
        for characters_body, _line in extract_named_blocks(clean, "characters"):
            for character_id, _character_body, _character_line in extract_top_level_definitions(characters_body):
                character_ids.add(character_id)
    return character_ids


def build_scientist_traits(root: str) -> set[str]:
    scientist_traits: set[str] = set()

    def _collect(base_root: str) -> None:
        scientist_root = os.path.join(base_root, SCIENTIST_TRAITS_DIR)
        if not os.path.isdir(scientist_root):
            return
        for path in iter_files(scientist_root, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            for trait_id, _trait_body, _trait_line in extract_top_level_definitions(clean):
                scientist_traits.add(trait_id)

    for ref_root in DEFAULT_REFERENCE_ROOTS:
        if os.path.isdir(ref_root):
            _collect(ref_root)
    _collect(root)
    return scientist_traits


def build_unit_leader_traits(root: str) -> set[str]:
    """Collect unit-leader trait ids (field marshal / corps commander / navy leader).

    Traits live nested inside `leader_traits = { trait = { ... } }` blocks under
    common/unit_leader/. Case-sensitive, like all HOI4 tokens.
    """
    traits: set[str] = set()

    def _collect(base_root: str) -> None:
        ul_root = os.path.join(base_root, UNIT_LEADER_DIR)
        if not os.path.isdir(ul_root):
            return
        for path in iter_files(ul_root, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            for lt_body, _lt_line in extract_named_blocks(clean, "leader_traits"):
                for trait_id, _body, _line in extract_top_level_definitions(lt_body):
                    traits.add(trait_id)

    for ref_root in DEFAULT_REFERENCE_ROOTS:
        if os.path.isdir(ref_root):
            _collect(ref_root)
    _collect(root)
    return traits


def parse_state_buildings_snapshot(body: str) -> tuple[dict[str, int], dict[tuple[int, str], int]]:
    state_levels: dict[str, int] = {}
    province_levels: dict[tuple[int, str], int] = {}
    for key, _line in extract_direct_keys(body):
        if key.isdigit():
            continue
        match = re.search(rf"\b{re.escape(key)}\s*=\s*(-?\d+)", body)
        if match:
            state_levels[key] = int(match.group(1))
    for key, nested_body, _line in extract_top_level_definitions(body):
        if key.isdigit():
            province_id = int(key)
            nested_top = blank_nested_braces(nested_body)
            for nested_key, rel_line in extract_direct_keys(nested_body):
                match = re.search(rf"\b{re.escape(nested_key)}\s*=\s*(-?\d+)", nested_top)
                if match:
                    province_levels[(province_id, nested_key)] = int(match.group(1))
            continue
        match = re.search(rf"\b{re.escape(key)}\s*=\s*(-?\d+)", body)
        if match:
            state_levels[key] = int(match.group(1))
    return state_levels, province_levels


def collect_bookmark_start_dates(root: str) -> set[tuple[int, int, int, int]]:
    return {date_value for _source, date_value in collect_bookmark_dates(root)}


def validate_adjacency_rules(root: str, errors: list[str]) -> None:
    path = os.path.join(root, "map", "adjacency_rules.txt")
    if not os.path.isfile(path):
        return
    loaded = load_text(path)
    if loaded is None:
        return
    _raw, text = loaded
    clean = strip_comments_and_strings(text)
    r = rel(root, path)
    province_to_rules: dict[int, list[tuple[str, int]]] = {}
    for rule_body, rule_line in extract_named_blocks(clean, "adjacency_rule"):
        top_rule = blank_nested_braces(rule_body)
        name_match = re.search(r'\bname\s*=\s*"([^"]+)"', top_rule)
        rule_name = name_match.group(1) if name_match else "<unnamed>"
        for prov_match in RE_REQUIRED_PROVINCES.finditer(top_rule):
            rel_line = rule_body.count("\n", 0, prov_match.start()) + 1
            for token in prov_match.group(1).split():
                if not token.isdigit():
                    continue
                province_to_rules.setdefault(int(token), []).append((rule_name, rule_line + rel_line - 1))
    for province_id, refs in sorted(province_to_rules.items()):
        rule_names = sorted({name for name, _line in refs})
        if len(refs) > 1:
            locations = ", ".join(f"{name}@{line}" for name, line in refs)
            errors.append(
                f"[adjacency-rule] {r}: province {province_id} is reused by multiple required_provinces entries ({locations})"
            )


def validate_dated_state_buildings(root: str, warnings: list[str]) -> None:
    state_root = os.path.join(root, "history", "states")
    if not os.path.isdir(state_root):
        return

    for path in iter_files(state_root, SCRIPT_EXT):
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)
        r = rel(root, path)

        for history_body, history_line in extract_named_blocks(clean, "history"):
            baseline_state: dict[str, int] = {}
            baseline_province: dict[tuple[int, str], int] = {}

            for buildings_body, buildings_line in extract_named_blocks(history_body, "buildings"):
                baseline_state, baseline_province = parse_state_buildings_snapshot(buildings_body)
                break

            for block_name, block_body, block_line in extract_top_level_definitions(history_body):
                if not RE_SCRIPT_DATE.match(block_name):
                    continue
                date_value = parse_script_date(block_name)

                buildings_blocks = extract_named_blocks(block_body, "buildings")
                if not buildings_blocks:
                    continue
                buildings_body, buildings_line = buildings_blocks[0]
                current_state, current_province = parse_state_buildings_snapshot(buildings_body)

                for key, prior_value in sorted(baseline_state.items()):
                    current_value = current_state.get(key, 0)
                    if current_value < prior_value:
                        line = block_line + buildings_line - 1
                        warnings.append(
                            f"[dated-buildings] {r}:{line}: dated buildings snapshot at {block_name} reduces state building '{key}' from {prior_value} to {current_value}; use explicit add/remove deltas instead"
                        )
                for (province_id, building_type), prior_value in sorted(baseline_province.items()):
                    current_value = current_province.get((province_id, building_type), 0)
                    if current_value < prior_value:
                        line = block_line + buildings_line - 1
                        warnings.append(
                            f"[dated-buildings] {r}:{line}: dated buildings snapshot at {block_name} reduces province {province_id} building '{building_type}' from {prior_value} to {current_value}; use explicit add/remove deltas instead"
                        )

                baseline_state = dict(current_state)
                baseline_province = dict(current_province)


def validate_history_naval_variants(root: str, errors: list[str], warnings: list[str]) -> None:
    country_root = os.path.join(root, "history", "countries")
    units_root = os.path.join(root, "history", "units")
    if not os.path.isdir(country_root) or not os.path.isdir(units_root):
        return

    variants_by_tag: dict[str, set[str]] = {}
    country_files_by_tag: dict[str, str] = {}
    referenced_naval_oobs: set[str] = set()
    known_upgrade_keys: set[str] = set()
    state_owner_timelines = build_state_owner_timelines(root)
    bookmark_dates = collect_bookmark_dates(root)
    known_character_ids = build_character_ids(root)
    known_scientist_traits = build_scientist_traits(root)
    known_unit_leader_traits = build_unit_leader_traits(root)
    equipment_unlock_techs = build_equipment_unlock_techs(root)
    naval_oob_bookmark_techs: dict[str, list[tuple[str, str, set[str]]]] = {}
    all_techs_by_tag: dict[str, set[str]] = {}

    # Techs granted at runtime via set_technology in focuses/events/effects/decisions.
    # Used to avoid false positives when an OOB is loaded by an effect that also
    # grants the enabling tech (e.g. HED haunted carriers focus).
    effect_granted_techs: set[str] = set()
    for effect_dir in ("common/national_focus", "events", "common/scripted_effects", "common/decisions"):
        effect_root = os.path.join(root, *effect_dir.split("/"))
        if not os.path.isdir(effect_root):
            continue
        for path in iter_files(effect_root, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            for tech_body, _tech_line in extract_named_blocks(clean, "set_technology"):
                for tech_key, _rel_line in extract_direct_keys(tech_body):
                    match = re.search(rf"\b{re.escape(tech_key)}\s*=\s*(-?\d+)", tech_body)
                    if match and int(match.group(1)) > 0:
                        effect_granted_techs.add(tech_key)

    upgrades_root = os.path.join(root, "common", "units", "equipment", "upgrades")
    if os.path.isdir(upgrades_root):
        for path in iter_files(upgrades_root, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            for upgrades_body, _line in extract_named_blocks(clean, "upgrades"):
                known_upgrade_keys.update(key for key, _ in extract_direct_keys(upgrades_body))

    for path in iter_files(country_root, SCRIPT_EXT):
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)
        r = rel(root, path)
        tag = country_tag_from_history_path(path)
        if tag is None:
            continue

        country_files_by_tag[tag] = r
        variant_types = variants_by_tag.setdefault(tag, set())
        top_clean = blank_nested_braces(clean)
        # strip_comments_and_strings deletes quoted values, so
        # 'set_naval_oob = "KUL_596_naval"' loses its name in `clean`.
        # OOB-name scans must run on comment-only-stripped text.
        text_nc = re.sub(r"#[^\n]*", "", text)
        top_text_nc = blank_nested_braces(text_nc)
        base_techs: set[str] = set()
        active_oob_name: str | None = None

        # NOTE: do not extract set_technology from blank_nested_braces output —
        # blanking erases the block bodies, so every tech list parses empty.
        # Instead walk top-level definitions and take non-dated set_technology.
        for block_name, block_body, _block_line in extract_top_level_definitions(text_nc):
            if block_name != "set_technology":
                continue
            for tech_key, _rel_line in extract_direct_keys(block_body):
                match = re.search(rf"\b{re.escape(tech_key)}\s*=\s*(-?\d+)", block_body)
                if match and int(match.group(1)) > 0:
                    base_techs.add(tech_key)

        # Union of every tech granted anywhere in this tag's history (any date),
        # for the air-wing check on OOBs loaded outside bookmark flow.
        tag_all_techs = all_techs_by_tag.setdefault(tag, set())
        for tech_body, _tech_line in extract_named_blocks(clean, "set_technology"):
            for tech_key, _rel_line in extract_direct_keys(tech_body):
                match = re.search(rf"\b{re.escape(tech_key)}\s*=\s*(-?\d+)", tech_body)
                if match and int(match.group(1)) > 0:
                    tag_all_techs.add(tech_key)

        for oob_match in RE_SET_NAVAL_OOB.finditer(top_text_nc):
            active_oob_name = oob_match.group(1).strip("\"'")

        for char_match in RE_HISTORY_CHARACTER_REF.finditer(clean):
            character_id = char_match.group(1)
            if character_id in known_character_ids:
                continue
            line = clean.count("\n", 0, char_match.start(1)) + 1
            errors.append(
                f"[history-character] {r}:{line}: unknown character '{character_id}' referenced from country history"
            )

        for oob_match in RE_SET_NAVAL_OOB.finditer(text_nc):
            raw_name = oob_match.group(1).strip("\"'")
            referenced_naval_oobs.add(raw_name)

        for body, block_line in extract_named_blocks(clean, "create_equipment_variant"):
            type_match = RE_HISTORY_VARIANT_TYPE.search(body)
            if type_match:
                variant_types.add(type_match.group(1))

            parent_match = RE_HISTORY_VARIANT_PARENT.search(body)
            if parent_match:
                rel_line = body.count("\n", 0, parent_match.start()) + 1
                errors.append(
                    f"[history-variant] {r}:{block_line + rel_line - 1}: create_equipment_variant in country history does not support 'parent = ...'"
                )

            upgrade_match = RE_HISTORY_VARIANT_UPGRADE.search(body)
            if upgrade_match:
                rel_line = body.count("\n", 0, upgrade_match.start()) + 1
                errors.append(
                    f"[history-variant] {r}:{block_line + rel_line - 1}: use 'upgrades = {{ ... }}' in country history, not 'upgrade = {{ ... }}'"
                )

            for upgrades_body, upgrades_line in extract_named_blocks(body, "upgrades"):
                for key, rel_line in extract_direct_keys(upgrades_body):
                    if key not in known_upgrade_keys:
                        errors.append(
                            f"[history-variant] {r}:{block_line + upgrades_line + rel_line - 2}: unknown equipment upgrade '{key}' in create_equipment_variant"
                        )

        for block_name, block_body, block_line in extract_top_level_definitions(clean):
            if not RE_SCRIPT_DATE.match(block_name):
                continue
            date_value = parse_script_date(block_name)
            top_block = blank_nested_braces(block_body)

            for capital_match in RE_DIRECT_CAPITAL.finditer(top_block):
                state_id = int(capital_match.group(1))
                line = block_line + top_block.count("\n", 0, capital_match.start(1))
                owner_tag = owner_for_state_on_date(state_owner_timelines, state_id, date_value)
                if owner_tag != tag:
                    errors.append(
                        f"[history-capital] {r}:{line}: {block_name} capital state {state_id} is owned by {owner_tag or 'nobody'} instead of {tag}"
                    )
                for bookmark_src, bookmark_date in bookmark_dates:
                    if bookmark_date < date_value:
                        continue
                    bookmark_owner = owner_for_state_on_date(state_owner_timelines, state_id, bookmark_date)
                    if bookmark_owner != tag:
                        errors.append(
                            f"[history-capital] {r}:{line}: {block_name} capital state {state_id} will be invalid by bookmark {bookmark_src} (owner {bookmark_owner or 'nobody'})"
                    )
                        break

            for capital_match in RE_DIRECT_SET_CAPITAL.finditer(top_block):
                state_id = int(capital_match.group(1))
                line = block_line + top_block.count("\n", 0, capital_match.start(1))
                owner_tag = owner_for_state_on_date(state_owner_timelines, state_id, date_value)
                if owner_tag != tag:
                    errors.append(
                        f"[history-capital] {r}:{line}: {block_name} set_capital state {state_id} is owned by {owner_tag or 'nobody'} instead of {tag}"
                    )
                for bookmark_src, bookmark_date in bookmark_dates:
                    if bookmark_date < date_value:
                        continue
                    bookmark_owner = owner_for_state_on_date(state_owner_timelines, state_id, bookmark_date)
                    if bookmark_owner != tag:
                        errors.append(
                            f"[history-capital] {r}:{line}: {block_name} set_capital state {state_id} will be invalid by bookmark {bookmark_src} (owner {bookmark_owner or 'nobody'})"
                        )
                        break

        dated_blocks = [
            (parse_script_date(block_name), block_name, block_body)
            for block_name, block_body, _block_line in extract_top_level_definitions(text_nc)
            if RE_SCRIPT_DATE.match(block_name)
        ]
        dated_blocks.sort(key=lambda item: item[0])

        for bookmark_src, bookmark_date in bookmark_dates:
            current_techs = set(base_techs)
            current_oob_name = active_oob_name
            for block_date, _block_name, block_body in dated_blocks:
                if block_date > bookmark_date:
                    break
                # Use the raw dated-block body: blank_nested_braces would erase
                # the set_technology contents (see note above).
                for tech_body, _tech_line in extract_named_blocks(block_body, "set_technology"):
                    for tech_key, _rel_line in extract_direct_keys(tech_body):
                        match = re.search(rf"\b{re.escape(tech_key)}\s*=\s*(-?\d+)", tech_body)
                        if match and int(match.group(1)) > 0:
                            current_techs.add(tech_key)
                for oob_match in RE_SET_NAVAL_OOB.finditer(block_body):
                    current_oob_name = oob_match.group(1).strip("\"'")
            if current_oob_name:
                naval_oob_bookmark_techs.setdefault(current_oob_name, []).append(
                    (tag, bookmark_src, set(current_techs))
                )

    characters_root = os.path.join(root, CHARACTERS_DIR)
    if os.path.isdir(characters_root):
        for path in iter_files(characters_root, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            r = rel(root, path)

            for characters_body, characters_line in extract_named_blocks(clean, "characters"):
                for _character_id, character_body, character_line in extract_top_level_definitions(characters_body):
                    for scientist_body, scientist_line in extract_named_blocks(character_body, "scientist"):
                        for traits_body, traits_line in extract_named_blocks(scientist_body, "traits"):
                            for trait_match in re.finditer(r"\b([A-Za-z0-9_@.:\'-]+)\b", traits_body):
                                trait_id = trait_match.group(1)
                                if trait_id in known_scientist_traits:
                                    continue
                                line = characters_line + character_line + scientist_line + traits_line + traits_body.count("\n", 0, trait_match.start()) - 3
                                errors.append(
                                    f"[scientist-trait] {r}:{line}: unknown scientist trait '{trait_id}'"
                                )
                    # Military-role traits must resolve against common/unit_leader
                    # (case-sensitive). A typo here crashes at recruit / game start,
                    # e.g. 'infinite_dragon_trait' vs defined 'Infinite_dragon_trait'.
                    for role in ("field_marshal", "corps_commander", "navy_leader", "general", "admiral"):
                        for role_body, role_line in extract_named_blocks(character_body, role):
                            for traits_body, traits_line in extract_named_blocks(role_body, "traits"):
                                for trait_match in re.finditer(r"\b([A-Za-z0-9_@.:\'-]+)\b", traits_body):
                                    trait_id = trait_match.group(1)
                                    if trait_id in known_unit_leader_traits:
                                        continue
                                    line = characters_line + character_line + role_line + traits_line + traits_body.count("\n", 0, trait_match.start()) - 3
                                    errors.append(
                                        f"[unit-leader-trait] {r}:{line}: unknown unit_leader trait '{trait_id}' in {role} (tokens are case-sensitive)"
                                    )

    seen_oob_requirements: set[tuple[str, str, str]] = set()
    for path in iter_files(units_root, SCRIPT_EXT):
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        clean = strip_comments_and_strings(text)
        r = rel(root, path)
        oob_name = os.path.splitext(os.path.basename(path))[0]

        # Air wings (carrier decks and air bases): an air wing whose equipment
        # the owner has never researched is a hard CTD at OOB load with no
        # error.log entry (null deref; this was the 596 Second War crash —
        # KUL flagship carrier wing of organic_fighter_equipment_1 without
        # fighter_breeds_1). Applies to ALL oob files, not just naval ones.
        # NOTE: scan comment-stripped raw text — strip_comments_and_strings
        # deletes quoted owner tags ('owner = "KUL"' -> 'owner = ').
        wings_text = re.sub(r"#[^\n]*", "", text)

        # SHIP-MOUNTED air wings are a guaranteed CTD in this mod's DLC set
        # (no Man the Guns / By Blood Alone => no cv_ carrier plane types, so
        # the wing's carrier-version lookup derefs null at OOB load). This
        # crashed the 596 Second War bookmark via KUL's flagship even WITH the
        # plane tech researched. Flag every air_wings inside a ship block.
        for ship_body, ship_line in extract_named_blocks(wings_text, "ship"):
            for _wb, wing_rel_line in extract_named_blocks(ship_body, "air_wings"):
                errors.append(
                    f"[oob-ship-air-wing] {r}:{ship_line + wing_rel_line - 1}: air_wings on a ship (carrier deck) — CTD at OOB load with this DLC set; remove the block (see KUL_581_naval precedent)"
                )

        for wings_body, wings_line in extract_named_blocks(wings_text, "air_wings"):
            for wing_match in RE_OOB_AIR_WING.finditer(wings_body):
                equipment_type = wing_match.group(1)
                owner_tag = wing_match.group(2)
                unlock_techs = equipment_unlock_techs.get(equipment_type)
                if not unlock_techs:
                    continue
                line = wings_line + wings_body.count("\n", 0, wing_match.start(1))
                dedupe_key = (r, owner_tag, "wing:" + equipment_type)
                if dedupe_key in seen_oob_requirements:
                    continue
                # Bookmark-accurate check when this OOB is set as a naval oob.
                flagged = False
                for bookmark_tag, bookmark_src, known_techs in naval_oob_bookmark_techs.get(oob_name, []):
                    if bookmark_tag != owner_tag:
                        continue
                    if unlock_techs.isdisjoint(known_techs):
                        seen_oob_requirements.add(dedupe_key)
                        errors.append(
                            f"[oob-air-wing-tech] {r}:{line}: {owner_tag} air wing uses {equipment_type} but has none of the enabling techs by bookmark {bookmark_src} ({', '.join(sorted(unlock_techs))}) — CTD at OOB load"
                        )
                        flagged = True
                        break
                if flagged:
                    continue
                # Otherwise: owner must receive an enabling tech SOMEWHERE
                # (any history date, or a set_technology in focuses/events/effects).
                owner_techs = all_techs_by_tag.get(owner_tag, set())
                if unlock_techs.isdisjoint(owner_techs) and unlock_techs.isdisjoint(effect_granted_techs):
                    seen_oob_requirements.add(dedupe_key)
                    errors.append(
                        f"[oob-air-wing-tech] {r}:{line}: {owner_tag} air wing uses {equipment_type} but {owner_tag} never receives any enabling tech ({', '.join(sorted(unlock_techs))}) — CTD at OOB load"
                    )

        if oob_name not in referenced_naval_oobs:
            continue

        for match in RE_OOB_CARRIER_EQUIPMENT.finditer(clean):
            equipment_type = match.group(1)
            owner_tag = match.group(2)
            if owner_tag not in country_files_by_tag:
                continue
            if equipment_type in variants_by_tag.get(owner_tag, set()):
                continue

            dedupe_key = (r, owner_tag, equipment_type)
            if dedupe_key in seen_oob_requirements:
                continue
            seen_oob_requirements.add(dedupe_key)

            line = clean.count("\n", 0, match.start(1)) + 1
            errors.append(
                f"[history-oob] {r}:{line}: {owner_tag} naval OOB uses {equipment_type} but {country_files_by_tag[owner_tag]} does not create a matching equipment variant"
            )

        for match in RE_OOB_EQUIPMENT.finditer(clean):
            equipment_type = match.group(1)
            owner_tag = match.group(2)
            unlock_techs = equipment_unlock_techs.get(equipment_type)
            if not unlock_techs:
                continue
            dedupe_key = (r, owner_tag, "tech:" + equipment_type)
            if dedupe_key in seen_oob_requirements:
                continue
            seen_oob_requirements.add(dedupe_key)
            line = clean.count("\n", 0, match.start(1)) + 1
            for bookmark_tag, bookmark_src, known_techs in naval_oob_bookmark_techs.get(oob_name, []):
                if bookmark_tag != owner_tag:
                    continue
                if unlock_techs.isdisjoint(known_techs):
                    # Ship hulls without the enabling tech load without crashing
                    # (unlike air wings), so this is a warning, not an error.
                    warnings.append(
                        f"[history-oob-tech] {r}:{line}: {owner_tag} naval OOB '{oob_name}' uses {equipment_type} but {country_files_by_tag[owner_tag]} has none of the required techs by bookmark {bookmark_src} ({', '.join(sorted(unlock_techs))})"
                    )
                    break


def build_equipment_unlock_techs(root: str) -> dict[str, set[str]]:
    unlocks: dict[str, set[str]] = {}

    def _collect(base_root: str) -> None:
        tech_root = os.path.join(base_root, "common", "technologies")
        if not os.path.isdir(tech_root):
            return
        for path in iter_files(tech_root, SCRIPT_EXT):
            loaded = load_text(path)
            if loaded is None:
                continue
            _raw, text = loaded
            clean = strip_comments_and_strings(text)
            # Tech files wrap everything in 'technologies = { ... }' — descend
            # into the wrapper, otherwise every equipment maps to the pseudo-tech
            # 'technologies' and the disjoint checks misfire.
            for wrapper_body, _wrapper_line in extract_named_blocks(clean, "technologies"):
                for tech_name, tech_body, _line in extract_top_level_definitions(wrapper_body):
                    for enable_body, _enable_line in extract_named_blocks(tech_body, "enable_equipments"):
                        for equipment_type, _rel_line in extract_direct_list_tokens(enable_body):
                            unlocks.setdefault(equipment_type, set()).add(tech_name)

    for ref_root in DEFAULT_REFERENCE_ROOTS:
        if os.path.isdir(ref_root):
            _collect(ref_root)
    _collect(root)
    return unlocks


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


def extract_direct_list_tokens(block_text: str) -> list[tuple[str, int]]:
    tokens: list[tuple[str, int]] = []
    depth = 0
    for lineno, line in enumerate(block_text.splitlines(), start=1):
        if depth == 0:
            m = re.match(r"^\s*([A-Za-z0-9_@.:\'-]+)\s*$", line)
            if m:
                tokens.append((m.group(1), lineno))
        depth += line.count("{") - line.count("}")
    return tokens


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
        choices=["loc", "focus-ref", "collision", "encoding", "braces", "event-ref", "ideology", "scripted", "runtime-script", "data-vocab", "history"],
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
                seg = text[m.end():m.end() + 4000]
                idm = RE_ID.search(seg)
                if idm:
                    fid = idm.group(1)
                    focus_defs.setdefault(fid, []).append(r)
                    focus_loc_expected.setdefault(r, set()).update({fid, f"{fid}_desc"})
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
    if _cat_active("history"):
        validate_history_naval_variants(root, errors, warnings)
        validate_adjacency_rules(root, errors)
        validate_dated_state_buildings(root, warnings)
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
