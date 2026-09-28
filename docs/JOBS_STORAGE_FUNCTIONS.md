# Functions, Jobs & Storage Definitions

## Serverless / cloud functions
**None.** All logic lives in the single FastAPI service (`backend/server.py`). There are no
standalone lambda/edge functions.

## Scheduled / background jobs
**None currently configured.** There is no cron/scheduler in this codebase (no
`.emergent/crons.yml`, no APScheduler). Sales projections (Toast) are entered manually.

Roadmap candidates (not yet built):
- Weekly ownership digest email (delivery discrepancies + vendor scorecard).
- Nightly par-recommendation recompute.

## Data-ingest "migrations" (`scripts/`)
Run manually against `MONGO_URL`/`DB_NAME`. These are the closest thing to migrations —
they populate/replace `items` and `purchases`.
- `import_berts_ytd.py` — imports the YTD purchasing-analysis par guide (items + suggested pars), with dedupe.
- `import_invoices.py` — parses real PFG / US Foods invoice CSVs into `purchases`
  (routes lines by ship-to; skips lines for other locations).
> These expect the original source spreadsheets/CSVs, which are **not** included (operational data).

## Object / file storage
**No external object storage** (no S3/GCS bucket wiring in use). Files are handled in-process:
- **PO PDFs** are generated on demand with `reportlab` and streamed from
  `GET /api/orders/{rid}/{oid}/pdf` (not persisted).
- Spreadsheet/CSV imports are read from local disk by the `scripts/` jobs.
- `boto3`/`s3transfer` are present transitively but not used by app code.

## Third-party integrations (runtime)
| Integration | Purpose | Key(s) |
|---|---|---|
| Emergent LLM (OpenAI GPT-4o via `emergentintegrations`) | "Sous" AI assistant (read-only over DB) | `EMERGENT_LLM_KEY` |
| Resend (Emergent-managed) | Supplier purchase-order emails | `EMERGENT_EMAIL_KEY`, `EMAIL_FROM_NAME` |

## Key API surface (all prefixed `/api`)
- `GET /health`
- `GET /state/{rid}` · `PUT /state/{rid}/{collection}` (bulk replace a collection)
- Items/dishes/areas/adjustments CRUD; counts; costing; sales; projections
- Prep: `POST /prep/session`, `POST /prep/complete-task`, prep list generate/update, overrides
- Purchase Orders: `POST /orders/{rid}`, `.../submit|approve|reject|reopen|send|receive|email|apply-prices`, `reorder-last`, `GET .../pdf`
- Owner rollups: `GET /owner/summary`, `/owner/prep-summary`, `/owner/orders`, `/owner/discrepancies`, `/owner/vendor-scorecard`
- Vendor contacts: `GET/PUT /vendor-contacts/{rid}`
- AI: `POST /ai/chat`, `GET/DELETE /ai/history`
