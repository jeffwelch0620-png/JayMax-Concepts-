#JayMax Restaurant Group — Inventory / Prep / Food-Costing App (JMAX Handoff)

A multi-location restaurant operations platform: inventory counts, purchasing/par
guidance, recipe costing, prep planning with auto inventory deduction, a purchase-order
approval chain (with supplier email + PDF), an ownership rollup dashboard, and an
AI assistant ("Sous").

**Stack:** React 19 (CRA + CRACO) · FastAPI · MongoDB (Motor async) · Tailwind + shadcn/ui
· Emergent LLM (OpenAI GPT-4o via `emergentintegrations`) · Resend (managed) for supplier email.

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
- MongoDB 5+ running locally or a connection string (Atlas works)

## Setup — Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# emergentintegrations comes from a private index:
pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
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
`MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `EMERGENT_LLM_KEY` (AI assistant),
`EMERGENT_EMAIL_KEY` + `EMAIL_FROM_NAME` (supplier email), `PUBLIC_APP_URL`
(server origin used to build the PO-PDF link in emails — must be a first-party https URL).

## Tests

```bash
cd backend && pytest tests/ -q      # requires backend running + MONGO_URL
```

## Security note (read before sharing widely)

The app currently has **no authentication** on its APIs (staff PIN gates only the
read-only staff prep sheet). This is a deliberate, deferred decision — RBAC is on the
roadmap. See `docs/ACCESS_POLICIES.md` and `docs/KNOWN_GAPS.md`.
