#!/usr/bin/env python3
"""
HOA rebuild — lightweight pre-launch validator.

Catches the most common crash/parse mistakes in HOI4 mod script WITHOUT running
the game (which is the slow part of the loop). It is intentionally conservative:
things reported as ERROR are almost always real; WARNINGs may have false positives
(cross-mod / vanilla references) and are for eyeballing.

Checks:
  1. Encoding        — every .txt/.gui/.gfx/.lua reads as UTF-8 (BOM allowed).
  2. Brace balance   — { and } balance per file (comments and "quoted" strings stripped).
  3. Focus ids       — duplicate focus ids (ERROR) and dangling references from
                       prerequisite / mutually_exclusive / relative_position_id /
                       shared_focus (ERROR: they point at no known focus).
  4. Event refs      — *_event = <ns.n> references resolve to a defined event id (WARN).

Usage:
  python tools/validate.py                # validate the mod this script lives in
  python tools/validate.py --path <dir>   # validate another dir
  python tools/validate.py --quiet        # only print the summary + errors

Exit code: 0 if no ERRORS, 1 otherwise (handy for a pre-commit hook).
"""
from __future__ import annotations
import argparse, os, re, sys

# Dirs whose .txt files use HOI4 script syntax (brace-balanced). Others skipped.
SCRIPT_DIRS = ("common", "events", "history", "map", "gfx", "interface", "tutorial")
SCRIPT_EXT  = (".txt",)
TEXT_EXT    = (".txt", ".gui", ".gfx", ".lua", ".yml", ".asset")

# --- helpers ---------------------------------------------------------------

def strip_comments_and_strings(text: str) -> str:
    """Remove #comments and "double quoted strings" so brace counting is accurate."""
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
        if c == '#':                     # comment to end of line
            j = text.find('\n', i)
            i = n if j == -1 else j
            continue
        out.append(c)
        i += 1
    return ''.join(out)

def iter_files(root: str, exts):
    for dp, _dn, fns in os.walk(root):
        if os.sep + '.git' in dp or os.sep + 'tools' in dp:
            continue
        for fn in fns:
            if fn.lower().endswith(exts):
                yield os.path.join(dp, fn)

def rel(root, p): return os.path.relpath(p, root).replace(os.sep, '/')

# Regexes (script is loosely formatted; keep patterns forgiving).
RE_FOCUS_BLOCK = re.compile(r'\bfocus\s*=\s*\{')
RE_ID          = re.compile(r'\bid\s*=\s*([A-Za-z0-9_.\']+)')
RE_FOCUS_REF   = re.compile(r'\bfocus\s*=\s*([A-Za-z0-9_.\']+)')
RE_RELPOS      = re.compile(r'\brelative_position_id\s*=\s*([A-Za-z0-9_.\']+)')
RE_SHARED      = re.compile(r'\bshared_focus\s*=\s*([A-Za-z0-9_.\']+)')
RE_ADD_NS      = re.compile(r'\badd_namespace\s*=\s*([A-Za-z0-9_]+)')
RE_EVENT_ID    = re.compile(r'\bid\s*=\s*([A-Za-z0-9_]+\.\d+)')
RE_EVENT_REF   = re.compile(r'\b(?:country_event|news_event|state_event|unit_leader_event|operative_leader_event)\s*=\s*(?:\{[^}]*\bid\s*=\s*)?([A-Za-z0-9_]+\.\d+)')

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--path', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()
    root = args.path

    errors: list[str] = []
    warnings: list[str] = []

    # --- pass 1: encoding + brace balance, and collect focus/event data ---
    focus_defs: dict[str, list[str]] = {}   # id -> [files]
    focus_refs: list[tuple[str, str, str]] = []  # (id, kind, file)
    event_defs: set[str] = set()
    event_refs: list[tuple[str, str]] = []  # (id, file)

    for path in iter_files(root, TEXT_EXT):
        r = rel(root, path)
        try:
            with open(path, 'rb') as fh:
                raw = fh.read()
            raw.decode('utf-8-sig')   # BOM tolerated
        except UnicodeDecodeError as e:
            errors.append(f"[encoding] {r}: not valid UTF-8 ({e})")
            continue
        text = raw.decode('utf-8-sig')

        # brace balance only for script .txt under script dirs
        top = r.split('/', 1)[0]
        if path.lower().endswith(SCRIPT_EXT) and top in SCRIPT_DIRS:
            clean = strip_comments_and_strings(text)
            o, c = clean.count('{'), clean.count('}')
            if o != c:
                errors.append(f"[braces]   {r}: {{={o} }}={c} (diff {o - c})")

        # focus data (national_focus files)
        if '/national_focus/' in '/' + r:
            # Both `focus = { id = X }` and `shared_focus = { id = X }` are DEFINITIONS.
            for m in re.finditer(r'\b(?:focus|shared_focus)\s*=\s*\{', text):
                seg = text[m.end():m.end() + 4000]  # block-ish window
                idm = RE_ID.search(seg)
                if idm:
                    focus_defs.setdefault(idm.group(1), []).append(r)
            for m in RE_FOCUS_REF.finditer(text):
                focus_refs.append((m.group(1), 'focus', r))
            for m in RE_RELPOS.finditer(text):
                focus_refs.append((m.group(1), 'relative_position_id', r))
            for m in RE_SHARED.finditer(text):
                focus_refs.append((m.group(1), 'shared_focus', r))

        # event data
        if '/events/' in '/' + r:
            for m in RE_EVENT_ID.finditer(text):
                event_defs.add(m.group(1))
        for m in RE_EVENT_REF.finditer(text):
            event_refs.append((m.group(1), r))

    # --- duplicate focus ids ---
    for fid, files in sorted(focus_defs.items()):
        if len(files) > 1:
            errors.append(f"[focus-dup] '{fid}' defined {len(files)}x: {', '.join(sorted(set(files)))}")

    # --- dangling focus references ---
    known = set(focus_defs)
    seen = set()
    for fid, kind, f in focus_refs:
        if fid in ('focus', 'yes', 'no'):   # noise from odd formatting
            continue
        if fid not in known and (fid, f) not in seen:
            seen.add((fid, f))
            errors.append(f"[focus-ref] {f}: {kind} -> unknown focus '{fid}'")

    # --- event references (warn only; cross-file/vanilla refs cause false positives) ---
    ev_seen = set()
    for eid, f in event_refs:
        if eid not in event_defs and (eid, f) not in ev_seen:
            ev_seen.add((eid, f))
            warnings.append(f"[event-ref] {f}: -> undefined event '{eid}'")

    # --- report ---
    if not args.quiet:
        for w in warnings:
            print("WARN  " + w)
    for e in errors:
        print("ERROR " + e)

    print("-" * 60)
    print(f"focus ids: {len(focus_defs)} | events defined: {len(event_defs)}")
    print(f"ERRORS: {len(errors)}   WARNINGS: {len(warnings)}")
    return 1 if errors else 0

if __name__ == '__main__':
    sys.exit(main())
