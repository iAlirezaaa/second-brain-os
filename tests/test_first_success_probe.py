"""Smoke the first-success probe without touching a real brain or network."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
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

        # A single installed-home trial has ONE wall-clock budget. Otherwise
        # install + ingest + search can each consume the full per-stage timeout.
        from types import SimpleNamespace
        from unittest.mock import patch

        clock = [100.0]
        observed_timeouts = []

        def fake_run(argv, **kwargs):
            observed_timeouts.append(kwargs["timeout"])
            clock[0] += 0.6
            if "--target" in argv:
                destination = Path(argv[argv.index("--target") + 1])
                (destination / "scripts").mkdir(parents=True)
                (destination / "scripts" / "kb.py").write_text(
                    "# Synthetic installed CLI placeholder\\n", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="indexed 2 notes", stderr="")

        with patch.object(first_success.time, "perf_counter",
                          side_effect=lambda: clock[0]):
            with patch.object(first_success.subprocess, "run", side_effect=fake_run):
                budget = first_success.installed_home_trial(
                    ROOT / "scripts" / "install.py", timeout=1.0)
        self.assertEqual(budget["reason"], "timeout", budget)
        self.assertEqual(len(observed_timeouts), 2,
                         "search must not launch after the shared trial deadline")
        self.assertGreater(observed_timeouts[0], observed_timeouts[1])

        # The default (non-install) smoke also needs ONE total deadline.
        # Old behavior allowed ingest and search a full timeout each and
        # accepted a late search as a merely missing-index failure.
        clock = [200.0]
        keyword_timeouts = []

        def fake_keyword_run(argv, **kwargs):
            keyword_timeouts.append(kwargs["timeout"])
            clock[0] += 0.6
            return SimpleNamespace(returncode=0, stdout="indexed 2 notes", stderr="")

        with patch.object(first_success.time, "perf_counter",
                          side_effect=lambda: clock[0]):
            with patch.object(first_success.subprocess, "run",
                              side_effect=fake_keyword_run):
                keyword_budget = first_success.trial(KB, timeout=1.0)
        self.assertEqual(keyword_budget["reason"], "timeout", keyword_budget)
        self.assertEqual(len(keyword_timeouts), 2)
        self.assertGreater(keyword_timeouts[0], keyword_timeouts[1])

        # A synthetic install can finish all subprocesses within budget while
        # SQLite verification itself runs past the deadline. The report must
        # not claim a successful, bounded first-recall run.
        from contextlib import closing
        from types import SimpleNamespace
        from unittest.mock import patch

        clock = [500.0]
        real_connect = first_success.sqlite3.connect

        def late_verification_connect(*args, **kwargs):
            clock[0] += 1.1
            return real_connect(*args, **kwargs)

        def valid_install_and_recall(argv, **kwargs):
            if "--target" in argv:
                home = Path(argv[argv.index("--target") + 1])
                (home / "scripts").mkdir(parents=True)
                (home / "scripts" / "kb.py").write_text(
                    "# Synthetic installed KB\\n", encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout="installed", stderr="")
            if "ingest" in argv:
                home = Path(kwargs["cwd"])
                cache = home / ".kb" / "kb.sqlite"
                cache.parent.mkdir(parents=True)
                with closing(real_connect(str(cache))) as conn, conn:
                    conn.execute("CREATE TABLE notes (path TEXT, body TEXT)")
                    for name in ("demo.md", "distractor.md"):
                        rel = "02_WIKI/" + name
                        body = (home / rel).read_text(encoding="utf-8")
                        conn.execute("INSERT INTO notes VALUES (?, ?)", (rel, body))
                return SimpleNamespace(returncode=0, stdout="indexed 2 notes",
                                       stderr="")
            return SimpleNamespace(returncode=0,
                                   stdout="02_WIKI/demo.md [synthetic]\\n",
                                   stderr="")

        with patch.object(first_success.time, "perf_counter",
                          side_effect=lambda: clock[0]):
            with patch.object(first_success.subprocess, "run",
                              side_effect=valid_install_and_recall):
                with patch.object(first_success.sqlite3, "connect",
                                  side_effect=late_verification_connect):
                    late = first_success.installed_home_trial(
                        ROOT / "scripts" / "install.py", timeout=1)
        self.assertFalse(late["success"], late)
        self.assertEqual(late["reason"], "timeout", late)

        # False-green fixture: a forged installed CLI prints the expected
        # index/search lines and creates a fake SQLite file, with no real rows.
        # This used to be reported as a successful first recall.
        def forged_install_and_recall(argv, **kwargs):
            from types import SimpleNamespace
            if "--target" in argv:
                home = Path(argv[argv.index("--target") + 1])
                (home / "scripts").mkdir(parents=True)
                (home / "scripts" / "kb.py").write_text(
                    "# Synthetic placeholder\n", encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout="installed", stderr="")
            if "ingest" in argv:
                cache = Path(kwargs["cwd"]) / ".kb" / "kb.sqlite"
                cache.parent.mkdir(parents=True)
                cache.write_bytes(b"not a real sqlite index")
                return SimpleNamespace(returncode=0, stdout="indexed 2 notes", stderr="")
            return SimpleNamespace(
                returncode=0, stdout="02_WIKI/demo.md [synthetic]\n", stderr="")

        with patch.object(first_success.subprocess, "run",
                          side_effect=forged_install_and_recall):
            forged = first_success.installed_home_trial(ROOT / "scripts" / "install.py")
        self.assertFalse(forged["success"],
                         "a printed keyword hit with a corrupt index is not retrieval")
        self.assertEqual(forged["reason"], "unexpected_search_or_index")

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


if __name__ == "__main__":
    unittest.main()
