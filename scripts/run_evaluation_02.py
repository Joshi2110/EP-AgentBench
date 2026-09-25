"""One frozen Evaluation 02 arm; do not execute without separate authorization."""
import argparse
from dataclasses import asdict
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys

from epagent.assessment02 import registered, run_suite
from epagent.episode import save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('fixtures', 'protocol', 'model-dir', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--arm', choices=('base', 'adapted'), required=True)
    parser.add_argument('--adapter-dir', type=Path)
    args = parser.parse_args()
    _, config, spec = registered(args.fixtures, args.protocol, args.arm, args.adapter_dir)
    args.out.mkdir(parents=True, exist_ok=False)
    save(args.out / 'registration.json', {'command': [sys.executable, *sys.argv], 'arm': args.arm,
        'config': asdict(config), 'protocol': spec, 'verification_feedback': False,
        'versions': {n: importlib.metadata.version(n) for n in ('mlx', 'mlx-lm', 'transformers', 'numpy')}})
    inhibitor = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(os.getpid())])
    try:
        report = run_suite(args.fixtures, args.protocol, args.model_dir, args.out / 'suite',
                           args.arm, args.adapter_dir)
        print(report['primary'], 'workflow;', report['independent'], 'independent repair')
    finally:
        inhibitor.terminate()
        save(args.out / 'cleanup.json', {'caffeinate_returncode': inhibitor.wait(timeout=10)})


if __name__ == '__main__':
    main()
