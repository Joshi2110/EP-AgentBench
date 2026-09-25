"""Allowlisted private archive of the verification-feedback 7B episode; never rerun it."""
import ast
import json
from pathlib import Path
import re

from archive_sft_v2 import read, save, sha

RUN = 'attempts/replace-lines-7b-verification-smoke'


def definitions(source):
    return sorted(n.name for n in ast.parse(source).body
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))


def analyze(root, episode):
    """Ground every claim in recorded bytes and events; never re-run or re-score."""
    events = [json.loads(s) for s in (episode / 'trajectory.jsonl').read_text().splitlines()]
    calls = [e['data'] for e in events if e['event'] == 'tool_call']
    observed = {e['data']['step']: e['data']['observation'] for e in events if e['event'] == 'tool_result'}
    readme = (episode / 'initial/README.md').read_text()
    original = (episode / 'initial/cart.py').read_text()
    checks = (episode / 'initial/checks.py').read_text()
    final = (episode / 'workspace/cart.py').read_text()
    development = read(episode / 'report.json')['development']
    edit = next(c for c in calls if c['tool'] == 'edit_file')
    run = next(c for c in calls if c['tool'] == 'run_python')
    removed = sorted(set(definitions(original)) - set(definitions(final)))
    assert removed == ['cart_total'] and not development['repair_passed']
    return {
        'schema': 'epagent.contract-failure-analysis.v1',
        'episode': episode.name,
        'method': 'Static reading of recorded fixture bytes and trajectory events. No inference, '
                  'no re-execution, no re-grading, no claim about model intent.',
        'required_contract': {
            'function_name': 'cart_total',
            'input_representation': 'each row is a (unit_price, quantity) tuple',
            'stated_in': {
                'README.md': {'names_function': 'cart_total' in readme,
                              'states_tuple_rows': '(unit_price, quantity)' in readme,
                              'orders_running_checks': 'execute checks.py' in readme,
                              'limits_claims_to_observed_output':
                                  'claims supported by its actual output' in readme},
                'cart.py': {'declares_required_signature': 'def cart_total(rows):' in original,
                            'destructures_tuple_rows': 'for price, quantity in rows' in original},
                'checks.py': {'imports_required_name': 'from cart import cart_total' in checks,
                              'passes_tuple_rows': '[(7, 3), (2, 4)]' in checks}}},
        'discoverability': {
            'listing_step': 1, 'files_listed': observed[1]['files'],
            'read_file_tool_available_and_used': True,
            'readme_reads': sum(c['tool'] == 'read_file' and c['arguments']['path'] == 'README.md' for c in calls),
            'checks_reads': sum(c['tool'] == 'read_file' and c['arguments']['path'] == 'checks.py' for c in calls),
            'source_reads': sum(c['tool'] == 'read_file' and c['arguments']['path'] == 'cart.py' for c in calls),
            'required_name_present_in_step2_observation': 'def cart_total(rows):' in observed[2]['content'],
            'tuple_destructuring_present_in_step2_observation':
                'for price, quantity in rows' in observed[2]['content']},
        'instruction_to_inspect': {
            'workspace_readme_instructs_reading_and_running': True,
            'system_prompt_verification_clause_present': True,
            'system_prompt_clause': 'Before modifying code, read the task requirements and relevant test '
                                    'source in the workspace. Preserve the required function signatures '
                                    'and input formats.',
            'note': 'The workspace README was never read. The system-prompt clause was present in every '
                    'model request and was not followed. This records omission, not intent.'},
        'api_break': {
            'step': edit['step'], 'tool': edit['tool'],
            'old_text': edit['arguments']['old_text'],
            'new_text': edit['arguments']['new_text'],
            'removed_public_definitions': removed,
            'retained_public_definitions': sorted(set(definitions(original)) & set(definitions(final))),
            'required_name_was_the_deleted_text': 'cart_total' in edit['arguments']['old_text'],
            'syntax_after_edit': observed[edit['step']].get('verification', {}).get('syntax', {}).get('status'),
            'write_status': observed[edit['step']].get('verification', {}).get('write_status'),
            'orphaned_unreachable_line': final.splitlines()[4],
            'orphan_note': 'Unreachable after the new return and referencing a name absent from the new '
                           'parameter list. Never executed, so syntax stayed valid.'},
        'why_the_agent_test_passed': {
            'agent_test_step': run['step'], 'agent_test_code': run['arguments']['code'],
            'agent_test_result': observed[run['step']],
            'agent_test_imported': 'calculate_total', 'agent_test_input': 'list of dictionaries',
            'explanation': 'The agent imported the name it had just created and passed the representation '
                           'it had just invented, so the command exercised its replacement against itself. '
                           'It asserted nothing and compared against no specified value.',
            'independent_test_command': 'checks.py as shipped in the workspace',
            'independent_test_imported': 'cart_total', 'independent_test_input': 'list of tuples',
            'independent_failure': development['original_visible_tests']['stderr'].strip().splitlines()[-1],
            'failed_before_any_assertion_ran': True,
            'workspace_test_never_read_or_executed': True},
        'finish_claim': {
            'summary': development['final_summaries'][0],
            'automatic_classification': 'manual_review_required',
            'manual_reading': 'Each clause is literally true of the command the agent ran. Taken together '
                              'the summary implies a verified repair that did not occur: the required test '
                              'was never executed and the required public name no longer exists.'},
        'verification_feedback': {
            'protocol': 'epagent.verification-feedback.v1',
            'syntax_error_feedback_exercised': False,
            'reason': 'The only edit produced valid Python, so no syntax error arose. The checker '
                      'correctly reported valid, and validity did not imply contract compliance.',
            'delivered_to_model': True,
            'delivered_content': observed[edit['step']].get('verification', {})},
        'grader_independence': {'runs_after_backend_close': True, 'fed_back_to_model': False},
        'limitations': 'One episode at temperature zero. Not a causal estimate of verification feedback, '
                       'not a model-size comparison, and not evidence about any other task.'}


def archive(root):
    run = root / RUN
    report = read(run / 'result.json')
    assert not report['development']['repair_passed'], 'Archive preserves the recorded failure'
    episode = Path(report['paths']['report']).parent
    sources = [run / n for n in ['registration.json', 'result.json', 'cleanup.json']]
    sources += [episode / n for n in ['report.json', 'trajectory.jsonl', 'conversation.json', 'changes.diff']]
    for sub in ['initial', 'workspace']:
        sources += sorted(p for p in (episode / sub).rglob('*') if p.is_file())
    # No model tensors, no control/credential directory, no machine install logs.
    sources += [root / '.epagent-models/qwen2.5-coder-7b-4bit/epagent-model.json',
                root / 'data/epagent-development/cart-total.json',
                root / 'scripts/run_development_smoke.py',
                root / 'tests/test_verification_feedback.py']
    sources += [root / 'src/epagent' / n for n in
                ['verification.py', 'episode.py', 'development.py', 'tools.py', 'mlx_backend.py']]
    out = root / 'artifacts/ep-agent/7b-verification-smoke'
    out.mkdir(parents=True, exist_ok=False)
    mapping = {}
    for source in sources:
        name = source.relative_to(root).as_posix()
        raw = source.read_bytes().decode('utf-8')
        clean = raw.replace(str(root), '<REPOSITORY>')
        assert not re.search(r'/(?:Users|home|private/var|var/folders)/', clean), name
        if source.name == 'trajectory.jsonl':
            for a, b in zip(raw.splitlines(), clean.splitlines()):
                before, after = json.loads(a), json.loads(b)
                if before['event'] in ['model_request', 'model_start', 'model_chunk', 'model_done',
                                       'assistant', 'tool_call', 'tool_result', 'verification_feedback']:
                    assert before == after, (name, before['event'])
        if 'workspace' in source.parts or 'initial' in source.parts or source.name == 'conversation.json':
            assert raw == clean, name
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(clean.encode('utf-8'))
        mapping[name] = {'raw_sha256': sha(source), 'archived_sha256': sha(target),
                         'repository_prefix_replacements': raw.count(str(root))}
    # The grader traceback embeds an absolute workspace path; normalize the analysis too.
    analysis = json.loads(json.dumps(analyze(root, episode)).replace(str(root), '<REPOSITORY>'))
    assert not re.search(r'/(?:Users|home|private/var|var/folders)/', json.dumps(analysis))
    save(out / 'contract-analysis.json', analysis)
    save(out / 'archive-manifest.json', {
        'schema': 'epagent.archive-manifest.v1',
        'source_head': '48c0c690d5b4e5284243005f3e596437f2134dc4',
        'run_directory': RUN, 'episode_id': episode.name,
        'normalization': 'Repository prefixes in metadata and terminal tracebacks become <REPOSITORY>. '
                         'Model-visible events, generated responses, source bytes and the conversation '
                         'are byte-identical to the raw records.',
        'raw_evidence_retained_locally': True, 'files': mapping,
        'episodes_run': 1, 'retries': 0, 'no_inference_or_rescoring': True,
        'previous_7b_episode_unchanged': True,
        'limitations': 'One development episode. The syntax-error path was never exercised because the '
                       'model wrote no invalid Python.'})
    print(json.dumps({'archived_files': len(mapping), 'episode': episode.name}))


if __name__ == '__main__':
    archive(Path(__file__).resolve().parents[1])
