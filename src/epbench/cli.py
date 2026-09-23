"""Export task workspaces, grade submissions, run agent attempts, and summarize them."""

from __future__ import annotations

import argparse
from importlib.resources import files
import json
from pathlib import Path
import sys

from . import TASKS, TASK_FILES, __version__
from .evaluation import EVALUABLE
from .grader import TIMEOUT_SECONDS, grade


def init(task: str, out: Path) -> None:
    if task not in TASKS:
        raise ValueError(f"Unknown task: {task}")
    source = files("epbench").joinpath("tasks", task)
    contents = {name: source.joinpath(name).read_bytes() for name in TASK_FILES[task]}
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"Output must be an empty directory or a new path: {out}")
    out.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items():
        with out.joinpath(name).open("xb") as destination:
            destination.write(content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="epbench", description="Electric propulsion coding task examples")
    parser.add_argument("--version", action="version", version=f"epbench {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List available coding tasks")
    make = sub.add_parser("init", help="Export a task specification and starter")
    make.add_argument("task", choices=TASKS)
    make.add_argument("--out", type=Path, required=True)
    evaluate = sub.add_parser("grade", help="Execute a trusted Python submission locally (not sandboxed)")
    evaluate.add_argument("task", choices=TASKS)
    evaluate.add_argument("--solution", type=Path, required=True, help="Python file, or directory for a Hall task")
    evaluate.add_argument("--json-out", type=Path, help="Also save the JSON report to this file")
    evaluate.add_argument("--timeout", type=float, default=TIMEOUT_SECONDS, help="Seconds per case (default: 5)")
    attempt = sub.add_parser("evaluate", help="Run one isolated Codex attempt and grade what it leaves behind")
    attempt.add_argument("task", choices=sorted(EVALUABLE))
    attempt.add_argument("--out", type=Path, required=True, help="Directory that will hold the attempt record")
    attempt.add_argument("--model", required=True, help="Backend model identifier, passed through verbatim")
    attempt.add_argument("--seconds", type=float, default=300.0, help="Wall-clock budget for the agent (default: 300)")
    report_summary = sub.add_parser("summarize", help="Aggregate attempt reports in a directory")
    report_summary.add_argument("--attempts", type=Path, required=True, help="Directory holding attempt records")
    report_summary.add_argument("--json-out", type=Path, help="Also save the summary JSON to this file")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            for name, description in TASKS.items():
                print(f"{name:20s} {description}")
        elif args.command == "init":
            init(args.task, args.out)
            print(f"Created task workspace: {args.out}")
            edits = [f for f in TASK_FILES[args.task] if f not in ("README.md", "run.py")]
            editable = " and ".join(edits)
            print(f"Edit {editable} in {args.out}")
        elif args.command == "evaluate":
            from .evaluation import evaluate as run_attempt
            report = run_attempt(args.task, args.out, args.model, seconds=args.seconds)
            print(json.dumps(report, indent=2, allow_nan=False))
            grading = report["grading"]["result"]
            score = f"{grading['passed']}/{grading['total']} cases passed" if grading else "not graded"
            if not report["scored"]:
                score += f" (excluded from aggregates: {report['exclusion_reason']})"
            print(f"{args.task}: {report['status']}, {score}", file=sys.stderr)
            print(f"Attempt record: {report['paths']['workspace']}", file=sys.stderr)
            return 0 if report["status"] == "success" else 1
        elif args.command == "summarize":
            from .summary import render, summarize
            result = summarize(args.attempts)
            text = json.dumps(result, indent=2, allow_nan=False) + "\n"
            if args.json_out:
                args.json_out.parent.mkdir(parents=True, exist_ok=True)
                args.json_out.write_text(text, encoding="utf-8")
            print(text, end="")
            print(render(result), file=sys.stderr)
            return 0
        else:
            if args.json_out:
                output, solution = args.json_out.resolve(), args.solution.resolve()
                if solution.is_dir() and (
                    output.is_relative_to(solution) or (
                        output.exists() and any(
                            p.is_file() and output.samefile(p) for p in solution.iterdir()
                        )
                    )
                ):
                    raise ValueError("JSON output must be outside the submission workspace and not alias its files")
                if output == solution or (
                    args.json_out.exists() and args.solution.exists()
                    and args.json_out.samefile(args.solution)
                ):
                    raise ValueError("JSON output must not overwrite the submission")
            result = grade(args.task, args.solution, timeout=args.timeout)
            report = json.dumps(result, indent=2, allow_nan=False) + "\n"
            if args.json_out:
                args.json_out.parent.mkdir(parents=True, exist_ok=True)
                args.json_out.write_text(report, encoding="utf-8")
            print(report, end="")
            print(f"{args.task}: {result['passed']}/{result['total']} cases passed", file=sys.stderr)
            return 0 if result["status"] == "passed" else 1
    except (OSError, ValueError) as exc:
        print(f"epbench: {exc}", file=sys.stderr)
        if args.command in ("grade", "evaluate"):
            print(json.dumps({"schema_version": 1, "task": args.task, "status": "error", "error": str(exc)}))
        elif args.command == "summarize":
            print(json.dumps({"schema_version": 1, "status": "error", "error": str(exc)}))
        return 2
    except KeyboardInterrupt:
        print("epbench: interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
