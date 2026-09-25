"""Author and replay fourteen inspectable workflow demonstrations. No model."""
import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile

from epagent.execution import preflight
from epagent.sft_data import digest, reviewed_examples, write_json
from epagent.tools import SYSTEM_PROMPT, ToolSession, changes, execute, parse_call, safe_path, snapshot

# id, family, signature, requirement, defective body, correction, shipped assertions, pattern
PLANS = [
 ('leap-calendar', 'gregorian-leap-year', 'leap(year)', 'Return whether a positive Gregorian year is leap.',
  '    return year % 4 == 0', '    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)',
  'assert F(1900) is False\nassert F(2000) is True\nassert F(2023) is False', 'test-first'),
 ('xml-attribute', 'xml-attribute-escaping', 'escape(text)', 'Escape XML &, <, > and both quotes using html.escape.',
  '    return text', '    import html\n    return html.escape(text, quote=True)',
  'assert F("<a&") == "&lt;a&amp;"\nassert F(\'"\') == "&quot;"', 'straight'),
 ('csv-field', 'quoted-csv-decoding', 'fields(line)', 'Parse one comma-separated CSV record, including quoted commas.',
  '    return line.split(",")', '    import csv\n    return next(csv.reader([line]))',
  'assert F(\'a,"b,c"\') == ["a", "b,c"]\nassert F("x,y") == ["x", "y"]', 'repair'),
 ('integer-bytes', 'signed-integer-serialization', 'encode(value)', 'Encode a signed integer as exactly two big-endian bytes.',
  '    return value.to_bytes(2, "little", signed=True)',
  '    return value.to_bytes(2, "big", signed=True)',
  'assert F(256) == b"\\x01\\x00"\nassert F(-2) == b"\\xff\\xfe"', 'stale'),
 ('polynomial', 'polynomial-evaluation', 'evaluate(coeffs, x)', 'Coefficients are in ascending power order; return the polynomial value.',
  '    return sum(coeffs)', '    return sum(c * x ** i for i, c in enumerate(coeffs))',
  'assert F([2, 3, 4], 2) == 24\nassert F([], 5) == 0', 'straight'),
 ('inverse-index', 'inverse-multimap', 'invert(mapping)', 'Map each value to its keys in insertion order.',
  '    return {v: k for k, v in mapping.items()}',
  '    out = {}\n    for key, value in mapping.items():\n        out.setdefault(value, []).append(key)\n    return out',
  'assert F({"a": 1, "b": 1}) == {1: ["a", "b"]}\nassert F({}) == {}', 'test-first'),
 ('interpolation', 'linear-interpolation', 'between(x, x0, y0, x1, y1)', 'Linearly interpolate; x0 and x1 differ.',
  '    return y0 + (y1 - y0) * x', '    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)',
  'assert F(3, 2, 10, 4, 20) == 15\nassert F(2, 2, 10, 4, 20) == 10', 'repair'),
 ('address-number', 'ipv4-integer-conversion', 'address(text)', 'Convert a valid dotted IPv4 address to its unsigned integer.',
  '    return sum(map(int, text.split(".")))',
  '    import ipaddress\n    return int(ipaddress.IPv4Address(text))',
  'assert F("1.0.0.0") == 16777216\nassert F("0.0.0.1") == 1', 'stale'),
 ('window-sums', 'sliding-window-sums', 'windows(values, width)', 'Return sums of consecutive full windows; width is positive.',
  '    return [sum(values)]',
  '    return [sum(values[i:i + width]) for i in range(len(values) - width + 1)]',
  'assert F([1, 2, 4], 2) == [3, 6]\nassert F([1], 2) == []', 'test-first'),
 ('insertion-index', 'lower-bound-search', 'position(values, item)', 'Sorted values: return the first insertion index, before equal items.',
  '    return len(values)', '    import bisect\n    return bisect.bisect_left(values, item)',
  'assert F([1, 3, 3], 3) == 1\nassert F([], 2) == 0', 'straight'),
 ('nested-copy', 'recursive-copy-independence', 'clone(rows)', 'Deep-copy nested lists so changing a clone does not alter its input.',
  '    return list(rows)', '    import copy\n    return copy.deepcopy(rows)',
  'x = [[1]]\ny = F(x)\ny[0].append(2)\nassert x == [[1]]\nassert F([]) == []', 'repair'),
 ('query-decode', 'url-query-unquoting', 'decode(text)', 'Decode percent escapes and plus-as-space in a URL query component.',
  '    return text', '    from urllib.parse import unquote_plus\n    return unquote_plus(text)',
  'assert F("a+b%21") == "a b!"\nassert F("x%2By") == "x+y"', 'unresolved'),
 ('json-pointer', 'json-pointer-token-decoding', 'tokens(pointer)', 'Decode a nonempty JSON Pointer into segments: ~1 is /, ~0 is ~.',
  '    return pointer[1:].split("/")',
  '    return [s.replace("~1", "/").replace("~0", "~") for s in pointer[1:].split("/")]',
  'assert F("/a~1b/~0") == ["a/b", "~"]\nassert F("/x") == ["x"]', 'straight'),
 ('greatest-divisor', 'euclidean-gcd', 'divisor(a, b)', 'Return nonnegative greatest common divisor of integers, including gcd(0,0)=0.',
  '    return min(a, b)', '    import math\n    return math.gcd(a, b)',
  'assert F(12, 8) == 4\nassert F(0, 0) == 0\nassert F(-6, 9) == 3', 'unresolved'),
]


def fixtures():
    cases = []
    for i, (ident, family, signature, requirement, bad, good, asserts, pattern) in enumerate(PLANS):
        source = ['logic.py', 'core/operation.py', 'lib/transform.py'][i % 3]
        header = 'def ' + signature + ':\n'
        starter, corrected = header + bad + '\n', header + good + '\n'
        check = (f'from {source[:-3].replace("/", ".")} import {signature.split("(")[0]} as F\n'
                 + asserts + f'\nprint("PASS {ident}")\n')
        files = {'README.md': requirement + f' Preserve {signature}. Fix {source}; keep checks.py '
                 'unchanged. Run checks.py and report the observed outcome.\n', source: starter,
                 'checks.py': check, 'notes.txt': 'Unrelated file; preserve.\n'}
        actions = []
        def add(tool, arguments, learn=True, **expect):
            actions.append(dict(tool=tool, arguments=arguments, learn=learn, expect=expect))
        if i % 3 == 1:
            add('list_files', {})
        add('read_file', {'path': 'README.md'}, False, content=files['README.md'])
        add('read_file', {'path': 'checks.py'}, False, content=check)
        test = {'code': "exec(open('checks.py').read())"}
        if pattern == 'test-first':
            add('run_python', test, status='python_error')
        add('read_file', {'path': source}, content=starter)
        # Both setup reads consume real version tokens; source is always v3.
        replacement = dict(path=source, version='v3', start_line=2, end_line=2, new_text=good)
        if pattern in ('repair', 'stale', 'unresolved'):
            # An authentic unsuccessful content change, retained only as history.
            partial = {
                'csv-field': '    return [line]',
                'integer-bytes': '    return value.to_bytes(2, "big")',
                'interpolation': '    return y0',
                'address-number': '    return int(text.split(".")[0])',
                'nested-copy': '    return rows[:]',
                'query-decode': '    return text.replace("+", " ")',
                'greatest-divisor': '    return abs(min(a, b))',
            }[ident]
            add('replace_lines', {**replacement, 'new_text': partial}, False, changed=True)
            if pattern == 'stale':
                add('replace_lines', replacement, False, error='ValueError')
            else:
                add('run_python', test, status='python_error')
            if pattern != 'unresolved':
                add('read_file', {'path': source}, content=header + partial + '\n')
                add('replace_lines', {**replacement, 'version': 'v4'}, changed=True)
        elif i % 2:
            add('edit_file', dict(path=source, old_text=bad, new_text=good), edited=source)
        else:
            add('replace_lines', replacement, changed=True)
        if pattern != 'unresolved':
            add('run_python', test, status='completed', stdout=f'PASS {ident}\n')
            summary = f'Preserved {signature} and repaired {source}. Ran checks.py; observed PASS {ident}.'
            final = corrected
        else:
            summary = f'Incomplete: checks.py failed with AssertionError. {source} is not repaired; no passing test observed.'
            final = header + partial + '\n'
        add('finish', {'summary': summary})
        cases.append(dict(id=ident, family=family, split='train' if i < 12 else 'valid', source=source,
                          files=files, actions=actions, budget_steps=12, pattern=pattern,
                          outcome='unresolved' if pattern == 'unresolved' else 'success',
                          final_files={**files, source: final}))
    return cases


def replay(cases, out):
    out.mkdir(parents=True, exist_ok=False)
    reviews, tools, transitions, lengths = [], {}, {}, {}
    for case in cases:
        with tempfile.TemporaryDirectory(prefix='epagent-demo-') as tmp:
            workspace = Path(tmp)
            for name, content in case['files'].items():
                path = safe_path(workspace, name); path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            preflight(workspace, [Path(__file__)])
            session = ToolSession(workspace)
            messages = [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content':
                f"Repair task development:{case['id']}. Start by inspecting the workspace. "
                'You have at most 12 tool turns and 300 seconds, including local model loading. '
                'Each Python run has at most 8 seconds. Use finish to submit your final work.'}]
            events, selected = [], []
            def emit(kind, data):
                events.append(dict(schema='epagent.episode.v1', episode_id=case['id'],
                                   sequence=len(events) + 1, event=kind, data=data))
            emit('episode_start', {'task_id': 'synthetic:' + case['id'], 'model': {'backend': 'scripted'},
                                   'provenance': 'Project-authored, no model-generated data'})
            assert len(case['actions']) <= 12
            for step, action in enumerate(case['actions'], 1):
                name, args = action['tool'], action['arguments']
                text = json.dumps({'tool': name, 'arguments': args})
                assert parse_call(text) == (name, args)
                emit('model_request', {'step': step, 'messages': json.loads(json.dumps(messages))})
                emit('assistant', {'step': step, 'text': text})
                emit('tool_call', {'step': step, 'tool': name, 'arguments': args})
                before = snapshot(workspace)
                try:
                    obs = execute(workspace, name, args, 8, 8192, session=session)
                except ValueError as exc:
                    obs = {'error': 'ValueError', 'detail': str(exc), 'changed': snapshot(workspace) != before}
                obs.pop('elapsed_seconds', None)
                for key in ('stdout', 'stderr'):
                    if key in obs:
                        for prefix in (str(workspace.resolve()), str(workspace)):
                            obs[key] = obs[key].replace(prefix + '/', '<workspace>/')
                for key, value in action['expect'].items():
                    assert obs.get(key) == value, (case['id'], step, key, obs)
                if name == 'run_python' and obs['status'] == 'python_error':
                    assert 'AssertionError' in obs['stderr']  # Not an infrastructure/import failure.
                if action['learn']:
                    assert 'error' not in obs
                    selected.append(step)
                emit('tool_result', {'step': step, 'observation': obs, 'patch': changes(before, snapshot(workspace))})
                messages += [{'role': 'assistant', 'content': text}, {'role': 'user', 'content': json.dumps(
                    {'tool_result': obs, 'steps_remaining': 12 - step})}]
            assert snapshot(workspace) == {n: s.encode() for n, s in case['final_files'].items()}
        target = out / (case['id'] + '.jsonl')
        target.write_text(''.join(json.dumps(e) + '\n' for e in events))
        reviews.append(dict(episode_id=case['id'], split=case['split'], family=case['family'],
            trace=target.name, trace_sha256=digest(target), origin='authored-synthetic-fixture',
            rights='Project-authored; no proprietary trajectories or benchmark references',
            review='Authored action plans inspected and replayed against real tools; expected observations, '
                   'preserved API and final bytes checked. Maintainer review pending.',
            selected_assistant_steps=selected, outcome=case['outcome'],
            excluded_steps=[i for i in range(1, len(case['actions']) + 1) if i not in selected],
            exclusion_reason='Setup README/test reads and deliberately unsuccessful edits remain context only'))
        tools.setdefault(case['split'], Counter()).update(case['actions'][i - 1]['tool'] for i in selected)
        names = [a['tool'] for a in case['actions']]
        transitions.setdefault(case['split'], Counter()).update(a + ' -> ' + b for a, b in zip(names, names[1:]))
        lengths[case['id']] = len(names)
    write_json(out / 'reviews.json', {'schema': 'epagent.sft-review.v1', 'episodes': reviews,
        'normalization': 'Only elapsed time omitted and temporary traceback path replaced by <workspace>/'})
    examples = reviewed_examples(out)
    result = {'targets': {k: dict(v) for k, v in tools.items()},
              'transitions_all_actions': {k: dict(v) for k, v in transitions.items()},
              'episode_lengths': lengths, 'examples': {k: len(v) for k, v in examples.items()},
              'model_inference': False, 'training': False}
    write_json(out / 'coverage.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cases = fixtures()
    write_json(args.out / 'fixtures.json', cases)
    print(json.dumps(replay(cases, args.out / 'trajectories')))
