"""Onboarding contract: a fresh clone is navigable and local recall really works.

The integration test uses an isolated, synthetic vault and no network or model.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUMAN_ONBOARDING = ("README.md", "00_START_HERE/README_FA.md")
ONBOARDING = HUMAN_ONBOARDING + ("skills/first-session/SKILL.md",)


def clone_block(text):
    fence = chr(96) * 3
    blocks = re.findall(r"(?ms)^" + fence + r"[^\n]*\n(.*?)^" +
                        fence + r"[ \t]*$", text)
    return next((block for block in blocks if
                 "git clone https://github.com/iAlirezaaa/second-brain-os" in block), None)


class FirstSessionOnboarding(unittest.TestCase):
    def test_every_onboarding_clone_enters_its_actual_directory(self):
        for document in ONBOARDING:
            with self.subTest(document=document):
                text = (ROOT / document).read_text(encoding="utf-8")
                block = clone_block(text)
                self.assertIsNotNone(block, "Onboarding needs a copyable git clone block")
                clone = re.search(
                    r"(?m)^git clone https://github\.com/iAlirezaaa/"
                    r"(?P<repo>[a-zA-Z0-9_.-]+?)(?:\.git)?"
                    r"(?:\s+(?P<destination>[a-zA-Z0-9_.-]+))?\s*$", block)
                self.assertIsNotNone(clone, "Document the exact repository clone")
                cd = re.search(r"(?m)^cd ([a-zA-Z0-9_.-]+)\s*$", block)
                self.assertIsNotNone(cd, "Onboarding must enter the cloned directory")
                self.assertEqual(cd.group(1), clone.group("destination") or clone.group("repo"),
                                 "git clone without a destination creates the repo-named folder")

                if document in HUMAN_ONBOARDING:
                    # Human quickstart should yield an actual offline result before
                    # asking newcomers to run the full maintainer test suite.
                    self.assertIn("python scripts/kb.py ingest", block,
                                  "first copy/paste block does not build a local index")
                    self.assertIn('python scripts/kb.py search "memory"', block,
                                  "first copy/paste block does not return a source-backed hit")
                    commands = [line.strip() for line in block.splitlines() if line.strip()]
                    self.assertLess(commands.index("cd second-brain-os"),
                                    commands.index("python scripts/kb.py ingest"),
                                    "index only after entering the cloned repo")
                    self.assertLess(commands.index("python scripts/kb.py ingest"),
                                    commands.index('python scripts/kb.py search "memory"'),
                                    "index before searching in the first-use block")
                    self.assertNotIn("python scripts/health.py", block,
                                     "maintainer checks must not block first human recall")
                    self.assertNotIn("python -m unittest", block,
                                     "the full test suite must follow first recall")

                    # A first-time user must have a *separate* home path,
                    # not be invited to put personal notes in the public clone.
                    install = "python scripts/install.py --target ../my-private-brain"
                    enter = "cd ../my-private-brain"
                    local_hit = 'python scripts/kb.py search "YOUR_UNIQUE_TERM"'
                    self.assertIn(install, text)
                    self.assertIn(enter, text)
                    self.assertIn("02_WIKI/my-first-note.md", text)
                    self.assertIn(local_hit, text)
                    self.assertLess(text.index(install), text.index(enter))
                    self.assertLess(text.index(enter), text.index(local_hit))
                    # Contributor checks must run in the source checkout, not the
                    # installed home (which only ships its installed-home test).
                    contributor_commands = chr(10).join((
                        "cd ../second-brain-os",
                        "python scripts/health.py",
                        "python -m unittest discover -s tests",
                    ))
                    self.assertIn(
                        contributor_commands, text,
                        "full-repository checks must first return to the source clone")
                    self.assertLess(text.index(local_hit),
                                    text.index("cd ../second-brain-os"),
                                    "return to the checkout only after optional private-home recall")
                    self.assertEqual((ROOT / "../my-private-brain").resolve().parent,
                                     ROOT.parent, "private home must be outside clone")


    def test_first_recall_works_from_synthetic_markdown_without_an_account(self):
        # The smoke command must run as a visible cross-platform CI step, not
        # merely appear as an optional README command or be hidden in unittests.
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("run: python scripts/first_success.py --repeat 3", ci,
                      "CI must publish synthetic offline recall JSON on each OS/Python job")
        self.assertIn("run: python scripts/first_success.py --installed-home --repeat 1", ci,
                      "CI must time an actual installed-home keyword recall on each supported runner")
        # The README's first search must work on the REAL public checkout,
        # not only on disposable notes with a guaranteed keyword.
        readme_commands = 'python scripts/kb.py ingest\n          python scripts/kb.py search "memory"'
        matrix_job = ci.split("  test:\n", 1)[1].split(
            "\n  first-recall-macos:\n", 1)[0]
        self.assertIn("name: README offline keyword recall (public checkout)",
                      matrix_job)
        self.assertIn(readme_commands, matrix_job)
        self.assertLess(matrix_job.index(readme_commands),
                        matrix_job.index("run: python scripts/first_success.py --repeat 3"),
                        "public README recall must precede synthetic smoke")
        # Scope the macOS assertion to its own job, never to matrix commands.
        self.assertIn("  first-recall-macos:\n", ci)
        macos_job = ci.split("  first-recall-macos:\n", 1)[1].split(
            "\n  backup-seal:", 1)[0]
        self.assertIn("runs-on: macos-15", macos_job)
        self.assertIn('python-version: "3.12"', macos_job)
        # macOS must exercise both the probe and the real bilingual/private-home
        # onboarding regression. A single-file smoke could miss installer or
        # privacy-boundary failures that only reproduce on macOS.
        # The macOS job previously covered recall only. Require the actual
        # source-tree integrity gate before declaring the first-use witness OK.
        health_step = "run: python scripts/health.py"
        focused_step = 'run: python -m unittest discover -s tests -p "test_first_*.py" -v'
        self.assertIn(health_step, macos_job,
                      "macOS must run the full repository health gate")
        self.assertIn(focused_step, macos_job)
        self.assertIn("name: README offline keyword recall (macOS public checkout)",
                      macos_job)
        self.assertIn(readme_commands, macos_job)
        self.assertRegex(
            macos_job,
            r'(?m)^      - name: Clean local checkout to first keyword hit \(macOS JSON\)\r?\n'
            r'        run: python scripts/clean_checkout_recall\.py$',
            "macOS must execute the checkout probe as a YAML step, not commented text")
        self.assertLess(macos_job.index(health_step), macos_job.index(readme_commands),
                        "macOS health must run before the real README witness")
        self.assertLess(macos_job.index(health_step), macos_job.index(focused_step),
                        "macOS health must precede onboarding tests")
        self.assertIn(
            "run: python scripts/first_success.py --installed-home --repeat 1",
            macos_job)
        for document in ONBOARDING:
            text = (ROOT / document).read_text(encoding="utf-8")
            with self.subTest(document=document):
                self.assertIn("python scripts/kb.py ingest", text)
                self.assertIn('python scripts/kb.py search "memory"', text)
        self.assertIn(".kb/", (ROOT / ".gitignore").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            notes = home / "02_WIKI"
            notes.mkdir()
            (notes / "example.md").write_text(
                "# Memory example\nA local memory note records source provenance.\n",
                encoding="utf-8")
            script = str(ROOT / "scripts" / "kb.py")
            build = subprocess.run([sys.executable, script, "ingest", "--vault", str(home)],
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            self.assertTrue((home / ".kb" / "kb.sqlite").is_file())
            recall = subprocess.run([sys.executable, script, "search", "memory",
                                     "--vault", str(home)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(recall.returncode, 0, recall.stdout + recall.stderr)
            self.assertIn("02_WIKI/example.md", recall.stdout)

        # Exercise the documented optional private-home path end to end; a
        # syntactically correct README can still point to an unusable install.
        # All note bytes are synthetic and stay outside this public checkout.
        with tempfile.TemporaryDirectory(prefix="sbo-onboarding-home-") as base:
            private_home = Path(base) / "my-private-brain"
            installed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "install.py"),
                 "--target", str(private_home)],
                cwd=str(ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=180)
            self.assertEqual(installed.returncode, 0,
                             installed.stdout + installed.stderr)
            personal_kb = private_home / "scripts" / "kb.py"
            self.assertTrue(personal_kb.is_file(), "installer must ship the KB CLI")
            note = private_home / "02_WIKI" / "my-first-note.md"
            note.parent.mkdir(parents=True, exist_ok=True)
            note.write_text(
                "# First personal note\nYOUR_UNIQUE_TERM is synthetic and contains no user data.\n",
                encoding="utf-8")
            for args in (("ingest",), ("search", "YOUR_UNIQUE_TERM")):
                result = subprocess.run(
                    [sys.executable, str(personal_kb), *args],
                    cwd=str(private_home), capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((private_home / ".kb" / "kb.sqlite").is_file())
            self.assertIn("02_WIKI/my-first-note.md", result.stdout)

        # An independent, machine-readable probe must measure *installation*
        # as well as indexing and recall. It excludes network clone time.
        probe = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "first_success.py"),
             "--installed-home", "--repeat", "1"],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=240)
        self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
        evidence = json.loads(probe.stdout)
        self.assertEqual(evidence["probe"], "synthetic_installed_home_keyword_recall")
        self.assertEqual(evidence["repeat"], 1)
        self.assertEqual(evidence["successes"], 1)
        self.assertEqual(evidence["trials"][0]["matched_paths"], ["02_WIKI/demo.md"])
        self.assertIn("excludes clone", evidence["scope"])

        # A separate, failure-aware probe must include a fresh committed Git
        # clone and verify its first hit points to a real checkout file.
        # The clone is LOCAL; it intentionally makes no network-speed claim.
        clone_probe = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "clean_checkout_recall.py")],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=240)
        self.assertEqual(clone_probe.returncode, 0,
                         clone_probe.stdout + clone_probe.stderr)
        clone_report = json.loads(clone_probe.stdout)
        self.assertEqual(clone_report["probe"],
                         "clean_local_git_clone_to_first_keyword_hit")
        self.assertEqual(clone_report["status"], "pass", clone_report)
        self.assertGreater(clone_report["indexed_notes"], 0)
        self.assertTrue(clone_report["matched_paths"])
        self.assertIn("excludes remote network", clone_report["scope"])
        self.assertGreaterEqual(clone_report["elapsed_ms"],
                                clone_report["clone_ms"])

        # Adversarial Git fixture: plausible text and a real Markdown file
        # are NOT proof of recall when the SQLite index is corrupt.
        import importlib.util
        source_spec = importlib.util.spec_from_file_location(
            "sbo_clean_checkout_probe", ROOT / "scripts" / "clean_checkout_recall.py")
        clean_module = importlib.util.module_from_spec(source_spec)
        source_spec.loader.exec_module(clean_module)
        with tempfile.TemporaryDirectory(prefix="sbo-forged-git-") as directory:
            fake_repo = Path(directory) / "source"
            (fake_repo / "scripts").mkdir(parents=True)
            (fake_repo / "02_WIKI").mkdir()
            (fake_repo / "02_WIKI" / "memory.md").write_text(
                "# Fake memory\n", encoding="utf-8")
            (fake_repo / "scripts" / "kb.py").write_text(
                "import pathlib, sys\n"
                "if 'ingest' in sys.argv:\n"
                "    pathlib.Path('.kb').mkdir(exist_ok=True)\n"
                "    pathlib.Path('.kb/kb.sqlite').write_bytes(b'not sqlite')\n"
                "    print('indexed 1 notes')\n"
                "else:\n"
                "    print('02_WIKI/memory.md  [02_WIKI] forged result')\n",
                encoding="utf-8")
            for args in (
                    ("init", "-q"),
                    ("add", "."),
                    ("-c", "user.name=Fixture", "-c",
                     "user.email=fixture@example.invalid",
                     "commit", "-qm", "synthetic")):
                step = subprocess.run(["git", *args], cwd=str(fake_repo),
                                      capture_output=True, text=True, timeout=30)
                self.assertEqual(step.returncode, 0, step.stdout + step.stderr)
            forged = clean_module.measure(fake_repo)
        self.assertEqual(forged["status"], "fail", forged)
        self.assertEqual(forged["reason"], "no_source_backed_hit", forged)

        # Execute the real installed-home installer, ingest and search with
        # synthetic parent-only credentials. None may inherit those values.
        import importlib.util
        import os
        from unittest import mock
        spec = importlib.util.spec_from_file_location(
            "sbo_first_success_installed", ROOT / "scripts" / "first_success.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original_run = subprocess.run
        observed_envs = []

        def capture_run(*args, **kwargs):
            observed_envs.append(kwargs.get("env"))
            return original_run(*args, **kwargs)

        with mock.patch.dict(os.environ, {
                "SBO_FIRST_RECALL_SECRET_CANARY": "synthetic-parent-only",
                "PYTHONPATH": "synthetic-untrusted-import-root"}):
            with mock.patch.object(module.subprocess, "run", side_effect=capture_run):
                measured = module.installed_home_trial(ROOT / "scripts" / "install.py")
        self.assertTrue(measured["success"], measured)
        self.assertEqual(measured["matched_paths"], ["02_WIKI/demo.md"])
        self.assertEqual(len(observed_envs), 3,
                         "installer, ingest and search must all be run")
        for child_env in observed_envs:
            self.assertIsNotNone(child_env, "child inherited the parent environment")
            self.assertNotIn("SBO_FIRST_RECALL_SECRET_CANARY", child_env)
            self.assertNotIn("PYTHONPATH", child_env)
            self.assertEqual(child_env.get("PYTHONIOENCODING"), "utf-8")
            self.assertEqual(child_env.get("PYTHONNOUSERSITE"), "1")



if __name__ == "__main__":
    unittest.main()
