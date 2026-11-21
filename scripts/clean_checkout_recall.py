#!/usr/bin/env python3
"""Measure a clean LOCAL Git checkout through the first source-backed keyword hit.

Run from a Git checkout: python scripts/clean_checkout_recall.py
A no-hardlinks clone copies committed files to a disposable directory, then
runs the documented ingest/search commands there. This includes local Git
clone time, NOT GitHub download latency, Python installation or editor time.
The source worktree must be clean: unstaged, staged and nonignored untracked
files are refused, because a local clone would silently omit them.
No network, LLM, user vault, or package installation is involved.
"""
import argparse
import datetime
import json
import os
import re
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 180
MAX_REPEAT = 5
ENV_KEYS = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
            "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE",
            "HOMEPATH", "LANG", "LC_ALL", "LC_CTYPE")


def _child_env():
    env = {k: os.environ[k] for k in ENV_KEYS if k in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _source_supports_keyword(checkout, relative_path, keyword="memory"):
    """Independently verify committed Markdown, not only derived SQLite metadata.

    A source filename can itself satisfy a keyword query. Resolve before
    reading, so the diagnostic never follows a tracked link outside its
    disposable checkout. Malformed/unreadable sources fail closed.
    """
    try:
        source = (checkout / relative_path).resolve(strict=True)
        if checkout.resolve() not in source.parents or not source.is_file():
            return False
        if keyword.casefold() in Path(relative_path).stem.casefold():
            return True
        return keyword.casefold() in source.read_text(encoding="utf-8").casefold()
    except (OSError, UnicodeError):
        return False


def measure(source=ROOT, timeout=TIMEOUT):
    """Return a failure-aware JSON-ready record; always delete the clone."""
    start = time.perf_counter()
    result = {"status": "fail", "reason": None, "elapsed_ms": None,
              "preflight_ms": None, "clone_ms": None,
              "ingest_ms": None, "search_ms": None,
              "indexed_notes": None, "matched_paths": [], "commit_sha": None}

    def remaining():
        left = timeout - (time.perf_counter() - start)
        if left <= 0:
            raise subprocess.TimeoutExpired("clean checkout first recall", timeout)
        return left

    def invoke(args, cwd=None):
        return subprocess.run(args, cwd=str(cwd) if cwd else None,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=remaining(),
                              env=_child_env(), check=False)

    try:
        # A local clone contains committed bytes only. Reject a dirty source
        # instead of silently benchmarking an older revision than the user sees.
        # Porcelain status is machine-readable, locale-independent, and ignores
        # generated .kb/ indexes via the repository's .gitignore.
        source_status = invoke(
            ["git", "-C", str(source), "status", "--porcelain=v1",
             "--untracked-files=normal"])
        if source_status.returncode != 0:
            result["reason"] = "source_status_unavailable"
            return result
        if source_status.stdout.strip():
            result["reason"] = "source_dirty"
            return result
        preflight_end = time.perf_counter()
        result["preflight_ms"] = round((preflight_end - start) * 1000, 3)
        with tempfile.TemporaryDirectory(prefix="sbo-clean-checkout-") as temp:
            checkout = Path(temp) / "second-brain-os"
            cloned = invoke(["git", "clone", "--quiet", "--local", "--no-hardlinks",
                             str(source), str(checkout)])
            if cloned.returncode != 0:
                result["reason"] = "local_clone_failed"
                return result
            # Pin the actual commit cloned (not the potentially moving source branch).
            # This Git query is included in clone_ms and the shared timeout.
            head = invoke(["git", "rev-parse", "--verify", "HEAD"], cwd=checkout)
            commit_sha = head.stdout.strip()
            if head.returncode != 0 or not re.fullmatch(
                    r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit_sha):
                result["reason"] = "commit_unverified"
                return result
            result["commit_sha"] = commit_sha
            clone_end = time.perf_counter()
            result["clone_ms"] = round((clone_end - preflight_end) * 1000, 3)
            kb = checkout / "scripts" / "kb.py"
            if not kb.is_file():
                result["reason"] = "kb_missing"
                return result
            indexed = invoke([sys.executable, str(kb), "ingest"], cwd=checkout)
            ingest_end = time.perf_counter()
            result["ingest_ms"] = round((ingest_end - clone_end) * 1000, 3)
            if indexed.returncode != 0:
                result["reason"] = "ingest_failed"
                return result
            searched = invoke([sys.executable, str(kb), "search", "memory"], cwd=checkout)
            search_end = time.perf_counter()
            result["search_ms"] = round((search_end - ingest_end) * 1000, 3)
            count = re.search(r"\bindexed (\d+) notes\b", indexed.stdout)
            result["indexed_notes"] = int(count.group(1)) if count else None
            hits = re.findall(r"(?m)^((?:[\w.-]+/)*[\w.-]+\.md)\s+\[", searched.stdout)
            result["matched_paths"] = hits
            # Every reported hit must be a real local checked-in source.
            valid_hits = bool(hits) and all(
                (checkout / path).is_file()
                and ".." not in Path(path).parts
                and _source_supports_keyword(checkout, path)
                and not path.casefold().startswith(("09_operations/", "11_control/",
                                                    "12_runtime/", "13_lab/",
                                                    "14_candidates/", "15_system/"))
                for path in hits)
            # Do not trust printed success alone: inspect actual SQLite rows.
            cache = checkout / ".kb" / "kb.sqlite"
            if valid_hits and cache.is_file():
                try:
                    with closing(sqlite3.connect(str(cache), timeout=max(0.001, remaining()))) as conn:
                        actual_count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
                        # A matching path and nonempty index are insufficient:
                        # verify the real indexed title/body actually contain
                        # the published search term, not just a forged CLI hit.
                        indexed_rows = [
                            conn.execute(
                                "SELECT title, norm FROM notes WHERE path = ?",
                                (path,)).fetchone()
                            for path in hits
                        ]
                    valid_hits = (
                        actual_count == result["indexed_notes"]
                        and all(
                            row is not None and
                            "memory" in " ".join(str(value or "") for value in row).casefold()
                            for row in indexed_rows
                        )
                    )
                except sqlite3.Error:
                    valid_hits = False
            else:
                valid_hits = False
            if (searched.returncode != 0 or not count
                    or result["indexed_notes"] <= 0 or not valid_hits):
                result["reason"] = "no_source_backed_hit"
                return result
            if time.perf_counter() - start > timeout:
                result["reason"] = "timeout"
                return result
            result["status"] = "pass"
            result["reason"] = "ok"
            return result
    except subprocess.TimeoutExpired:
        result["reason"] = "timeout"
        return result
    except (OSError, ValueError):
        result["reason"] = "process_or_filesystem_error"
        return result
    finally:
        result["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)


def evaluate(repeat, source=ROOT, timeout=TIMEOUT):
    """Repeat the full temporary-clone path; report failures, not just a median.

    Each trial gets a fresh Git clone and SQLite index. Median includes failed
    trials to avoid silently cherry-picking fast successes.
    """
    trials = [measure(source, timeout) for _ in range(repeat)]
    durations = [trial["elapsed_ms"] for trial in trials]
    successes = sum(trial["status"] == "pass" for trial in trials)
    commits = [trial.get("commit_sha") for trial in trials]
    stable_commit = bool(commits[0]) and all(sha == commits[0] for sha in commits)
    report = {
        "repeat": repeat,
        "successes": successes,
        "success_rate": round(successes / repeat, 3),
        "commit_sha": commits[0] if stable_commit else None,
        "median_ms": round(statistics.median(durations), 3),
        "max_ms": max(durations),
        "trials": trials,
    }
    if repeat == 1:
        # Keep the existing one-trial JSON keys for CI consumers.
        report.update(trials[0])
    else:
        report.update({
            "status": "pass" if successes == repeat else "fail",
            "reason": "ok" if successes == repeat else "one_or_more_trials_failed",
            "elapsed_ms": round(sum(durations), 3),
        })
        # A moving source branch cannot yield one comparable repeatability
        # sample, even if each individual clone happened to find a hit.
        if successes == repeat and not stable_commit:
            report["status"] = "fail"
            report["reason"] = "commit_mismatch"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=1,
                        help="independent local-clone trials (1..5, default 1)")
    args = parser.parse_args(argv)
    if not 1 <= args.repeat <= MAX_REPEAT:
        parser.error("--repeat must be between 1 and %d" % MAX_REPEAT)
    report = {"schema_version": 1,
              "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "probe": "clean_local_git_clone_to_first_keyword_hit",
              "scope": "clean-source Git status preflight + local committed clone + index + keyword search; excludes remote network, Python setup and editor time",
              "python": sys.version.split()[0], "platform": sys.platform}
    report.update(evaluate(args.repeat))
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
