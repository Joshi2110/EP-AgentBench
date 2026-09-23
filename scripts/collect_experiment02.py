#!/usr/bin/env python3
"""Experiment 02 collector: follows the committed schedule, resumable, never re-runs a valid slot.

Usage:  caffeinate -i -m -s python3 scripts/collect_experiment02.py <logfile> [--dry-run]
The epbench entry point is taken from the interpreter running this script.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCHEDULE = REPO / "docs/experiment-02-schedule.json"
OUT = REPO / "attempts/experiment-02"
WARMUP = 12


def reports(out: Path) -> list[dict]:
    found = []
    for path in sorted(out.glob("*/report.json")):
        try:
            found.append(json.loads(path.read_text()))
        except (OSError, ValueError):
            pass
    return found


def filled(out: Path) -> Counter:
    """Valid scored attempts already collected, keyed by (task, protocol)."""
    return Counter((r["task"], r.get("protocol")) for r in reports(out) if r.get("scored"))


def pending(schedule: dict, done: Counter) -> list[dict]:
    """Slots still to run, in the committed order. Never reorders, never re-runs."""
    seen: Counter = Counter()
    todo = []
    for slot in schedule["order"]:
        key = (slot["task"], slot["protocol"])
        seen[key] += 1
        if seen[key] > done[key]:
            todo.append(slot)
    return todo


def main(argv: list[str]) -> int:
    log_path = Path(argv[1])
    dry = "--dry-run" in argv
    schedule = json.loads(SCHEDULE.read_text())
    out = OUT
    out.mkdir(parents=True, exist_ok=True)
    epbench = str(Path(sys.executable).with_name("epbench"))

    def log(message: str) -> None:
        with log_path.open("a") as handle:
            handle.write(f"{time.strftime('%H:%M:%S')} {message}\n")

    if not dry:
        log(f"warmup {WARMUP}s: verify sleep prevention before the first attempt")
        time.sleep(WARMUP)
    done = filled(out)
    todo = pending(schedule, done)
    log(f"resume: {sum(done.values())}/{schedule['total_valid']} valid present, "
        f"{len(reports(out))} raw, {len(todo)} slots pending, interpreter={sys.executable}")
    if dry:
        print(json.dumps({"valid": sum(done.values()), "pending": len(todo),
                          "next": todo[0] if todo else None}))
        return 0

    raw = len(reports(out))
    for slot in todo:
        started = time.monotonic()
        subprocess.run([epbench, "evaluate", slot["task"], "--out", str(out),
                        "--model", schedule["model_requested"],
                        "--seconds", str(schedule["seconds"]),
                        "--protocol", slot["protocol"]],
                       cwd=REPO, capture_output=True, text=True)
        current = reports(out)
        if len(current) <= raw:
            log("no new report written; stopping")
            return 0
        raw = len(current)
        newest = max(current, key=lambda r: r.get("started_at", ""))
        scored = bool(newest.get("scored"))
        done = filled(out)
        log(f"slot {slot['index']:>2} {slot['task']:<15} {slot['protocol']:<10} "
            f"status={newest.get('status')} scored={scored} "
            f"reason={newest.get('exclusion_reason')} "
            f"score={(newest.get('score') or {}).get('passed')} "
            f"wall={time.monotonic() - started:.0f}s "
            f"-> valid={sum(done.values())}/{schedule['total_valid']}")
        error = (newest.get("execution") or {}).get("backend_error") or ""
        if not scored and ("usage limit" in error.lower() or "quota" in error.lower()):
            log("QUOTA EXHAUSTED - stopping cleanly; rerun to resume at the same slot")
            return 0
        if not scored:
            # Excluded attempts are preserved and the slot is retried, never reordered.
            todo.append(slot)
    log(f"done: {sum(filled(out).values())}/{schedule['total_valid']} valid, {raw} raw")
    print(f"VALID={sum(filled(out).values())} RAW={raw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
