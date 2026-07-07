#!/usr/bin/env python3
"""
Analyze a HOI4 crash minidump when error.log is silent.

Usage:
    python tools/crashdump.py "C:/Users/<user>/Documents/Paradox Interactive/Hearts of Iron IV/crashes/hoi4_YYYYMMDD_HHMMSS"
    python tools/crashdump.py <path-to-minidump.dmp>

Requires:  pip install minidump

What it prints and how to read it
---------------------------------
1) EXCEPTION
   - code: EXCEPTION_ACCESS_VIOLATION etc.
   - params [op, addr]: op 0=read 1=write; addr is the faulting memory address.
     * addr is SMALL (0x0..0x1000): NULL-pointer deref reading a member at
       offset +addr. A script object lookup returned null (missing equipment/
       tech/variant/idea/character reference). This is the common case for
       "crash with clean error.log".
     * addr near a stack guard page / RSP: stack overflow (infinite recursion
       in scripted effects/triggers or focus relative_position cycles).
   - crash offset inside hoi4.exe: stable across runs = same code path,
     i.e. the crash is deterministic data, not memory corruption.

2) STACK STRINGS of the crashing thread
   This is the money shot. The game's parsers keep the tokens they are
   currently chewing on the stack (small-string optimization), so the strings
   reveal WHICH subsystem died and often the EXACT token:
     e.g. 'carrier_equipment_2', 'air_wings', 'task_force', 'fleet', 'units/'
     -> died loading a naval OOB, on a carrier air wing.
   Then grep the repo for those tokens to find the offending file.

3) Do NOT trust exception.txt's symbolized frames (PHYSFS_swapULE64 etc.).
   Paradox ships no PDB; those are nearest-export guesses and are meaningless.
   The raw dump data above is what's real.

Real example (2026-07-07 Second War crash): params [0x0, 0x58] = null+0x58
read; stack strings showed air_wings/carrier -> KUL_596_naval.txt carrier had
an air wing of organic_fighter_equipment_1 while KUL never received
fighter_breeds_1. Fix: grant the enabling tech (or remove the wing).
An air wing of un-researched equipment in any OOB is a guaranteed silent CTD.
"""

import logging
import os
import re
import sys

logging.disable(logging.CRITICAL)  # minidump lib whines about PEB on HOI4 dumps; harmless

try:
    from minidump.minidumpfile import MinidumpFile
except ImportError:
    sys.exit("pip install minidump")


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip().splitlines()[2].strip())
    path = sys.argv[1]
    if os.path.isdir(path):
        path = os.path.join(path, "minidump.dmp")
    if not os.path.isfile(path):
        sys.exit(f"not found: {path}")

    mf = MinidumpFile.parse(path)

    print("=== MODULES (game) ===")
    game_base = None
    for m in mf.modules.modules:
        name = m.name.lower()
        if "hoi4" in name or "eu4" in name or "ck3" in name or "victoria" in name:
            print(f"  {m.name}  base={hex(m.baseaddress)} size={hex(m.size)}")
            game_base = m.baseaddress

    crash_tid = None
    if mf.exception:
        print("=== EXCEPTION ===")
        for rec in mf.exception.exception_records:
            er = rec.ExceptionRecord
            crash_tid = rec.ThreadId
            print(f"  code   : {er.ExceptionCode}")
            print(f"  address: {hex(er.ExceptionAddress)}"
                  + (f"  (module offset {hex(er.ExceptionAddress - game_base)})" if game_base else ""))
            params = [hex(p) for p in er.ExceptionInformation[: er.NumberParameters]]
            print(f"  params : {params}")
            if len(params) >= 2:
                op = "read" if params[0] == "0x0" else "write"
                target = int(params[1], 16)
                if target < 0x10000:
                    print(f"  -> {op} at {params[1]}: NULL DEREF, member offset +{params[1]}."
                          " A lookup by name returned null — hunt a broken data reference.")
                else:
                    print(f"  -> {op} at {params[1]} (not a near-null pointer; check for"
                          " stack overflow or corruption)")

    print("=== CRASHING THREAD STACK STRINGS ===")
    buff = mf.get_reader().get_buffered_reader()
    for t in mf.threads.threads:
        if t.ThreadId != crash_tid:
            continue
        buff.move(t.Stack.StartOfMemoryRange)
        data = buff.read(t.Stack.MemoryLocation.DataSize)
        seen: list[str] = []
        for raw in re.findall(rb"[\x20-\x7e]{4,}", data):
            s = raw.decode()
            if s not in seen:
                seen.append(s)
        for s in seen:
            print(f"  {s}")
        print(f"  ({len(data)} stack bytes scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
