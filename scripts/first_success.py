#!/usr/bin/env python3
"""Measure a reproducible *local* first recall with only synthetic Markdown.

This is an offline smoke/latency probe for the existing keyword KB CLI, not a
semantic-memory benchmark or a git-clone timer. Every trial uses a new temporary
brain; no user files, network services, LLMs, or repositories are written.

Usage: python scripts/first_success.py --repeat 3
Returns JSON and exits nonzero if any synthetic ingest/recall trial fails.
"""
import argparse
import datetime
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED = "02_WIKI/demo.md"
QUERY = "ORCHIDMEMORY2026"
MAX_REPEAT = 10

# Minimize inherited settings for the disposable install+recall subprocesses.
# This mirrors PR #134's environment boundary; it is not a process sandbox.
_CHILD_ENV_KEYS = (
    "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
    "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE",
    "HOMEDRIVE", "HOMEPATH", "LANG", "LC_ALL", "LC_CTYPE",
)


def _child_environment():
    env = {key: os.environ[key] for key in _CHILD_ENV_KEYS if key in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONNOUSERSITE"] = "1"
    return env



def trial(kb_script, timeout=30):
    """Run both CLI commands with synthetic data and an isolated SQLite cache."""
    with tempfile.TemporaryDirectory(prefix="sbo-first-recall-") as tmp:
        vault = Path(tmp)
        notes = vault / "02_WIKI"
        notes.mkdir()
        (notes / "demo.md").write_text(
            "# Example memory\n" + QUERY + " is a made-up recall marker.\n",
            encoding="utf-8")
        (notes / "distractor.md").write_text(
            "# A different note\nThis note has no matching token.\n",
            encoding="utf-8")

        start = time.perf_counter()

        # Ingest and search share one budget. Per-subprocess timeouts could
        # otherwise double the declared maximum, especially on a hung CLI.
        def time_left():
            remaining = timeout - (time.perf_counter() - start)
            if remaining <= 0:
                raise subprocess.TimeoutExpired("synthetic first recall", timeout)
            return remaining

        def invoke(*args):
            return subprocess.run(
                [sys.executable, str(kb_script), *args, "--vault", str(vault)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=time_left(), check=False)
        try:
            ingest = invoke("ingest")
            if ingest.returncode != 0:
                return {"success": False, "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
                        "reason": "ingest_exit_nonzero"}
            search = invoke("search", QUERY)
            elapsed = round((time.perf_counter() - start) * 1000, 3)
            if elapsed > timeout * 1000:
                raise subprocess.TimeoutExpired("synthetic first recall", timeout)
        except subprocess.TimeoutExpired:
            return {"success": False, "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
                    "reason": "timeout"}
        except OSError:
            return {"success": False, "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
                    "reason": "process_start_failed"}

        index = (vault / ".kb" / "kb.sqlite").is_file()
        # Only the matching note can appear as a result; the search must not
        # silently return an unrelated note, or only an empty/error message.
        paths = re.findall(r"(?m)^((?:[\w-]+/)+[\w.-]+\.md)\s+\[", search.stdout)
        indexed = re.search(r"\bindexed (\d+) notes\b", ingest.stdout)
        passed = (search.returncode == 0 and index and indexed is not None
                  and int(indexed.group(1)) == 2 and paths == [EXPECTED])
        return {"success": bool(passed), "elapsed_ms": elapsed,
                "reason": "ok" if passed else "unexpected_search_or_index",
                "indexed_notes": int(indexed.group(1)) if indexed else None,
                "matched_paths": paths}



def installed_home_trial(installer_script, timeout=180):
    """Time actual local installation + keyword recall; clone and editor time excluded."""
    with tempfile.TemporaryDirectory(prefix="sbo-installed-recall-") as tmp:
        home = Path(tmp) / "my-private-brain"
        start = time.perf_counter()

        def failed(reason):
            return {"success": False,
                    "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
                    "reason": reason}

        # One budget for installation, indexing and search together. Giving
        # each subprocess the full timeout can silently triple the wall time.
        def time_left():
            remaining = timeout - (time.perf_counter() - start)
            if remaining <= 0:
                raise subprocess.TimeoutExpired("installed-home first recall", timeout)
            return remaining

        try:
            install = subprocess.run(
                [sys.executable, str(installer_script), "--target", str(home)],
                cwd=str(HERE.parent), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=time_left(), check=False,
                env=_child_environment())
            if install.returncode != 0:
                return failed("install_exit_nonzero")
            kb_script = home / "scripts" / "kb.py"
            if not kb_script.is_file():
                return failed("installed_kb_missing")

            notes = home / "02_WIKI"
            notes.mkdir(parents=True, exist_ok=True)
            (notes / "demo.md").write_text(
                "# First personal memory\n" + QUERY + " is a synthetic marker.\n",
                encoding="utf-8")
            (notes / "distractor.md").write_text(
                "# Other note\nContains no recall marker.\n", encoding="utf-8")

            def invoke(*args):
                return subprocess.run(
                    [sys.executable, str(kb_script), *args, "--vault", str(home)],
                    cwd=str(home), capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=time_left(), check=False,
                    env=_child_environment())

            ingest = invoke("ingest")
            if ingest.returncode != 0:
                return failed("ingest_exit_nonzero")
            search = invoke("search", QUERY)
            if time.perf_counter() - start > timeout:
                return failed("timeout")
        except subprocess.TimeoutExpired:
            return failed("timeout")
        except OSError:
            return failed("process_or_filesystem_error")

        elapsed = round((time.perf_counter() - start) * 1000, 3)
        index = (home / ".kb" / "kb.sqlite").is_file()
        indexed = re.search(r"\bindexed (\d+) notes\b", ingest.stdout)
        paths = re.findall(r"(?m)^((?:[\w-]+/)+[\w.-]+\.md)\s+\[", search.stdout)
        passed = (search.returncode == 0 and index and indexed is not None
                  and int(indexed.group(1)) >= 2 and paths == [EXPECTED])
        return {"success": bool(passed), "elapsed_ms": elapsed,
                "reason": "ok" if passed else "unexpected_search_or_index",
                "indexed_notes": int(indexed.group(1)) if indexed else None,
                "matched_paths": paths}


def evaluate(repeat, kb_script, installed_home=False):
    samples = [installed_home_trial(HERE / "install.py") if installed_home
               else trial(kb_script) for _ in range(repeat)]
    successes = sum(1 for sample in samples if sample["success"])
    durations = [sample["elapsed_ms"] for sample in samples]
    return {
        "schema_version": 1,
        "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "probe": ("synthetic_installed_home_keyword_recall" if installed_home
                  else "synthetic_keyword_ingest_then_recall"),
        "scope": ("local install + synthetic note creation + indexing + keyword search; excludes clone, editor time and health"
                  if installed_home else
                  "local CLI subprocess startup + synthetic indexing + keyword search; excludes clone, health and setup"),
        "dependencies": "Python standard library; no model or account",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "repeat": repeat,
        "successes": successes,
        "success_rate": round(successes / repeat, 3),
        "median_ms": round(statistics.median(durations), 3),
        "max_ms": max(durations),
        "status": "pass" if successes == repeat else "fail",
        "trials": samples,
    }


def main(argv=None, kb_script=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=3,
                        help="number of independent synthetic trials (1..10, default 3)")
    parser.add_argument("--installed-home", action="store_true",
                        help="time a fresh local install, synthetic indexing and recall (excludes git clone)")
    args = parser.parse_args(argv)
    if not 1 <= args.repeat <= MAX_REPEAT:
        parser.error("--repeat must be between 1 and %d" % MAX_REPEAT)
    script = Path(kb_script) if kb_script is not None else HERE / "kb.py"
    result = evaluate(args.repeat, script, installed_home=args.installed_home)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
