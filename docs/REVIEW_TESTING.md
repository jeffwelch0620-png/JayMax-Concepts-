# Repeatable review checks

Run from the repository root on the reviewed PR17 branch. These are selected
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
acceptance cases and the partial-item change tests. PostgreSQL migrations are
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

The new item-change route requires frontend and backend from this correction
to be deployed together. An older backend does not implement that route.
