"""Evaluation 02 registration; reuse the existing independent checks and metric definitions."""
from dataclasses import asdict, replace
import json
from pathlib import Path

from .assessment import independent_result, measure, visible_fixture
from .episode import Config, now, run_episode, save
from .mlx_backend import MLXBackend, MODEL_7B, REVISION_7B, adapter_manifest
from .sft import local_model
from .sft_data import digest


def registered(fixtures, protocol, arm, adapter_dir=None):
    spec = json.loads(Path(protocol).read_text())
    cases = json.loads(Path(fixtures).read_text())
    if (spec.get('schema') != 'epagent.evaluation-02.v1' or arm not in ('base', 'adapted')
            or spec['model_id'] != MODEL_7B or spec['revision'] != REVISION_7B
            or spec['verification_feedback'] is not False or spec['attempts_per_case'] != 1
            or spec['seed'] != 0 or len(cases) != 10 or [c['id'] for c in cases] != spec['fixtures']
            or digest(fixtures) != spec['fixtures_sha256']):
        raise ValueError('Expected frozen Evaluation 02 protocol and ten cases')
    root = Path(protocol).resolve().parents[2]
    for name, sha in spec['frozen_sha256'].items():
        if digest(root / name) != sha:
            raise ValueError('Frozen experiment file changed: ' + name)
    config = Config(**spec['config'])
    if config.adapter_dir is not None:
        raise ValueError('The common registered configuration must use the original base')
    if (arm == 'base') != (adapter_dir is None):
        raise ValueError('Base must have no adapter; adapted must supply the completed registered run')
    if arm == 'adapted':
        training = json.loads((Path(adapter_dir) / 'run.json').read_text())
        adapter = adapter_manifest(adapter_dir)
        if (training['status'] != 'complete' or training['updates_requested'] != spec['training_updates']
                or training['prepared_manifest_sha256'] != spec['prepared_manifest_sha256']
                or training['prepared']['model'] != spec['model_manifest']
                or adapter['sha256']['adapters.safetensors'] != training['checkpoint_sha256']['adapters.safetensors']):
            raise ValueError('Adapter is not the completed frozen 7B training artifact')
        expected = training['prepared']['config']
        if adapter['config'] != {'fine_tune_type': 'lora', 'num_layers': expected['num_layers'],
                                 'lora_parameters': expected['lora_parameters']}:
            raise ValueError('Adapter configuration changed')
        config = replace(config, adapter_dir=str(Path(adapter_dir).resolve()))
    config.validate()
    return cases, config, spec


def run_suite(fixtures, protocol, model_dir, out, arm, adapter_dir=None, *, backend_factory=MLXBackend):
    cases, config, spec = registered(fixtures, protocol, arm, adapter_dir)
    if local_model(model_dir) != spec['model_manifest']:
        raise ValueError('Base model bytes or provenance differ from registration')
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema': spec['schema'], 'arm': arm, 'status': 'running', 'start_time': now(),
              'protocol_sha256': digest(protocol), 'verification_feedback': False,
              'config': asdict(config), 'cases': [], 'workflow_completions': 0, 'independent_repairs': 0}
    save(out / 'suite.json', report)
    try:
        for case in cases:
            backend = backend_factory(model_dir, asdict(config))
            episode = run_episode('development:' + case['id'], out / 'episodes', backend, config,
                                  development=visible_fixture(case), verification_feedback=False)
            entry = {'fixture': case['id'], 'episode': episode['paths']['report'], 'status': episode['status'],
                     'metrics': None, 'independent': None}
            report['cases'].append(entry)
            save(out / 'suite.json', report)  # Preserve failed attempt before any validation/analysis.
            actual = episode['model'].get('adapter', {})
            expected = adapter_manifest(config.adapter_dir)
            if (actual.get('loaded') != (arm == 'adapted') or actual.get('id') != expected['id']
                    or actual.get('sha256') != expected['sha256']):
                raise ValueError('Runtime adapter load/identity was not confirmed; preserve and stop')
            if episode['status'] in ('infrastructure_failure', 'backend_failure', 'interrupted') or not episode['scored']:
                raise ValueError('Episode infrastructure/grading failure; preserve and stop without replacement')
            workspace = episode['paths']['workspace']
            events = [json.loads(s) for s in Path(episode['paths']['trace']).read_text().splitlines()]
            entry['independent'] = independent_result(case, workspace, config.tool_seconds, config.output_bytes)
            entry['metrics'] = measure(case, episode, events, workspace)
            report['workflow_completions'] += int(entry['metrics']['evidence_supported_finish'])
            report['independent_repairs'] += int(entry['independent']['passed'])
            save(out / 'suite.json', report)
        report['status'] = 'complete'
    except BaseException as exc:
        report.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                      error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report.update(end_time=now(), primary=f"{report['workflow_completions']}/10",
                      independent=f"{report['independent_repairs']}/10",
                      unattempted=[c['id'] for c in cases[len(report['cases']):]])
        save(out / 'suite.json', report)
    return report
