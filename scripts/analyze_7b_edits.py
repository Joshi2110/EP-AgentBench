"""Reconstruct recorded edits and compile snapshots without executing agent code."""
import difflib
import hashlib
import json
from pathlib import Path
import re


def syntax(source):
    try:
        compile(source, 'cart.py', 'exec', dont_inherit=True)
        return {'valid': True}
    except SyntaxError as exc:
        return {'valid': False, 'error': type(exc).__name__, 'message': exc.msg,
                'line': exc.lineno, 'column': exc.offset, 'source_line': exc.text}


def signatures(source):
    # Declarations only: an invalid module does not expose callable APIs.
    return re.findall(r'^def ([^\n]+):$', source, re.MULTILINE)


def analyze(archive):
    folder = archive / 'attempts/replace-lines-7b-smoke'
    episode = next((folder / 'episodes').iterdir())
    events = [json.loads(s) for s in (episode / 'trajectory.jsonl').read_text().splitlines()]
    results = {e['data']['step']: e for e in events if e['event'] == 'tool_result'}
    requested = (episode / 'initial/README.md').read_text()
    source = (episode / 'initial/cart.py').read_text()
    observed, rows = None, []
    judgments = {
        3: 'Adds price-times-quantity arithmetic, but moves away from the required callable: '
           'renames cart_total(rows) and assumes dictionaries instead of the specified tuples. '
           'Leaves an unreachable old return. Not a valid repair.',
        5: 'Moves away: deletes the function definition and makes the entire module unimportable.',
        7: 'No repair progress: alters the docstring and duplicates an indented return; syntax remains invalid.',
        9: 'Removes a duplicate return, but makes no progress toward an importable required API.',
        11: 'Removes the leftover old return, but leaves no required function and invalid syntax.'}
    for event in events:
        if event['event'] != 'tool_call':
            continue
        call = event['data']; args = call['arguments']; step = call['step']
        result = results[step]
        if call['tool'] == 'read_file' and args['path'] == 'cart.py':
            observed = {'event': result['sequence'], 'source': result['data']['observation']['content'],
                        'version': result['data']['observation']['version']}
            assert observed['source'] == source
        if call['tool'] not in ['edit_file', 'replace_lines']:
            continue
        assert observed and observed['source'] == source
        before = source
        if call['tool'] == 'edit_file':
            assert before.count(args['old_text']) == 1
            start = before[:before.index(args['old_text'])].count('\n') + 1
            end = start  # This recorded call replaces the single function header.
            source = before.replace(args['old_text'], args['new_text'], 1)
        else:
            lines = before.splitlines(keepends=True)
            start, end = args['start_line'], args['end_line']
            replacement = args['new_text']
            if lines[end - 1].endswith('\n') and replacement and not replacement.endswith('\n'):
                replacement += '\n'
            source = ''.join(lines[:start - 1]) + replacement + ''.join(lines[end:])
            assert args['version'] == observed['version']
        # Track selected lines, not difflib's ambiguous alignment of duplicates.
        a, b = before.splitlines(keepends=True), source.splitlines(keepends=True)
        delta = len(b) - len(a)
        preserved = [{'before_line': n + 1, 'after_line': n + 1 if n < start - 1 else n + 1 + delta,
                      'text': a[n]} for n in range(len(a)) if n < start - 1 or n >= end]
        removed = [{'line': n + 1, 'text': a[n]} for n in range(start - 1, end)]
        added = [{'line': n + 1, 'text': b[n]} for n in range(start - 1, end + delta)]
        assert all(a[r['before_line'] - 1] == b[r['after_line'] - 1] for r in preserved)
        patch = ''.join(difflib.unified_diff(a, b, fromfile='before/cart.py', tofile='after/cart.py'))
        assert patch == result['data']['patch']
        rows.append({'step': step, 'call_event': event['sequence'], 'result_event': result['sequence'],
            'observed': dict(observed), 'task_requirement': requested, 'tool': call['tool'], 'arguments': args,
            'generated_replacement': args['new_text'], 'before': before, 'after': source,
            'preserved_lines': preserved, 'removed_lines': removed, 'added_lines': added,
            'syntax_before': syntax(before), 'syntax_after': syntax(source),
            'declarations_before': signatures(before), 'declarations_after': signatures(source),
            'required_cart_total_declared': 'cart_total(rows)' in signatures(source),
            'direction': judgments[step], 'after_sha256': hashlib.sha256(source.encode()).hexdigest()})
    assert source.encode() == (episode / 'workspace/cart.py').read_bytes()
    return {'edits': rows, 'first_syntax_breaking_step': next(r['step'] for r in rows if not r['syntax_after']['valid']),
            'method': 'Exact recorded replacements, checked against every recorded patch and final bytes; compile only, no execution or regrading.',
            'discoverability': {'listing_event': 29, 'files': ['README.md', 'cart.py', 'checks.py'],
                'system_explicitly_requested_readme_read': True, 'readme_reads': 0, 'test_reads': 0,
                'limitation': 'Files were accessible and discoverable. The prompt did not explicitly require reading tests before editing. '
                              'The trajectory establishes omission, not the model\'s intent or an isolated causal explanation.'}}


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    archive = root / 'artifacts/ep-agent/7b-development-smoke'
    (archive / 'edit-analysis.json').write_text(json.dumps(analyze(archive), indent=2) + '\n')
