"""Evidence attribution for recorded agent commands (Experiment 02 primary outcome)."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

VERDICT = re.compile(r"(?m)^\s*EPBENCH_CHECK\s+(\S+)\s+(PASS|FAIL)\s*$")
SHELL = re.compile(r"""^\s*\S*\b(?:sh|bash|zsh|dash)\b\s+-[a-zA-Z]*c\s+(['"])(?P<body>.*)\1\s*$""", re.S)
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
NESTED = re.compile(r"""\b(?:sh|bash|zsh|dash)\b\s+-[a-zA-Z]*c\b""")
TRUNCATED = re.compile(r"\[\s*(?:output\s+)?truncated|\.\.\.\s*truncated", re.I)
SEPARATORS = ("&&", "||", ";", "|", "\n")


def _script(command: str) -> str | None:
    """Unwrap one level of `sh -c "..."`; return None when that cannot be done safely."""
    match = SHELL.match(command)
    if not match:
        return command if command.strip() else None
    body = match.group("body")
    # A nested shell invocation cannot be attributed safely; report ambiguity instead.
    return None if NESTED.search(body) else body


def _segments(script: str) -> list[str] | None:
    """Split a script into top-level commands, skipping quotes and heredoc bodies."""
    parts, current, i, n = [], [], 0, len(script)
    quote = None
    pending: list[str] = []
    while i < n:
        char = script[i]
        if quote:
            if char == quote:
                quote = None
            current.append(char)
            i += 1
            continue
        if char in "'\"":
            quote = char
            current.append(char)
            i += 1
            continue
        if char == "\\" and i + 1 < n:
            current.extend(script[i:i + 2])
            i += 2
            continue
        heredoc = HEREDOC.match(script, i)
        if heredoc:
            pending.append(heredoc.group(2))
            current.append(heredoc.group(0))
            i = heredoc.end()
            continue
        if char == "\n" and pending:
            # Consume heredoc bodies before treating newlines as separators again.
            end = script.find(f"\n{pending[0]}\n", i)
            terminator = script.find(f"\n{pending[0]}", i)
            if end == -1 and (terminator == -1 or not script[terminator:].rstrip().endswith(pending[0])):
                return None
            stop = end if end != -1 else terminator
            i = stop + len(pending.pop(0)) + 1
            continue
        for separator in SEPARATORS:
            if script.startswith(separator, i):
                parts.append("".join(current))
                current = []
                i += len(separator)
                break
        else:
            current.append(char)
            i += 1
    if quote or pending:
        return None
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def classify(command: str, output: str | None, exit_code: Any = None) -> dict:
    """Attribute one recorded command's check outcome. Never guesses."""
    text = output or ""
    verdicts = VERDICT.findall(text)
    script = _script(command or "")
    segments = _segments(script) if script is not None else None
    # Fall back to the raw command so an unparseable check is still counted as attempted.
    has_assert = bool(re.search(r"\bassert\b", script if script is not None else (command or "")))
    checks = bool(verdicts) or has_assert
    if not checks:
        return {"checks": False, "attribution": "none", "verdicts": 0}
    if verdicts:
        if TRUNCATED.search(text):
            return {"checks": True, "attribution": "ambiguous", "verdicts": len(verdicts)}
        return {"checks": True, "attribution": "verdict", "verdicts": len(verdicts)}
    if segments is None:
        return {"checks": True, "attribution": "ambiguous", "verdicts": 0}
    if len(segments) == 1:
        return {"checks": True, "attribution": "single_program", "verdicts": 0}
    return {"checks": True, "attribution": "masked", "verdicts": 0}


def audit(trace: Path) -> dict:
    """Per-attempt evidence attribution. rate is None when nothing was attempted."""
    commands = []
    for line in Path(trace).read_text().splitlines():
        try:
            event = (json.loads(line) or {}).get("event") or {}
        except ValueError:
            continue
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        if item.get("type") != "command_execution" or item.get("exit_code") is None:
            continue
        result = classify(item.get("command", ""), item.get("aggregated_output"), item["exit_code"])
        result["id"] = item.get("id")
        commands.append(result)
    attempted = [c for c in commands if c["checks"]]
    counts = {name: sum(1 for c in attempted if c["attribution"] == name)
              for name in ("verdict", "single_program", "masked", "ambiguous")}
    attributable = counts["verdict"] + counts["single_program"]
    return {
        "attempted_checks": len(attempted),
        "attributable": attributable,
        "masked": counts["masked"],
        "ambiguous": counts["ambiguous"],
        "verdict_lines": sum(c["verdicts"] for c in commands),
        # Undefined, not perfect, when the agent attempted no checks at all.
        "rate": attributable / len(attempted) if attempted else None,
        "commands": commands,
    }
