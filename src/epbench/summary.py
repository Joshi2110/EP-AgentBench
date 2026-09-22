"""Aggregate attempt reports without ever scoring an excluded attempt."""

from __future__ import annotations

import json
from pathlib import Path

from . import __version__

FIELDS = ("attempt_id", "status", "scored", "exclusion_reason")


def _load(directory: Path) -> tuple[list[dict], list[str]]:
    reports, unreadable = [], []
    for path in sorted(directory.glob("*/report.json")):
        try:
            report = json.loads(path.read_text())
            if not isinstance(report, dict) or not all(key in report for key in FIELDS):
                raise ValueError("missing required fields")
        except (OSError, ValueError):
            unreadable.append(path.parent.name)
        else:
            reports.append(report)
    return reports, unreadable


def _spread(values: list[float]) -> dict | None:
    if not values:
        return None
    return {"mean": round(sum(values) / len(values), 3), "min": min(values), "max": max(values)}


def summarize(directory: Path) -> dict:
    """Valid attempts are those the runner marked scored; everything else is diagnostic."""
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory}")
    reports, unreadable = _load(directory)
    valid = [r for r in reports if r.get("scored") and r.get("score")]
    excluded = [r for r in reports if r not in valid]
    exclusions: dict[str, int] = {}
    for report in excluded:
        reason = report.get("exclusion_reason") or "unknown"
        exclusions[reason] = exclusions.get(reason, 0) + 1

    successes = [r for r in valid if r["status"] == "success"]
    attempts = [
        {
            "attempt_id": r["attempt_id"], "status": r["status"], "scored": bool(r.get("scored")),
            "exclusion_reason": r.get("exclusion_reason"),
            "model": r.get("agent", {}).get("model_requested"),
            "passed": (r.get("score") or {}).get("passed"),
            "total": (r.get("score") or {}).get("total"),
            "elapsed_seconds": r.get("execution", {}).get("elapsed_seconds"),
            "tool_calls": r.get("execution", {}).get("tool_calls"),
        }
        for r in reports
    ]
    summary = {
        "schema_version": 1, "epbench_version": __version__, "source": str(directory.resolve()),
        "attempts_found": len(reports), "unreadable_attempts": unreadable,
        "valid_attempts": len(valid), "excluded_attempts": len(excluded), "exclusions": exclusions,
        "task_success": None, "case_score": None,
        "models": sorted({a["model"] for a in attempts if a["model"]}),
        "attempts": attempts,
        "notes": [],
    }
    if not valid:
        summary["notes"].append(
            "No valid agent attempts yet: no claim about agent reliability is supported by this data.")
        return summary
    summary["task_success"] = {
        "successes": len(successes), "valid_attempts": len(valid),
        "rate": round(len(successes) / len(valid), 3),
    }
    totals = {r["score"]["total"] for r in valid}
    summary["case_score"] = {
        "mean_success_rate": round(sum(r["score"]["success_rate"] for r in valid) / len(valid), 3),
        "passed": _spread([r["score"]["passed"] for r in valid]),
        "cases_per_attempt": totals.pop() if len(totals) == 1 else sorted(totals),
    }
    summary["runtime_seconds"] = _spread(
        [a["elapsed_seconds"] for a in attempts if a["scored"] and a["elapsed_seconds"] is not None])
    summary["tool_calls"] = _spread(
        [a["tool_calls"] for a in attempts if a["scored"] and a["tool_calls"] is not None])
    summary["notes"].append(
        "Case scores are 13 checks of one task, not independent scientific tasks.")
    if len(valid) < 10:
        summary["notes"].append(
            f"{len(valid)} valid attempts is too few for a reliability estimate; report raw counts only.")
    return summary


def render(summary: dict) -> str:
    lines = [
        f"attempts found      {summary['attempts_found']}",
        f"valid (scored)      {summary['valid_attempts']}",
        f"excluded            {summary['excluded_attempts']}",
    ]
    for reason, count in sorted(summary["exclusions"].items()):
        lines.append(f"  {reason:<34} {count}")
    if summary["task_success"]:
        success = summary["task_success"]
        score = summary["case_score"]
        lines += [
            f"task success        {success['successes']}/{success['valid_attempts']}",
            f"mean case rate      {score['mean_success_rate']} of {score['cases_per_attempt']} cases",
        ]
    for note in summary["notes"]:
        lines.append(f"note: {note}")
    return "\n".join(lines)
