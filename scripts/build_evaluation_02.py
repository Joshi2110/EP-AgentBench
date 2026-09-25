"""New held-out families, authored after the 7B training freeze. No generation."""
import argparse
import json
from pathlib import Path

from build_evaluation_01 import build, hidden_material_absent, validate
from epagent.sft_data import digest, write_json

# Requirements, starter, reference and visible/independent assertions are all inspectable.
# Only build(case)['files'] are exported to an agent workspace.
CASES = [
 ('reachable-nodes', 'directed-reachability', 'reachable(graph, start)',
  'Return a set of all nodes reachable from start, including start; missing keys have no outgoing edges.',
  '    return set(graph.get(start, []))',
  '    seen, pending = set(), [start]\n    while pending:\n        node = pending.pop()\n        if node not in seen:\n            seen.add(node)\n            pending.extend(graph.get(node, []))\n    return seen',
  ['assert F({1: [2], 2: [3]}, 1) == {1, 2, 3}', 'assert F({}, 9) == {9}'],
  ['assert F({1: [1]}, 1) == {1}', 'assert F({1: [2], 2: [1]}, 1) == {1, 2}',
   'assert F({1: [2, 3], 3: [4], 8: [9]}, 1) == {1, 2, 3, 4}']),
 ('tree-depth', 'binary-tree-height', 'height(tree)',
  'A tree is None or (value, left, right). Return height in nodes; an empty tree has height zero.',
  '    return 0 if tree is None else 1',
  '    return 0 if tree is None else 1 + max(height(tree[1]), height(tree[2]))',
  ['assert F(None) == 0', 'assert F((1, (2, None, None), None)) == 2'],
  ['assert F((0, None, None)) == 1', 'assert F((0, None, (1, None, (2, None, None)))) == 3',
   'assert F((0, (1, None, None), (2, None, None))) == 2']),
 ('prime-factors', 'prime-factorization', 'factors(n)',
  'For a positive integer, return prime factors in ascending order, with multiplicity. One gives [].',
  '    return [] if n == 1 else [n]',
  '    out, divisor = [], 2\n    while divisor * divisor <= n:\n        while n % divisor == 0:\n            out.append(divisor)\n            n //= divisor\n        divisor += 1\n    if n > 1:\n        out.append(n)\n    return out',
  ['assert F(12) == [2, 2, 3]', 'assert F(1) == []'],
  ['assert F(13) == [13]', 'assert F(49) == [7, 7]', 'assert F(30) == [2, 3, 5]']),
 ('sparse-product', 'sparse-vector-dot-product', 'dot(left, right)',
  'Sparse vectors map integer indices to numbers. Return their dot product; absent indices mean zero.',
  '    return sum(left.values()) * sum(right.values())',
  '    return sum(value * right.get(index, 0) for index, value in left.items())',
  ['assert F({0: 2, 2: 3}, {0: 4, 1: 5}) == 8', 'assert F({}, {0: 1}) == 0'],
  ['assert F({2: -3}, {2: 4}) == -12', 'assert F({1: 2}, {2: 3}) == 0',
   'assert F({1: 0, 3: 2}, {1: 9, 3: 5}) == 10']),
 ('varint-bytes', 'unsigned-leb128', 'encode(n)',
  'Encode a nonnegative integer as unsigned LEB128 bytes: low seven bits per byte, high bit set when more follow.',
  '    return bytes([n & 127])',
  '    out = []\n    while n >= 128:\n        out.append((n & 127) | 128)\n        n >>= 7\n    out.append(n)\n    return bytes(out)',
  ['assert F(128) == b"\\x80\\x01"', 'assert F(0) == b"\\x00"'],
  ['assert F(127) == b"\\x7f"', 'assert F(300) == b"\\xac\\x02"',
   'assert F(16384) == b"\\x80\\x80\\x01"']),
 ('wildcard-text', 'whole-string-wildcards', 'matches(text, pattern)',
  'Match the whole text: ? matches one character and * matches any sequence. Other characters are literal. Inputs contain letters, ? and * only.',
  '    return text == pattern',
  '    import fnmatch\n    return fnmatch.fnmatchcase(text, pattern)',
  ['assert F("abc", "a*c") is True', 'assert F("abc", "a?") is False'],
  ['assert F("", "*") is True', 'assert F("ab", "??") is True',
   'assert F("abc", "b*") is False']),
 ('recent-keys', 'lru-recency-update', 'touch(keys, key, capacity)',
  'Keys are unique, oldest first. Return a new LRU list after touching key, evicting oldest to positive capacity; do not mutate input.',
  '    return (keys + [key])[-capacity:]',
  '    return ([item for item in keys if item != key] + [key])[-capacity:]',
  ['assert F(["a", "b"], "a", 3) == ["b", "a"]', 'assert F([], "a", 1) == ["a"]'],
  ['assert F([1, 2], 3, 2) == [2, 3]', 'assert F([1, 2], 2, 2) == [1, 2]',
   'x = [1, 2]\nassert F(x, 1, 1) == [1]\nassert x == [1, 2]']),
 ('adler-checksum', 'adler32-checksum', 'checksum(data)',
  'Return the unsigned Adler-32 checksum of a bytes object, using the standard initial value of one.',
  '    return sum(data)', '    import zlib\n    return zlib.adler32(data)',
  ['assert F(b"") == 1', 'assert F(b"a") == 6422626'],
  ['assert F(b"abc") == 38600999', 'assert F(b"Wikipedia") == 300286872',
   'assert F(b"\\0") == 65537']),
 ('utc-clock', 'timezone-normalized-timestamp', 'stamp(text)',
  'Parse an ISO 8601 datetime with an explicit offset or Z. Return integer Unix seconds; supplied dates have whole seconds.',
  '    from datetime import datetime\n    return int(datetime.fromisoformat(text).replace(tzinfo=None).timestamp())',
  '    from datetime import datetime\n    return int(datetime.fromisoformat(text).timestamp())',
  ['assert F("1970-01-01T01:00:00+01:00") == 0', 'assert F("1970-01-01T00:00:00Z") == 0'],
  ['assert F("1970-01-01T00:00:00+02:00") == -7200',
   'assert F("1970-01-01T00:00:00-03:00") == 10800',
   'assert F("2000-01-01T00:00:00Z") == 946684800']),
 ('tab-columns', 'tab-stop-expansion', 'expand(text, size)',
  'Expand tabs to spaces at multiples of positive size, resetting column at newlines; preserve all other characters.',
  '    return text.replace("\\t", " " * size)', '    return text.expandtabs(size)',
  ['assert F("a\\tb", 4) == "a   b"', 'assert F("\\t", 2) == "  "'],
  ['assert F("abcd\\tx", 4) == "abcd    x"', 'assert F("a\\n\\tb", 3) == "a\\n   b"',
   'assert F("ab\\t\\tc", 4) == "ab      c"']),
]


def fixtures():
    rows = []
    for i, (ident, family, signature, requirement, bad, good, visible, extra) in enumerate(CASES):
        package = 'case_' + str(i)
        source = package + '/logic.py'
        prefix = 'def ' + signature + ':\n'
        rows.append(build(dict(id=ident, family=family, source=source, fn=signature.split('(')[0],
            requirement=requirement + f' Preserve the public signature {signature}.',
            starter=prefix + bad + '\n', reference=prefix + good + '\n', visible=visible,
            hidden=visible + extra, extra={package + '/label.py': 'def label():\n    return "keep"\n'},
            keep=(package + '.label', 'label', '"keep"'))))
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    freeze = root / 'data/epagent-sft-7b-v1/training-freeze.json'
    assert freeze.is_file(), 'Freeze training before authoring held-out cases'
    cases = fixtures()
    hidden_material_absent(cases)
    validation = validate(cases)
    args.out.mkdir(parents=True, exist_ok=False)
    write_json(args.out / 'fixtures.json', cases)
    write_json(args.out / 'validation.json', {'fixtures': validation,
        'fixtures_sha256': digest(args.out / 'fixtures.json'), 'training_freeze_sha256': digest(freeze),
        'model_inference_performed': False, 'hidden_material_absent_from_workspace': True})
    print(json.dumps({'fixtures': len(cases), 'offline_validation': 'passed'}))
