import glob
import json
from pathlib import Path
import sys
import tempfile
import unittest

from epbench import TASK_FILES, evaluation
from epbench.evaluation import PROMPT, PROTOCOLS
from epbench.trace_audit import audit, classify

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_evaluation import AGENT, MockBackend, REFERENCE  # noqa: E402


def rendered(task, protocol):
    title = evaluation.EVALUABLE[task][0]
    edits = [f for f in TASK_FILES[task] if f not in ("README.md", "run.py")]
    return PROMPT.format(title=title, files=" and ".join(edits)) + PROTOCOLS[protocol]


class TestConditions(unittest.TestCase):
    def test_baseline_is_byte_identical_to_experiment_01(self):
        stored = sorted(glob.glob(str(ROOT / "attempts/experiment-01/*/prompt.txt")))
        if not stored:
            self.skipTest("Experiment 01 records are not present")
        self.assertEqual(rendered("hall-transport", "baseline"), Path(stored[0]).read_text())

    def test_conditions_differ_only_by_the_intervention(self):
        for task in evaluation.EVALUABLE:
            with self.subTest(task=task):
                a, b = rendered(task, "baseline"), rendered(task, "structured")
                self.assertTrue(b.startswith(a), "B must extend A, never edit it")
                self.assertEqual(b[len(a):], PROTOCOLS["structured"])
        self.assertEqual(PROTOCOLS["baseline"], "")
        block = PROTOCOLS["structured"]
        # Frozen literal: any drift in the intervention invalidates the comparison.
        self.assertEqual(block, "\n".join([
            "",
            "Run each verification check as its own shell command, not chained after another",
            "command. Make each check print one line of the form",
            "EPBENCH_CHECK <name> PASS or EPBENCH_CHECK <name> FAIL.",
            "In your final message, report only checks that printed such a line.",
            "",
        ]))
        self.assertEqual(block.strip().count("."), 3, "three sentences, as written in the design")
        for reserved in ("mobility", "momentum", "ionization", "u_n", "sigma", "threshold",
                         "tolerance", "13", "conservation", "Maxwell"):
            self.assertNotIn(reserved.lower(), block.lower(), "must add no physics or reserved detail")

    def test_report_records_the_condition(self):
        for protocol in PROTOCOLS:
            with self.subTest(protocol=protocol), tempfile.TemporaryDirectory() as directory:
                report = evaluation.evaluate("hall-transport", Path(directory), "mock-model",
                                             seconds=90, protocol=protocol,
                                             backend=MockBackend("solve"))
                self.assertEqual(report["protocol"], protocol)
                self.assertEqual(report["status"], "success")
                attempt = Path(report["paths"]["workspace"]).parent
                self.assertEqual((attempt / "prompt.txt").read_text(),
                                 rendered("hall-transport", protocol))

    def test_unknown_protocol_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            evaluation.evaluate("hall-transport", Path(directory), "m", protocol="nope",
                                backend=MockBackend("idle"))

    def test_environment_is_identical_across_conditions(self):
        backends = {}
        for protocol in PROTOCOLS:
            with tempfile.TemporaryDirectory() as directory:
                backend = MockBackend("idle")
                report = evaluation.evaluate("hall-thrust", Path(directory), "same-model",
                                             seconds=90, protocol=protocol, backend=backend)
                backends[protocol] = (report["budget"], report["agent"]["model_requested"],
                                      sorted(p.name for p in backend.withheld),
                                      report["grading"]["result"]["total"])
        self.assertEqual(backends["baseline"], backends["structured"],
                         "budget, model, withheld files and grader must not differ")


class TestEvidenceAttribution(unittest.TestCase):
    def test_required_command_examples(self):
        cases = [
            ("attributable exit", '/bin/zsh -lc "python3 -c \'assert 1 == 1\'"', "", "single_program", True),
            ("silent assert then program",
             '/bin/zsh -lc "python3 - <<\'PY\'\nassert 1\nPY\npython3 run.py"', "", "masked", True),
            ("printed verdict", '/bin/zsh -lc "python3 c.py"',
             "EPBENCH_CHECK a PASS\nEPBENCH_CHECK b FAIL\n", "verdict", True),
            ("trailing git diff masks",
             '/bin/zsh -lc "python3 - <<\'PY\'\nassert 1\nPY\ngit diff -- a b"', "d\n", "masked", True),
            ("no checks", '/bin/zsh -lc "find . -type f | sort"', "./a\n", "none", False),
            ("truncated evidence", '/bin/zsh -lc "python3 c.py"',
             "EPBENCH_CHECK a PASS\n[output truncated]", "ambiguous", True),
            ("missing output", '/bin/zsh -lc "python3 -c \'assert True\'"', None, "single_program", True),
            ("unbalanced quote", '/bin/zsh -lc "python3 -c \'assert 1', "", "ambiguous", True),
            ("nested shell", '/bin/sh -c "bash -c \\"python3 -c \'assert 1\'\\""', "", "ambiguous", True),
        ]
        for name, command, output, attribution, checks in cases:
            with self.subTest(name=name):
                result = classify(command, output, 0)
                self.assertEqual(result["attribution"], attribution)
                self.assertEqual(result["checks"], checks)

    def test_a_printed_verdict_must_come_from_execution(self):
        # The same text in a final message, not in recorded output, is not evidence.
        self.assertEqual(classify('/bin/zsh -lc "python3 c.py"', "", 0)["attribution"], "none")
        claimed = classify('/bin/zsh -lc "echo done"', "done\n", 0)
        self.assertFalse(claimed["checks"], "claims alone never create evidence")

    def test_no_attempted_checks_is_undefined_not_perfect(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "t.jsonl"
            trace.write_text(json.dumps({"event": {"item": {
                "type": "command_execution", "exit_code": 0, "id": "c1",
                "command": '/bin/zsh -lc "ls"', "aggregated_output": "a\n"}}}) + "\n")
            result = audit(trace)
        self.assertEqual(result["attempted_checks"], 0)
        self.assertIsNone(result["rate"], "a run with no checks is not perfect verification")

    def test_rate_counts_only_attributable_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "t.jsonl"
            rows = [
                ('/bin/zsh -lc "python3 -c \'assert 1\'"', ""),
                ('/bin/zsh -lc "python3 - <<\'PY\'\nassert 1\nPY\ngit diff"', "d\n"),
            ]
            trace.write_text("".join(json.dumps({"event": {"item": {
                "type": "command_execution", "exit_code": 0, "id": f"c{i}",
                "command": c, "aggregated_output": o}}}) + "\n" for i, (c, o) in enumerate(rows)))
            result = audit(trace)
        self.assertEqual((result["attempted_checks"], result["attributable"], result["masked"]), (2, 1, 1))
        self.assertAlmostEqual(result["rate"], 0.5)

    def test_printed_outcome_counts_in_any_format(self):
        # A check that prints its own result is attributable whatever wording it uses;
        # crediting only the structured form would make the metric a compliance measure.
        masked = '/bin/zsh -lc "python3 - <<\'PY\'\nassert 1\nPY\npython3 run.py"'
        self.assertEqual(classify(masked, "all local checks passed\n{}\n", 0)["attribution"],
                         "printed_outcome")
        self.assertEqual(classify(masked, "{}\n", 0)["attribution"], "masked")
        self.assertEqual(classify(masked, '+        "ok": 1,\n', 0)["attribution"], "masked",
                         "source echo is not a printed outcome")

    def test_structured_verdicts_are_counted_separately(self):
        result = classify('/bin/zsh -lc "python3 c.py && echo done"', "EPBENCH_CHECK a PASS\n", 0)
        self.assertEqual(result["attribution"], "verdict")
        self.assertEqual(result["verdicts"], 1)

    def test_parser_tracks_the_manual_construct_on_archived_traces(self):
        traces = sorted(glob.glob(str(ROOT / "attempts/*/*/trace.jsonl")))
        if len(traces) < 20:
            self.skipTest("insufficient archived traces")
        means = {}
        for label, predicate in (("supported", lambda a: a["rate"] == 1.0),
                                 ("none", lambda a: a["rate"] == 0.0)):
            rates = [audit(Path(t))["rate"] for t in traces]
            means[label] = [r for r in rates if r is not None]
        rates = means["supported"]
        self.assertTrue(any(r == 1.0 for r in rates), "fully attributable runs exist")
        self.assertTrue(any(r == 0.0 for r in rates), "fully masked runs exist")
        self.assertGreater(sum(rates) / len(rates), 0.1,
                           "baseline must be reachable without the intervention")

    def test_archived_baseline_traces_parse_without_ambiguity(self):
        traces = sorted(glob.glob(str(ROOT / "attempts/*/*/trace.jsonl")))
        if not traces:
            self.skipTest("no archived traces")
        results = [audit(Path(t)) for t in traces]
        self.assertEqual(sum(r["ambiguous"] for r in results), 0)
        self.assertEqual(sum(r["verdict_lines"] for r in results), 0, "baseline emits no verdicts")
        self.assertTrue(any(r["attempted_checks"] for r in results))


if __name__ == "__main__":
    unittest.main()
