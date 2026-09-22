"""Subprocess entry point; receives only the current case on stdin."""

import json
import math
from pathlib import Path
import runpy
import sys


def main() -> None:
    result_path = Path.cwd() / "result.json"
    inputs = json.load(sys.stdin)
    mode = sys.argv[1]
    try:
        if mode == "hall":
            # Only submitted modules run here; all verification stays in the parent.
            sys.path.insert(0, str(Path.cwd()))
            if inputs["operation"] == "mobility":
                from physics import cross_field_mobility
                value = [cross_field_mobility(b, inputs["nu_per_s"]) for b in inputs["b_t"]]
            else:
                from model import Parameters, solve
                value = [solve(Parameters(**parameters)) for parameters in inputs["parameters"]]
        else:
            module = runpy.run_path("submission.py", run_name="epbench_submission")
            solve = module.get("solve")
            if not callable(solve):
                raise TypeError("Submission must define a callable solve")
            value = solve(**inputs)
    except (Exception, SystemExit) as exc:
        result = {"status": "runtime_error", "detail": f"{type(exc).__name__}: {exc}"[:500]}
    else:
        try:
            if mode == "scalar":
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("solve must return a finite Python int or float (not bool)")
                value = float(value)
            json.dumps(value, allow_nan=False)
            result = {"status": "ok", "detail": "", "value": value}
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            result = {"status": "invalid_output", "detail": str(exc)[:500]}
    result_path.write_text(json.dumps(result, allow_nan=False, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
