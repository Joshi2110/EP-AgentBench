"""Deterministic local grading for trusted files and Hall workspaces."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from typing import Any, Iterator

from . import TASKS, __version__
from . import hall
from .physics import axial_electric_field, ideal_beam_thrust, ion_exit_speed

TIMEOUT_SECONDS = 5.0
REL_TOL = 1e-6
ABS_TOL = {"ion-acceleration": 1e-8, "beam-thrust": 1e-12, "axial-field": 1e-8}
WARNING = "Trusted local execution only: Python -I and temporary directories are not a security sandbox."


def _cases(task: str) -> Iterator[tuple[dict[str, float | int], float]]:
    if task == "ion-acceleration":
        for speed, voltage in [
            (1100.0, 150.0), (2300.0, 300.0), (0.0, 450.0),
            (8000.0, 80.0), (100.0, 610.0), (0.0, 0.0),
            (2300.0, 0.0), (0.0, 0.001), (100000.0, 1000.0),
            (100000.0, 0.1),
        ]:
            yield {"v_in_m_s": speed, "discharge_v": voltage}, ion_exit_speed(speed, voltage)
    elif task == "beam-thrust":
        for current, speed, charge in [
            (1.1, 11000.0, 1), (4.8, 18500.0, 1), (0.6, 26000.0, 1),
            (2.4, 9000.0, 2), (5.2, 30000.0, 2), (0.0, 20000.0, 1),
            (1.0, 0.0, 2), (0.001, 100.0, 2), (10.0, 100000.0, 2),
            (2.4, 9000.0, 1),
        ]:
            yield {
                "beam_current_a": current, "ion_speed_m_s": speed, "charge_state": charge,
            }, ideal_beam_thrust(current, speed, charge)
        yield {"beam_current_a": 1.1, "ion_speed_m_s": 11000.0}, ideal_beam_thrust(1.1, 11000.0)
    elif task == "axial-field":
        for left, right, length in [
            (300.0, 0.0, 0.038), (250.0, 20.0, 0.04), (0.0, 0.0, 0.05),
            (180.0, 30.0, 0.025), (600.0, 100.0, 0.08), (0.0, 300.0, 0.038),
            (-100.0, -400.0, 0.038), (250.0, 250.0, 0.001),
            (-1000.0, 1000.0, 0.001), (0.0, 0.001, 1.0),
        ]:
            yield {
                "phi_left_v": left, "phi_right_v": right, "length_m": length,
            }, axial_electric_field(left, right, length)
    else:
        raise ValueError(f"Unknown task: {task}")


def _run_case(
    source: bytes | dict[str, bytes], inputs: dict[str, Any], timeout: float,
    *, mode: str = "scalar",
) -> dict[str, Any]:
    worker = Path(__file__).with_name("_worker.py")
    with tempfile.TemporaryDirectory(prefix="epbench-") as directory:
        workspace = Path(directory)
        submission = {"submission.py": source} if isinstance(source, bytes) else source
        for name, content in submission.items():
            workspace.joinpath(name).write_bytes(content)
        with subprocess.Popen(
            [sys.executable, "-I", "-B", str(worker), mode],
            cwd=workspace,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(os.name == "posix"),
        ) as process:
            try:
                process.communicate(json.dumps(inputs).encode("utf-8"), timeout=timeout)
            except subprocess.TimeoutExpired:
                return {"status": "timeout", "detail": f"Exceeded {timeout:g} seconds"}
            finally:
                # Reap ordinary child processes too; this is cleanup, not containment.
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif process.poll() is None:
                    process.kill()
                process.wait()
            if process.returncode:
                return {"status": "runtime_error", "detail": f"Python exited with code {process.returncode}"}
        try:
            limit = 2_000_000 if mode == "hall" else 4096
            with workspace.joinpath("result.json").open("rb") as result_file:
                data = result_file.read(limit + 1)
            if len(data) > limit:
                raise ValueError(f"Result exceeds {limit} bytes")
            result = json.loads(data)
            if not isinstance(result, dict) or result.get("status") not in (
                "ok", "runtime_error", "invalid_output",
            ):
                raise ValueError("Malformed worker result")
            if not isinstance(result.get("detail"), str):
                raise ValueError("Missing result detail")
            if result["status"] == "ok" and mode == "scalar":
                value = result.get("value")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("Result must be a finite scalar number")
            return result
        except (OSError, ValueError, OverflowError) as exc:
            return {"status": "invalid_output", "detail": f"Cannot read worker result: {exc}"}


def grade(
    task: str, solution_file: str | Path, *, timeout: float = TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Grade trusted Python; raise ValueError/OSError for invalid configuration."""
    if task not in TASKS:
        raise ValueError(f"Unknown task: {task}")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Timeout must be a positive finite number")
    path = Path(solution_file).resolve()
    if task == "hall-transport":
        if not path.is_dir():
            raise ValueError("hall-transport requires a directory containing physics.py and model.py")
        source = {}
        for name in ("physics.py", "model.py"):
            member = path / name
            if member.is_symlink() or not member.is_file():
                raise ValueError(f"Workspace requires a regular, non-symlink file: {name}")
            source[name] = member.read_bytes()
        results = []
        for index, inputs in enumerate(hall.cases(), start=1):
            outcome = _run_case(source, inputs, timeout, mode="hall")
            if outcome["status"] == "ok":
                outcome = hall.verify(inputs, outcome.get("value"))
            results.append({
                "case": f"case-{index:02d}", "kind": inputs["operation"],
                "passed": outcome["status"] == "passed", "status": outcome["status"],
                "relative_error": None, "detail": outcome["detail"],
                "diagnostics": outcome.get("diagnostics", {}),
            })
        return _report(task, results, timeout, hall.TOLERANCE)
    source = path.read_bytes()
    results = []
    for index, (inputs, expected) in enumerate(_cases(task), start=1):
        outcome = _run_case(source, inputs, timeout)
        relative_error = None
        if outcome["status"] == "ok":
            value = outcome["value"]
            passed = math.isclose(value, expected, rel_tol=REL_TOL, abs_tol=ABS_TOL[task])
            if expected != 0:
                error = abs(value - expected) / abs(expected)
                relative_error = error if math.isfinite(error) else None
            outcome = {
                "status": "passed" if passed else "mismatch",
                "detail": "Within tolerance" if passed else "Numerical / physical mismatch",
            }
        results.append({
            "case": f"case-{index:02d}", "passed": outcome["status"] == "passed",
            "status": outcome["status"], "relative_error": relative_error,
            "detail": outcome["detail"],
        })
    return _report(task, results, timeout, {"relative": REL_TOL, "absolute": ABS_TOL[task]})


def _report(task: str, results: list[dict[str, Any]], timeout: float, tolerance: dict) -> dict[str, Any]:
    passed_count = sum(case["passed"] for case in results)
    return {
        "schema_version": 1, "epbench_version": __version__, "task": task,
        "status": "passed" if passed_count == len(results) else "failed",
        "passed": passed_count, "total": len(results),
        "success_rate": passed_count / len(results),
        "tolerance": tolerance,
        "timeout_seconds": timeout, "cases": results, "warning": WARNING,
    }
