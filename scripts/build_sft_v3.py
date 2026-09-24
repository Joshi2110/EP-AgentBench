"""Execute explicitly authored v3 action plans with real tools, without a model."""

import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile

from epagent.execution import preflight
from epagent.sft_data import digest, reviewed_examples, write_json
from epagent.tools import SYSTEM_PROMPT, changes, execute, parse_call, safe_path, snapshot


def build(fixtures, out):
    cases = json.loads(fixtures.read_text())
    out.mkdir(parents=True, exist_ok=False)
    reviews, counts, patterns = [], {}, {}
    for case in cases:
        with tempfile.TemporaryDirectory(prefix='epagent-v3-demo-') as tmp:
            workspace = Path(tmp)
            for name, content in case['files'].items():
                path = safe_path(workspace, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            preflight(workspace, [Path(__file__)])
            messages = [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user',
                'content': 'Repair this synthetic Python workspace. Read README.md for the requirement. '
                           f"You have at most {case['budget_steps']} tool turns. Report only observed outcomes."}]
            events, selected, excluded, context, observed = [], [], [], [], {}

            def emit(kind, data):
                events.append({'schema': 'epagent.episode.v1', 'episode_id': case['id'],
                               'sequence': len(events) + 1, 'event': kind, 'data': data})

            emit('episode_start', {'task_id': 'synthetic:' + case['id'],
                'config': {'steps': case['budget_steps']},
                'model': {'backend': 'scripted-demonstration', 'model_id': None},
                'provenance': 'New project-authored synthetic action plan; no harvested trajectory'})
            assert len(case['actions']) <= case['budget_steps']
            for step, action in enumerate(case['actions'], 1):
                name, args, learn = action['tool'], action['arguments'], action.get('learn', True)
                text = json.dumps({'tool': name, 'arguments': args})
                assert parse_call(text) == (name, args)
                emit('model_request', {'step': step, 'messages': json.loads(json.dumps(messages))})
                emit('assistant', {'step': step, 'text': text})
                emit('tool_call', {'step': step, 'tool': name, 'arguments': args})
                messages.append({'role': 'assistant', 'content': text})
                before = snapshot(workspace)
                if name == 'edit_file' and learn:
                    # Every positive edit copies a unique, nonempty observed span.
                    assert args['old_text'] and observed[args['path']].count(args['old_text']) == 1
                    assert args['old_text'] != args['new_text']
                try:
                    obs = execute(workspace, name, args, 8, 8192)
                except ValueError as exc:
                    obs = {'error': 'ValueError', 'detail': str(exc)}
                obs.pop('elapsed_seconds', None)
                for key in ['stdout', 'stderr']:
                    if key in obs:
                        for prefix in [str(workspace.resolve()), str(workspace)]:
                            obs[key] = obs[key].replace(prefix + '/', '<workspace>/')
                for key, expected in action['expect'].items():
                    assert obs.get(key) == expected, (case['id'], step, obs)
                if learn:
                    assert 'error' not in obs
                    selected.append(step)
                elif 'error' in obs:
                    assert obs == {'error': 'ValueError', 'detail': 'old_text must match exactly once'}
                    excluded.append(step)
                else:
                    assert action.get('context_reason') and name == 'read_file'
                    context.append(step)
                if name == 'read_file':
                    assert not obs['truncated']
                    observed[args['path']] = obs['content']
                emit('tool_result', {'step': step, 'observation': obs,
                                    'patch': changes(before, snapshot(workspace))})
                messages.append({'role': 'user', 'content': json.dumps({'tool_result': obs,
                                 'steps_remaining': case['budget_steps'] - step})})
            assert case['actions'][-1]['tool'] == 'finish'
            for name, text in case['final_files'].items():
                assert (workspace / name).read_text() == text
            path = out / (case['id'] + '.jsonl')
            path.write_text(''.join(json.dumps(e) + '\n' for e in events))
            reviews.append({'episode_id': case['id'], 'split': case['split'], 'family': case['family'],
                'trace': path.name, 'trace_sha256': digest(path), 'origin': 'authored-synthetic-fixture',
                'rights': 'Project-authored synthetic plans; no provider trajectory or benchmark reference targets',
                'review': 'Action plans inspected; exact observed edit spans, actual tool results and final bytes checked. Independent maintainer review pending.',
                'outcome': case['outcome'], 'budget_steps': case['budget_steps'],
                'selected_assistant_steps': selected, 'excluded_failed_edit_steps': excluded,
                'excluded_setup_read_steps': context})
            counts.setdefault(case['split'], Counter()).update(case['actions'][i-1]['tool'] for i in selected)
            patterns[case['id']] = [a['tool'] + ('' if a.get('learn', True) else ' (context only)') for a in case['actions']]
    write_json(out / 'reviews.json', {'schema': 'epagent.sft-review.v1',
        'observation_normalization': 'Omit elapsed_seconds; temporary workspace prefixes in stdout/stderr become <workspace>/',
        'fixtures_sha256': digest(fixtures), 'episodes': reviews})
    examples = reviewed_examples(out)
    summary = {'counts': {s: dict(c) for s, c in counts.items()},
               'examples': {s: len(r) for s, r in examples.items()}, 'patterns': patterns,
               'training_performed': False, 'model_evaluation_performed': False}
    write_json(out / 'coverage.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.fixtures, args.out)['examples']))
