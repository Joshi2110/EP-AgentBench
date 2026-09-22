import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from epbench import TASKS, TASK_FILES, __version__
from epbench.cli import init

ROOT = Path(__file__).resolve().parents[1]


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="epbench cli ")
        self.addCleanup(self.directory.cleanup)
        self.cwd = Path(self.directory.name)
        self.executable = shutil.which("epbench")
        self.assertIsNotNone(self.executable, "Install the package before running tests")

    def run_cli(self, *args):
        result = subprocess.run(
            [self.executable, *map(str, args)], cwd=self.cwd,
            capture_output=True, text=True, timeout=60,
        )
        self.assertNotIn("Traceback", result.stderr)
        return result

    def test_list_and_version(self):
        result = self.run_cli("list")
        self.assertEqual(result.returncode, 0)
        self.assertEqual({line.split()[0] for line in result.stdout.splitlines()}, set(TASKS))
        self.assertEqual(self.run_cli("--version").stdout.strip(), f"epbench {__version__}")

    def test_init_all_tasks_only_exports_public_files(self):
        for task in TASKS:
            with self.subTest(task=task):
                result = self.run_cli("init", task, "--out", task)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual({p.name for p in (self.cwd / task).iterdir()}, set(TASK_FILES[task]))
        result = self.run_cli("init", "axial-field", "--out", "axial-field")
        self.assertEqual(result.returncode, 2)
        empty = self.cwd / "empty"
        empty.mkdir()
        self.assertEqual(self.run_cli("init", "axial-field", "--out", empty).returncode, 0)

    def test_quick_start_and_json_report(self):
        self.assertEqual(self.run_cli("init", "ion-acceleration", "--out", "my-first-task").returncode, 0)
        result = self.run_cli(
            "grade", "ion-acceleration", "--solution", "my-first-task/starter.py",
            "--json-out", "results/first.json",
        )
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "failed")
        self.assertEqual((self.cwd / "results/first.json").read_text(), result.stdout)
        self.assertIn("2/10 cases passed", result.stderr)
        self.assertEqual(report["schema_version"], 1)

    def test_reference_grading(self):
        for task in TASKS:
            with self.subTest(task=task):
                name = task if task.startswith("hall-") else f"{task}.py"
                result = self.run_cli("grade", task, "--solution", ROOT / "examples/solutions" / name)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "passed")

    def test_bad_arguments_and_paths(self):
        (self.cwd / "file").write_text("keep")
        cases = [
            (), ("init", "unknown", "--out", "task"),
            ("grade", "unknown", "--solution", "missing.py"),
            ("grade", "axial-field", "--solution", "missing.py"),
            ("grade", "axial-field", "--solution", "."),
            ("grade", "axial-field", "--solution", "file", "--timeout", "nan"),
            ("grade", "axial-field", "--solution", "file", "--timeout", "0"),
            ("init", "axial-field", "--out", "file"),
        ]
        for args in cases:
            with self.subTest(args=args):
                self.assertEqual(self.run_cli(*args).returncode, 2)
        self.assertEqual((self.cwd / "file").read_text(), "keep")
        self.assertFalse((self.cwd / "task").exists())
        with self.assertRaises(ValueError):
            init("unknown", self.cwd / "task")
        self.assertFalse((self.cwd / "task").exists())

    def test_broken_python_produces_failed_report(self):
        source = self.cwd / "broken.py"
        source.write_text("def solve(:")
        result = self.run_cli("grade", "axial-field", "--solution", source)
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["passed"], 0)
        self.assertTrue(all(case["status"] == "runtime_error" for case in report["cases"]))

    def test_report_cannot_overwrite_submission(self):
        source = self.cwd / "source.py"
        source.write_text("do not overwrite")
        link = self.cwd / "alias.py"
        link.symlink_to(source)
        hardlink = self.cwd / "hardlink.py"
        hardlink.hardlink_to(source)
        for destination in (source, link, hardlink):
            with self.subTest(destination=destination):
                result = self.run_cli("grade", "axial-field", "--solution", source, "--json-out", destination)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["status"], "error")
        self.assertEqual(source.read_text(), "do not overwrite")

    def test_unwritable_report_path(self):
        blocker = self.cwd / "file"
        blocker.write_text("keep")
        result = self.run_cli(
            "grade", "axial-field", "--solution", ROOT / "examples/solutions/axial-field.py",
            "--json-out", blocker / "report.json",
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "error")
        self.assertEqual(blocker.read_text(), "keep")

    def test_evaluate_requires_a_supported_task_model_and_budget(self):
        self.assertIn("evaluate", self.run_cli("--help").stdout)
        for args in (
            ("evaluate", "hall-transport", "--out", "runs"),
            ("evaluate", "hall-transport", "--model", "m"),
            ("evaluate", "ion-acceleration", "--out", "runs", "--model", "m"),
        ):
            with self.subTest(args=args):
                result = subprocess.run([self.executable, *args], cwd=self.cwd,
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.cwd / "runs").exists())

    def test_module_entry_point(self):
        result = subprocess.run(
            [sys.executable, "-m", "epbench.cli", "list"], cwd=self.cwd,
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("axial-field", result.stdout)

    def test_hall_directory_grading_and_json(self):
        self.assertEqual(self.run_cli("init", "hall-transport", "--out", "hall task").returncode, 0)
        result = self.run_cli("grade", "hall-transport", "--solution", "hall task", "--json-out", "results/hall.json")
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual((report["passed"], report["total"]), (2, 13))
        self.assertEqual((self.cwd / "results/hall.json").read_text(), result.stdout)
        for case in report["cases"]:
            self.assertTrue(case["diagnostics"])
        result = self.run_cli("grade", "hall-transport", "--solution", "hall task", "--timeout", "0.000001")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(all(case["status"] == "timeout" for case in json.loads(result.stdout)["cases"]))

    def test_hall_report_stays_outside_workspace(self):
        path = self.cwd / "hall"
        init("hall-transport", path)
        original = (path / "model.py").read_bytes()
        alias = self.cwd / "alias.json"
        alias.symlink_to(path / "model.py")
        hardlink = self.cwd / "hardlink.json"
        hardlink.hardlink_to(path / "model.py")
        for destination in (path / "report.json", path / "model.py", alias, hardlink):
            with self.subTest(destination=destination):
                result = self.run_cli("grade", "hall-transport", "--solution", path, "--json-out", destination)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["status"], "error")
        self.assertEqual((path / "model.py").read_bytes(), original)
        self.assertFalse((path / "report.json").exists())

    def test_hall_bad_workspace_and_broken_module(self):
        path = self.cwd / "hall"
        path.mkdir()
        for submission in (path, path / "missing", ROOT / "examples/solutions/axial-field.py"):
            result = self.run_cli("grade", "hall-transport", "--solution", submission)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "error")
        init("hall-transport", path)
        (path / "model.py").write_text("def solve(:")
        result = self.run_cli("grade", "hall-transport", "--solution", path)
        self.assertEqual(result.returncode, 1)
        cases = json.loads(result.stdout)["cases"]
        self.assertTrue(all(case["status"] == "runtime_error" for case in cases if case["kind"] != "mobility"))
