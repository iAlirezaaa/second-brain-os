"""Regression for issue #60: zero lessons cannot certify a source checkout.

A first-run installed home may legitimately have no recorded lessons, but the
source repository advertises a shipped evidence-backed ledger. A blanked ledger
must not pass its canonical health gate or machine-readable --json variant.
All fixtures are synthetic; neither test reads or edits private memory.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "memory.py"


def blank_memory_home(path, source_checkout):
    (path / "15_SYSTEM" / "memory").mkdir(parents=True)
    (path / "15_SYSTEM" / "memory" / "lessons.jsonl").write_text("", encoding="utf-8")
    (path / "MEMORY.md").write_text("# Empty memory\n", encoding="utf-8")
    if source_checkout:
        (path / "pyproject.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")


def call_check(path, *flags):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(path), "--check", *flags],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )


class TestEmptyMemoryLedgerGate(unittest.TestCase):
    def test_repo_checkout_blank_ledger_refuses_with_denominator(self):
        with tempfile.TemporaryDirectory(prefix="sbo-memory-gate-") as home:
            root = Path(home)
            blank_memory_home(root, source_checkout=True)
            result = call_check(root)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("REFUSED", result.stdout)
            self.assertIn("no lessons", result.stdout.lower())
            self.assertNotIn("OK — 0 lesson(s)", result.stdout)

    def test_json_gate_reports_same_refusal_as_text_gate(self):
        with tempfile.TemporaryDirectory(prefix="sbo-memory-gate-") as home:
            root = Path(home)
            blank_memory_home(root, source_checkout=True)
            result = call_check(root, "--json")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["lessons"], 0)
            self.assertTrue(any("no lessons" in p.lower() for p in payload["problems"]))

    def test_empty_installed_home_remains_valid(self):
        with tempfile.TemporaryDirectory(prefix="sbo-memory-home-") as home:
            root = Path(home)
            blank_memory_home(root, source_checkout=False)
            result = call_check(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("OK — 0 lesson(s)", result.stdout)


if __name__ == "__main__":
    unittest.main()
