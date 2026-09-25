"""Opt-in syntax feedback and execution evidence; never repair or grade code."""
import ast
import hashlib
from pathlib import PurePosixPath
import re
import time

from .execution import run_python
from .tools import SYSTEM_PROMPT

PROTOCOL = 'epagent.verification-feedback.v3'
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
If an edit removes a function or class that existed before it, the removal is
reported back to you; confirm it was intended and that callers still work.
If the workspace ships its own test file and you request finish without running
it, you may receive one reminder and can keep using tools within your budget.
'''

EVIDENCE_SCOPE = (
    'Runner-initiated execution of the original workspace test bytes. This is observation, not '
    'independent verification and not agent-initiated testing. Exit status zero, a printed marker '
    'and verified correctness are three different things; read the recorded status and output. A '
    'discovered workspace test may be the same file an independent post-episode grader uses. Where '
    'it is, this feedback exposes the functional evaluation signal during the episode, and those '
    'episodes must be analyzed separately from episodes run without it.')

TEST_TOKENS = {'test', 'tests', 'check', 'checks', 'verify', 'verifies',
               'validate', 'validation', 'spec', 'specs'}
EXECUTING_CALLS = {'run_path', 'run_module', 'run', 'call', 'check_call', 'check_output', 'system'}


def public_definitions(source):
    """Top-level non-underscore def/class names, or None when the source will not parse.

    Nested and method definitions are deliberately out of scope: this reports the
    module's own public surface, not every callable it happens to contain.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    return sorted(node.name for node in tree.body
                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                  and not node.name.startswith('_'))


def removed_definitions(before, after):
    """Names present before an action and absent after it. Removal may be intended."""
    report, skipped = {}, {}
    for path in sorted(after):
        old, new = before.get(path), after[path]
        if old is None or new is None:
            continue
        was = public_definitions(old.decode('utf-8', 'replace'))
        now = public_definitions(new.decode('utf-8', 'replace'))
        if was is None or now is None:
            # Invalid Python on either side: syntax feedback already covers it.
            skipped[path] = 'not_compared: source did not parse'
            continue
        gone = [name for name in was if name not in now]
        if gone:
            report[path] = gone
    return report, skipped


def discover_tests(paths):
    """Conservative convention-based discovery; no task-specific filename is assumed."""
    found = []
    for path in sorted(paths):
        if not path.endswith('.py'):
            continue
        pure = PurePosixPath(path)
        tokens = set()
        for part in list(pure.parts[:-1]) + [pure.stem]:
            tokens.update(t for t in re.split(r'[^A-Za-z0-9]+', part.lower()) if t)
        if tokens & TEST_TOKENS:
            found.append(path)
    return found


def executed_tests(code, candidates):
    """Recognize running a workspace test: importing its module, or naming it in an
    executing call. An arbitrary Python command that merely prints is not execution."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return []
    literals = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    executing = any(
        isinstance(node, ast.Call) and (
            (isinstance(node.func, ast.Name) and node.func.id in {'exec', 'eval'})
            or (isinstance(node.func, ast.Attribute) and node.func.attr in EXECUTING_CALLS))
        for node in ast.walk(tree))
    found = []
    for path in candidates:
        pure = PurePosixPath(path)
        module = '.'.join(pure.with_suffix('').parts)
        named = path in literals or pure.name in literals
        if module in modules or (named and executing):
            found.append(path)
    return found


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


def run_workspace_tests(workspace, originals, seconds, output_bytes, on_disk):
    """Execute the original test bytes against the current source. Writes nothing.

    The preserved bytes are used even when the agent has edited the test on disk,
    and the difference is reported rather than corrected. An exhausted budget is
    reported as not_checked; a passing result is never assumed.
    """
    results, remaining = [], seconds
    for path in sorted(originals):
        source = originals[path]
        identity = {'test': path, 'initiated_by': 'runner',
                    'method': 'original workspace test bytes executed as a program in the workspace root',
                    'original_sha256': hashlib.sha256(source).hexdigest(),
                    'on_disk_matches_original': on_disk.get(path) == source}
        if remaining <= 0:
            results.append({**identity, 'execution': 'not_checked',
                            'reason': 'remaining episode/tool budget exhausted'})
            continue
        started = time.monotonic()
        outcome = run_python(workspace, source.decode('utf-8', 'replace'), remaining, output_bytes)
        remaining -= time.monotonic() - started
        results.append({**identity,
                        'execution': 'timed_out' if outcome['status'] == 'timeout' else 'completed',
                        'status': outcome['status'], 'returncode': outcome['returncode'],
                        'stdout': outcome['stdout'], 'stderr': outcome['stderr'],
                        'elapsed_seconds': outcome['elapsed_seconds']})
    return results


class VerificationFeedback:
    """Observable workspace facts only. Never consults the grader, never edits code."""

    FINISH_REMINDERS = 1          # at most one nonterminal reminder per episode
    MIN_REMAINING_TURNS = 2       # enough turns left to run a test and then finish

    def __init__(self):
        self.last_change = 0
        self.python_runs = []
        self.workspace_tests = []
        self.initial_test_bytes = {}
        self.test_reads = []
        self.test_runs = []          # agent-initiated only; gates the agent-execution endpoint
        self.runner_runs = []        # runner-initiated; never credited to the agent
        self.finish_reminders = 0

    def register_workspace(self, initial):
        """Discover tests in the original workspace. Agent-created files never qualify."""
        self.workspace_tests = discover_tests(initial)
        self.initial_test_bytes = {p: initial[p] for p in self.workspace_tests}
        return self.workspace_tests

    def executed(self):
        """Agent-initiated executions only. Runner executions are deliberately excluded."""
        return sorted({path for run in self.test_runs for path in run['tests']})

    def runner_executed(self):
        return sorted({path for run in self.runner_runs for path in run['tests']})

    def test_evidence(self, after=None):
        return {
            'discovered': list(self.workspace_tests),
            'read': sorted(set(self.test_reads)),
            'executed': self.executed(),
            'executions': list(self.test_runs),
            'runner_executed': self.runner_executed(),
            'runner_executions': list(self.runner_runs),
            'scope': 'Discovery uses the original workspace and common naming conventions only. '
                     '"executed" counts agent-initiated runs only; runner-initiated runs are listed '
                     'separately and never credited to the agent. A completed run is observed output, '
                     'not independent functional verification; printed text is agent-controlled. '
                     'Absence of a test file is not a failure.'}

    def observe(self, workspace, step, name, before, after, observation, seconds, output_bytes,
                arguments=None):
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
                gone, skipped = removed_definitions(before, {p: after.get(p) for p in python})
                if gone:
                    feedback['removed_definitions'] = gone
                    feedback['definition_note'] = (
                        'These top-level names existed before this action and do not exist after it. '
                        'Removal can be intended; if it was not, restore them or update every caller.')
                if skipped:
                    feedback['definitions_not_compared'] = skipped
                if self.workspace_tests:
                    left = seconds - feedback['syntax'].get('seconds', 0)
                    results = run_workspace_tests(workspace, self.initial_test_bytes, left,
                                                  output_bytes, after)
                    feedback['workspace_test_feedback'] = {
                        'initiated_by': 'runner', 'trigger': 'accepted action changed Python bytes',
                        'results': results, 'scope': EVIDENCE_SCOPE}
                    ran = [r['test'] for r in results if r['execution'] != 'not_checked']
                    if ran:
                        self.runner_runs.append({'step': step, 'tests': ran, 'initiated_by': 'runner',
                            'statuses': {r['test']: r['status'] for r in results if r['test'] in ran}})
            feedback['reminder'] = ('Bytes changed; inspect any syntax errors, then run relevant tests. '
                                    'An applied edit or valid syntax is not a verified repair.')
        if name == 'read_file' and arguments and arguments.get('path') in self.workspace_tests:
            self.test_reads.append(arguments['path'])
        if name == 'run_python':
            self.python_runs.append({'step': step, 'status': observation.get('status', 'unknown')})
            ran = executed_tests(arguments['code'], self.workspace_tests) if arguments else []
            if ran:
                self.test_runs.append({
                    'step': step, 'tests': ran, 'status': observation.get('status', 'unknown'),
                    'tests_unmodified': all(after.get(p) == self.initial_test_bytes.get(p) for p in ran)})
        if name == 'finish':
            current = [r for r in self.python_runs if r['step'] > self.last_change]
            evidence = {'last_change_step': self.last_change, 'python_runs': self.python_runs.copy(),
                        'post_change_python_runs': current,
                        'workspace_tests': self.test_evidence(after)}
            if self.workspace_tests and not self.executed():
                evidence['claim_support'] = 'no_workspace_test_execution'
            elif not current:
                evidence['claim_support'] = 'no_post_change_execution'
            else:
                evidence['claim_support'] = 'manual_review_required'
            evidence['scope'] = ('Execution is not proof of a relevant or passing test. Review commands and '
                                 'outputs in tool_call/tool_result events; automatic syntax checks do not count.')
            feedback['finish_evidence'] = evidence
        return feedback

    def consider_finish(self, step, total_steps, seconds_left):
        """One bounded, nonterminal reminder, and only while acting on it is still possible.

        Returns None whenever finish must proceed: no discoverable test, a test already
        run, the single reminder already spent, or too little budget left to act.
        """
        remaining = total_steps - step
        if not self.workspace_tests or self.executed():
            return None
        if self.finish_reminders >= self.FINISH_REMINDERS:
            return None
        if remaining < self.MIN_REMAINING_TURNS or seconds_left <= 0:
            return None
        self.finish_reminders += 1
        return {
            'accepted': False, 'reminders_used': self.finish_reminders,
            'reminders_allowed': self.FINISH_REMINDERS, 'remaining_turns': remaining,
            'discovered_tests': list(self.workspace_tests), 'executed_tests': self.executed(),
            'reason': 'This workspace ships its own test file, and no recorded action has run it.',
            'action': 'Run the workspace test with the Python tool and inspect its real output, '
                      'then call finish again describing what you observed. Finish will be accepted '
                      'next time regardless of the result; report failures honestly.',
            'guarantee': 'This reminder is issued at most once per episode and never blocks a later finish.'}
