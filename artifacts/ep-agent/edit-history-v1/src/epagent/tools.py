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

Return one JSON object with exactly two keys: tool (a name below) and arguments
(an object). Bare JSON or one complete Markdown fence labelled json or unlabelled
is accepted. No text outside the object/fence and no additional blocks.
All listed arguments are required strings; additional keys are not allowed.
Available tools and argument fields:
list_files: no arguments -- list workspace files.
read_file: path -- read a UTF-8 file at a relative workspace path.
edit_file: path, old_text, new_text -- replace exactly one occurrence of old_text
  with new_text. Copy old_text from an observed file; choose new_text for your
  intended edit. Empty old_text creates a new file only.
run_python: code -- execute your diagnostic Python in the workspace; no shell,
  network or subprocesses; Python standard library and local modules only.
finish: summary -- describe changes and checks actually observed, submit and stop.
Tool results arrive as user messages. Errors consume a step; correct the call.
Use observations to decide your next action. Do not invent file contents or claim
checks passed without observing their output. Finish within budget.
'''

ARGUMENTS = {"list_files": set(), "read_file": {"path"},
             "edit_file": {"path", "old_text", "new_text"}, "run_python": {"code"},
             "finish": {"summary"}}


FORMAT_HELP = ('Return one JSON object with exactly tool and arguments, bare or inside '
               'one complete ```json or unlabelled ``` fence, with no outside text.')


class CallError(ValueError):
    """An agent-facing protocol error, without internal execution details."""
    def __init__(self, category, problem):
        self.category = category
        super().__init__(problem + ' ' + FORMAT_HELP)


def decode_call(text):
    """Decode the entire permitted envelope; never extract a JSON substring."""
    text = text.strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if (len(lines) < 3 or lines[0].strip() not in ('```', '```json')
                or lines[-1].strip() != '```'
                or any(line.strip().startswith('```') for line in lines[1:-1])):
            raise CallError('invalid_wrapper', 'Use one complete fence with only an optional json label; '
                            'multiple/incomplete blocks or text outside the fence are not accepted.')
        text = '\n'.join(lines[1:-1])

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CallError('schema_violation', 'Duplicate JSON keys are not allowed.')
            result[key] = value
        return result

    def invalid_constant(value):
        raise CallError('json_syntax', 'Non-finite constants are not valid JSON.')

    try:
        return json.loads(text, object_pairs_hook=unique_keys, parse_constant=invalid_constant)
    except json.JSONDecodeError as exc:
        raise CallError('json_syntax', f'Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}.') from exc


def parse_call(text):
    call = decode_call(text)
    if not isinstance(call, dict):
        raise CallError('schema_violation', 'The top-level JSON value must be an object.')
    if 'tool' not in call:
        raise CallError('invalid_tool', 'Missing tool name. Allowed tools: ' + ', '.join(ARGUMENTS) + '.')
    name = call['tool']
    if not isinstance(name, str) or name not in ARGUMENTS:
        raise CallError('invalid_tool', 'Unknown or non-string tool name. Allowed tools: ' + ', '.join(ARGUMENTS) + '.')
    if 'arguments' not in call:
        raise CallError('missing_arguments', 'Missing arguments object; use an empty object for list_files.')
    if set(call) != {'tool', 'arguments'}:
        raise CallError('schema_violation', 'Extra top-level keys are not allowed.')
    args = call['arguments']
    if not isinstance(args, dict):
        raise CallError('schema_violation', 'arguments must be a JSON object.')
    missing = ARGUMENTS[name] - args.keys()
    if missing:
        raise CallError('missing_arguments', f'Missing required arguments for {name}: ' + ', '.join(sorted(missing)) + '.')
    if set(args) != ARGUMENTS[name] or any(not isinstance(v, str) for v in args.values()):
        raise CallError('schema_violation', f'Arguments for {name} must be strings with exactly these keys: '
                        + ', '.join(sorted(ARGUMENTS[name])) + '.')
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
