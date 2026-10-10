# Repeatable review checks

Run from the repository root on the reviewed branch. These are selected
review checks, not a claim that the entire historical backend suite passes.
Use a fresh Python virtual environment and install `backend/requirements.txt`.
The selected checks require Python 3.11 or later and the pinned pytest 9.1.1,
which includes subtest support. No real vendor CSV or private configuration is
needed for the offline checks; their invoice fixtures are invented.

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt
.venv/Scripts/python tools/run_review_tests.py offline --report ../review-evidence/offline.xml
```

On macOS/Linux, use `.venv/bin/python` in place of `.venv/Scripts/python`.
Use a new evidence path for each attempt. The runner sets synthetic authentication
values, disables dotenv loading, clears application database connections, and
refuses successful completion if selected checks were skipped. `--list` shows
the selection. `--noconftest` intentionally avoids the historical repository-wide
fixture file; these selected suites own their fixtures and do not depend on it.
Migration and feature guides are checked against their source constants first.

## Disposable PostgreSQL acceptance

Use an independently created **local test cluster**, never the hosted build
database or an application database. The test administrator role must be named
`purchase_implementation_test`, with a control database named
`native_purchase_test_control` and permission to create/drop disposable databases
and roles. Only explicit loopback connections with a port are accepted. Fixtures
create unique databases and clean them up; failure evidence must be inspected
before removing any leftover test databases. The runner does not initialize,
start, stop, or replace a cluster and does not apply migrations to the control
database.

```powershell
$env:NATIVE_PURCHASE_TEST_DSN = 'postgresql://purchase_implementation_test@127.0.0.1:55439/native_purchase_test_control'
$env:NATIVE_BACKUP_PG_DUMP = 'C:/path/to/postgresql/bin/pg_dump.exe'
$env:NATIVE_BACKUP_EVIDENCE = 'C:/path/to/private-local-review-evidence'
.venv/Scripts/python tools/run_review_tests.py database --report ../review-evidence/database.xml
```

Configure any required local test password privately; do not commit it or reuse
an application credential. Use PostgreSQL 17 or later with a matching `pg_dump`
version. The database profile includes the 19 combined purchase/count/prep/recovery
acceptance cases, partial-item change tests, and physical-conversion confirmation,
retry, source-staleness and fixed-unit guards. PostgreSQL migrations are
applied only inside disposable fixture databases. Database/role inventory before
and after a run and ownership of any server startup/shutdown remain the local
supervisor's responsibility. This runner is not a hosted migration or backup job.

## Browser application

In `frontend`, install the locked dependencies using Yarn 1.22.22 with
`yarn install --frozen-lockfile`, then run `yarn test --watchAll=false --runInBand`
and `yarn build`. Repeat the full tests with frontend feature settings unset,
explicitly held, and the matched native testing profile in
[BUILD_TEST_FEATURE_PROFILE.md](BUILD_TEST_FEATURE_PROFILE.md).
Set `REACT_APP_USE_PG=true` for held/native profiles and use a synthetic backend
URL during tests. These tests mock their network requests; they do not test the
live Render environment. Existing build warnings must be reported separately.

## GitHub merge checks

`.github/workflows/ci.yml` runs for pull requests (including drafts) and pushes to
`main`. Its stable **Inventory CI** result succeeds only when both frontend and
backend jobs succeed. Actions are pinned to commit SHAs, permissions are limited
to `contents: read`, and checkout does not retain credentials. There are no
deployment steps, hosted database credentials, operational CSVs or repository
secrets. Do not use `pull_request_target` to run contributed code.

The frontend uses **Yarn 1.22.22 with the frozen existing `yarn.lock`**. `npm ci`
would require a different lockfile, so CI follows this repository's declared
package manager. `tools/ci_frontend_profile.py` reads the reviewed feature map
without importing backend code and selects the full native browser profile.
Jest runs all component/adapter tests, then `CI=true` makes production-build
warnings fail the job. This does not alter Render's dashboard settings.

The backend installs the existing pinned requirements, runs both selected review
profiles, and requires nonzero executed tests with no skips, failures or errors.
It uses a disposable PostgreSQL 17 service and matching backup client. The literal
synthetic service password belongs only to this job and is not an application
credential. Fixtures install migrations in their own disposable databases and
exercise accounting isolation, corrections, exact replay and restore.

After a successful GitHub run, require the **Inventory CI** status on `main`.
This is a merge gate; it does not authorize merging a draft or accepting the live
workflow. The Bert's fictional item/count/history walkthrough remains a separate
acceptance step after an explicitly approved merge reaches the test deployment.

Component suites can use `frontend/src/testHelpers/componentApiMock.js` for a
complete API mock: native flags default off, configured read defaults return
empty synthetic shapes, and unconfigured calls fail explicitly. Writes must be
mocked deliberately with a valid receipt; this helper never invents save success.

The new item-change route requires frontend and backend from this correction
to be deployed together. An older backend does not implement that route.
