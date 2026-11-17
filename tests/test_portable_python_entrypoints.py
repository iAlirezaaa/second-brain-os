"""Prevent onboarding docs from pinning an interpreter the user may not have.

Issue #46: the Windows launcher pin py -3.10 failed on a machine with
supported Python versions but no 3.10. The tested floor is 3.9, not a pin.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sync_hosts  # noqa: E402

PUBLIC_ENTRYPOINTS = (
    "AGENTS.md",
    "README.md",
    "00_START_HERE/START.md",
    "CONTRIBUTING.md",
    "skills/first-session/SKILL.md",
    "skills/self-audit/SKILL.md",
    "00_START_HERE/GUIDE_FA_EN.md",
    "00_START_HERE/PLAN_FA.md",
    "00_START_HERE/DESIGN_v3.md",
    "start.bat",
    "scripts/sync_hosts.py",
)


class PortablePythonEntrypoints(unittest.TestCase):
    def test_no_uninstalled_python_pin_in_public_entrypoints(self):
        """A current installation of Python >=3.9 must work without 3.10."""
        for rel in PUBLIC_ENTRYPOINTS:
            with self.subTest(path=rel):
                content = (ROOT / rel).read_text(encoding="utf-8")
                self.assertNotIn("py -3.10", content, rel)
        start = (ROOT / "00_START_HERE/START.md").read_text(encoding="utf-8")
        self.assertIn("python scripts/first_success.py --repeat 3", start)
        self.assertIn("python 15_SYSTEM", start)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("python scripts/health.py", readme)
        launcher = (ROOT / "start.bat").read_text(encoding="ascii")
        self.assertIn("python 15_SYSTEM\\scripts\\hades.py doctor", launcher)
        self.assertIn("python 15_SYSTEM\\scripts\\test_hades.py", launcher)
        if sys.platform == "win32":
            self._assert_windows_launcher_exit_codes()

    def _assert_windows_launcher_exit_codes(self):
        """Invoke the actual batch file against disposable Python scripts on Windows.

        The launcher is copied into a path containing spaces to exercise quoting;
        the real repository and user data are never opened by the synthetic scripts.
        No Python 3.10 or network access is required.
        """
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory(prefix="second brain launcher ") as directory:
            fixture = Path(directory)
            (fixture / "start.bat").write_bytes((ROOT / "start.bat").read_bytes())
            scripts = fixture / "15_SYSTEM" / "scripts"
            scripts.mkdir(parents=True)
            for action, target in (("check", "hades.py"), ("test", "test_hades.py")):
                script = scripts / target
                for expected in (0, 7):
                    script.write_text(
                        "import sys\\nprint('SYNTHETIC_LAUNCHER')\\nsys.exit(%d)\\n" % expected,
                        encoding="ascii",
                    )
                    result = subprocess.run(
                        ["cmd.exe", "/d", "/c", str(fixture / "start.bat"), action],
                        cwd=str(fixture),
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    with self.subTest(action=action, expected=expected):
                        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                        self.assertIn("SYNTHETIC_LAUNCHER", result.stdout)

    def test_every_agent_host_projection_is_fresh_and_portable(self):
        """Host files are rendered, not independently edited into another law."""
        for _key, host, rel, needs_mdc in sync_hosts.HOSTS:
            with self.subTest(host=host):
                projection = (ROOT / rel).read_text(encoding="utf-8")
                self.assertEqual(projection, sync_hosts.render(host, needs_mdc))
                self.assertNotIn("py -3.10", projection)


if __name__ == "__main__":
    unittest.main()
