"""Live checks against the installed Codex CLI; skipped where it is unavailable."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from epbench import codex_backend

ROOT = Path(__file__).resolve().parents[1]


def _available():
    try:
        codex_backend.locate()
    except RuntimeError:
        return False
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return (home / "auth.json").is_file()


@unittest.skipUnless(_available(), "Codex CLI with file credentials is not installed")
class TestLiveIsolation(unittest.TestCase):
    def setUp(self):
        # Must sit outside TMPDIR, which the permission profile leaves readable.
        base = Path(tempfile.mkdtemp(prefix=".isolation-", dir=ROOT))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        self.workspace, self.control = base / "ws", base / "control"
        self.workspace.mkdir()
        self.control.mkdir()
        self.launch = codex_backend.prepare(
            self.workspace, self.control, "test-model", [ROOT / "src" / "epbench" / "hall.py"])

    def denied(self, *command):
        result = subprocess.run(
            [codex_backend.locate(), "sandbox", "-P", "evaluation", "-C", str(self.workspace), *command],
            env=self.launch.environment, capture_output=True, text=True, timeout=60)
        return result.returncode != 0 and "auth.json" not in result.stdout

    def test_copied_credentials_are_unreadable_while_the_agent_runs(self):
        auth = self.control / "codex-home" / "auth.json"
        self.assertTrue(auth.is_file(), "the backend must still authenticate from a private home")
        self.assertTrue(self.denied("/bin/cat", str(auth)))
        self.assertTrue(self.denied("/bin/cat", str(self.control / "bin" / ".." / "codex-home" / "auth.json")))
        self.assertTrue(self.denied("/bin/ls", str(self.control / "codex-home")))
        self.assertTrue(self.denied("/usr/bin/find", str(self.control), "-name", "auth.json"))

    def test_host_credentials_and_withheld_cases_are_unreadable(self):
        host = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json"
        self.assertTrue(self.denied("/bin/cat", str(host)))
        self.assertTrue(self.denied("/bin/cat", str(ROOT / "src" / "epbench" / "hall.py")))

    def test_preflight_refuses_when_a_withheld_path_is_readable(self):
        # /tmp stays readable under the minimal profile; TMPDIR is remapped and does not.
        readable = Path(tempfile.mkdtemp(prefix="epbench-readable-", dir="/tmp")) / "cases.py"
        self.addCleanup(shutil.rmtree, readable.parent, ignore_errors=True)
        readable.write_text("cases = []\n")
        workspace, control = self.workspace.parent / "ws2", self.workspace.parent / "control2"
        workspace.mkdir()
        control.mkdir()
        with self.assertRaises(RuntimeError) as caught:
            codex_backend.prepare(workspace, control, "test-model", [readable])
        self.assertIn("no agent was launched", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
