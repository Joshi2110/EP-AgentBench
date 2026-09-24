"""One bounded episode, with terminal-only verification and durable JSON records."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import time
import uuid

from epbench import __version__ as benchmark_version, grader
from epbench.cli import init
from . import __version__
from .execution import preflight
from .mlx_backend import BackendError, ContextLimit
from .reward import grade_submission
from .tools import CallError, SYSTEM_PROMPT, changes, execute, parse_call, snapshot

SCHEMA = 'epagent.episode.v1'


@dataclass(frozen=True)
class Config:
    steps: int = 12
    seconds: float = 300.0
    tool_seconds: float = 8.0
    output_bytes: int = 8192
    context_tokens: int = 8192
    max_tokens: int = 768
    temperature: float = 0.0
    seed: int = 0
    adapter_dir: str | None = None

    def validate(self):
        if self.adapter_dir is not None and (not isinstance(self.adapter_dir, str) or not self.adapter_dir):
            raise ValueError('adapter_dir must be a nonempty path or None')
        for name, low, high in [('steps', 1, 100), ('output_bytes', 256, 32768),
                                ('context_tokens', 1024, 16384), ('max_tokens', 32, 2048),
                                ('seed', 0, 2**32 - 1)]:
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'{name} must be an integer in [{low}, {high}]')
        for name, low, high in [('seconds', 0, 3600), ('tool_seconds', 0, 20), ('temperature', -1e-9, 2)]:
            value = getattr(self, name)
            if not math.isfinite(value) or not low < value <= high:
                raise ValueError(f'{name} is outside the supported finite range')
        if self.max_tokens >= self.context_tokens:
            raise ValueError('max_tokens must be less than context_tokens')


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def hashes(files):
    return {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}


def run_episode(task, out, backend, config=Config(), *, synthetic=None):
    config.validate()
    if synthetic is not None:
        from .synthetic import export_fixture, inject_setup, score_trajectory
        if task != 'synthetic:' + synthetic['id']:
            raise ValueError('Synthetic task ID does not match fixture')
    elif task not in grader.WORKSPACES:
        raise ValueError('EP-Agent supports the three existing Hall workspaces')
    episode_id = uuid.uuid4().hex
    directory = Path(out).resolve() / episode_id
    directory.mkdir(parents=True, exist_ok=False)
    workspace, control = directory / 'workspace', directory / 'control'
    control.mkdir()
    report_path, trace_path = directory / 'report.json', directory / 'trajectory.jsonl'
    started = time.monotonic()
    report = {'schema': SCHEMA, 'epagent_version': __version__, 'benchmark_version': benchmark_version,
              'episode_id': episode_id, 'task_id': task, 'instance_id': None, 'start_time': now(),
              'end_time': None, 'config': asdict(config), 'model': dict(backend.metadata),
              'host': {'system': platform.system(), 'release': platform.release(),
                       'machine': platform.machine(), 'python': platform.python_version()},
              'runner_sha256': hashes({p.name: p.read_bytes() for p in Path(__file__).parent.glob('*.py')}),
              'status': 'running', 'termination_reason': None, 'steps': 0, 'tool_calls': 0,
              'errors': [], 'reward': None, 'grading': None, 'scored': False,
              'paths': {'report': str(report_path), 'trace': str(trace_path),
                        'workspace': str(workspace), 'initial_workspace': str(directory / 'initial'),
                        'patch': str(directory / 'changes.diff'),
                        'conversation': str(directory / 'conversation.json'), 'control': str(control)}}
    save(report_path, report)
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': f'Repair task {task}. Start by inspecting the workspace. '
                 f'You have at most {config.steps} tool turns and {config.seconds:g} seconds, '
                 f'including local model loading. Each Python run has at most {config.tool_seconds:g} seconds. '
                 'Use finish to submit your final work.'}]
    if synthetic is not None:
        messages[1]['content'] = synthetic['files']['README.md'] + (
            f'\nYou have {config.steps} model tool turns and {config.seconds:g} seconds after setup. '
            'The following two tool turns are supplied experimental interventions, not your actions. '
            'Recover from the failed edit using observed source. Report the outcome honestly.')
        report['evaluation_kind'] = 'synthetic_tool_recovery'
    initial, completions = {}, []
    agent_started = None
    model_responded = False
    sequence = 0
    with trace_path.open('x') as trace:
        def emit(kind, data):
            nonlocal sequence
            sequence += 1
            trace.write(json.dumps({'schema': SCHEMA, 'episode_id': episode_id, 'sequence': sequence,
                                   'time': now(), 'event': kind, 'data': data}, allow_nan=False) + '\n')
            trace.flush()

        emit('episode_start', {'task_id': task, 'config': asdict(config), 'model': backend.metadata})
        try:
            if synthetic is None:
                init(task, workspace)
            else:
                export_fixture(synthetic, workspace)
            initial = snapshot(workspace)
            shutil.copytree(workspace, directory / 'initial')
            report['initial_sha256'] = hashes(initial)
            export_hash = hashlib.sha256(json.dumps(report['initial_sha256'], sort_keys=True).encode()).hexdigest()
            report['instance_id'] = f'{task}:default:{export_hash}'
            canary = control / 'private-canary.txt'
            canary.write_text('EP-Agent private preflight canary\n')
            withheld = [canary, grader.__file__]
            if synthetic is None:
                withheld.append(grader.WORKSPACES[task][1].__file__)
            else:
                withheld.append(Path(__file__).with_name('synthetic.py'))
            report['execution_boundary'] = preflight(workspace, withheld)
            emit('preflight', report['execution_boundary'])
            if synthetic is not None:
                inject_setup(synthetic, workspace, messages, emit, config)
            agent_started = time.monotonic()
            deadline = agent_started + config.seconds
            backend.start(control)
            report['status'], report['termination_reason'] = 'unfinished', 'step_limit'
            for step in range(1, config.steps + 1):
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError('Agent wall-time budget reached')
                report['steps'] = step
                emit('model_request', {'step': step, 'messages': messages})
                completion = backend.generate(messages, left, emit)
                completions.append(completion)
                model_responded = True
                messages.append({'role': 'assistant', 'content': completion['text']})
                emit('assistant', {'step': step, **completion})
                before = snapshot(workspace)
                try:
                    name, arguments = parse_call(completion['text'])
                    report['tool_calls'] += 1
                    emit('tool_call', {'step': step, 'tool': name, 'arguments': arguments})
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise TimeoutError('Agent wall-time budget reached before tool execution')
                    observation = execute(workspace, name, arguments, min(config.tool_seconds, left), config.output_bytes)
                except (ValueError, OSError) as exc:
                    # TimeoutError is an OSError subclass; budget exhaustion is terminal.
                    if isinstance(exc, TimeoutError):
                        raise
                    name = None
                    observation = {'error': exc.category if isinstance(exc, CallError) else type(exc).__name__,
                                   'detail': str(exc)[:1000]}
                    report['errors'].append({'step': step, **observation})
                after = snapshot(workspace)
                patch = changes(before, after)
                result = {'step': step, 'observation': observation, 'patch': patch}
                if synthetic is not None:
                    result['workspace_sha256'] = hashes(after)
                emit('tool_result', result)
                messages.append({'role': 'user', 'content': json.dumps({'tool_result': observation,
                                 'steps_remaining': config.steps - step}, ensure_ascii=False)})
                if name == 'finish':
                    report['status'], report['termination_reason'] = 'finished', 'finish_tool'
                    break
        except ContextLimit as exc:
            report['status'], report['termination_reason'] = 'unfinished', 'context_limit'
            report['errors'].append({'error': type(exc).__name__, 'detail': str(exc)})
        except TimeoutError as exc:
            report['status'], report['termination_reason'] = 'timeout', 'wall_time_limit'
            report['errors'].append({'error': type(exc).__name__, 'detail': str(exc)})
        except BackendError as exc:
            report['status'], report['termination_reason'] = 'backend_failure', 'inference_error'
            report['errors'].append({'error': type(exc).__name__, 'detail': str(exc)})
        except KeyboardInterrupt:
            report['status'], report['termination_reason'] = 'interrupted', 'keyboard_interrupt'
        except Exception as exc:
            report['status'], report['termination_reason'] = 'infrastructure_failure', 'runner_error'
            report['errors'].append({'error': type(exc).__name__, 'detail': str(exc)[:1000]})
        finally:
            try:
                backend.close()
            except Exception as exc:
                report['status'], report['termination_reason'] = 'infrastructure_failure', 'cleanup_error'
                report['errors'].append({'error': type(exc).__name__, 'detail': str(exc)[:1000]})
            report['agent_seconds'] = time.monotonic() - agent_started if agent_started else None
            report['model'] = dict(backend.metadata)
            save(directory / 'conversation.json', messages)
            emit('agent_terminated', {'status': report['status'], 'reason': report['termination_reason']})

        # No grading observation can enter the completed conversation or policy process.
        try:
            final = snapshot(workspace)
            report['final_sha256'] = hashes(final)
            report['modified_files'] = sorted(n for n in initial.keys() | final.keys() if initial.get(n) != final.get(n))
            (directory / 'changes.diff').write_text(changes(initial, final))
            if model_responded and report['status'] != 'infrastructure_failure':
                grading_started = time.monotonic()
                if synthetic is None:
                    report.update(grade_submission(task, workspace))
                else:
                    events = [json.loads(line) for line in trace_path.read_text().splitlines()]
                    report['behavior'] = score_trajectory(synthetic, events, report['initial_sha256'])
                report['grading_seconds'] = time.monotonic() - grading_started
                report['scored'] = True
                if synthetic is None:
                    emit('terminal_reward', {k: report[k] for k in ['reward', 'grading']})
                else:
                    emit('behavior_score', report['behavior'])
        except Exception as exc:
            report['grading_error'] = {'error': type(exc).__name__, 'detail': str(exc)[:1000]}
            emit('grading_error', report['grading_error'])
        # Counts cover completed generations only. Streaming events preserve partial
        # generations on timeout; never fabricate counts for an unavailable response.
        measured = [c for c in completions if c.get('generation_tokens') is not None]
        report['usage'] = {'completed_generations': len(completions),
                          'prompt_tokens': sum(c['prompt_tokens'] for c in measured) if measured else None,
                          'generation_tokens': sum(c['generation_tokens'] for c in measured) if measured else None,
                          'scope': 'completed generations; prompt includes repeated history',
                          'peak_mlx_bytes': max((c.get('peak_mlx_bytes', 0) for c in measured), default=None),
                          'peak_rss_bytes': max((c.get('peak_rss_bytes', 0) for c in measured), default=None),
                          'token_logprobs_recorded': False, 'cost': None}
        report['end_time'], report['total_seconds'] = now(), time.monotonic() - started
        report['evaluation_status'] = ('grading_failure' if 'grading_error' in report else
                                       'scored' if report['scored'] else 'not_scored')
        emit('episode_end', report)
        save(report_path, report)
    return report
