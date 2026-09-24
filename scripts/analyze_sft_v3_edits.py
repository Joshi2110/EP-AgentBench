"""Read-only edit forensics. No scorer, model, tool execution or workspace mutation."""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import statistics

from archive_sft_v2 import sha, read, lines, save


def parseable(text):
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False


def minimal_extensions(source, old):
    """Enumerate shortest source-context extensions around EACH matching occurrence.

    Minimum means fewest added characters, not inferred intent or semantic repair.
    Keep all ties; never silently choose between occurrences.
    """
    starts = [i for i in range(len(source)) if source.startswith(old, i)]
    result = []
    for start in starts:
        end = start + len(old)
        for extra in range(1, len(source) + 1):
            candidates = []
            for left in range(extra + 1):
                right = extra - left
                if start < left or end + right > len(source):
                    continue
                candidate = source[start-left:end+right]
                if source.count(candidate) == 1:
                    candidates.append({'occurrence_start': start, 'start': start-left,
                        'end': end+right, 'added_characters': extra, 'old_text': candidate})
            if candidates:
                result.extend(candidates)
                break
    return result


def classify(source, old, correct_file):
    if not correct_file:
        return 'wrong_file'
    if source.count(old) > 1:
        return 'duplicated_span'
    if source.count(old) == 1:
        return 'other'
    if [s.lstrip(' \t') for s in source.splitlines(True)] == [s.lstrip(' \t') for s in old.splitlines(True)]:
        return 'indentation'
    if old.replace('"', "'") == source:
        return 'quoting'
    if ''.join(source.split()) == ''.join(old.split()):
        return 'other_whitespace'
    return 'wrong_content'


def lengths(values):
    return {'count': len(values), 'min': min(values), 'median': statistics.median(values),
            'mean': statistics.mean(values), 'max': max(values),
            'histogram': {str(k): v for k, v in sorted(Counter(values).items())}}


def analyze(root, archive):
    rows = []
    fixtures = {c['id']: c for c in read(root / 'data/epagent-sft-v3/eval-fixtures.json')}
    for arm in ['base', 'adapted']:
        suite = read(archive / f'attempts/tool-recovery-v3-{arm}/suite.json')
        for case in suite['cases']:
            report_path = archive / case['report'].removeprefix('<REPOSITORY>/')
            report = read(report_path)
            events = lines(report_path.with_name('trajectory.jsonl'))
            calls = {e['data']['step']: e for e in events if e['event'] == 'tool_call'}
            observations, setup = {}, None
            for event in events:
                data, kind = event['data'], event['event']
                if kind == 'setup_tool_call':
                    setup = event
                if kind in ['setup_tool_result', 'tool_result']:
                    call = setup if kind == 'setup_tool_result' else calls[data['step']]
                    name, args, obs = call['data']['tool'], call['data']['arguments'], data['observation']
                    if name == 'read_file' and 'content' in obs:
                        observations[args['path']] = {'call_event': call['sequence'], 'observation_event': event['sequence'],
                            'setup_intervention': kind == 'setup_tool_result', 'content': obs['content'], 'truncated': obs['truncated']}
                    if kind != 'tool_result' or name != 'edit_file' or 'error' not in obs:
                        continue
                    observed = observations[args['path']]
                    source = (report_path.parent / 'workspace' / args['path']).read_text()
                    assert not observed['truncated'] and observed['content'] == source
                    old, new = args['old_text'], args['new_text']
                    cause = classify(source, old, args['path'] == fixtures[case['case_id']]['source'])
                    future = [c for step, c in sorted(calls.items()) if step > data['step']]
                    next_call = future[0] if future else None
                    next_edit = next((c for c in future if c['data']['tool'] == 'edit_file'), None)
                    next_kind = 'budget_end' if next_call is None else (
                        'reinspect_same_source' if next_call['data']['tool'] == 'read_file' and next_call['data']['arguments']['path'] == args['path'] else
                        'repeat_same_rejected_edit' if next_call['data']['tool'] == 'edit_file' and next_call['data']['arguments'] == args else 'other')
                    if cause == 'duplicated_span':
                        candidates = minimal_extensions(source, old)
                        correction_note = 'Minimum added source-context characters per occurrence; target occurrence is not uniquely determined by this analysis.'
                    else:
                        assert cause in ['indentation', 'quoting']
                        candidates = [{'old_text': source, 'start': 0, 'end': len(source)}]
                        correction_note = 'Copy the observed full file, correcting only the identified indentation/quote mismatch.'
                    for candidate in candidates:
                        corrected = candidate['old_text']
                        assert source.count(corrected) == 1
                        after = source.replace(corrected, new, 1)
                        candidate.update(executable_by_current_match_rule=True, changes_bytes=after != source,
                                         resulting_source=after, resulting_python_parseable=parseable(after))
                    rows.append({'arm': arm, 'fixture': case['case_id'], 'episode_id': report['episode_id'],
                        'turn': data['step'], 'call_event': call['sequence'], 'observation_event': event['sequence'],
                        'path': args['path'], 'latest_source_observation': observed, 'old_text': old, 'new_text': new,
                        'old_text_characters': len(old), 'old_text_utf8_bytes': len(old.encode()), 'old_text_lines': len(old.splitlines()),
                        'occurrences': source.count(old), 'cause': cause, 'rejection': obs,
                        'matches_injected_arguments': args == fixtures[case['case_id']]['forced_failed_edit']['arguments'],
                        'next_action': next_kind, 'next_call_event': next_call['sequence'] if next_call else None,
                        'subsequent_edit_event': next_edit['sequence'] if next_edit else None,
                        'subsequent_edit_arguments_changed': next_edit['data']['arguments'] != args if next_edit else None,
                        'meaningful_response': 'Procedural reread, followed by unchanged rejected edit.' if next_kind == 'reinspect_same_source' else
                            'No subsequent action: budget exhausted.' if next_kind == 'budget_end' else 'No adaptation: immediate repeat.',
                        'minimal_correction_definition': correction_note, 'minimal_correction_candidates': candidates,
                        'new_text_equals_complete_observed_file': new == source,
                        'whole_file_old_text_alternative': {'old_text': source, 'unique': source.count(source) == 1,
                            'changes_bytes': source.replace(source, new, 1) != source,
                            'caveat': 'Whole-file target is an explicit counterfactual, not inferred model intent; not minimal for duplicated spans.'}})
    demos = []
    for review in read(root / 'data/epagent-sft-v3/trajectories/reviews.json')['episodes']:
        events = lines(root / 'data/epagent-sft-v3/trajectories' / review['trace'])
        calls = {e['data']['step']: e['data'] for e in events if e['event'] == 'tool_call'}
        seen = {}
        for e in events:
            if e['event'] != 'tool_result':
                continue
            d = e['data'];c = calls[d['step']];a = c['arguments'];o = d['observation']
            if c['tool'] == 'read_file':
                seen[a['path']] = o['content']
            if c['tool'] == 'edit_file':
                source, old = seen[a['path']], a['old_text']
                demos.append({'episode': review['episode_id'], 'split': review['split'], 'step': d['step'],
                    'selected_target': d['step'] in review['selected_assistant_steps'],
                    'characters': len(old), 'utf8_bytes': len(old.encode()), 'lines': len(old.splitlines()),
                    'observed_occurrences': source.count(old), 'full_observed_file': source == old,
                    'contains_indentation': any(s.startswith((' ', '\t')) for s in old.splitlines()),
                    'contains_quotes': any(q in old for q in ['"', "'"]), 'ends_in_newline': old.endswith('\n'),
                    'new_text_equals_old_text': old == a['new_text'], 'cause_if_rejected': classify(source, old, True) if 'error' in o else None})
    summaries = {}
    for split in ['train', 'valid']:
        selected = [d for d in demos if d['split'] == split and d['selected_target']]
        context = [d for d in demos if d['split'] == split and not d['selected_target']]
        summaries[split] = {'positive_old_text_characters': lengths([d['characters'] for d in selected]),
            'positive_old_text_lines': lengths([d['lines'] for d in selected]),
            'whole_file_targets': sum(d['full_observed_file'] for d in selected),
            'unique_observed_matches': sum(d['observed_occurrences'] == 1 for d in selected),
            'indented_targets': sum(d['contains_indentation'] for d in selected),
            'quoted_targets': sum(d['contains_quotes'] for d in selected),
            'newline_terminated_targets': sum(d['ends_in_newline'] for d in selected),
            'context_only_failed_edits': len(context), 'context_failure_causes': dict(Counter(d['cause_if_rejected'] for d in context))}
    result = {'schema': 'epagent.offline-edit-forensics.v1', 'scope': 'Recorded edits only. No model, scorer, tool or edited program was executed.',
        'rejections': rows, 'by_arm': {arm: {'rejected_edits': len(rs), 'causes': dict(Counter(r['cause'] for r in rs)),
            'occurrence_counts': dict(Counter(str(r['occurrences']) for r in rs)), 'next_actions': dict(Counter(r['next_action'] for r in rs)),
            'subsequent_edits_with_changed_arguments': sum(r['subsequent_edit_arguments_changed'] is True for r in rs),
            'old_text_lengths': lengths([r['old_text_characters'] for r in rs])} for arm in ['base','adapted'] if (rs := [r for r in rows if r['arm']==arm])},
        'demonstration_edits': demos, 'demonstrations': summaries,
        'inputs_sha256': {'archive_manifest': sha(archive / 'archive-manifest.json'),
            'v3_demo_reviews': sha(root / 'data/epagent-sft-v3/trajectories/reviews.json')}}
    save(archive / 'edit-failures.json', result)
    print(json.dumps({k:v for k,v in result.items() if k in ['by_arm','demonstrations']}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    analyze(Path(__file__).resolve().parents[1], args.archive)
