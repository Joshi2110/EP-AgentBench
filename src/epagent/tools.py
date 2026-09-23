"""Five workspace tools; model text is never passed to a shell."""

import difflib
import json
from pathlib import Path
import stat

from .execution import run_python

SYSTEM_PROMPT = '''You are EP-Agent, a scientific Python coding agent. Repair the supplied task.
You can access only the task workspace. Read README.md and the source, edit code,
and use Python to check your work. Do not seek external files, credentials,
reference solutions, graders, prior attempts, or the network.

Return exactly ONE JSON object per turn, without markdown fences or other text:
{"tool": "tool_name", "arguments": {...}}
Available tools:
list_files: {} -- list workspace files.
read_file: {"path": "README.md"} -- read a UTF-8 file (relative path).
edit_file: {"path": "physics.py", "old_text": "exact existing text", "new_text": "replacement"}
  Replace exactly one occurrence. To create a new file, use empty old_text.
run_python: {"code": "print(2 + 2)"} -- execute Python in the workspace; no shell,
  no network or subprocesses; Python standard library and local modules only.
finish: {"summary": "Changes made and checks actually observed"} -- submit and stop.
Tool results arrive as user messages. Errors consume a step; correct the call.
Do not claim checks passed unless you observed their output. Finish within budget.
'''

ARGUMENTS = {"list_files": set(), "read_file": {"path"},
             "edit_file": {"path", "old_text", "new_text"}, "run_python": {"code"},
             "finish": {"summary"}}


def parse_call(text):
    call = json.loads(text)
    if not isinstance(call, dict) or set(call) != {"tool", "arguments"}:
        raise ValueError("Return one JSON object with tool and arguments")
    name, args = call['tool'], call['arguments']
    if not isinstance(name, str) or name not in ARGUMENTS or not isinstance(args, dict):
        raise ValueError("Unknown tool or invalid arguments")
    if set(args) != ARGUMENTS[name] or any(not isinstance(v, str) for v in args.values()):
        raise ValueError(f"Arguments for {name} must be strings with keys {sorted(ARGUMENTS[name])}")
    return name, args


def safe_path(workspace, relative):
    p = Path(relative)
    if p.is_absolute() or not p.parts or '..' in p.parts:
        raise ValueError("Use a relative file path within the workspace")
    target = workspace / p
    if not target.resolve().is_relative_to(workspace.resolve()):
        raise ValueError("Path leaves the workspace")
    for member in (target, *target.parents):
        if member == workspace.parent:
            break
        if member.is_symlink():
            raise ValueError("Symlinks are not supported")
    if target.exists() and (not target.is_file() or target.stat().st_nlink != 1):
        raise ValueError("Expected a regular unlinked file")
    return target


def snapshot(workspace):
    result = {}
    # Bounded traversal, without following links or special files.
    pending = [workspace]
    count = total = 0
    while pending:
        for p in pending.pop().iterdir():
            count += 1
            if count > 128:
                raise ValueError("Workspace exceeds 128 entries")
            mode = p.lstat().st_mode
            if stat.S_ISDIR(mode):
                pending.append(p)
            elif stat.S_ISREG(mode) and p.stat().st_nlink == 1:
                total += p.stat().st_size
                if p.stat().st_size > 256_000 or total > 2_000_000:
                    raise ValueError("Workspace exceeds file/total byte limits")
                result[str(p.relative_to(workspace))] = p.read_bytes()
            else:
                raise ValueError("Workspace contains a link or special file")
    return result


def changes(before, after):
    patch = []
    for name in sorted(before.keys() | after.keys()):
        a, b = before.get(name, b''), after.get(name, b'')
        if a != b:
            patch.extend(difflib.unified_diff(a.decode(errors='replace').splitlines(True),
                         b.decode(errors='replace').splitlines(True), fromfile='before/'+name, tofile='after/'+name))
    return ''.join(patch)


def execute(workspace, name, args, seconds, output_bytes):
    if name == 'list_files':
        return {"files": sorted(snapshot(workspace))}
    if name == 'read_file':
        data = safe_path(workspace, args['path']).read_bytes()
        return {"content": data[:output_bytes].decode(errors='replace'), "truncated": len(data) > output_bytes}
    if name == 'edit_file':
        p = safe_path(workspace, args['path'])
        old, new = args['old_text'], args['new_text']
        if not old:
            if p.exists():
                raise ValueError("Empty old_text is only valid for a new file")
            content = new
        else:
            content = p.read_text()
            if content.count(old) != 1:
                raise ValueError("old_text must match exactly once")
            content = content.replace(old, new, 1)
        if len(content.encode()) > 256_000:
            raise ValueError("File exceeds 256000 bytes")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return {"edited": args['path']}
    if name == 'run_python':
        if len(args['code'].encode()) > 32768:
            raise ValueError("Python input exceeds 32768 bytes")
        return run_python(workspace, args['code'], seconds, output_bytes)
    return {"finished": True, "summary": args['summary']}
