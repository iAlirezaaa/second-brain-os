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
