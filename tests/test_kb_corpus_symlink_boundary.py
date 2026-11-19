"""KB ingestion must never dereference aliased Markdown outside its own note tree.

Each fixture is disposable; the outside sentinel is synthetic, never user data.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import kb  # noqa: E402


class KbCorpusAliases(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / "brain"
        self.notes = self.root / "02_WIKI"
        self.notes.mkdir(parents=True)
        self.real = self.notes / "real.md"
        self.real.write_text("# Local note\nLOCALORCHID is a synthetic note.\n",
                             encoding="utf-8")

    def link(self, name, target, directory=False):
        dest = self.notes / name
        try:
            dest.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            if os.name == "nt":
                self.skipTest("this Windows runner cannot create symbolic links")
            raise
        return dest

    def indexed(self):
        return {rel for rel, _path in kb.corpus(self.root)}

    def test_ordinary_markdown_is_still_indexed_and_searchable(self):
        # Operations is a human zone but denied to the default agent context.
        # A local keyword index must not accidentally make its client data searchable.
        private = self.root / "09_OPERATIONS" / "decisions" / "client.md"
        private.parent.mkdir(parents=True)
        private.write_text("# Private operation\nONLY_OPERATIONS_CANARY stays private.\n",
                           encoding="utf-8")
        # The default MCP read policy also refuses .env.* names. The local
        # keyword cache must not quietly re-expose an .env.-named Markdown note.
        env_note = self.notes / ".env.private.md"
        env_note.write_text("# Synthetic configuration\nENV_NOTE_CANARY must stay private.\n",
                            encoding="utf-8")
        self.assertNotIn("02_WIKI/.env.private.md", self.indexed())
        self.assertIn("02_WIKI/real.md", self.indexed())
        self.assertNotIn("09_OPERATIONS/decisions/client.md", self.indexed())
        self.assertEqual(0, kb.ingest(self.root))
        self.assertEqual([], kb.find(self.root, "ONLY_OPERATIONS_CANARY"))
        self.assertEqual([], kb.find(self.root, "ENV_NOTE_CANARY"))
        self.assertEqual(["02_WIKI/real.md"],
                         [hit["path"] for hit in kb.find(self.root, "LOCALORCHID")])
        # A pre-fix cache could already hold the .env.-named note. Merely
        # changing the next ingest does not stop reads from that old cache.
        with closing(sqlite3.connect(str(self.root / ".kb" / "kb.sqlite"))) as conn, conn:
            conn.execute("UPDATE kb_meta SET value = '3' WHERE key = 'schema'")
            conn.execute("INSERT OR REPLACE INTO notes VALUES (?,?,?,?,?,?)",
                         ("02_WIKI/.env.private.md", "Old private cache", "02_WIKI",
                          "ENV_NOTE_CANARY", "env_note_canary", "2026-11-19"))
        # sqlite3 transaction context does not close the handle: Windows cleanup needs that.
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")
        with self.assertRaisesRegex(RuntimeError, "older corpus rule"):
            kb.find(self.root, "ENV_NOTE_CANARY")
        self.assertEqual(0, kb.ingest(self.root))
        self.assertEqual([], kb.find(self.root, "ENV_NOTE_CANARY"))

        # Case-insensitive default access policy forbids these paths on every OS.
        # A case-sensitive corpus filter must not silently publish their contents.
        case_root = self.base / "casefold-policy"
        visible = case_root / "02_WIKI" / "visible.md"
        visible.parent.mkdir(parents=True)
        visible.write_text("# Visible\nVISIBLECASE_CANARY is synthetic.\n",
                           encoding="utf-8")
        secret_cases = (
            ("02_WIKI/SeCrEtS/private.md", "SECRETS_CASE_CANARY"),
            ("09_operations/decisions/private.md", "OPS_CASE_CANARY"),
            ("12_runtime/private.md", "MACHINE_CASE_CANARY"),
        )
        for rel, marker in secret_cases:
            note = case_root / rel
            note.parent.mkdir(parents=True, exist_ok=True)
            note.write_text("# Protected\n" + marker + " is synthetic.\n",
                            encoding="utf-8")
        self.assertEqual({"02_WIKI/visible.md"},
                         {rel for rel, _note in kb.corpus(case_root)})
        self.assertEqual(0, kb.ingest(case_root))
        for _rel, marker in secret_cases:
            with self.subTest(marker=marker):
                self.assertEqual([], kb.find(case_root, marker))
        self.assertEqual(["02_WIKI/visible.md"],
                         [hit["path"] for hit in kb.find(case_root, "VISIBLECASE_CANARY")])

    def test_external_file_symlink_is_never_ingested(self):
        outside = self.base / "outside.md"
        outside.write_text("# Outside\nEXTERNALCANARY synthetic only.\n", encoding="utf-8")
        self.link("alias.md", outside)
        self.assertNotIn("02_WIKI/alias.md", self.indexed())
        self.assertEqual(0, kb.ingest(self.root))
        self.assertEqual([], kb.find(self.root, "EXTERNALCANARY"))

    def test_in_root_alias_is_not_a_second_note(self):
        self.link("alias.md", self.real)
        self.assertEqual({"02_WIKI/real.md"}, self.indexed())
        self.assertEqual(0, kb.ingest(self.root))

    def test_broken_symlink_does_not_crash_ingest(self):
        self.link("missing.md", self.base / "not-here.md")
        self.assertNotIn("02_WIKI/missing.md", self.indexed())
        self.assertEqual(0, kb.ingest(self.root))
        self.assertEqual(["02_WIKI/real.md"],
                         [hit["path"] for hit in kb.find(self.root, "LOCALORCHID")])

    def test_aliased_parent_directory_is_rejected_even_if_walked(self):
        outside_dir = self.base / "elsewhere"
        outside_dir.mkdir()
        outside_note = outside_dir / "note.md"
        outside_note.write_text("# Elsewhere\nPARENTALIAS synthetic only.\n",
                                encoding="utf-8")
        linked = self.link("shortcut", outside_dir, directory=True)
        # Some Python versions do not descend into directory symlinks. Model
        # a walker that does, so the boundary is tested on all supported versions.
        with patch.object(kb, "iter_markdown",
                          return_value=[self.real, linked / "note.md"]):
            self.assertEqual({"02_WIKI/real.md"}, self.indexed())


if __name__ == "__main__":
    unittest.main()
