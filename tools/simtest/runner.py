#!/usr/bin/env python3
"""
HOI4 Simulation Test Runner — Phase 1: Smoke Tests.

Launches HOI4 with -start_save, monitors game.log for [SIMTEST] markers,
generates a Markdown report.

Usage:
    python tools/simtest/runner.py
"""

import os
import sys
import subprocess
import time
import shutil
import json
import psutil
from datetime import datetime

# --- Paths ---
HOI4_EXE = r"C:\SteamLibrary\steamapps\common\Hearts of Iron IV\hoi4.exe"
HOI4_DIR = os.path.dirname(HOI4_EXE)
DOCS_DIR = os.path.expanduser(r"~/Documents/Paradox Interactive/Hearts of Iron IV")
SAVE_DIR = os.path.join(DOCS_DIR, "save games")
LOG_DIR  = os.path.join(DOCS_DIR, "logs")
GAME_LOG = os.path.join(LOG_DIR, "game.log")
ERROR_LOG = os.path.join(LOG_DIR, "error.log")
CONTINUE_JSON = os.path.join(DOCS_DIR, "continue_game.json")

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR   = os.path.dirname(SCRIPT_DIR)
MOD_ROOT    = os.path.dirname(TOOLS_DIR)
SIMTEST_DIR = SCRIPT_DIR
REPORTS_DIR = os.path.join(SIMTEST_DIR, "reports")

SMOKE_CONFIG = {
    "name": "second_war_smoke",
    "desc": "15-day smoke test from Second War start",
    "save_source": os.path.join(SAVE_DIR, "KUL_START_SECOND_WAR.hoi4"),
    "timeout": 900,       # 15 min total (game takes ~5 min to load)
    "idle_timeout": 180,  # 3 min no activity after startup = crash
}

RUN_LOG: list[str] = []
RUN_LOG_PATH = os.path.join(SIMTEST_DIR, "last_run.log")


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    RUN_LOG.append(line)
    print(line, flush=True)


def snapshot_file(path: str) -> int:
    try:
        return os.path.getsize(path)
    except FileNotFoundError:
        return 0


def read_tail(path: str, start_offset: int) -> tuple[str, int]:
    """Read new content from file starting at start_offset.
    Handles file truncation (HOI4 truncates logs on restart).
    Returns (new_text, new_offset)."""
    try:
        actual_size = os.path.getsize(path)
    except FileNotFoundError:
        return "", start_offset
    # HOI4 truncates game.log on startup — reset offset if file shrunk
    if actual_size < start_offset:
        start_offset = 0
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            fh.seek(start_offset)
            text = fh.read()
            return text, fh.tell()
    except FileNotFoundError:
        return "", start_offset


def get_hoi4_pids() -> set[int]:
    """Return set of PIDs for all running hoi4.exe processes."""
    pids = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == "hoi4.exe":
                pids.add(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return pids


def kill_all_hoi4() -> None:
    """Terminate all hoi4.exe processes."""
    killed = 0
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == "hoi4.exe":
                log(f"  killing hoi4.exe PID={proc.info['pid']}")
                proc.kill()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if killed:
        time.sleep(3)
        log(f"  killed {killed} hoi4 process(es)")


def run_test(config: dict) -> dict:
    r = {
        "name": config["name"],
        "started": str(datetime.now()),
        "simtest": [],
        "errors_new": [],
        "errors_known": 0,
        "startup": False,
        "checkpoints": 0,
        "complete": False,
        "timed_out": False,
        "crashed": False,
        "fatal": None,
    }

    src = config["save_source"]
    if not os.path.isfile(src):
        r["fatal"] = f"save not found: {src}"
        return r

    apath = os.path.join(SAVE_DIR, "autosave.hoi4")
    bpath = os.path.join(SAVE_DIR, "_simtest_autosave.bak")
    cj_backup = os.path.join(DOCS_DIR, "_simtest_continue_game.bak")

    # --- 1. Prepare ---
    log("preparing test save...")
    if os.path.exists(apath):
        shutil.copy2(apath, bpath)
        os.remove(apath)
    shutil.copy2(src, apath)
    log(f"  {os.path.basename(src)} -> autosave.hoi4 ({os.path.getsize(apath)/1024/1024:.0f} MB)")

    if os.path.exists(CONTINUE_JSON):
        shutil.copy2(CONTINUE_JSON, cj_backup)
    cj = {
        "title": f"SimTest {config['name']}",
        "desc": "",
        "date": time.asctime() + "\n",
        "filename": "autosave.hoi4",
        "is_remote": False,
    }
    with open(CONTINUE_JSON, "w") as f:
        json.dump(cj, f, indent="\t")
        f.write("\n")
    log("  continue_game.json updated")

    # --- 2. Snapshot logs ---
    gl_off = snapshot_file(GAME_LOG)
    el_off = snapshot_file(ERROR_LOG)
    log(f"  game.log before: {gl_off} bytes")

    # --- 3. Launch ---
    before_pids = get_hoi4_pids()
    cmd = [HOI4_EXE, "-start_save=autosave", "-hands_off", "-debug"]
    log(f"launching: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(cmd, cwd=HOI4_DIR,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        r["fatal"] = f"launch failed: {e}"
        _cleanup(apath, bpath, cj_backup)
        return r

    log(f"  launcher PID={proc.pid}, waiting for game to load...")

    # --- 4. Monitor ---
    t_start = time.time()
    timeout = config["timeout"]
    idle_timeout = config.get("idle_timeout", 180)
    last_activity = t_start  # any log growth = activity
    last_heartbeat = 0
    gl_cur = gl_off
    el_cur = el_off
    game_pid = None

    try:
        while True:
            now = time.time()
            elapsed = now - t_start

            if int(elapsed) - int(last_heartbeat) >= 20:
                last_heartbeat = elapsed
                log(f"  [{elapsed:.0f}s] alive, startup={r['startup']}, chk={r['checkpoints']}")

            if elapsed > timeout:
                log(f"TIMEOUT after {timeout:.0f}s")
                r["timed_out"] = True
                break

            # Find the actual game PID (after launcher starts it)
            if game_pid is None:
                current_pids = get_hoi4_pids()
                new_pids = current_pids - before_pids
                if len(new_pids) > 1:  # game started
                    game_pid = max(new_pids)
                    log(f"  game detected, PID={game_pid}")

            # Check alive
            if game_pid is not None:
                alive = psutil.pid_exists(game_pid) if game_pid else False
            else:
                alive = proc.poll() is None

            if game_pid is not None and not alive:
                log(f"  game PID={game_pid} died")
                r["crashed"] = True
                time.sleep(3)
                break
            elif game_pid is None and not alive:
                continue  # launcher may exit after spawning game

            # Read BOTH game.log AND error.log for activity detection
            new_gl, gl_cur = read_tail(GAME_LOG, gl_off)
            new_el, el_cur = read_tail(ERROR_LOG, el_cur)

            has_activity = False

            if new_gl:
                has_activity = True
                gl_off = gl_cur
                for line in new_gl.splitlines():
                    if "[SIMTEST]" in line:
                        r["simtest"].append(line.strip())
                        last_activity = now
                        if "STARTUP" in line:
                            r["startup"] = True
                            log("  >>>> STARTUP detected! Game loaded!")
                        elif "CHECKPOINT" in line:
                            r["checkpoints"] += 1
                            log(f"  >>>> CHECKPOINT #{r['checkpoints']}")
                        elif "TEST_COMPLETE" in line:
                            r["complete"] = True
                            log("  >>>> TEST_COMPLETE detected!")

            if new_el:
                has_activity = True
                el_off = el_cur
                for line in new_el.splitlines():
                    s = line.strip()
                    if not s:
                        continue
                    if any(p in s for p in ("Malformed token", "Unexpected token", "Missing UTF8 BOM")):
                        r["errors_known"] += 1
                    else:
                        r.setdefault("errors_new", []).append(s)

            if has_activity:
                last_activity = now

            if r["complete"]:
                log("  flushing final lines...")
                time.sleep(5)
                new_gl, _ = read_tail(GAME_LOG, gl_off)
                if new_gl:
                    for line in new_gl.splitlines():
                        if "[SIMTEST]" in line:
                            r["simtest"].append(line.strip())
                break

            # Crash: no log activity at all for idle_timeout after startup
            if r["startup"] and (now - last_activity > idle_timeout):
                log(f"  NO ACTIVITY for {idle_timeout:.0f}s — likely crash/stuck")
                r["crashed"] = True
                break

            # Loading: game.log OR error.log growth = alive. Only flag stuck if
            # NEITHER log grew in 3 minutes AND we haven't seen startup yet.
            # Exception: don't kill while loading < 6 minutes in.
            loading_deadline = max(360, idle_timeout)  # at least 6 min for loading
            if not r["startup"] and elapsed < loading_deadline:
                pass  # still within loading window, keep waiting
            elif not r["startup"] and (now - last_activity > idle_timeout):
                log(f"  no log growth for {idle_timeout:.0f}s, elapsed={elapsed:.0f}s — loading stuck")
                r["crashed"] = True
                break

            time.sleep(3)

    except KeyboardInterrupt:
        log("interrupted by user")
    finally:
        kill_all_hoi4()
        time.sleep(3)

    # --- 5. Final log read ---
    new_txt, _ = read_tail(GAME_LOG, gl_off)
    if new_txt:
        for line in new_txt.splitlines():
            if "[SIMTEST]" in line:
                r["simtest"].append(line.strip())

    # --- 6. Error.log delta ---
    if el_off > 0:
        el_txt, _ = read_tail(ERROR_LOG, el_off)
        if el_txt:
            for line in el_txt.splitlines():
                s = line.strip()
                if not s:
                    continue
                if any(p in s for p in ("Malformed token", "Unexpected token", "Missing UTF8 BOM")):
                    r["errors_known"] += 1
                else:
                    r["errors_new"].append(s)

    # --- 7. Cleanup ---
    _cleanup(apath, bpath, cj_backup)

    r["duration"] = round(time.time() - t_start, 1)
    log(f"DONE: {r['duration']:.0f}s, startup={r['startup']}, chk={r['checkpoints']}, complete={r['complete']}")
    return r


def _cleanup(apath, bpath, cj_backup):
    if os.path.exists(bpath):
        try:
            shutil.copy2(bpath, apath)
            os.remove(bpath)
            log("  original autosave restored")
        except Exception:
            pass
    if os.path.exists(cj_backup):
        try:
            shutil.copy2(cj_backup, CONTINUE_JSON)
            os.remove(cj_backup)
            log("  continue_game.json restored")
        except Exception:
            pass


def assess(r: dict) -> dict:
    chk = {}
    chk["startup"] = r["startup"]
    chk["progress"] = r["checkpoints"] > 0
    chk["no_crash"] = not r["crashed"] and not r["timed_out"]
    chk["no_new_errors"] = len(r["errors_new"]) == 0
    return chk


def generate_report(r: dict, chk: dict) -> str:
    ok = all(chk.values())
    lines = [
        f"# SimTest: {r['name']}",
        f"**{'PASS' if ok else 'FAIL'}** | {r['started']} | duration={r.get('duration','?')}s",
        "",
        "## Summary",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Startup | {r['startup']} |",
        f"| Checkpoints | {r['checkpoints']} |",
        f"| Complete | {r['complete']} |",
        f"| Timed out | {r['timed_out']} |",
        f"| Crashed | {r['crashed']} |",
        f"| New errors | {len(r['errors_new'])} |",
        f"| Known noise | {r['errors_known']} |",
        "",
        "## Checks",
    ]
    for name, val in chk.items():
        lines.append(f"- {'PASS' if val else 'FAIL'}: {name}")

    lines.extend(["", "## Runner log", "```"])
    lines.extend(RUN_LOG)
    lines.append("```")

    if r["simtest"]:
        lines.extend(["", "## [SIMTEST] markers", "```"])
        lines.extend(r["simtest"])
        lines.append("```")
    else:
        lines.append("\n## [SIMTEST] markers\n*(none)*")

    if r["errors_new"]:
        lines.extend(["", "## New error.log", "```"])
        lines.extend(r["errors_new"][:40])
        lines.append("```")

    lines.extend(["", "## Full results (JSON)", "```json"])
    safe = {k: v for k, v in r.items() if k != "simtest"}
    safe["simtest_count"] = len(r["simtest"])
    lines.append(json.dumps(safe, indent=2, default=str))
    lines.append("```")

    return "\n".join(lines)


def main():
    log(f"=== SMOKE TEST: {SMOKE_CONFIG['name']} ===")

    if not os.path.isfile(HOI4_EXE):
        log(f"FATAL: HOI4 not found at {HOI4_EXE}")
        return 1

    if not os.path.isfile(SMOKE_CONFIG["save_source"]):
        log(f"FATAL: save not found at {SMOKE_CONFIG['save_source']}")
        return 1

    r = run_test(SMOKE_CONFIG)

    if r.get("fatal"):
        log(f"FATAL: {r['fatal']}")
        report = f"# SimTest: {SMOKE_CONFIG['name']}\n**FATAL**\n{r['fatal']}\n"
    else:
        chk = assess(r)
        report = generate_report(r, chk)
        overall = "PASS" if all(chk.values()) else "FAIL"
        log(f"overall: {overall}")

    ts = time.strftime("%Y%m%d_%H%M%S")
    rpath = os.path.join(REPORTS_DIR, f"{SMOKE_CONFIG['name']}_{ts}.md")
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(rpath, "w", encoding="utf-8") as f:
        f.write(report)
    log(f"report: {rpath}")

    # Also save run log
    with open(RUN_LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(RUN_LOG))
        f.write("\n\n")
        f.write(report)

    print(f"\n{report}")

    return 0 if not r.get("fatal") and all(assess(r).values()) else 1


if __name__ == "__main__":
    sys.exit(main())
