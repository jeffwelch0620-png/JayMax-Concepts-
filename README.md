# JayMax Restaurant Group — Inventory / Prep / Food-Costing App

The October 7 correction pass is documented in
[`docs/PR_REVIEW_CORRECTIONS.md`](docs/PR_REVIEW_CORRECTIONS.md). It records save/retry,
session-expiry, catalog batching, supplier selection, targeted recipe saves and
test-configuration fixes,
their validation, and remaining review work.
PRs 14–16 remain draft and unmerged; hosted development validation is still pending.

Current PR15 correction checks: **359 frontend tests / 44 suites** pass in default and
native configurations; **28 selected backend checks** and **four final recipe rechecks**
pass. The production build passes with three existing hook warnings. Checkpoint evidence
below describes the original snapshots, before the review corrections.

## Published workflow checkpoint — October 7, 2026

[Draft PR #15 — supplier, order and prep execution workflows](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/15)
publishes the continuation on `codex/inventory-workflow-continuation`. It is based on
`codex/postgres-invoice-capture`, the branch of
[draft PR #14 — PostgreSQL inventory foundation](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/14),
so its diff contains only work added since that checkpoint. Both PRs remain unmerged.
When ready, review and merge #14 first, retarget #15 to `main`, and revalidate the combined result.
Merge, operational enablement and deployment remain separate decisions.

The [foundation checkpoint README](docs/INVENTORY_FOUNDATION_README.md) records the original
invoice capture, purchased-item accounting, prep analytical journals, shared catalog and recovery
work. The [machine-readable review](docs/INVENTORY_REVIEW_STATUS.json) retains all 20 findings,
source anchors, scoped fixes and acceptance criteria. Its status remains **six fixed within their
stated local scope, 13 open and one deferred**. Publishing this checkpoint does not close the
remaining findings.

### Work completed since PR #14

| Area | Implemented and tested locally | Contract and evidence |
|---|---|---|
| Menu recipes | Canonical ingredient identities, strict definition validation and explicit incomplete/null planning costs. Missing mappings cannot silently become zero cost. | [Menu recipe integrity](docs/MENU_RECIPE_INTEGRITY.md) |
| Supplier prices | Immutable source observations and reviewed price adoption, retaining purchase provenance without rewriting original invoice facts. | [Supplier price history](docs/SUPPLIER_PRICE_HISTORY.md) |
| Orders | Versioned creation, edits, transitions and archive history; exact retries, current-state acknowledgements and retained uncertain drafts. | [Order command integrity](docs/ORDER_COMMAND_INTEGRITY.md) |
| Supplier contacts | Stable supplier relationships, reviewed legacy contact mapping, raw-field preservation and versioned saves. | [Supplier contact integrity](docs/SUPPLIER_CONTACT_INTEGRITY.md) |
| Standing prep | Immutable planning versions, explicit daily/bulk tracks, weekday/weekend pars, schedules and retirement history. | [Prep planning integrity](docs/PREP_PLANNING_INTEGRITY.md) |
| Dated prep drafts | Prior-day physical counts, explicit units/unknown stock, reviewed day overrides and sealed daily/bulk task sets. | [Dated prep drafts](docs/PREP_DAY_DRAFT_INTEGRITY.md) |
| Manager execution | Reviewed release/reopen commands and once-per-production-root links to measured production. | [Prep execution integrity](docs/PREP_EXECUTION_INTEGRITY.md) |
| Progress and corrections | Multiple whole batches per task, exact decimal totals, explicit finish and reviewed corrections/voids. | [Prep progress and reconciliation](docs/PREP_PROGRESS_INTEGRITY.md) |

For example, a task can accumulate multiple measured batches while remaining in progress.
Finishing requires an explicit reviewed decision, even if output exceeds its planned quantity.
A corrected batch is visible but requires renewed review; a void contributes zero and reopens
the task. Its production root remains reserved to the original task. Any linked production
history keeps the released list pinned. Fractional allocation and reassignment are future work.

### Inventory and accounting boundaries

- **Track 1 — actual purchased inventory:** opening physical count plus received purchases minus
  closing physical count determines actual usage. Counts include purchased items only, with
  explicit opening/closing count values for actual Food Cost. **Date received is the purchase
  date of record.** Taxes and fees remain separate and retained for future accounting modules.
- **Track 2 — prep and waste:** measured batches, physical prep counts, waste and expected usage
  explain the purchased-inventory baseline and support planning/variance analysis. They do not
  deduct or revalue Track 1.
- **Track 3 — sales:** future Toast portions provide theoretical usage and demand evidence.
  They do not change Track 1's accounting quantities or values.

All original invoice fields remain preserved by the foundation, including fields without a
current mapped output. No real invoices were imported for these checkpoints. Incomplete
analytics must disclose missing coverage before claiming an unexplained variance.

### Original workflow checkpoint verification and preserved snapshot

| Check | Recorded result and limit |
|---|---|
| Frontend | 329 tests passed across 40 suites with native paths enabled for testing; component tests, not a live browser walkthrough. |
| Selected backend | 30 distinct checks passed across the main run and two focused rechecks; not the full backend suite. |
| Offline contracts | 23 checks passed. |
| Recovery and upgrade | Whole SQL restore and an actual old-schema additive upgrade preserved immutable history, old request hashes and exact retries. |
| Production frontend build | Passed with three existing hook warnings in PurchaseOrdersTab, SchedulingTab and StaffTab. |
| Source checkpoint | Compilation/whitespace checks and all 70 prepublication source hashes verified; publication documentation updated separately. |

The backend main run passed 28 checks and encountered a connection timeout and a test-fixture
cached-statement error after DDL. Both cases passed focused rechecks. The upgrade fixture now
recycles connections after DDL, matching a stopped-app migration/restart rehearsal; the
application pool already disables statement caching. All attempts are retained.

The unchanged local prepublication archive is
`JayMax-prep-progress-2026-10-07-review-package.zip` (92 entries, 70 verified source paths),
SHA-256 `4687a6c254fb4eb4f9e3e1268788098a1e10db6002eb54c213c4f55acd9f33c5`.
It preserves the cumulative patch against foundation commit
`a472c8674a7e3f173e838907e1b9d13d7665a028`, review notes, source hashes, all test attempts and
earlier nested snapshots. Application implementation was published in commit
`d64dea4bbb4e42bb8f6e7c70acba7e516867c751`; this README records the subsequent publication update.
Local archives, runtime files and raw invoice samples are outside Git.

Tests used invented fixtures and disposable loopback PostgreSQL outside synced Documents/Drive.
These results are local evidence, not managed-platform or production acceptance proof. Earlier
milestone documents retain their original local/unpublished wording as historical records;
this README is the current publication and remaining-work guide.

### Schema and feature status

The continuation adds these migrations to the foundation dependency chain:

- `20261006_supplier_price_history.sql`
- `20261006_order_commands.sql`
- `20261006_supplier_contacts.sql`
- `20261007_prep_planning.sql`
- `20261007_prep_day_tasks.sql`
- `20261007_prep_execution.sql`
- `20261007_prep_progress.sql`

Consult each linked contract for prerequisites; this list is not a complete bootstrap command.
The progress migration follows execution and preserves old command serialization and retries.
All eleven native backend/frontend feature pairs remain false in repository examples, including
the new order, contact, planning, dated-task and execution gates. Price history uses the existing
purchase/accounting/catalog gates. Installed database guards continue holding covered legacy
writers even with a new flag off; flag toggles alone are not a rollback plan.

No operational migrations, feature enablement or deployment were performed. New execution
writes retain existing owner/manager authorization. Staff identity/assignment and login/PIN
redesign remain future work. Draft retention currently covers signed-in navigation; persistence
through browser reload or logout is not promised.

### Next build sequence and completion checks

1. **Native staff prep count submissions.** Define location/date/product/count scope and actor
   evidence; distinguish unknown from zero; preserve immutable submissions and manager review
   before counts feed dated planning. Complete when duplicates, concurrent conflicts, access
   boundaries and uncertain-save recovery are tested without changing Track 1.
2. **Verified container execution.** Normalize dimensions, units and capacity; distinguish
   stated, brimful and usable-fill measurements. Require reviewed recipe/output conversions.
   Complete when partial containers and service movements preserve exact identity/quantity
   without the legacy whole-group deletion behavior.
3. **Staff task access and assignment.** Connect verified identities to permitted stores and
   tasks. Complete when assignment, authorization, acknowledgements and retained drafts are
   tested; shared-PIN name selection alone must not confer elevated access.
4. **Finish the remaining integrity and operating cutover.** Close direct legacy API gaps,
   full canonical-unit/menu/price contracts, broader retirement and scope policy, invoice edge
   cases, durable recovery and supplier delivery/outbox behavior. Rehearse a supported baseline,
   ordered migrations, seeds/grants and native backup/restore before any enablement. The
   [foundation review](docs/INVENTORY_FOUNDATION_README.md) and machine-readable finding criteria
   remain the full acceptance list.
5. **Reserved integrations.** Add Toast, Scheduling, Operations and Analytics against stable
   identities and versioned contracts. Retain external event/revision IDs, date/unit/recipe
   evidence, corrections and completeness; compare common physical-count boundaries and avoid
   duplicate theoretical usage. Toast remains analytical evidence, separate from accounting.

Continue the next milestone on a separate local branch from this published checkpoint.
Keep #15 stable for review; publish the next draft PR only when authorized. If #15 changes,
reconcile those changes into the local continuation before its later publication.

The deployment overview below describes the earlier application configuration. It is not
evidence that these workflows are deployed or that a clean target reproduces them. Supported
managed-platform bootstrap and the broader operating cutover remain unfinished.

A multi-location restaurant operations platform for Bert's Hometown Grill & Pizzeria, Rudd's Pies
and Fries, and Papa Leoni's Pizza. It covers:

- inventory counts
- purchasing/par guidance
- recipe costing
- prep planning and measured production with separate analytical inventory evidence
- a purchase-order approval chain, with supplier email and PDF
- an ownership rollup dashboard
- an AI assistant ("Sous") and an AI par advisor

**Stack:**
- **Frontend:** React 19 (CRA + CRACO), Tailwind + shadcn/ui
- **Backend:** FastAPI
- **Database:** Supabase (Postgres, via asyncpg)
- **AI:** Claude, through the Anthropic API
- **Email:** Resend
- **Hosting:** Render, configured in `render.yaml`

**No secrets are in this repo.** See `backend/.env.example` and `frontend/.env.example` for placeholders.

---

## Live deployment

| Piece | Where |
|---|---|
| Web app (static site) | `https://jaymax-concepts.onrender.com` |
| API (Python web service) | `https://jaymax-api.onrender.com` — health check `GET /api/health` |
| Database | Supabase Postgres (37 tables, RLS enabled on all; see `supabase/`) |
| Deploy branch | `main` (Render redeploys on push) |

First-deploy steps (Render services, secrets, bootstrapping the owner) are in
[`docs/HOSTING_PROVIDERS.md`](docs/HOSTING_PROVIDERS.md).

---

## Repository layout

```
backend/
  server.py            # all routes: auth, inventory, costing, prep, PO chain, AI, email/PDF
  db_pg.py             # Postgres pool (connect timeout + background retry)
  requirements.txt     # pinned Python deps (public PyPI only)
  .env.example         # placeholders only
  tests/               # pytest suites (see Tests)
frontend/
  src/                 # App.js, components/, lib/ (api.js, calc.js), hooks/
  package.json, yarn.lock
  .env.example
supabase/
  schema.sql           # pg_dump of the live schema
  README.md            # applied migrations, RLS notes
migrations/            # earlier SQL plus new review-only native migrations; see checkpoint README
scripts/               # data import + Mongo->Postgres transforms (not used: no Mongo data was migrated)
sample-data/           # sanitized demo dataset (not operational data)
docs/                  # schema, access policies, hosting, migration plan, PRD
render.yaml            # Render Blueprint for both services
```

---

## How it's set up

- **Database:** Supabase Postgres only. `USE_PG=true` on the backend, so it never connects to MongoDB.
  - The legacy Mongo route families return `410` in this mode.
  - The frontend calls `/api/pg/*` by default. Only a build with `REACT_APP_USE_PG=false` uses the legacy routes.
- **Sign-in:** email + password accounts are stored in `app_users`.
  - Passwords are hashed with PBKDF2. Sessions are HMAC-signed tokens (`AUTH_SECRET`).
  - Roles: `owner`, `manager`, `staff`, `readonly`, each with per-store access.
- **Staff PIN portal:** cooks tap in with a shared per-store PIN and pick their name from the roster.
- **Managing access (owners):** the **Staff** tab has two parts:
  - **Email / Password Logins:** create, list, reset password, remove.
  - **PIN Roster:** the names people pick after entering the shared PIN.
- **AI (Sous chat + par advisor):** runs through the Anthropic Python SDK.
  - Model: `claude-opus-5-5` (override with `ANTHROPIC_MODEL`).
  - Server-side refusal fallback is turned on.
  - When Sous can't answer, the chat shows the cause: a missing or bad key, no credits, a key not tied to a workspace, or the model not being available.
- **Supplier email:** sent through the Resend API from `EMAIL_FROM_ADDRESS`, which must be on a domain verified in Resend.

---

## Environment variables

### Backend (`jaymax-api`)

| Variable | Required | Purpose |
|---|---|---|
| `USE_PG` | yes | `true` — Supabase mode |
| `DATABASE_URL` | yes | Supabase connection string (Connect → Shared pooler, transaction mode) |
| `PYTHON_VERSION` | Render | `3.11.9` |
| `AUTH_REQUIRED` | yes | `true` |
| `AUTH_SECRET` | yes | Random secret that signs session tokens (Render generates it) |
| `CORS_ORIGINS` | yes | The web app's exact https origin, no trailing slash |
| `PUBLIC_APP_URL` | yes | The API's own https URL (PO-PDF links in emails) |
| `ANTHROPIC_API_KEY` | for AI | Anthropic API key — create it **inside a workspace** |
| `ANTHROPIC_WORKSPACE_ID` | only if needed | Needed only for an organization-level key that isn't tied to a workspace |
| `ANTHROPIC_MODEL` | no | Override the AI model |
| `RESEND_API_KEY` | for email | Resend API key |
| `EMAIL_FROM_ADDRESS` | for email | Sender address on a Resend-verified domain |
| `EMAIL_FROM_NAME` | no | Sender display name (render.yaml sets "JayMax Restaurant Group") |
| `SESSION_TTL_SECONDS` | no | Session length (default 28800 = 8 h) |
| `RATE_LIMIT_PER_MINUTE` | no | AI chat / order email rate limit (default 60) |
| `BOOTSTRAP_TOKEN` | one time | Only to create the first owner; delete it afterwards |

### Frontend (`jaymax-concepts`)

These are read when the site is built, so redeploy the static site after changing them.

| Variable | Value |
|---|---|
| `REACT_APP_BACKEND_URL` | `https://jaymax-api.onrender.com` (no trailing slash) |
| `CI` | `false` (so existing lint warnings don't fail the build) |

Render static-site settings:
- Root directory: `frontend`
- Build command: `yarn install --frozen-lockfile && yarn build`
- Publish directory: `build`
- Rewrite: `/*` → `/index.html`

---

## Local development

Prerequisites: Python 3.11+, Node 18+ with **Yarn** (not npm), and a Postgres connection string
(Supabase, or a local Postgres loaded from `supabase/schema.sql`).

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in real values; USE_PG=true
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Frontend
cd frontend
yarn install
cp .env.example .env          # REACT_APP_BACKEND_URL=http://localhost:8001
yarn start                    # http://localhost:3000
```

All API routes are under `/api`; Postgres routes under `/api/pg`.

### First owner account

The first owner is created once, while `BOOTSTRAP_TOKEN` is set on the API, by calling
`POST /api/auth/bootstrap`. The exact request is in `docs/HOSTING_PROVIDERS.md`. After that:

1. Delete `BOOTSTRAP_TOKEN` from the API's environment.
2. Create every other login from **Staff → Email / Password Logins**.

---

## Tests

```bash
cd backend
# Offline unit tests (no database needed)
pytest --noconftest tests/test_pg_routes.py tests/test_pg_migrations.py -q
# Integration tests against a real Postgres loaded from supabase/schema.sql
TEST_PG_URL=postgresql://postgres@localhost:55432/jmax_test \
  pytest --noconftest tests/test_pg_local_integration.py -q
```

- The AI tests run the real Anthropic SDK against a mock HTTP transport, so they make no network calls and need no key.
- The other suites in `backend/tests/` target the legacy Mongo deployment through a running server, so they need its URL and credentials.

---

## Security

- Every API route requires a signed-in session. Roles and per-store access are enforced in the backend.
- The staff portal is the one exception by design: it uses a per-store PIN. **Set a custom PIN for every store.** A store without one accepts `1234`.
- RLS is enabled on every Supabase table with no policies, so the public `anon` key can't read or write anything. The backend connects as the database owner.
- Never commit keys or passwords, and never paste them into chat or tickets. Enter them only in Render or Supabase.

More detail: [`docs/ACCESS_POLICIES.md`](docs/ACCESS_POLICIES.md) and [`docs/KNOWN_GAPS.md`](docs/KNOWN_GAPS.md).
