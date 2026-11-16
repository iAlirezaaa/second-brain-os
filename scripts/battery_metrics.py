#!/usr/bin/env python
"""Measure the real HADES battery (issue #53), never a source-code estimate.

Usage: python scripts/battery_metrics.py [--timeout 900]
Outputs one JSON object. A bad/missing/ambiguous battery verdict exits 1 with
checks: null; it never becomes a plausible-looking zero or success.
No persistent data or network service is added. The underlying battery runs
against its own disposable, synthetic vault as in the existing CI gate.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATTERY = ROOT / "15_SYSTEM" / "scripts" / "test_hades.py"
SUMMARY = re.compile(r"^checks: ([0-9]+) \| passed: ([0-9]+) \| failed: ([0-9]+)$")
FAILURE = re.compile(r"^\s*FAIL(?:\s|:)", re.MULTILINE)
# The probe must not hand arbitrary ambient API credentials to its child.
ENV_NAMES = {"PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR", "HOME",
             "USERPROFILE", "APPDATA", "LOCALAPPDATA"}


def assess(output, returncode):
    """Accept exactly one coherent nonempty verdict from a successful battery run."""
    # Count all summary *attempts*, not only perfectly formatted ones.
    # Otherwise a valid line can conceal a second malformed or negative count.
    summaries = [line.strip() for line in output.splitlines()
                 if line.lstrip().startswith("checks:")]
    if len(summaries) != 1:
        raise ValueError("expected exactly one checks summary")
    match = SUMMARY.fullmatch(summaries[0])
    if match is None:
        raise ValueError("malformed checks summary")
    checks, passed, failed = (int(value) for value in match.groups())
    if checks <= 0 or passed + failed != checks:
        raise ValueError("battery check totals are empty or contradictory")
    if returncode or failed or FAILURE.search(output):
        raise ValueError("battery failed or printed a failure marker")
    return checks, passed, failed


def measure(path, timeout):
    started = time.monotonic()
    result = {"status": "invalid", "checks": None, "passed": None,
              "failed": None, "battery_sha256": None, "elapsed_seconds": 0.0}
    try:
        if timeout < 1:
            raise ValueError("timeout must be a positive integer")
        if not path.is_file():
            raise ValueError("battery script does not exist")
        result["battery_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        env = {key: value for key, value in os.environ.items() if key.upper() in ENV_NAMES}
        env["PYTHONIOENCODING"] = "utf-8"
        child = subprocess.run([sys.executable, str(path)], cwd=str(ROOT),
                               env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout)
        counts = assess((child.stdout or "") + "\n" + (child.stderr or ""),
                        child.returncode)
        result.update(status="verified", checks=counts[0], passed=counts[1],
                      failed=counts[2])
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        # Neither child stdout nor raw exception paths are returned: those might
        # accidentally contain local/private material or credential values.
        if isinstance(exc, subprocess.TimeoutExpired):
            result["error"] = "battery timed out"
        elif isinstance(exc, OSError):
            result["error"] = "battery could not be read or executed"
        else:
            result["error"] = str(exc)
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--battery", type=Path, default=DEFAULT_BATTERY,
                        help="override the executable battery path (for isolated tests)")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    result = measure(args.battery, args.timeout)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "verified" else 1


if __name__ == "__main__":
    sys.exit(main())
