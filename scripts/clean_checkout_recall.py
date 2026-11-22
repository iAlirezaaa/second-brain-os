#!/usr/bin/env python3
"""Measure a clean LOCAL Git checkout through the first source-backed keyword hit.

Run from a Git checkout: python scripts/clean_checkout_recall.py
A no-hardlinks clone copies committed files to a disposable directory, then
runs the documented ingest/search commands there. This includes local Git
clone time, NOT GitHub download latency, Python installation or editor time.
The source worktree must be clean: unstaged, staged and nonignored untracked
files are refused, because a local clone would silently omit them.
Default mode uses no network, LLM, user vault, or package installation.
Use --github to opt in to transferring this public repository over HTTPS.
"""
import argparse
import datetime
import json
import os
import re
import sqlite3
import statistics
import subprocess
import unicodedata
import sys
import tempfile
import time
from pathlib import Path
from contextlib import closing

# Parse committed Markdown with the same standard-library contract as KB ingest.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import parse_frontmatter

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 180
MAX_REPEAT = 5
PUBLIC_GITHUB_URL = "https://github.com/iAlirezaaa/second-brain-os.git"
ENV_KEYS = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
            "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE",
            "HOMEPATH", "LANG", "LC_ALL", "LC_CTYPE")


def _child_env():
    env = {k: os.environ[k] for k in ENV_KEYS if k in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONNOUSERSITE"] = "1"
    return env



def _checkout_paths_safe(checkout):
    """Refuse executable/cache symlink aliases in a disposable Git checkout.

    Resolve existing paths to catch Windows directory junctions as well as
    Unix symlinks. This is a diagnostic guard, not an OS process sandbox.
    """
    try:
        root = checkout.resolve(strict=True)
        for path in (checkout / "scripts", checkout / "scripts" / "kb.py",
                     checkout / ".kb", checkout / ".kb" / "kb.sqlite"):
            if path.is_symlink():
                return False
            if path.exists() and root not in path.resolve(strict=True).parents:
                return False
        return True
    except (OSError, RuntimeError):
        return False


def _public_markdown_source(checkout, relative_path):
    """Return a non-aliased public Markdown path, or None for a denied path.

    Both keyword and SQLite/source comparisons must enforce this boundary;
    the earlier keyword check cannot authorize a later unvalidated read.
    This is a best-effort diagnostic guard, not an atomic OS sandbox.
    """
    try:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            return None
        root = checkout.resolve(strict=True)
        candidate = checkout / relative
        source = candidate.resolve(strict=True)
        denied = ("09_operations", "11_control", "12_runtime",
                  "13_lab", "14_candidates", "15_system")
        if (candidate.is_symlink() or source != root.joinpath(*relative.parts)
                or root not in source.parents or not source.is_file()
                or source.relative_to(root).parts[0].casefold() in denied):
            return None
        return source
    except (OSError, RuntimeError, ValueError):
        return None


def _source_supports_keyword(checkout, relative_path, keyword="memory"):
    """Independently verify non-aliased committed Markdown, not only SQLite."""
    source = _public_markdown_source(checkout, relative_path)
    if source is None:
        return False
    try:
        if keyword.casefold() in Path(relative_path).stem.casefold():
            return True
        return keyword.casefold() in source.read_text(encoding="utf-8").casefold()
    except (OSError, UnicodeError, RuntimeError, ValueError):
        return False



def _indexed_row_matches_source(checkout, relative_path, row):
    """Compare a stored hit's complete content to the committed Markdown.

    A CLI can print a real source path and forge an SQLite keyword match while
    silently indexing unrelated bytes. Such a row is not recall provenance.
    """
    if row is None or len(row) != 3 or not all(isinstance(item, str) for item in row):
        return False
    try:
        title, body, norm = row
        source_path = _public_markdown_source(checkout, relative_path)
        if source_path is None:
            return False
        source = source_path.read_text(encoding="utf-8", errors="replace")
        frontmatter, expected_body = parse_frontmatter(source)
        heading = None
        for line in expected_body.splitlines():
            if line.startswith("# "):
                heading = line[2:].strip()
                break
            if line.strip() and not line.startswith("#"):
                break
        expected_title = str(frontmatter.get("title") or heading or Path(relative_path).stem)
        expected_norm = unicodedata.normalize("NFKC", expected_body).casefold().translate(
            str.maketrans({"ي": "ی", "ك": "ک"}))
        return title == expected_title and body == expected_body and norm == expected_norm
    except (OSError, UnicodeError, RuntimeError, TypeError, ValueError):
        return False



def _reported_hit_paths(output):
    """Parse KB search headers without dropping spaces or brackets in note names.

    The KB prints "path.md  [zone]  title" on unindented lines, followed by
    indented excerpts. The downstream Git tree and source checks still decide
    whether each parsed path can substantiate a successful recall.
    """
    return re.findall(r"(?m)^([^\s\r\n][^\r\n]*\.md)  \[", output)


def measure(source=ROOT, timeout=TIMEOUT, remote=False):
    """Return a failure-aware JSON-ready record; always delete the clone."""
    start = time.perf_counter()
    result = {"status": "fail", "reason": None, "elapsed_ms": None,
              "preflight_ms": None, "clone_ms": None,
              "ingest_ms": None, "search_ms": None,
              "indexed_notes": None, "matched_paths": [], "commit_sha": None,
              "transport": "git_remote" if remote else "local_git"}

    def remaining():
        left = timeout - (time.perf_counter() - start)
        if left <= 0:
            raise subprocess.TimeoutExpired("clean checkout first recall", timeout)
        return left

    def invoke(args, cwd=None):
        env = _child_env()
        if remote:
            # Public HTTPS must not prompt for credentials or read Git configs
            # that could rewrite this URL to a private host.
            env.update({"GIT_TERMINAL_PROMPT": "0",
                        "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_CONFIG_GLOBAL": os.devnull})
        return subprocess.run(args, cwd=str(cwd) if cwd else None,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=remaining(),
                              env=env, check=False)

    try:
        # A local clone contains committed bytes only. Reject a dirty source
        # instead of silently benchmarking an older revision than the user sees.
        # Porcelain status is machine-readable, locale-independent, and ignores
        # generated .kb/ indexes via the repository's .gitignore.
        if not remote:
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
            clone_cmd = (["git", "-c", "credential.helper=", "clone",
                          "--quiet", "--no-hardlinks"] if remote else
                         ["git", "clone", "--quiet", "--local", "--no-hardlinks"])
            cloned = invoke(clone_cmd + [str(source), str(checkout)])
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
            # Snapshot the tracked tree BEFORE running the indexer. A fake
            # ingest may create a plausible Markdown note inside this clone;
            # existing files are not necessarily committed source evidence.
            tree = invoke(["git", "ls-tree", "-r", "-z", "--name-only", "HEAD"],
                          cwd=checkout)
            if tree.returncode != 0:
                result["reason"] = "tracked_paths_unavailable"
                return result
            tracked_paths = set(tree.stdout.split("\0"))
            clone_end = time.perf_counter()
            result["clone_ms"] = round((clone_end - preflight_end) * 1000, 3)
            if not _checkout_paths_safe(checkout):
                result["reason"] = "unsafe_checkout_path"
                return result
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
            if not _checkout_paths_safe(checkout):
                result["reason"] = "unsafe_checkout_path"
                return result
            searched = invoke([sys.executable, str(kb), "search", "memory"], cwd=checkout)
            search_end = time.perf_counter()
            result["search_ms"] = round((search_end - ingest_end) * 1000, 3)
            count = re.search(r"\bindexed (\d+) notes\b", indexed.stdout)
            result["indexed_notes"] = int(count.group(1)) if count else None
            hits = _reported_hit_paths(searched.stdout)
            result["matched_paths"] = hits
            if not _checkout_paths_safe(checkout):
                result["reason"] = "unsafe_checkout_path"
                return result
            # Every reported hit must be a real local checked-in source.
            valid_hits = bool(hits) and all(
                path in tracked_paths
                and (checkout / path).is_file()
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
                                "SELECT title, body, norm FROM notes WHERE path = ?",
                                (path,)).fetchone()
                            for path in hits
                        ]
                    valid_hits = (
                        actual_count == result["indexed_notes"]
                        and all(
                            _indexed_row_matches_source(checkout, path, row)
                            and "memory" in (row[0] + " " + row[2]).casefold()
                            for path, row in zip(hits, indexed_rows)
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


def evaluate(repeat, source=ROOT, timeout=TIMEOUT, remote=False):
    """Repeat the full temporary-clone path; report failures, not just a median.

    Each trial gets a fresh Git clone and SQLite index. Median includes failed
    trials to avoid silently cherry-picking fast successes.
    """
    trials = [measure(source, timeout, remote=remote) for _ in range(repeat)]
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
    parser.add_argument("--github", action="store_true",
                        help="opt-in public GitHub HTTPS clone measurement")
    args = parser.parse_args(argv)
    if not 1 <= args.repeat <= MAX_REPEAT:
        parser.error("--repeat must be between 1 and %d" % MAX_REPEAT)
    report = {"schema_version": 1,
              "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "probe": ("public_github_https_clone_to_first_keyword_hit"
                        if args.github else "clean_local_git_clone_to_first_keyword_hit"),
              "scope": ("fixed public GitHub HTTPS clone + committed source checks + "
                        "index + keyword search; includes network download, excludes "
                        "Python setup and editor time"
                        if args.github else
                        "clean-source Git status preflight + local committed clone + "
                        "index + keyword search; excludes remote network, "
                        "Python setup and editor time"),
              "python": sys.version.split()[0], "platform": sys.platform}
    report.update(evaluate(args.repeat,
                           source=PUBLIC_GITHUB_URL if args.github else ROOT,
                           remote=args.github))
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
