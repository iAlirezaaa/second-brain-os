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
        # An executable YAML step, not a comment or a quoted string, must
        # measure three independent committed-clone recall trials on Windows and Ubuntu.
        self.assertRegex(
            matrix_job,
            r'(?m)^      - name: Clean local checkout to first keyword hit \(matrix JSON\)\r?\n'
            r'        run: python scripts/clean_checkout_recall\.py --repeat 3$',
            "matrix runners must execute local-clone recall as a CI step")
        self.assertLess(
            matrix_job.index(readme_commands),
            matrix_job.index("run: python scripts/clean_checkout_recall.py --repeat 3"),
            "real README recall must precede the local-clone measurement")
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
            r'        run: python scripts/clean_checkout_recall\.py --repeat 3$',
            "macOS must execute all three checkout trials as a YAML step, not commented text")
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
        commit = subprocess.run(["git", "rev-parse", "--verify", "HEAD"],
                                cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        self.assertEqual(commit.returncode, 0, commit.stderr)
        self.assertEqual(clone_report["commit_sha"], commit.stdout.strip(),
                         "benchmark must report the exact committed checkout revision")
        self.assertIn("excludes remote network", clone_report["scope"])
        self.assertGreaterEqual(clone_report["elapsed_ms"],
                                clone_report["clone_ms"])
        self.assertIsInstance(clone_report["preflight_ms"], float)
        self.assertGreaterEqual(clone_report["preflight_ms"], 0)

        # Regression for issue #147: opt-in Git transport must exercise the
        # same committed-source/SQLite witness without needing an internet
        # connection in CI. file:// forces Git's transfer path instead of
        # the local hardlink-optimized checkout mode; the CLI itself will
        # only offer the fixed public GitHub URL.
        transferred = clean_module.measure(ROOT.as_uri(), remote=True)
        self.assertEqual(transferred["status"], "pass", transferred)
        self.assertEqual(transferred["transport"], "git_remote")
        self.assertEqual(transferred["commit_sha"], commit.stdout.strip())
        self.assertTrue(transferred["matched_paths"])
        self.assertGreaterEqual(transferred["elapsed_ms"], transferred["clone_ms"])

        # Repeatability is measured with independent clones, not by timing
        # one result twice. Preserve individual outcomes for auditing.
        repeated_probe = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "clean_checkout_recall.py"),
             "--repeat", "2"],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=480)
        self.assertEqual(repeated_probe.returncode, 0,
                         repeated_probe.stdout + repeated_probe.stderr)
        repeated = json.loads(repeated_probe.stdout)
        self.assertEqual(repeated["repeat"], 2)
        self.assertEqual(repeated["successes"], 2)
        self.assertEqual(repeated["success_rate"], 1.0)
        self.assertEqual(len(repeated["trials"]), 2)
        self.assertTrue(all(t["status"] == "pass" for t in repeated["trials"]))
        self.assertEqual(repeated["commit_sha"], commit.stdout.strip())
        self.assertTrue(all(t["commit_sha"] == repeated["commit_sha"]
                            for t in repeated["trials"]))
        self.assertGreater(repeated["median_ms"], 0)
        self.assertGreaterEqual(repeated["max_ms"], repeated["median_ms"])
        invalid_repeat = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "clean_checkout_recall.py"),
             "--repeat", "0"], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(invalid_repeat.returncode, 0)
        self.assertIn("between 1 and 5", invalid_repeat.stderr)

        # Adversarial Git fixture: plausible text and a real Markdown file
        # are NOT proof of recall when the SQLite index is corrupt.
        import importlib.util
        source_spec = importlib.util.spec_from_file_location(
            "sbo_clean_checkout_probe", ROOT / "scripts" / "clean_checkout_recall.py")
        clean_module = importlib.util.module_from_spec(source_spec)
        source_spec.loader.exec_module(clean_module)
        # A real KB search prints the entire Markdown path before "  [zone]".
        # Spaces and brackets inside a valid filename must not disappear from
        # the recall witness; the indented excerpt is NOT another search hit.
        printed_hits = (
            "02_WIKI/Team Memory Notes.md  [02_WIKI]  Team memory\n"
            "    02_WIKI/snippet.md  [02_WIKI]  excerpt only\n"
            "02_WIKI/[Weekly] memory.md  [02_WIKI]  Weekly\n"
        )
        self.assertEqual(
            ["02_WIKI/Team Memory Notes.md", "02_WIKI/[Weekly] memory.md"],
            clean_module._reported_hit_paths(printed_hits),
            "the CLI witness must retain Markdown names with spaces/brackets"
        )
        # Two green trials from different revisions are NOT one reproducible
        # benchmark. Use measured-looking synthetic records, not a fake Git repo.
        from unittest.mock import patch
        with patch.object(clean_module, "measure", side_effect=[
            {"status": "pass", "elapsed_ms": 10.0, "commit_sha": "a" * 40},
            {"status": "pass", "elapsed_ms": 12.0, "commit_sha": "b" * 40},
        ]):
            mixed_revisions = clean_module.evaluate(2)
        self.assertEqual(mixed_revisions["successes"], 2)
        self.assertEqual(mixed_revisions["status"], "fail")
        self.assertEqual(mixed_revisions["reason"], "commit_mismatch")
        self.assertIsNone(mixed_revisions["commit_sha"])
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
            # Red-first: a CLI can forge a plausible result and a VALID
            # SQLite file, yet point at a row without the searched term.
            # The probe must refuse an index that does not substantiate a hit.
            (fake_repo / "scripts" / "kb.py").write_text(
                "import pathlib, sqlite3, sys\n"
                "if 'ingest' in sys.argv:\n"
                "    pathlib.Path('.kb').mkdir(exist_ok=True)\n"
                "    db = sqlite3.connect('.kb/kb.sqlite')\n"
                "    db.execute('CREATE TABLE notes (path TEXT PRIMARY KEY, title TEXT, zone TEXT, body TEXT, norm TEXT, updated TEXT)')\n"
                "    db.execute(\"INSERT INTO notes VALUES ('02_WIKI/memory.md','Unrelated','02_WIKI','nothing relevant here','nothing relevant here','2026-11-21')\")\n"
                "    db.commit(); db.close()\n"
                "    print('indexed 1 notes')\n"
                "else:\n"
                "    print('02_WIKI/memory.md  [02_WIKI] forged result')\n",
                encoding="utf-8")
            for args in (("add", "scripts/kb.py"),
                         ("-c", "user.name=Fixture", "-c",
                          "user.email=fixture@example.invalid", "commit", "-qm",
                          "synthetic valid but unrelated index")):
                step = subprocess.run(["git", *args], cwd=str(fake_repo),
                                      capture_output=True, text=True, timeout=30)
                self.assertEqual(step.returncode, 0, step.stdout + step.stderr)
            forged_valid_sqlite = clean_module.measure(fake_repo)
            # A fabricated index can echo the keyword in SQLite while the
            # committed Markdown (and filename) does not support the claim.
            # Before the fix this valid, same-count SQLite fixture passed.
            (fake_repo / "02_WIKI" / "claim.md").write_text(
                "# Ordinary note\nOnly unrelated facts.\n",
                encoding="utf-8")
            (fake_repo / "scripts" / "kb.py").write_text(
                "import pathlib, sqlite3, sys\n"
                "if 'ingest' in sys.argv:\n"
                "    pathlib.Path('.kb').mkdir(exist_ok=True)\n"
                "    db = sqlite3.connect('.kb/kb.sqlite')\n"
                "    db.execute('CREATE TABLE notes (path TEXT PRIMARY KEY, title TEXT, zone TEXT, body TEXT, norm TEXT, updated TEXT)')\n"
                "    db.execute(\"INSERT INTO notes VALUES ('02_WIKI/claim.md','Memory claim','02_WIKI','memory','memory','2026-11-21')\")\n"
                "    db.commit(); db.close()\n"
                "    print('indexed 1 notes')\n"
                "else:\n"
                "    print('02_WIKI/claim.md  [02_WIKI] forged result')\n",
                encoding="utf-8")
            for args in (("add", "scripts/kb.py", "02_WIKI/claim.md"),
                         ("-c", "user.name=Fixture", "-c",
                          "user.email=fixture@example.invalid", "commit", "-qm",
                          "synthetic index disconnected from source")):
                step = subprocess.run(["git", *args], cwd=str(fake_repo),
                                      capture_output=True, text=True, timeout=30)
                self.assertEqual(step.returncode, 0, step.stdout + step.stderr)
            forged_source_only = clean_module.measure(fake_repo)
            # RED FIRST: a fake ingest can create a plausible Markdown file
            # INSIDE the clone only, then echo it in a consistent SQLite row.
            # That path is not in HEAD, so it cannot substantiate a measured
            # committed-clone recall even though both the row and file agree.
            generated_cli = fake_repo / "scripts" / "kb.py"
            generated_cli.write_text(
                generated_cli.read_text(encoding="utf-8")
                .replace("02_WIKI/claim.md", "02_WIKI/generated-memory.md")
                .replace("    pathlib.Path('.kb').mkdir(exist_ok=True)\n",
                         "    pathlib.Path('02_WIKI/generated-memory.md').write_text("
                         "'synthetic memory\\n', encoding='utf-8')\n"
                         "    pathlib.Path('.kb').mkdir(exist_ok=True)\n"),
                encoding="utf-8")
            for args in (("add", "scripts/kb.py"),
                         ("-c", "user.name=Fixture", "-c",
                          "user.email=fixture@example.invalid", "commit", "-qm",
                          "synthetic generated but untracked hit")):
                step = subprocess.run(["git", *args], cwd=str(fake_repo),
                                      capture_output=True, text=True, timeout=30)
                self.assertEqual(step.returncode, 0, step.stdout + step.stderr)
            forged_generated = clean_module.measure(fake_repo)
            # A fabricated row can quote the keyword and the exact committed
            # path while storing text absent from that Markdown.
            (fake_repo / "scripts" / "kb.py").write_text(
                "import pathlib, sqlite3, sys\n"
                "if 'ingest' in sys.argv:\n"
                "    pathlib.Path('.kb').mkdir(exist_ok=True)\n"
                "    db = sqlite3.connect('.kb/kb.sqlite')\n"
                "    db.execute('CREATE TABLE notes (path TEXT PRIMARY KEY, title TEXT, zone TEXT, body TEXT, norm TEXT, updated TEXT)')\n"
                "    db.execute(\"INSERT INTO notes VALUES ('02_WIKI/memory.md','Fake memory','02_WIKI','Invented memory claim','invented memory claim','2026-11-22')\")\n"
                "    db.commit(); db.close()\n"
                "    print('indexed 1 notes')\n"
                "else:\n"
                "    print('02_WIKI/memory.md  [02_WIKI] forged result')\n",
                encoding="utf-8")
            for args in (("add", "scripts/kb.py"),
                         ("-c", "user.name=Fixture", "-c",
                          "user.email=fixture@example.invalid", "commit", "-qm",
                          "synthetic fabricated SQLite body")):
                step = subprocess.run(["git", *args], cwd=str(fake_repo),
                                      capture_output=True, text=True, timeout=30)
                self.assertEqual(step.returncode, 0, step.stdout + step.stderr)
            forged_body = clean_module.measure(fake_repo)
            # A local clone ignores uncommitted work; accepting it as a live
            # source benchmark would conceal the files a newcomer is editing.
            untracked = fake_repo / "02_WIKI" / "draft-untracked.md"
            untracked.write_text("# Not committed yet\n", encoding="utf-8")
            dirty_untracked = clean_module.measure(fake_repo)
            untracked.unlink()
            tracked = fake_repo / "02_WIKI" / "claim.md"
            tracked.write_text(
                tracked.read_text(encoding="utf-8") + "Uncommitted edit\n",
                encoding="utf-8")
            dirty_tracked = clean_module.measure(fake_repo)
            # A linked executable/cache can escape the disposable checkout.
            # Assert that the guard runs before any KB subprocess is launched.
            tracked.write_text("# Ordinary note\nOnly unrelated facts.\n",
                               encoding="utf-8")
            with patch.object(clean_module, "_checkout_paths_safe",
                              return_value=False) as blocked_guard:
                blocked_link = clean_module.measure(fake_repo)
            self.assertEqual(blocked_link["reason"], "unsafe_checkout_path",
                             blocked_link)
            self.assertGreaterEqual(blocked_guard.call_count, 1)
        for dirty in (dirty_untracked, dirty_tracked):
            self.assertEqual(dirty["status"], "fail", dirty)
            self.assertEqual(dirty["reason"], "source_dirty", dirty)
            self.assertIsNone(dirty["clone_ms"], dirty)
        self.assertEqual(forged["status"], "fail", forged)
        self.assertEqual(forged["reason"], "no_source_backed_hit", forged)
        self.assertEqual(forged_valid_sqlite["status"], "fail", forged_valid_sqlite)
        self.assertEqual(forged_valid_sqlite["reason"],
                         "no_source_backed_hit", forged_valid_sqlite)
        self.assertEqual(forged_source_only["status"], "fail", forged_source_only)
        self.assertEqual(forged_generated["matched_paths"],
                         ["02_WIKI/generated-memory.md"], forged_generated)
        self.assertEqual(forged_generated["status"], "fail", forged_generated)
        self.assertEqual(forged_generated["reason"],
                         "no_source_backed_hit", forged_generated)
        self.assertEqual(forged_body["matched_paths"], ["02_WIKI/memory.md"])
        self.assertEqual(forged_body["status"], "fail", forged_body)
        self.assertEqual(forged_body["reason"], "no_source_backed_hit", forged_body)
        self.assertEqual(forged_source_only["reason"],
                         "no_source_backed_hit", forged_source_only)


        # Repro: Path.is_file() can be true for an out-of-checkout link.
        # Mocked alias checks work on Windows runners without symlink privilege;
        # a real directory symlink is also covered where the OS allows it.
        with tempfile.TemporaryDirectory(prefix="sbo-path-guard-") as directory:
            checkout = Path(directory) / "checkout"
            (checkout / "scripts").mkdir(parents=True)
            (checkout / "scripts" / "kb.py").write_text("# synthetic\n",
                                                          encoding="utf-8")
            self.assertTrue(clean_module._checkout_paths_safe(checkout))
            actual_is_symlink = Path.is_symlink
            for basename in ("scripts", "kb.py", ".kb", "kb.sqlite"):
                with self.subTest(unsafe_alias=basename):
                    with patch.object(Path, "is_symlink",
                                      lambda item, name=basename:
                                      item.name == name or actual_is_symlink(item)):
                        self.assertFalse(clean_module._checkout_paths_safe(checkout))
            external = Path(directory) / "external"
            external.mkdir()
            try:
                (checkout / ".kb").symlink_to(external, target_is_directory=True)
            except (OSError, NotImplementedError):
                pass  # Windows may deny symlink creation; mock cases above remain.
            else:
                self.assertFalse(clean_module._checkout_paths_safe(checkout))

        # RED-FIRST: the old helper followed an in-checkout symlink from
        # public 02_WIKI to denied 09_OPERATIONS, then called it a public hit.
        # A synthetic Path.is_symlink alias proves this gate on Windows where
        # creating real symlinks may require elevated privileges.
        with tempfile.TemporaryDirectory(prefix="sbo-source-alias-") as directory:
            checkout = Path(directory) / "checkout"
            public = checkout / "02_WIKI"
            restricted = checkout / "09_OPERATIONS"
            public.mkdir(parents=True)
            restricted.mkdir()
            (public / "ordinary.md").write_text("Synthetic public memory.\n",
                                                encoding="utf-8")
            (public / "mock-alias.md").write_text("Synthetic public memory.\n",
                                                  encoding="utf-8")
            private_note = restricted / "private.md"
            private_note.write_text("Synthetic restricted memory.\n",
                                    encoding="utf-8")
            self.assertTrue(clean_module._source_supports_keyword(
                checkout, "02_WIKI/ordinary.md"))
            # Red-first (#146): even if a SQLite row exactly matches the
            # bytes behind a path, it is not public committed provenance when
            # that path is denied or masquerades as a symlink/junction.
            public_row = ("ordinary", "Synthetic public memory.\n",
                          "synthetic public memory.\n")
            private_row = ("private", "Synthetic restricted memory.\n",
                           "synthetic restricted memory.\n")
            self.assertTrue(clean_module._indexed_row_matches_source(
                checkout, "02_WIKI/ordinary.md", public_row))
            self.assertFalse(clean_module._indexed_row_matches_source(
                checkout, "09_OPERATIONS/private.md", private_row))
            self.assertFalse(clean_module._source_supports_keyword(
                checkout, "09_OPERATIONS/private.md"))
            self.assertFalse(clean_module._source_supports_keyword(
                checkout, "../outside.md"))
            actual_is_symlink = Path.is_symlink
            with patch.object(Path, "is_symlink",
                              lambda item: (item.name == "mock-alias.md"
                                            or actual_is_symlink(item))):
                self.assertFalse(clean_module._source_supports_keyword(
                    checkout, "02_WIKI/mock-alias.md"))
                self.assertFalse(clean_module._indexed_row_matches_source(
                    checkout, "02_WIKI/mock-alias.md",
                    ("mock-alias", "Synthetic public memory.\n",
                     "synthetic public memory.\n")))
            try:
                (public / "alias.md").symlink_to(private_note)
            except (OSError, NotImplementedError):
                pass  # Windows symlink privilege is optional; mock above is required.
            else:
                self.assertFalse(clean_module._source_supports_keyword(
                    checkout, "02_WIKI/alias.md"))
                self.assertFalse(clean_module._indexed_row_matches_source(
                    checkout, "02_WIKI/alias.md",
                    ("alias", "Synthetic restricted memory.\n",
                     "synthetic restricted memory.\n")))

        # Execute the real installed-home installer, ingest and search with
        # synthetic parent-only credentials. None may inherit those values.
        import importlib.util
        import os
        from unittest import mock
        # A failed trial must make the aggregate fail even when another
        # trial passed; count and median always include the failed attempt.
        with mock.patch.object(clean_module, "measure", side_effect=[
                {"status": "pass", "elapsed_ms": 10.0},
                {"status": "fail", "elapsed_ms": 20.0}]) as measured:
            failed_batch = clean_module.evaluate(2)
        self.assertEqual(measured.call_count, 2)
        self.assertEqual(failed_batch["status"], "fail")
        self.assertEqual(failed_batch["reason"], "one_or_more_trials_failed")
        self.assertEqual(failed_batch["successes"], 1)
        self.assertEqual(failed_batch["success_rate"], 0.5)
        self.assertEqual(failed_batch["median_ms"], 15.0)
        self.assertEqual(len(failed_batch["trials"]), 2)
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
