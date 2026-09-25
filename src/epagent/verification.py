"""Opt-in syntax feedback and execution evidence; never repair or grade code."""
import ast

from .execution import run_python
from .tools import SYSTEM_PROMPT

PROTOCOL = 'epagent.verification-feedback.v1'
INSTRUCTIONS = '''
Before modifying code, read the task requirements and relevant test source in the
workspace. Preserve the required function signatures and input formats.
After a Python file changes, automatic syntax feedback describes the actual
written bytes. A write can succeed while leaving invalid Python. Inspect reported
errors before making further edits. No code is automatically repaired or reverted.
Syntax validity does not establish correct behavior. Run the relevant tests after
making changes and inspect their output. If they fail, investigate the failure.
Use finish to report what changed, the test command and observed result, and any
unresolved failure. If you did not run tests, say so; do not claim a verified repair.
'''


def system_prompt(enabled=False):
    return SYSTEM_PROMPT + INSTRUCTIONS if enabled else SYSTEM_PROMPT


def check_syntax(workspace, changed, seconds, output_bytes):
    """Compile snapshot bytes in the existing bounded child, without executing them.

    Builtins only: workspace files cannot shadow checker imports. Compiler errors
    and resource limits remain observations, not permission to undo a write.
    """
    if seconds <= 0:
        return {'status': 'not_checked', 'reason': 'episode time budget exhausted'}
    code = f'files = {changed!r}\n' + '''results = {}
for name, source in files.items():
    if source is None:
        results[name] = {'status': 'not_checked', 'reason': 'file deleted'}
        continue
    try:
        compile(source, name, 'exec', dont_inherit=True)
        results[name] = {'status': 'valid'}
    except (SyntaxError, ValueError) as exc:
        results[name] = {'status': 'invalid', 'error': type(exc).__name__,
                         'message': str(exc)[:300],
                         'line': getattr(exc, 'lineno', None),
                         'column': getattr(exc, 'offset', None)}
print(repr(results))
'''
    result = run_python(workspace, code, seconds, output_bytes)
    if result['status'] != 'completed':
        return {'status': 'not_checked', 'reason': 'syntax checker ' + result['status'],
                'execution': result}
    try:
        files = ast.literal_eval(result['stdout'])
        if not isinstance(files, dict) or files.keys() != changed.keys():
            raise ValueError('incomplete checker output')
    except (SyntaxError, ValueError):
        return {'status': 'not_checked', 'reason': 'unreadable syntax checker output',
                'execution': result}
    statuses = {value['status'] for value in files.values()}
    return {'status': 'invalid' if 'invalid' in statuses else
            'not_checked' if 'not_checked' in statuses else 'valid',
            'files': files, 'seconds': result['elapsed_seconds']}


class VerificationFeedback:
    def __init__(self):
        self.last_change = 0
        self.python_runs = []

    def observe(self, workspace, step, name, before, after, observation, seconds, output_bytes):
        changed = {p: after.get(p) for p in before.keys() | after.keys()
                   if before.get(p) != after.get(p)}
        feedback = {}
        if changed:
            self.last_change = step
            python = {p: data for p, data in sorted(changed.items()) if p.endswith('.py')}
            if python:
                feedback['syntax'] = check_syntax(workspace, python, seconds, output_bytes)
                feedback['write_status'] = ('applied_with_syntax_errors'
                    if feedback['syntax']['status'] == 'invalid' else 'applied')
            feedback['reminder'] = ('Bytes changed; inspect any syntax errors, then run relevant tests. '
                                    'An applied edit or valid syntax is not a verified repair.')
        if name == 'run_python':
            self.python_runs.append({'step': step, 'status': observation.get('status', 'unknown')})
        if name == 'finish':
            current = [r for r in self.python_runs if r['step'] > self.last_change]
            feedback['finish_evidence'] = {
                'last_change_step': self.last_change, 'python_runs': self.python_runs.copy(),
                'post_change_python_runs': current,
                'claim_support': 'manual_review_required' if current else 'no_post_change_execution',
                'scope': 'Execution is not proof of a relevant or passing test. Review commands and '
                         'outputs in tool_call/tool_result events; automatic syntax checks do not count.'}
        return feedback
