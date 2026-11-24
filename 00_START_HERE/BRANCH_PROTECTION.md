# Protected-main CI status checks — read-only audit

**Observed 2026-11-14 (UTC):** GitHub's public
[`GET /branches/main`](https://api.github.com/repos/iAlirezaaa/second-brain-os/branches/main)
reported that `main` is protected but still requires
`test (ubuntu-latest, 3.9)` and `test (ubuntu-latest, 3.12)`.
The current [CI workflow](../.github/workflows/ci.yml) instead emits
`test (ubuntu-24.04, 3.9)` and `test (ubuntu-24.04, 3.12)`.
The Windows 3.9 and 3.12 status names match. All seven jobs on
[PR #111's CI run](https://github.com/iAlirezaaa/second-brain-os/actions/runs/43587402335)
completed successfully, but green jobs alone do **not** clear obsolete
required-status checks. Tracked in [issue #107](https://github.com/iAlirezaaa/second-brain-os/issues/107).

## Reproduce without editing GitHub settings

Run from the repository checkout (Python 3.9+ stdlib):

```sh
python scripts/ci_floor.py --live-protection
```

This explicitly performs **one read-only public HTTPS GET**, with a
10-second timeout, to the repository's `branches/main` endpoint. It sends
no credentials and changes no files or branch rules. It exits nonzero and
prints missing/obsolete check names if the branch configuration contradicts
the checked-in `jobs.test` matrix. A blocked, offline or rate-limited
request is a named refusal, **not a pass**.

For offline review, export the public JSON snapshot separately and run:

```sh
python scripts/ci_floor.py --branch-json path/to/branch-main.json
```

This offline mode makes **no** network request. Do not commit a snapshot
from a private repository or a response containing credentials. Normal
`python scripts/ci_floor.py` remains fully offline and does **not**
claim to have verified GitHub's remote settings.

## Local cross-platform matrix integrity

The offline audit also requires the active, failure-propagating `Unit tests` step
running `python -m unittest discover -s tests -v`. Missing or no-op tests,
and truthy/unknown `continue-on-error` in the test job, fail closed. This is a
narrow static check for the current workflow, not proof of actual runner execution
or a substitute for seven exact-head GitHub Actions results. Different legitimate
test commands need reviewed, test-first compatibility updates.

The same `ci_floor.py` offline gate also verifies that `jobs.test`
contains **both Ubuntu and Windows**. Other jobs (including the separate
Ubuntu backup-seal job) cannot prove that unit tests ran on Linux. Missing
or unrecognizable unit-test matrices now fail closed, even if the declared
Python floor appears in another job. This is a static coverage check, not
a replacement for inspecting live GitHub Actions jobs.

## Required maintainer action

A repository administrator must open **Settings → Branches → main branch
protection → Require status checks to pass** (or the applicable repository
ruleset), preserving review and other protection requirements, and replace
only the two obsolete Ubuntu contexts:

| Remove obsolete required context | Require current emitted context |
| --- | --- |
| `test (ubuntu-latest, 3.9)` | `test (ubuntu-24.04, 3.9)` |
| `test (ubuntu-latest, 3.12)` | `test (ubuntu-24.04, 3.12)` |

Keep `test (windows-latest, 3.9)` and
`test (windows-latest, 3.12)` required and leave unrelated protections
untouched. The diagnostic does **not** administer GitHub; this integration
does not have branch-protection write access. Do **not** use an admin bypass,
force push, fictitious status, or a renamed job that conceals its runner.

## Verify the before/after check sources (2026-11-24)

Before changing settings, save the public JSON from the branch-summary URL
above as `before.json` (browser Save As, JSON rather than HTML); after
the authorized change, save a fresh response as `after.json`. Store both
outside the checkout. The 2026-11-24 read-only response listed App ID 15368
for all four required checks. Preserve each existing check source; the
number is an observation, not a hardcoded requirement for another repo.

For this exact two-context migration, copy the following example into a
temporary `verify_contexts.py` file outside the checkout. It compares
both context names and app IDs, including unrelated checks, and refuses
a missing Windows check, a changed source, an unchanged snapshot, or
duplicate entries. The example uses only Python 3.9+ standard library.

<!-- context-migration-example -->
```python
import json
import sys
from pathlib import Path


def checks(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("protected") is not True:
        raise ValueError("main is not reported protected")
    required = data["protection"]["required_status_checks"]
    rows = required["checks"]
    mapping = {row["context"]: row["app_id"] for row in rows}
    if len(mapping) != len(rows) or set(mapping) != set(required["contexts"]):
        raise ValueError("duplicate or inconsistent required checks")
    return mapping


try:
    before, after = (checks(path) for path in sys.argv[1:])
    expected = dict(before)
    for version in ("3.9", "3.12"):
        old = f"test (ubuntu-latest, {version})"
        new = f"test (ubuntu-24.04, {version})"
        if new in expected or old not in expected:
            raise ValueError("unexpected before snapshot; inspect manually")
        expected[new] = expected.pop(old)
    if after != expected:
        raise ValueError("required context names or check sources changed unexpectedly")
except (OSError, KeyError, TypeError, ValueError) as exc:
    raise SystemExit(f"REFUSED: {exc}")
print("OK: only the two required Ubuntu context names changed")
```
<!-- /context-migration-example -->

Run it from the directory containing the three temporary files:

```sh
python verify_contexts.py before.json after.json
```

On Windows, use `py -3` if that is the verified Python launcher; on
macOS/Linux use `python3` if needed. This is an offline, read-only
comparison. A passing comparison **does not** prove review rules,
rulesets, strictness, enforcement for administrators or the live PR's
merge eligibility; inspect those independently in GitHub settings.
If the detailed settings are inaccessible, stop before merging.
The public branch summary is not a complete protection-policy backup.
Do not claim that the migration was performed merely because the
synthetic example passes.

After the change, rerun `--live-protection`, inspect the actual seven CI
jobs and the PR's `mergeable_state`, and merge only if **all** repository
rules permit it. The audit checks the `test` matrix contexts, **not** all
possible rules or the backup checks. If `jobs.test` gains a custom display
name or non-inline matrix, the parser intentionally refuses to guess;
update its tested contract before relying on it.

**Rollback:** no persistent state is changed by either audit mode. The
administrator can restore the prior protection settings through GitHub's
normal review process if the replacement is incorrect; never weaken
requirements merely to make the check green.

**Next 1:** administrator aligns the two Ubuntu contexts, revalidates the
live snapshot, and unblocks reviewed/green fixes starting with PR #105.
**Next 2:** test merge readiness against all other repository rules and
check the next CI matrix revision for status-name drift.
