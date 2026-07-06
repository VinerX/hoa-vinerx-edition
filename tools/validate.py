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



def validate_focus_coordinate_collisions(root: str, errors: list[str], warnings: list[str]) -> None:
    """
    Parse all focus_tree blocks, resolve absolute (x,y) for every focus
    in each tree (including shared_focus subtrees), and report overlaps.
    """
    national_focus_dir = os.path.join(root, "common", "national_focus")
    if not os.path.isdir(national_focus_dir):
        return
    focus_files = list(iter_files(national_focus_dir, SCRIPT_EXT))

    focus_data: dict[str, dict] = {}

    for path in focus_files:
        loaded = load_text(path)
        if loaded is None:
            continue
        _raw, text = loaded
        r = rel(root, path)

        for m in re.finditer(r"\b(?:focus|shared_focus)\s*=\s*\{", text):
            open_idx = text.find("{", m.start())
            if open_idx == -1:
                continue
            close_idx = find_matching_brace(text, open_idx)
            if close_idx == -1:
                continue
            body = text[open_idx + 1 : close_idx]

            idm = RE_ID.search(body)
            if not idm:
                continue
            fid = idm.group(1)
            if fid in FOCUS_REF_NOISE:
                continue

            x, y = 0, 0
            relpos = None
            prereqs: list[str] = []

            xm = re.search(r"\bx\s*=\s*(-?\d+)", body)
            if xm:
                x = int(xm.group(1))
            ym = re.search(r"\by\s*=\s*(-?\d+)", body)
            if ym:
                y = int(ym.group(1))
            rm = RE_RELPOS.search(body)
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

            reported_pairs: set[tuple[str, str]] = set()
            for i in range(len(tree_foci_list)):
                for j in range(i + 1, len(tree_foci_list)):
                    fid_a, (xa, ya) = tree_foci_list[i]
                    fid_b, (xb, yb) = tree_foci_list[j]
                    if abs(xa - xb) <= 1 and abs(ya - yb) <= 1:
                        reported_pairs.add((fid_a, fid_b))
                        errors.append(
                            f"[focus-collision] {r}: focus tree '{tree_id}' overlapping at "
                            f"(x={xa}, y={ya}) '{fid_a}' and (x={xb}, y={yb}) '{fid_b}'"
                        )

            # WARN on cross-file near-collisions not already caught above
            for fid_a in tree_foci:
                for fid_b in tree_foci:
                    if fid_a >= fid_b:
                        continue
                    if fid_a not in abs_positions or fid_b not in abs_positions:
                        continue
                    if focus_data.get(fid_a, {}).get("file") == focus_data.get(fid_b, {}).get("file"):
                        continue
                    if (fid_a, fid_b) in reported_pairs:
                        continue
                    pa, pb = abs_positions[fid_a], abs_positions[fid_b]
                    if abs(pa[0] - pb[0]) <= 1 and abs(pa[1] - pb[1]) <= 1:
                        warnings.append(
                            f"[focus-nearby] {r}: focus tree '{tree_id}' nearby at "
                            f"(x={pa[0]}, y={pa[1]}) '{fid_a}' and "
                            f"(x={pb[0]}, y={pb[1]}) '{fid_b}'"
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
    args = ap.parse_args()
    root = args.path

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

    for path in iter_files(root, TEXT_EXT):
        r = rel(root, path)
        loaded = load_text(path)
        if loaded is None:
            errors.append(f"[encoding] {r}: not valid UTF-8")
            continue
        raw, text = loaded
        clean = strip_comments_and_strings(text)

        if path.lower().endswith(".yml"):
            for key in RE_LOC_KEY.findall(text):
                if key != "l_english":
                    loc_defs.setdefault(key.strip(), []).append(r)

        top = r.split("/", 1)[0]
        if path.lower().endswith(SCRIPT_EXT) and top in SCRIPT_DIRS:
            o, c = clean.count("{"), clean.count("}")
            if o != c:
                errors.append(f"[braces]   {r}: {{={o} }}={c} (diff {o - c})")

        if "/national_focus/" in "/" + r:
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
            for m in RE_FOCUS_REF.finditer(text):
                focus_refs.append((m.group(1), "focus", r))
            for m in RE_RELPOS.finditer(text):
                focus_refs.append((m.group(1), "relative_position_id", r))
            for m in RE_SHARED.finditer(text):
                focus_refs.append((m.group(1), "shared_focus", r))
            for m in RE_TOOLTIP_REF.finditer(text):
                tooltip_loc_expected.setdefault(r, set()).add(m.group(1))

        if "/history/countries/" in "/" + r:
            for m in RE_FOCUS_TREE_REF.finditer(clean):
                focus_refs.append((m.group(1), "load_focus_tree", r))

        if "/events/" in "/" + r:
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
            event_refs.append((m.group(1), r))

        if path.lower().endswith(SCRIPT_EXT):
            for ideology in RE_IDEOLOGY.findall(clean):
                if ideology in INVALID_IDEOLOGY_TOKENS:
                    errors.append(
                        f"[ideology] {r}: vanilla ideology token '{ideology}' is not allowed "
                        f"(use HOA ideologies: {', '.join(sorted(VALID_IDEOLOGIES))}; leader ideologies may use *_type)"
                    )

    validate_scripted_constructs(root, errors, known_effect_keys, known_trigger_keys)
    validate_focus_coordinate_collisions(root, errors, warnings)
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
