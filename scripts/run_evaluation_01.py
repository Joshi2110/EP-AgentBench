"""Run exactly one registered Evaluation 01 arm. No retries, no replacement episodes."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from epagent.assessment import ARMS, registered, run_suite
from epagent.episode import save
from epagent.mlx_backend import MLXBackend


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['fixtures', 'protocol', 'model-dir', 'out']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--arm', choices=sorted(ARMS), required=True)
    args = parser.parse_args()
    _, config, feedback, spec = registered(args.fixtures, args.protocol, args.arm)
    args.out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    save(args.out / 'registration.json', {
        'kind': 'one registered Evaluation 01 arm; no recovery or replacement run',
        'arm': args.arm, 'verification_feedback': feedback, 'config': asdict(config),
        'command': [sys.executable, *sys.argv], 'protocol': spec,
        'fixtures_sha256': hashlib.sha256(args.fixtures.read_bytes()).hexdigest(),
        'protocol_sha256': hashlib.sha256(args.protocol.read_bytes()).hexdigest(),
        'implementation_commit': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'python': platform.python_version(),
        'host': {'system': platform.system(), 'machine': platform.machine()}})
    inhibitor = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(os.getpid())])
    try:
        report = run_suite(args.fixtures, args.protocol, args.model_dir, args.out / 'suite',
                           args.arm, backend_factory=MLXBackend)
        print(json.dumps({'arm': report['arm'], 'status': report['status'],
                          'primary': report['primary'],
                          'suite': str(args.out / 'suite' / 'suite.json')}), flush=True)
        return 0 if report['status'] == 'complete' else 1
    finally:
        inhibitor.terminate()
        save(args.out / 'cleanup.json', {'inhibitor_returncode': inhibitor.wait()})


if __name__ == '__main__':
    raise SystemExit(main())
