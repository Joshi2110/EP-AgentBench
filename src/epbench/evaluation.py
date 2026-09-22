"""Single-attempt evaluation; never resume, retry, or feed grader feedback to an agent."""

from __future__ import annotations

from datetime import datetime, timezone
import difflib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import time
import uuid

from . import TASK_FILES, __version__, codex_backend, hall
from .grader import grade

PROMPT = """Repair the Hall Transport & Potential Closure task in this workspace.
Read README.md and inspect the supplied files. Edit physics.py and model.py to
satisfy the documented interface, prescribed profiles, and physical relations.
You may execute Python and create your own local checks. Python is available as
python or python3. Use only the task materials in this directory. Do not access
external references, installed evaluators, previous attempts, or the network.
The benchmark CLI and its grader are deliberately unavailable during this attempt.
Finish by briefly describing your changes and the checks you actually ran.
"""
TOOL_ITEMS = {"command_execution", "file_change", "mcp_tool_call", "web_search"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(text: str, secrets: tuple[str, ...]) -> str:
    for value in sorted(secrets, key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}", "[REDACTED]", text)
    return re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~-]+", r"\1[REDACTED]", text)


def _stop(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def _execute(launch: codex_backend.Launch, workspace: Path, trace: Path, seconds: float) -> dict:
    started = time.monotonic()
    calls = set()
    completed = False
    failed = False
    seen_thread = False
    malformed = False
    backend_error = None
    reason = "backend_exit"
    status = "agent_error"
    with trace.open("w", encoding="utf-8") as log:
        with subprocess.Popen(
            launch.command, cwd=workspace, env=launch.environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        ) as process:
            try:
                process.stdin.write(PROMPT.encode())
                process.stdin.close()
                with selectors.DefaultSelector() as selector:
                    buffers = {}
                    for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
                        selector.register(stream, selectors.EVENT_READ, name)
                        buffers[name] = bytearray()
                    while selector.get_map():
                        remaining = seconds - (time.monotonic() - started)
                        if remaining <= 0:
                            status, reason = "timeout", "wall_time_budget_exceeded"
                            break
                        for key, _ in selector.select(min(remaining, 0.1)):
                            chunk = os.read(key.fileobj.fileno(), 65536)
                            name = key.data
                            buffers[name].extend(chunk)
                            if not chunk:
                                selector.unregister(key.fileobj)
                            if len(buffers[name]) > 2_000_000:
                                status, reason = "infrastructure_error", "trace_line_limit_exceeded"
                                break
                            while b"\n" in buffers[name] or (not chunk and buffers[name]):
                                line, _, rest = buffers[name].partition(b"\n")
                                buffers[name] = bytearray(rest)
                                text = _redact(line.decode("utf-8", errors="replace"), launch.secrets)
                                record = {"time": _now(), "stream": name}
                                try:
                                    event = json.loads(text)
                                    if not isinstance(event, dict):
                                        raise ValueError("event must be an object")
                                except ValueError:
                                    record["text"] = text
                                    if name == "stdout":
                                        malformed = True
                                else:
                                    record["event"] = event
                                    if name == "stdout":
                                        kind = event.get("type")
                                        if kind == "error" and backend_error is None:
                                            backend_error = str(event.get("message", ""))[:300]
                                        seen_thread |= kind == "thread.started"
                                        completed |= kind == "turn.completed"
                                        failed |= kind == "turn.failed"
                                        item = event.get("item", {})
                                        if isinstance(item, dict) and item.get("type") in TOOL_ITEMS and isinstance(item.get("id"), str):
                                            calls.add(item["id"])
                                log.write(json.dumps(record, ensure_ascii=False) + "\n")
                                log.flush()
                        if reason == "trace_line_limit_exceeded":
                            break
                    else:
                        remaining = seconds - (time.monotonic() - started)
                        try:
                            process.wait(timeout=max(remaining, 0.001))
                        except subprocess.TimeoutExpired:
                            status, reason = "timeout", "wall_time_budget_exceeded"
                        else:
                            if malformed or not seen_thread:
                                status, reason = "infrastructure_error", "invalid_backend_event_stream"
                            elif failed:
                                status, reason = "agent_error", "backend_turn_failed"
                            elif process.returncode != 0:
                                status, reason = "agent_error", "backend_nonzero_exit"
                            elif not completed:
                                status, reason = "infrastructure_error", "missing_turn_completed"
                            else:
                                status, reason = "completed", "turn_completed"
            except KeyboardInterrupt:
                status, reason = "interrupted", "user_interrupt"
            finally:
                _stop(process)
    return {
        "status": status, "termination_reason": reason, "returncode": process.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "tool_calls": len(calls) if seen_thread else None,
        "tool_call_metric": "unique observed action-item IDs; excludes hidden/internal tool calls",
        "backend_error": backend_error,
    }


def _hashes(directory: Path) -> dict[str, str | None]:
    return {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        if (directory / name).is_file() and not (directory / name).is_symlink() else None
        for name in TASK_FILES["hall-transport"]
    }


def _scoring(execution: dict) -> tuple[bool, str | None]:
    """Only attempts where the agent actually worked belong in model-performance aggregates."""
    status, calls = execution["status"], execution.get("tool_calls")
    if status in ("not_started", "infrastructure_error"):
        return False, "no_attempt"
    if status == "interrupted":
        return False, "interrupted"
    if not calls:
        if execution.get("backend_error"):
            return False, "backend_error_before_agent_work"
        if status == "agent_error":
            return False, "no_agent_execution"
    return True, None


def evaluate(task: str, out: Path, model: str, *, seconds: float = 300, backend=codex_backend) -> dict:
    """Preserve one attempt, including partial files after agent errors/timeouts."""
    if task != "hall-transport":
        raise ValueError("Agent evaluation currently supports hall-transport only")
    if not model.strip() or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("An explicit model and a positive finite time budget are required")
    if os.name != "posix":
        raise ValueError("The evaluation runner currently requires macOS or Linux")
    from .cli import init

    attempt_id = uuid.uuid4().hex
    attempt = out.resolve() / attempt_id
    attempt.mkdir(parents=True, mode=0o700)
    trace = attempt / "trace.jsonl"
    trace.touch(mode=0o600)
    report = {
        "schema_version": 1, "task": task, "benchmark_version": __version__,
        "attempt_id": attempt_id, "started_at": _now(), "ended_at": None,
        "agent": {"name": "codex", "model_requested": model, "model_observed": None},
        "budget": {"wall_seconds": seconds}, "status": "infrastructure_error",
        "execution": {"status": "not_started", "termination_reason": None, "tool_calls": None, "backend_error": None},
        "grading": {"status": "not_run", "result": None},
        "scored": False, "exclusion_reason": "no_attempt", "score": None,
        "paths": {"workspace": str(attempt / "workspace"), "trace": str(trace), "diff": str(attempt / "changes.patch")},
        "limitations": [
            "Local CLI restrictions are not a comprehensive security boundary.",
            "Public evaluation cases are withheld at runtime, not secret.",
            "No token counts, costs, or model determinism are inferred.",
            "Attempts with scored=false are diagnostic only and must be kept out of model aggregates.",
        ],
    }
    (attempt / "prompt.txt").write_text(PROMPT)
    (attempt / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    secrets = ()
    try:
        # The agent's live workspace sits beside, not inside, everything it must not read.
        live, control = attempt / "live", attempt / "control"
        control.mkdir(mode=0o700)
        init(task, live)
        shutil.copytree(live, attempt / "initial")
        report["initial_sha256"] = _hashes(live)
        launched = False
        try:
            withheld = [Path(hall.__file__), Path(__file__).with_name("grader.py"), attempt / "initial" / "README.md"]
            launch = backend.prepare(live, control, model, withheld)
            secrets = launch.secrets
            report["agent"] = {k: v for k, v in launch.metadata.items() if k != "config"}
            (attempt / "backend-config.toml").write_text(launch.metadata.get("config", ""))
            launched = True
            report["execution"] = _execute(launch, live, trace, seconds)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            report["execution"] = {"status": "infrastructure_error", "termination_reason": _redact(str(exc), secrets), "tool_calls": None, "backend_error": None}
        except KeyboardInterrupt:
            report["execution"] = {"status": "interrupted", "termination_reason": "user_interrupt", "tool_calls": None, "backend_error": None}
        finally:
            # Never follow submitted symlinks into host files while preserving the workspace.
            shutil.copytree(live, attempt / "workspace", symlinks=True)
            # The control tree holds a copy of the Codex credentials; it must not outlive the run.
            for scratch in (live, control):
                shutil.rmtree(scratch, ignore_errors=True)
            report["final_sha256"] = _hashes(attempt / "workspace")
        execution = report["execution"]["status"]
        if launched:
            try:
                result = grade(task, attempt / "workspace")
                report["grading"] = {"status": result["status"], "result": result}
            except (OSError, ValueError) as exc:
                report["grading"] = {"status": "error", "result": None, "error": _redact(str(exc), secrets)}
        report["status"] = {
            "timeout": "timed_out", "agent_error": "agent_failed", "interrupted": "interrupted",
            "infrastructure_error": "infrastructure_error",
        }.get(execution, "grading_error" if report["grading"]["status"] == "error" else
              "success" if report["grading"]["status"] == "passed" else "grading_failed")
        report["scored"], report["exclusion_reason"] = _scoring(report["execution"])
        graded = report["grading"]["result"]
        if report["scored"] and graded:
            report["score"] = {"passed": graded["passed"], "total": graded["total"],
                               "success_rate": graded["success_rate"]}
        changes = []
        for name in TASK_FILES[task]:
            final = attempt / "workspace" / name
            original = (attempt / "initial" / name).read_text().splitlines(keepends=True)
            current = final.read_text(errors="replace").splitlines(keepends=True) if final.is_file() and not final.is_symlink() else []
            changes.extend(difflib.unified_diff(original, current, fromfile=f"initial/{name}", tofile=f"workspace/{name}"))
        (attempt / "changes.patch").write_text(_redact("".join(changes), secrets))
    except (OSError, ValueError, RuntimeError) as exc:
        report["status"] = "infrastructure_error"
        report["error"] = _redact(str(exc), secrets)
    finally:
        report["ended_at"] = _now()
        destination = attempt / "report.json"
        pending = attempt / "report.tmp"
        pending.write_text(_redact(json.dumps(report, indent=2, allow_nan=False), secrets) + "\n")
        pending.replace(destination)
    return report
