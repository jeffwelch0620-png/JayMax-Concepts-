#JayMax Restaurant Group — Inventory / Prep / Food-Costing App (JMAX Handoff)

A multi-location restaurant operations platform: inventory counts, purchasing/par
guidance, recipe costing, prep planning with auto inventory deduction, a purchase-order
approval chain (with supplier email + PDF), an ownership rollup dashboard, and an
AI assistant ("Sous").

**Stack:** React 19 (CRA + CRACO) · FastAPI · MongoDB (Motor async) · Tailwind + shadcn/ui
· Supabase (Postgres) · Claude (Anthropic API) for the AI assistant · Resend for supplier email.
Deployed on Render via `render.yaml`.

> This package is a **source + docs handoff**. It contains editable source, dependency/lock
> files, DB schema/collection definitions, data-ingest scripts ("migrations"), a sanitized
> **demo** dataset (isolated from operational data), and setup instructions.
> **No secrets are included** — see `backend/.env.example` and `frontend/.env.example`.

---

## Repository layout

```
handoff/
├── backend/                # FastAPI app
│   ├── server.py           # ALL routes, models, UOM/costing math, seeds, AI, PO chain, email/PDF
│   ├── requirements.txt    # Python deps (pinned)
│   ├── .env.example        # placeholders only
│   └── tests/              # pytest suites (PO chain, security, prep workflow)
├── frontend/               # React app (CRA + CRACO)
│   ├── src/                # App.js + components/, lib/ (api.js, calc.js), hooks/
│   ├── package.json
│   ├── yarn.lock           # lockfile
│   └── .env.example        # placeholders only
├── scripts/                # Data-ingest "migrations" (YTD par guide, real invoices)
├── sample-data/
│   └── demo_dataset.json   # sanitized, fabricated demo records (NOT operational)
├── scripts/load_demo_data.py  # loads demo_dataset.json into an isolated demo DB
└── docs/
    ├── DATABASE_SCHEMA.md      # every collection + field
    ├── ACCESS_POLICIES.md      # auth model, PIN, known risks (security audit)
    ├── JOBS_STORAGE_FUNCTIONS.md
    ├── DATA_SEPARATION.md      # demo vs operational
    ├── KNOWN_GAPS.md
    ├── HOSTING_PROVIDERS.md
    └── PRD.md                  # full product/requirements + changelog
```

---

## Prerequisites

- Python 3.11+
- Node 18+ and **Yarn** (do not use npm — resolutions rely on Yarn)
- A Supabase (Postgres) connection string -- or, for the legacy Mongo mode only, MongoDB 5+

## Setup — Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in real values
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

All API routes are prefixed with `/api`. Health check: `GET /api/health` → `{"status":"ok"}`.

## Setup — Frontend

```bash
cd frontend
yarn install
cp .env.example .env      # set REACT_APP_BACKEND_URL to your backend origin
yarn start                # http://localhost:3000
```

The frontend talks to the backend **only** via `REACT_APP_BACKEND_URL` (never hardcode URLs).

## First run / seeding

- On startup the backend auto-seeds the **restaurant registry** (`berts`, `rudds`,
  `papa_leonis`) and default storage areas. There are **no items/dishes** until you add
  them in the UI (Item Setup / Menu) or import them (see `scripts/`).
- To explore with fake data without touching operational records, load the **demo**
  dataset into an isolated database — see `docs/DATA_SEPARATION.md`.

## Environment variables

See `backend/.env.example` and `frontend/.env.example`. Required backend keys:
`USE_PG=true` + `DATABASE_URL` (Supabase; `MONGO_URL`/`DB_NAME` only in legacy Mongo mode), `CORS_ORIGINS`,
`AUTH_SECRET`, `ANTHROPIC_API_KEY` (AI assistant), `RESEND_API_KEY` + `EMAIL_FROM_ADDRESS` + `EMAIL_FROM_NAME`
(supplier email), `PUBLIC_APP_URL`
(server origin used to build the PO-PDF link in emails — must be a first-party https URL).

## Tests

```bash
cd backend && pytest tests/ -q      # requires backend running + MONGO_URL
```

## Security note (read before sharing widely)

Every API route requires a signed-in session (`AUTH_REQUIRED=true`, the default) with
roles `owner` / `manager` / `staff` / `readonly` and per-location access, enforced in the
backend. The staff portal is the exception by design: it signs in with a per-store PIN.
Set a custom PIN for every store before go-live -- a store without one accepts `1234`.
See `docs/ACCESS_POLICIES.md` and `docs/KNOWN_GAPS.md`.
