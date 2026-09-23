"""Binary terminal reward using the existing independent verifier unchanged."""

from pathlib import Path
import subprocess
import stat
from types import SimpleNamespace

from epbench import grader
from .execution import environment, interpreter, profile


def grade_submission(task, workspace, timeout=5):
    """Restrict submitted worker code without changing cases or verification logic.

    The existing grader owns case generation, worker I/O, timeouts, and physical
    verification. Only its process launcher is scoped here, in this synchronous
    adapter, so model-generated Python is never re-executed unrestricted at grading.
    """
    original = grader.subprocess

    class Worker(subprocess.Popen):
        def communicate(self, *args, **kwargs):
            result = super().communicate(*args, **kwargs)
            # The unchanged trusted-local grader reads result.json in its parent.
            # Do not let generated code redirect that read to a private file.
            path = self.output_directory / 'result.json'
            if path.is_symlink() or (path.exists() and
                    (not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_nlink != 1)):
                raise ValueError('Grading worker created an unsafe result file')
            return result

    def launch(command, **kwargs):
        cwd = Path(kwargs['cwd']).resolve()
        expected = Path(grader.__file__).with_name('_worker.py').resolve()
        if len(command) != 5 or Path(command[3]).resolve() != expected:
            raise RuntimeError("Unexpected grader worker command")
        worker = cwd / '_epagent_worker.py'
        worker.write_bytes(expected.read_bytes())
        code = '''import resource, runpy, sys
resource.setrlimit(resource.RLIMIT_FSIZE, (2000000, 2000000))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
'''
        kwargs['env'] = environment(cwd)
        process = Worker(['/usr/bin/sandbox-exec', '-p', profile(cwd), interpreter(),
                          '-I', '-S', '-B', '-c', code, str(worker), command[4]], **kwargs)
        process.output_directory = cwd
        return process

    grader.subprocess = SimpleNamespace(Popen=launch, PIPE=subprocess.PIPE,
                                       DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)
    try:
        result = grader.grade(task, workspace, timeout=timeout)
    finally:
        grader.subprocess = original
    return {"reward": int(result['status'] == 'passed'), "reward_definition": "all verifier cases passed",
            "case_fraction_for_analysis_only": result['success_rate'], "grading": result}
