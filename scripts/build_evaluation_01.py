"""Author and validate the Evaluation 01 fixtures offline. No model, no network."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from epagent.execution import preflight, run_python
from epagent.tools import safe_path
from epagent.verification import discover_tests

VISIBLE_TEST = 'checks.py'          # the existing development grader reads this name
HIDDEN_MARKER = 'INDEPENDENT OK'

CASES = [
 dict(id='interval-merge', family='interval-merging', source='ranges/merge.py', fn='merge_spans',
      extra={'ranges/labels.py': 'def unit():\n    return "span"\n'},
      keep=('ranges.labels', 'unit', '"span"'),
      requirement='Merge overlapping or touching closed integer spans and return them sorted by start. '
                  'Touching spans such as (1, 2) and (3, 4) are separate; (1, 3) and (3, 5) merge.',
      starter='def merge_spans(spans):\n    return sorted(spans)\n',
      reference=('def merge_spans(spans):\n'
                 '    merged = []\n'
                 '    for start, end in sorted(spans):\n'
                 '        if merged and start <= merged[-1][1]:\n'
                 '            merged[-1] = (merged[-1][0], max(merged[-1][1], end))\n'
                 '        else:\n'
                 '            merged.append((start, end))\n'
                 '    return merged\n'),
      visible=['assert F([(1, 3), (2, 5)]) == [(1, 5)]',
               'assert F([]) == []'],
      hidden=['assert F([(1, 3), (2, 5)]) == [(1, 5)]',
              'assert F([]) == []',
              'assert F([(1, 2), (3, 4)]) == [(1, 2), (3, 4)]',
              'assert F([(5, 6), (1, 2)]) == [(1, 2), (5, 6)]',
              'assert F([(1, 10), (2, 3)]) == [(1, 10)]']),

 dict(id='roman-numeral', family='roman-numeral-encoding', source='numerals/convert.py', fn='to_roman',
      extra={'numerals/meta.py': 'def scheme():\n    return "roman"\n'},
      keep=('numerals.meta', 'scheme', '"roman"'),
      requirement='Convert an integer from 1 to 3999 into a Roman numeral, using the subtractive forms '
                  'IV, IX, XL, XC, CD and CM where they apply.',
      starter=('VALUES = [(1000, "M"), (500, "D"), (100, "C"), (50, "L"), (10, "X"), (5, "V"), (1, "I")]\n\n'
               'def to_roman(number):\n'
               '    out = ""\n'
               '    for value, sign in VALUES:\n'
               '        while number >= value:\n'
               '            out += sign\n'
               '            number -= value\n'
               '    return out\n'),
      reference=('VALUES = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),\n'
                 '          (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]\n\n'
                 'def to_roman(number):\n'
                 '    out = ""\n'
                 '    for value, sign in VALUES:\n'
                 '        while number >= value:\n'
                 '            out += sign\n'
                 '            number -= value\n'
                 '    return out\n'),
      visible=['assert F(4) == "IV"', 'assert F(3) == "III"'],
      hidden=['assert F(4) == "IV"', 'assert F(3) == "III"', 'assert F(9) == "IX"',
              'assert F(1994) == "MCMXCIV"', 'assert F(40) == "XL"', 'assert F(3999) == "MMMCMXCIX"']),

 dict(id='bracket-balance', family='bracket-matching', source='syntax/brackets.py', fn='is_balanced',
      extra={'syntax/tokens.py': 'def opener():\n    return "("\n'},
      keep=('syntax.tokens', 'opener', '"("'),
      requirement='Report whether round, square and curly brackets in the text are balanced and correctly '
                  'nested. Other characters are ignored.',
      starter=('PAIRS = {")": "(", "]": "[", "}": "{"}\n\n'
               'def is_balanced(text):\n'
               '    return len([c for c in text if c in "([{"]) == len([c for c in text if c in ")]}"])\n'),
      reference=('PAIRS = {")": "(", "]": "[", "}": "{"}\n\n'
                 'def is_balanced(text):\n'
                 '    stack = []\n'
                 '    for char in text:\n'
                 '        if char in "([{":\n'
                 '            stack.append(char)\n'
                 '        elif char in PAIRS:\n'
                 '            if not stack or stack.pop() != PAIRS[char]:\n'
                 '                return False\n'
                 '    return not stack\n'),
      visible=['assert F("(a[b]{c})") is True', 'assert F(")(") is False'],
      hidden=['assert F("(a[b]{c})") is True', 'assert F(")(") is False', 'assert F("(") is False',
              'assert F("([)]") is False', 'assert F("") is True', 'assert F("no brackets") is True']),

 dict(id='run-length', family='run-length-encoding', source='codecs_local/rle.py', fn='encode_runs',
      extra={'codecs_local/name.py': 'def codec():\n    return "rle"\n'},
      keep=('codecs_local.name', 'codec', '"rle"'),
      requirement='Compress a sequence into (value, count) pairs, one pair per run of consecutive equal '
                  'values, preserving order.',
      starter='def encode_runs(items):\n    return [(item, 1) for item in items]\n',
      reference=('def encode_runs(items):\n'
                 '    runs = []\n'
                 '    for item in items:\n'
                 '        if runs and runs[-1][0] == item:\n'
                 '            runs[-1] = (item, runs[-1][1] + 1)\n'
                 '        else:\n'
                 '            runs.append((item, 1))\n'
                 '    return runs\n'),
      visible=['assert F(["a", "a", "b"]) == [("a", 2), ("b", 1)]', 'assert F([]) == []'],
      hidden=['assert F(["a", "a", "b"]) == [("a", 2), ("b", 1)]', 'assert F([]) == []',
              'assert F([1]) == [(1, 1)]', 'assert F([1, 2, 1]) == [(1, 1), (2, 1), (1, 1)]',
              'assert F([7, 7, 7, 7]) == [(7, 4)]']),

 dict(id='caesar-shift', family='alphabet-rotation', source='cipher/shift.py', fn='shift_letters',
      extra={'cipher/alphabet.py': 'def size():\n    return 26\n'},
      keep=('cipher.alphabet', 'size', '26'),
      requirement='Rotate ASCII letters forward by a given amount, wrapping within their own case. '
                  'Characters that are not ASCII letters are returned unchanged.',
      starter=('def shift_letters(text, amount):\n'
               '    return "".join(chr(ord(c) + amount) for c in text)\n'),
      reference=('def shift_letters(text, amount):\n'
                 '    out = []\n'
                 '    for char in text:\n'
                 '        if "a" <= char <= "z":\n'
                 '            out.append(chr((ord(char) - 97 + amount) % 26 + 97))\n'
                 '        elif "A" <= char <= "Z":\n'
                 '            out.append(chr((ord(char) - 65 + amount) % 26 + 65))\n'
                 '        else:\n'
                 '            out.append(char)\n'
                 '    return "".join(out)\n'),
      visible=['assert F("xyz", 3) == "abc"', 'assert F("", 3) == ""'],
      hidden=['assert F("xyz", 3) == "abc"', 'assert F("", 3) == ""', 'assert F("abc", 1) == "bcd"',
              'assert F("Hello, World!", 1) == "Ifmmp, Xpsme!"', 'assert F("abc", 0) == "abc"']),

 dict(id='matrix-transpose', family='grid-transposition', source='grids/matrix.py', fn='transpose',
      extra={'grids/shape.py': 'def kind():\n    return "grid"\n'},
      keep=('grids.shape', 'kind', '"grid"'),
      requirement='Return the transpose of a rectangular grid given as a list of equal-length rows, as a '
                  'list of lists. An empty grid transposes to an empty list.',
      starter='def transpose(rows):\n    return [list(row) for row in rows]\n',
      reference='def transpose(rows):\n    return [list(column) for column in zip(*rows)]\n',
      visible=['assert F([[1, 2], [3, 4]]) == [[1, 3], [2, 4]]', 'assert F([]) == []'],
      hidden=['assert F([[1, 2], [3, 4]]) == [[1, 3], [2, 4]]', 'assert F([]) == []',
              'assert F([[1, 2, 3]]) == [[1], [2], [3]]', 'assert F([[1], [2], [3]]) == [[1, 2, 3]]',
              'assert F([[1, 2], [3, 4], [5, 6]]) == [[1, 3, 5], [2, 4, 6]]']),

 dict(id='banker-rounding', family='half-even-rounding', source='money/rounding.py', fn='round_cents',
      extra={'money/currency.py': 'def places():\n    return 2\n'},
      keep=('money.currency', 'places', '2'),
      requirement='Round a decimal string to two places using round-half-to-even, returning a string with '
                  'exactly two decimal places. Exact halves go to the even digit.',
      starter=('def round_cents(text):\n'
               '    return "%.2f" % (int(float(text) * 1000 + 5) / 1000)\n'),
      reference=('from decimal import Decimal, ROUND_HALF_EVEN\n\n'
                 'def round_cents(text):\n'
                 '    return str(Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))\n'),
      visible=['assert F("1.005") == "1.00"', 'assert F("2.341") == "2.34"'],
      hidden=['assert F("1.005") == "1.00"', 'assert F("2.341") == "2.34"', 'assert F("1.015") == "1.02"',
              'assert F("2.675") == "2.68"', 'assert F("-1.005") == "-1.00"', 'assert F("0.125") == "0.12"']),

 dict(id='path-normalize', family='path-normalisation', source='fsutil/paths.py', fn='normalize',
      extra={'fsutil/sep.py': 'def separator():\n    return "/"\n'},
      keep=('fsutil.sep', 'separator', '"/"'),
      requirement='Normalize a relative POSIX path by collapsing repeated separators, dropping "." '
                  'segments and resolving ".." against the preceding segment. Leading ".." segments that '
                  'cannot be resolved are kept. An empty result is ".".',
      starter=('def normalize(path):\n'
               '    return "/".join(part for part in path.split("/") if part)\n'),
      reference=('def normalize(path):\n'
                 '    parts = []\n'
                 '    for part in path.split("/"):\n'
                 '        if not part or part == ".":\n'
                 '            continue\n'
                 '        if part == ".." and parts and parts[-1] != "..":\n'
                 '            parts.pop()\n'
                 '        else:\n'
                 '            parts.append(part)\n'
                 '    return "/".join(parts) or "."\n'),
      visible=['assert F("a//b") == "a/b"', 'assert F("a/./b") == "a/b"'],
      hidden=['assert F("a//b") == "a/b"', 'assert F("a/./b") == "a/b"', 'assert F("a/b/../c") == "a/c"',
              'assert F("../a") == "../a"', 'assert F("a/..") == "."', 'assert F("") == "."']),

 dict(id='histogram-buckets', family='half-open-bucketing', source='stats/buckets.py', fn='bucket_counts',
      extra={'stats/edge.py': 'def closed():\n    return False\n'},
      keep=('stats.edge', 'closed', 'False'),
      requirement='Count values into half-open buckets given ascending edges: bucket i holds values with '
                  'edges[i] <= value < edges[i+1]. Values outside the edge range are not counted. Return '
                  'one count per bucket.',
      starter=('def bucket_counts(values, edges):\n'
               '    return [len([v for v in values if edges[i] <= v <= edges[i + 1]])\n'
               '            for i in range(len(edges) - 1)]\n'),
      reference=('def bucket_counts(values, edges):\n'
                 '    return [len([v for v in values if edges[i] <= v < edges[i + 1]])\n'
                 '            for i in range(len(edges) - 1)]\n'),
      visible=['assert F([4], [0, 4, 8]) == [0, 1]', 'assert F([], [0, 4]) == [0]'],
      hidden=['assert F([4], [0, 4, 8]) == [0, 1]', 'assert F([], [0, 4]) == [0]',
              'assert F([1, 5], [0, 4, 8]) == [1, 1]', 'assert F([8], [0, 4, 8]) == [0, 0]',
              'assert F([-1, 9], [0, 4, 8]) == [0, 0]', 'assert F([0, 0], [0, 4]) == [2]']),

 dict(id='retry-backoff', family='capped-exponential-backoff', source='net/backoff.py', fn='delays',
      extra={'net/policy.py': 'def strategy():\n    return "exponential"\n'},
      keep=('net.policy', 'strategy', '"exponential"'),
      requirement='Return the delay for each attempt as base doubled per attempt, never exceeding the cap. '
                  'Attempt zero waits base seconds. Zero attempts produce an empty list.',
      starter='def delays(attempts, base, cap):\n    return [base * 2 ** i for i in range(attempts)]\n',
      reference='def delays(attempts, base, cap):\n    return [min(base * 2 ** i, cap) for i in range(attempts)]\n',
      visible=['assert F(5, 1, 4) == [1, 2, 4, 4, 4]', 'assert F(0, 1, 100) == []'],
      hidden=['assert F(5, 1, 4) == [1, 2, 4, 4, 4]', 'assert F(0, 1, 100) == []',
              'assert F(3, 1, 100) == [1, 2, 4]', 'assert F(3, 10, 15) == [10, 15, 15]',
              'assert F(1, 7, 7) == [7]']),
]


def module(path):
    return path[:-3].replace('/', '.')


def program(case, body, marker):
    module_path, keep_module, keep_fn, keep_value = module(case['source']), *case['keep']
    lines = [f'from {module_path} import {case["fn"]} as F',
             f'from {keep_module} import {keep_fn}']
    lines += body
    lines.append(f'assert {keep_fn}() == {keep_value}')
    lines.append(f'print({marker!r})')
    return '\n'.join(lines) + '\n'


def build(case):
    files = {'README.md': case['requirement'] + '\nRepair ' + case['fn'] + ' in ' + case['source']
             + '. Keep the other modules and ' + VISIBLE_TEST + ' unchanged. Read the source, make the '
               'change, run ' + VISIBLE_TEST + ' with the Python tool and report only what you observed.\n',
             case['source']: case['starter'], **case['extra'],
             VISIBLE_TEST: program(case, case['visible'], 'PASS ' + case['id'])}
    return {'id': case['id'], 'family': case['family'], 'source': case['source'],
            'function': case['fn'], 'pass_marker': 'PASS ' + case['id'], 'files': files,
            'independent_test': program(case, case['hidden'], HIDDEN_MARKER),
            'independent_marker': HIDDEN_MARKER,
            'reference_source': case['reference'],
            'visible_assertions': len(case['visible']), 'independent_assertions': len(case['hidden'])}


def run_suite(files, source_text, source_path, test_source, seconds=8):
    with tempfile.TemporaryDirectory(prefix='epagent-eval01-') as tmp:
        workspace = Path(tmp)
        for name, content in files.items():
            path = safe_path(workspace, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        safe_path(workspace, source_path).write_text(source_text)
        return run_python(workspace, test_source, seconds, 8192)


def validate(fixtures):
    report = []
    for fixture in fixtures:
        files, source = fixture['files'], fixture['source']
        visible, hidden = files[VISIBLE_TEST], fixture['independent_test']
        starter, reference = files[source], fixture['reference_source']
        assert visible != hidden, fixture['id']
        checks = {
            'starter_fails_independent': run_suite(files, starter, source, hidden),
            'starter_fails_visible': run_suite(files, starter, source, visible),
            'reference_passes_independent': run_suite(files, reference, source, hidden),
            'reference_passes_visible': run_suite(files, reference, source, visible)}
        for name, result in checks.items():
            expected_pass = name.startswith('reference')
            marker = (fixture['independent_marker'] if name.endswith('independent')
                      else fixture['pass_marker'])
            ok = result['status'] == 'completed' and marker in result['stdout'].splitlines()
            assert ok == expected_pass, (fixture['id'], name, result)
            if not expected_pass:
                assert 'AssertionError' in result['stderr'], (fixture['id'], name, result)
        only_hidden = [line for line in hidden.splitlines() if line not in visible.splitlines()]
        report.append({
            'id': fixture['id'], 'family': fixture['family'], 'source': source,
            'files': sorted(files), 'workspace_files': len(files),
            'discovered_visible_tests': discover_tests(files),
            'visible_assertions': fixture['visible_assertions'],
            'independent_assertions': fixture['independent_assertions'],
            'assertions_only_in_independent': len([l for l in only_hidden if l.startswith('assert F')]),
            'visible_equals_independent': False,
            'starter_fails_independent': True, 'starter_fails_visible': True,
            'reference_passes_independent': True, 'reference_passes_visible': True,
            'starter_independent_stderr_tail':
                checks['starter_fails_independent']['stderr'].strip().splitlines()[-1]})
    return report


def hidden_material_absent(fixtures):
    """No exported workspace file may contain a hidden test or a reference repair."""
    for fixture in fixtures:
        blob = '\n'.join(fixture['files'].values())
        for secret in (fixture['independent_test'], fixture['reference_source'],
                       fixture['independent_marker']):
            assert secret not in blob, fixture['id']
        for line in fixture['independent_test'].splitlines():
            if line.startswith('assert F') and line not in fixture['files'][VISIBLE_TEST]:
                assert line not in blob, (fixture['id'], line)
    return True


def sandbox_isolation(fixtures, repository):
    """The agent's Python tool must not read the fixture file holding hidden material."""
    target = repository / 'data/epagent-evaluation-01/fixtures.json'
    with tempfile.TemporaryDirectory(prefix='epagent-eval01-probe-') as tmp:
        workspace = Path(tmp)
        for name, content in fixtures[0]['files'].items():
            path = safe_path(workspace, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        boundary = preflight(workspace, [target])
        probe = run_python(workspace, f'open({str(target)!r}).read()', 8, 8192)
    return {'preflight': boundary, 'direct_read_status': probe['status'],
            'direct_read_blocked': probe['status'] != 'completed',
            'stderr_tail': probe['stderr'].strip().splitlines()[-1] if probe['stderr'] else ''}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    fixtures = [build(case) for case in CASES]
    assert len({f['id'] for f in fixtures}) == len({f['family'] for f in fixtures}) == 10
    assert hidden_material_absent(fixtures)
    validation = validate(fixtures)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / 'fixtures.json'
    path.write_text(json.dumps(fixtures, indent=2) + '\n')
    # Probe the real committed file, so the check covers the bytes an agent would want.
    isolation = sandbox_isolation(fixtures, repository)
    (args.out / 'validation.json').write_text(json.dumps({
        'schema': 'epagent.evaluation-01-validation.v1',
        'method': 'Offline scripted execution in the existing bounded runner. No model, no network.',
        'fixtures': validation, 'sandbox_isolation': isolation,
        'hidden_material_absent_from_workspace': True,
        'fixtures_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'model_inference_performed': False}, indent=2) + '\n')
    print(json.dumps({'fixtures': len(fixtures),
                      'fixtures_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'sandbox_read_blocked': isolation['direct_read_blocked']}))


if __name__ == '__main__':
    main()
