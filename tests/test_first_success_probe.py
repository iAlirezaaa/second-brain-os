"""Smoke the first-success probe without touching a real brain or network."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
import os
import subprocess
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "first_success.py"
KB = ROOT / "scripts" / "kb.py"
spec = importlib.util.spec_from_file_location("first_success", SCRIPT)
first_success = importlib.util.module_from_spec(spec)
spec.loader.exec_module(first_success)


class FirstRecallProbe(unittest.TestCase):
    def test_real_cli_measures_synthetic_recall(self):
        report = first_success.evaluate(2, KB)
        self.assertEqual(report["probe"], "synthetic_keyword_ingest_then_recall")
        self.assertEqual(report["status"], "pass", report)
        self.assertEqual(report["successes"], 2)
        self.assertEqual(report["success_rate"], 1.0)
        self.assertGreaterEqual(report["median_ms"], 0)
        self.assertTrue(all(t["matched_paths"] == ["02_WIKI/demo.md"] for t in report["trials"]))

    def test_missing_cli_is_a_failure_not_a_false_success(self):
        with tempfile.TemporaryDirectory() as directory:
            report = first_success.evaluate(1, Path(directory) / "absent_kb.py")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["success_rate"], 0)
        self.assertFalse(report["trials"][0]["success"])

    def test_invalid_repeat_cannot_run_unbounded_probes(self):
        for repeat in ("0", "11", "garbage"):
            with self.subTest(repeat=repeat), self.assertRaises(SystemExit) as error:
                first_success.main(["--repeat", repeat])
            self.assertEqual(error.exception.code, 2)

    def test_json_cli_returns_machine_readable_metrics(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = first_success.main(["--repeat", "1"])
        report = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["repeat"], 1)
        self.assertNotIn("sbo-first-recall-", output.getvalue())

        # Real KB subprocesses, with a synthetic canary in the parent shell.
        # Without an explicit env= these inherit credentials and PYTHONPATH.
        observed_envs = []
        actual_run = subprocess.run

        def capture_and_run(*args, **kwargs):
            observed_envs.append(kwargs.get("env"))
            return actual_run(*args, **kwargs)

        with mock.patch.dict(os.environ, {
                "SBO_FIRST_RECALL_SECRET_CANARY": "synthetic-only",
                "PYTHONPATH": "synthetic-untrusted-import-root"}):
            with mock.patch.object(first_success.subprocess, "run",
                                   side_effect=capture_and_run):
                canary_report = first_success.evaluate(1, KB)
        self.assertEqual(canary_report["status"], "pass", canary_report)
        self.assertEqual(len(observed_envs), 2)  # ingest and search
        for child_env in observed_envs:
            self.assertIsNotNone(child_env, "child inherited caller environment")
            self.assertNotIn("SBO_FIRST_RECALL_SECRET_CANARY", child_env)
            self.assertNotIn("PYTHONPATH", child_env)
            self.assertEqual(child_env["PYTHONIOENCODING"], "utf-8")
            self.assertEqual(child_env["PYTHONNOUSERSITE"], "1")


if __name__ == "__main__":
    unittest.main()
