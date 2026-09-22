"""One fresh Codex CLI session behind a filesystem and network boundary we verify."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

BUNDLED = ("/Applications/ChatGPT.app/Contents/Resources/codex", "~/.codex/plugins/.plugin-appserver/codex")
REQUIRED_FLAGS = ("--ephemeral", "--json", "--ignore-rules", "--skip-git-repo-check", "--model", "--cd")
PROBE = """
import importlib.util, pathlib, socket, sys

def check():
    try:
        pathlib.Path('.epbench-probe').write_text('ok')
        pathlib.Path('.epbench-probe').unlink()
    except OSError as exc:
        return 'workspace is not writable: %s' % exc.strerror
    if importlib.util.find_spec('epbench') is not None:
        return 'benchmark package is importable'
    import os
    for entry in sys.argv[1:]:
        kind, name = entry[0], entry[2:]
        try:
            os.listdir(name) if kind == 'd' else pathlib.Path(name).read_bytes()
        except PermissionError:
            continue
        except OSError as exc:
            return 'unexpected errno %s for %s' % (exc.errno, name)
        return 'readable: %s' % name
    try:
        socket.socket().connect(('93.184.216.34', 80))
    except PermissionError:
        return None
    except OSError as exc:
        return 'network denial unconfirmed (errno %s)' % exc.errno
    return 'network reachable'

reason = check()
print('EPBENCH_PREFLIGHT_OK' if reason is None else 'EPBENCH_PREFLIGHT_FAIL ' + reason)
raise SystemExit(0 if reason is None else 1)
"""


@dataclass
class Launch:
    command: list[str]
    environment: dict[str, str]
    metadata: dict
    secrets: tuple[str, ...] = ()


def locate() -> str:
    """Codex is often installed as an app bundle rather than on PATH."""
    candidates = [os.environ["EPBENCH_CODEX"]] if os.environ.get("EPBENCH_CODEX") else []
    on_path = shutil.which("codex")
    if on_path:
        candidates.append(on_path)
    candidates += [os.path.expanduser(path) for path in BUNDLED]
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
    raise RuntimeError("Codex CLI not found; install it or set EPBENCH_CODEX to its path")


def _secrets(value, found: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, str) and child and any(w in key.lower() for w in ("token", "key", "secret")):
                found.append(child)
            else:
                _secrets(child, found)
    elif isinstance(value, list):
        for child in value:
            _secrets(child, found)


def prepare(workspace: Path, control: Path, model: str, unreadable: list[Path]) -> Launch:
    """Build a self-contained Codex home and refuse to launch unless the boundary holds."""
    executable = locate()
    version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    help_text = subprocess.run([executable, "exec", "--help"], capture_output=True, text=True, timeout=30, check=True).stdout
    missing = [flag for flag in REQUIRED_FLAGS if flag not in help_text]
    if missing:
        raise RuntimeError(f"Installed Codex lacks required options: {' '.join(missing)}")

    source_auth = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json"
    if not source_auth.is_file():
        raise RuntimeError("Codex has no file-based credentials (auth.json); run codex login first")
    auth_bytes = source_auth.read_bytes()
    found: list[str] = []
    _secrets(json.loads(auth_bytes), found)

    home = control / "codex-home"
    home.mkdir(mode=0o700)
    home.joinpath("auth.json").write_bytes(auth_bytes)
    home.joinpath("auth.json").chmod(0o600)

    interpreter = Path(getattr(sys, "_base_executable", None) or sys.executable).resolve()
    prefix = Path(sys.base_prefix).resolve()
    runtime = control / "bin"
    runtime.mkdir(mode=0o755)
    for name in ("python", "python3"):
        wrapper = runtime / name
        wrapper.write_text(f'#!/bin/sh\nexec {shlex.quote(str(interpreter))} -S "$@"\n')
        wrapper.chmod(0o755)

    shell_env = {
        "PATH": f"{runtime}:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(workspace), "TMPDIR": str(workspace), "PYTHONNOUSERSITE": "1",
    }
    config = [
        'approval_policy = "never"', 'default_permissions = "evaluation"',
        'web_search = "disabled"', 'project_doc_max_bytes = 0',
        '[shell_environment_policy]', 'inherit = "none"', '[shell_environment_policy.set]',
        *(f"{key} = {json.dumps(value)}" for key, value in shell_env.items()),
        '[permissions.evaluation.filesystem]', '":minimal" = "read"', '":workspace_roots" = "write"',
        *(f'{json.dumps(str(path))} = "read"' for path in (prefix, runtime)),
        '[permissions.evaluation.network]', 'enabled = false',
    ]
    config_text = "\n".join(config) + "\n"
    home.joinpath("config.toml").write_text(config_text)
    # A private CODEX_HOME keeps prior conversations, skills, MCP servers and user rules out of the run.
    environment = shell_env | {"CODEX_HOME": str(home), "LANG": "en_US.UTF-8", "SHELL": "/bin/sh"}

    # The agent must not reach the credentials we just copied, nor the originals, while it runs.
    credentials = [home / "auth.json", source_auth]
    hidden = [f"f:{Path(path).resolve()}" for path in [*unreadable, *credentials]]
    hidden += [f"d:{Path(path).resolve()}" for path in (home, control)]
    probe = subprocess.run(
        [executable, "sandbox", "-P", "evaluation", "-C", str(workspace),
         str(interpreter), "-I", "-S", "-B", "-c", PROBE, *hidden],
        env=environment, capture_output=True, text=True, timeout=120,
    )
    verdict = probe.stdout.strip().splitlines()[-1:] or [""]
    if probe.returncode or verdict[0] != "EPBENCH_PREFLIGHT_OK":
        # Surface only the probe's own verdict; sandbox stderr can echo local configuration.
        reason = verdict[0].removeprefix("EPBENCH_PREFLIGHT_FAIL ") or "no preflight verdict"
        raise RuntimeError(f"Codex isolation preflight failed ({reason}); no agent was launched")

    command = [
        executable, "exec", "--json", "--ephemeral", "--ignore-rules", "--skip-git-repo-check",
        "--color", "never", "--model", model, "--cd", str(workspace), "-",
    ]
    return Launch(command, environment, {
        "name": "codex", "version": version, "model_requested": model, "model_observed": None,
        "isolation": "codex permission profile; preflight verified", "config": config_text,
    }, tuple(found))
