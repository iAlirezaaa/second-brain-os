"""Onboarding contract: a fresh clone is navigable and local recall really works.

The integration test uses an isolated, synthetic vault and no network or model.
"""
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
                    self.assertRegex(
                        text,
                        r"(?m)^cd \\.\\./second-brain-os[ \\t]*$\\n"
                        r"python scripts/health\\.py[ \\t]*$\\n"
                        r"python -m unittest discover -s tests[ \\t]*$",
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


if __name__ == "__main__":
    unittest.main()
