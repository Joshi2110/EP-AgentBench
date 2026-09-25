"""Run one explicitly authorized original-base development episode, never retry."""
import argparse
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from epagent.episode import Config, run_episode, save
from epagent.mlx_backend import MLXBackend
from epagent.verification import PROTOCOL, system_prompt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--verification-feedback', action='store_true',
                        help='Enable explicitly recorded syntax feedback and test reminders')
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text())
    args.out.mkdir(parents=True, exist_ok=False)
    config = Config()  # Original base, 12 turns, 300 seconds, seed 0, temperature 0.
    backend = MLXBackend(args.model_dir, asdict(config))
    assert backend.metadata['adapter']['requested'] is False
    save(args.out / 'registration.json', {
        'kind': 'one development episode; no recovery/replacement run',
        'command': [sys.executable, *sys.argv], 'config': asdict(config),
        'fixture': fixture, 'fixture_sha256': hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
        'system_prompt': system_prompt(args.verification_feedback), 'model': backend.metadata,
        'verification_feedback': PROTOCOL if args.verification_feedback else None,
        'implementation_commit': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parents[1], text=True).strip(),
        'python': platform.python_version(),
        'software': {n: importlib.metadata.version(n) for n in ['mlx', 'mlx-lm', 'transformers', 'numpy']},
        'measurement': 'Changed source, preserved unrelated files, original visible tests, '
                       'actual agent Python results and manual final-claim review. No ML generalization claim.'})
    inhibitor = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(os.getpid())])
    try:
        report = run_episode('development:' + fixture['id'], args.out / 'episodes', backend,
                             config, development=fixture, verification_feedback=args.verification_feedback)
        save(args.out / 'result.json', report)
        print(json.dumps({'status': report['status'], 'report': report['paths']['report'],
                          'development': report.get('development')}), flush=True)
    finally:
        inhibitor.terminate()
        inhibitor.wait(timeout=10)
        save(args.out / 'cleanup.json', {'caffeinate_pid': inhibitor.pid,
            'caffeinate_returncode': inhibitor.returncode,
            'model_process_running': backend.process is not None and backend.process.poll() is None})


if __name__ == '__main__':
    main()
