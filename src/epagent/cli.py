"""Small local-only EP-Agent command line."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from epbench.grader import WORKSPACES
from . import __version__
from .episode import Config, run_episode
from .mlx_backend import MLXBackend, download


def main(argv=None):
    parser = argparse.ArgumentParser(prog='epagent', description='Local open-weight scientific coding agent')
    parser.add_argument('--version', action='version', version=f'epagent {__version__}')
    commands = parser.add_subparsers(dest='command', required=True)
    get = commands.add_parser('download', help='Download the reviewed pinned model (less than 2 GB)')
    get.add_argument('--out', type=Path, required=True)
    run = commands.add_parser('run', help='Run exactly one local MLX episode; no automatic retries')
    run.add_argument('task', choices=sorted(WORKSPACES))
    run.add_argument('--model-dir', type=Path, required=True)
    run.add_argument('--out', type=Path, required=True)
    for name, default in asdict(Config()).items():
        run.add_argument('--' + name.replace('_', '-'), type=str if default is None else type(default), default=default)
    synthetic = commands.add_parser('synthetic', help='Run one registered synthetic evaluation arm; no retries')
    for name in ['model-dir', 'out', 'fixtures', 'protocol']:
        synthetic.add_argument('--' + name, type=Path, required=True)
    synthetic.add_argument('--arm', choices=['base', 'adapted'], required=True)
    synthetic.add_argument('--adapter-dir')
    args = parser.parse_args(argv)
    try:
        if args.command == 'download':
            print(json.dumps(download(args.out), indent=2))
            return 0
        if args.command == 'synthetic':
            from .synthetic import run_suite
            report = run_suite(args.fixtures, args.protocol, args.model_dir, args.out, args.arm, args.adapter_dir)
            print(json.dumps(report, indent=2))
            return 0 if report['scorable_cases'] == report['registered_cases'] else 1
        config = Config(**{key: getattr(args, key) for key in asdict(Config())})
        config.validate()
        backend = MLXBackend(args.model_dir, asdict(config))
        report = run_episode(args.task, args.out, backend, config)
        print(json.dumps(report, indent=2))
        return 0 if report['status'] == 'finished' and report['scored'] else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'epagent: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
