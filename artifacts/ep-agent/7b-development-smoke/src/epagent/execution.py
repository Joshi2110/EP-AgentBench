"""Constrained macOS Python execution; never fall back to unrestricted execution."""

import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

BOOTSTRAP = """import os, resource, sys
resource.setrlimit(resource.RLIMIT_FSIZE, (2000000, 2000000))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
sys.path.insert(0, os.getcwd())
exec(compile(sys.stdin.read(), '<agent-python>', 'exec'), {'__name__': '__main__'})
"""


def interpreter():
    return str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())


def profile(workspace):
    if sys.platform != "darwin" or not Path('/usr/bin/sandbox-exec').is_file():
        raise RuntimeError("Python execution requires the verified macOS development profile")
    workspace = Path(workspace).resolve()
    prefix = Path(sys.base_prefix).resolve()
    if workspace.is_relative_to(prefix) or prefix.is_relative_to(workspace):
        raise ValueError("Workspace must not overlap the Python runtime")
    q = json.dumps
    # dyld needs the root directory descriptor. Metadata is readable, private
    # file contents/directories are not. No process-fork/network/Mach allowance.
    return f'''(version 1)
(deny default)
(allow file-read-metadata)
(allow sysctl-read)
(allow process-exec (subpath {q(str(prefix))}))
(allow file-read-data (literal "/") (subpath {q(str(prefix))})
 (subpath {q(str(workspace))}) (subpath "/System") (subpath "/usr/lib")
 (literal "/dev/null") (literal "/dev/urandom"))
(allow file-write* (subpath {q(str(workspace))}))
'''


def environment(workspace):
    return {"HOME": str(workspace), "TMPDIR": str(workspace), "LANG": "en_US.UTF-8",
            "PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"}


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_python(workspace, code, seconds=8, output_bytes=8192):
    command = ['/usr/bin/sandbox-exec', '-p', profile(workspace), interpreter(),
               '-I', '-S', '-B', '-c', BOOTSTRAP]
    started = time.monotonic()
    output = {"stdout": bytearray(), "stderr": bytearray()}
    status = "completed"
    with subprocess.Popen(command, cwd=workspace, env=environment(workspace), stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True) as process:
        try:
            try:
                process.stdin.write(code.encode())
                process.stdin.close()
            except BrokenPipeError:
                pass
            with selectors.DefaultSelector() as selector:
                for stream, name in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
                    selector.register(stream, selectors.EVENT_READ, name)
                while selector.get_map():
                    left = seconds - (time.monotonic() - started)
                    if left <= 0:
                        status = "timeout"
                        break
                    for key, _ in selector.select(min(left, 0.1)):
                        data = os.read(key.fileobj.fileno(), 8192)
                        if not data:
                            selector.unregister(key.fileobj)
                        remaining = output_bytes - sum(len(v) for v in output.values())
                        output[key.data].extend(data[:remaining])
                        if len(data) > remaining:
                            status = "output_limit"
                            break
                    if status != "completed":
                        break
                if status == "completed":
                    try:
                        process.wait(timeout=max(0.001, seconds - (time.monotonic() - started)))
                    except subprocess.TimeoutExpired:
                        status = "timeout"
        finally:
            stop(process)
    if status == "completed" and process.returncode:
        status = "python_error"
    return {"status": status, "returncode": process.returncode,
            **{k: bytes(v).decode(errors='replace') for k, v in output.items()},
            "elapsed_seconds": round(time.monotonic() - started, 4)}


def preflight(workspace, withheld):
    code = '''import importlib.util, os, pathlib, socket, subprocess
p = pathlib.Path('.probe')
p.write_text('ok'); assert p.read_text() == 'ok'; p.unlink()
assert importlib.util.find_spec('epbench') is None
for name in %r:
    try:
        pathlib.Path(name).read_bytes()
    except PermissionError:
        pass
    else:
        raise AssertionError('private file readable')
try:
    socket.socket().connect(('127.0.0.1', 9))
except PermissionError:
    pass
else:
    raise AssertionError('network allowed')
try:
    os.fork()
except PermissionError:
    pass
else:
    raise AssertionError('fork allowed')
print('EPAGENT_PREFLIGHT_OK')
''' % [str(Path(p).resolve()) for p in withheld]
    result = run_python(workspace, code, seconds=10)
    if result['status'] != 'completed' or result['stdout'].strip() != 'EPAGENT_PREFLIGHT_OK':
        raise RuntimeError("EP-Agent execution preflight failed; no agent was started")
    return {"mode": "macos-constrained-development", "verified": True,
            "private_reads": "denied", "network": "denied", "fork": "denied",
            "limitations": "System runtime reads and file metadata remain available; not a production security boundary."}
