# JayMax Restaurant Group — Inventory / Prep / Food-Costing App

A multi-location restaurant operations platform for Bert's Hometown Grill & Pizzeria, Rudd's Pies
and Fries, and Papa Leoni's Pizza. It covers:

- inventory counts
- purchasing/par guidance
- recipe costing
- prep planning with automatic inventory deduction
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
migrations/            # one-off SQL already applied to Supabase (see supabase/README.md)
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
