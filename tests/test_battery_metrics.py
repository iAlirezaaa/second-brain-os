"""Measured HADES battery evidence: a child run, not a typed count (issue #53)."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "battery_metrics.py"


class BatteryMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.battery = Path(self.tmp.name) / "fake_battery.py"

    def run_probe(self, body=None, path=None, timeout=3):
        if body is not None:
            self.battery.write_text(body, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--battery", str(path or self.battery),
             "--timeout", str(timeout)],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
        try:
            data = json.loads(proc.stdout)
        except ValueError:
            self.fail("no valid JSON result: %r / %r" % (proc.stdout, proc.stderr))
        return proc, data

    def test_real_child_result_has_count_and_source_hash(self):
        code = "print('checks: 3 | passed: 3 | failed: 0')\n"
        result, data = self.run_probe(code)
        self.assertEqual(result.returncode, 0, data)
        self.assertEqual(data["status"], "verified")
        self.assertEqual((data["checks"], data["passed"], data["failed"]), (3, 3, 0))
        self.assertEqual(data["battery_sha256"], hashlib.sha256(code.encode()).hexdigest())

    def test_zero_count_is_not_success(self):
        result, data = self.run_probe("print('checks: 0 | passed: 0 | failed: 0')\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(data["status"], "invalid")
        self.assertIsNone(data["checks"])

    def test_missing_summary_is_unknown(self):
        result, data = self.run_probe("print('all tests passed')\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(data["checks"])

    def test_inconsistent_or_malformed_summaries_are_refused(self):
        for summary in ("checks: 3 | passed: 2 | failed: 0",
                        "checks: -3 | passed: 3 | failed: 0",
                        "checks: 3 | passed: three | failed: 0"):
            with self.subTest(summary=summary):
                result, data = self.run_probe("print(%r)\n" % summary)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(data["status"], "invalid")

    def test_explicit_failure_cannot_hide_beneath_green_summary(self):
        result, data = self.run_probe("print('    FAIL harness: broken')\n"
                                      "print('checks: 3 | passed: 3 | failed: 0')\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(data["status"], "invalid")

    def test_nonzero_child_exit_is_failure(self):
        result, data = self.run_probe("print('checks: 3 | passed: 3 | failed: 0')\n"
                                      "raise SystemExit(2)\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(data["status"], "invalid")

    def test_duplicate_summary_is_ambiguous(self):
        result, data = self.run_probe("print('checks: 3 | passed: 3 | failed: 0')\n" * 2)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(data["status"], "invalid")

    def test_missing_script_is_unknown(self):
        result, data = self.run_probe(path=Path(self.tmp.name) / "absent.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(data["checks"])

    def test_timeout_is_unknown(self):
        result, data = self.run_probe("import time\ntime.sleep(4)\n", timeout=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(data["status"], "invalid")
        self.assertIsNone(data["checks"])


if __name__ == "__main__":
    unittest.main()
