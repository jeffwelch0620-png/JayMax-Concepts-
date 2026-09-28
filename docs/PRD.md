# Bert's Restaurant Group — Operations Platform

## Original Problem Statement
User had a standalone 2,786-line React JSX inventory & food-costing app (Bert's Hometown Grill & Pizzeria, localStorage-only) built in Claude/ChatGPT. Goals: (1) audit and improve it, (2) rebuild with data persistence, (3) add a Prep module — daily/biweekly/weekly prep lists from a separate prep inventory with automatic raw-inventory deduction via established recipes and prep breakdown into service containers, (4) multi-location: three restaurants (Bert's Hometown Grill & Pizzeria, Rudd's Pies and Fries, Papa Leoni's Pizza) each with their own inventory/recipes, plus an Ownership Management Dashboard over all three (~$8M combined annual sales, high volume), (5) ChatGPT AI assistant integration. Roadmap after this: Scheduling, then Checklists & Compliance, Training, SOPs.

## Architecture
- **Backend** `/app/backend/server.py` — FastAPI + Motor (MongoDB). Per-restaurant namespaced documents (`restaurantId`). Routes: `GET /api/state/{rid}` (full state, auto-seeds on first hit), `PUT /api/state/{rid}/{collection|salesPeriod|areas}` (bulk persistence), `POST /api/prep/{rid}/complete|apply-sales|use-container` (server-side atomic prep deduction), `GET /api/owner/summary` (3-store rollup), `POST /api/ai/chat` (SSE streaming, OpenAI gpt-5.4 via EMERGENT_LLM_KEY, live-data system context, chat history in Mongo), `GET/DELETE /api/ai/history/{rid}`, `GET /api/health`.
- **Frontend** `/app/frontend/src/` — React 19 + Tailwind (dark slate theme, Outfit/Inter/JetBrains Mono). `lib/calc.js` holds all ported business logic (UOM conversion, portion costing, variance, invoice CSV import w/ fuzzy matching, order pack conversion). `lib/api.js` client incl. SSE stream reader. Components: DashboardTab, PrepTab, CountsTab, SetupTab, InvoicesTab, OrderTab, MenuTab, CostingTab, RecipeCardsTab, SalesTrackingTab, AdjustmentsTab, HistoryTab, SchedulingTab (placeholder), OwnerDashboard (recharts), AiAssistant (drawer).
- **Design** per `/app/design_guidelines.json` (Performance Pro + Luxury Gastronomy archetypes, per-location accent colors via CSS var `--acc`).

## User Personas
- Kitchen manager / owner-operator entering counts, invoices, recipes, prep at one location
- Ownership group viewing consolidated 3-location rollup

## Implemented (2026-06-13, iteration 1)
- Full audit of original JSX; all costing/variance/import logic preserved
- MongoDB persistence replacing localStorage (per-location isolation + auto-seed themed data per restaurant)
- Multi-location switcher + Ownership Dashboard (totals, per-store cards, food-cost leaders, comparison chart)
- **Prep Module**: prep recipes with par + frequency (set in Menu Costing), daily/biweekly/weekly prep lists, batch completion → automatic raw ingredient deduction server-side + prep stock, container breakdown, "send to service" container usage, "Deduct Prep Usage from Sales" using Sales Tracking dish quantities, deduction log
- **AI assistant "Sous"**: ChatGPT (gpt-5.4) streaming chat with live per-location inventory/costing/prep context, suggestion prompts, history
- Backup/Restore JSON per location; Sales Tracking auto-save debounce (was per-keystroke writes); UTC date-shift fix in todayISO()
- Testing: backend pytest 9/9 (`/app/backend/tests/backend_test.py`), frontend 100% pass (iteration_1)

## Implemented (2026-09-17, iteration 2 — Nightly Prep Count & Task Workflow)
- **Evening Prep Count** (Prep → Evening Count): per-item saved states, attributed to a person, dated sessions, blank ≠ zero (blank saves rejected), submit with uncounted acknowledgment, post-submit corrections archived as visible revisions (originals never erased)
- **Generated Prep Lists** (Prep → Prep List): par − counted = needed, rounded up to whole batches; draft → manager adjust → release to staff; uncounted items flagged "planned at full par"
- **Transactional task completion**: partial batches allowed, attributed, inventory auto-deducted via shared `_deduct_and_stock` engine, optional container breakdown per completion
- **Staff Prep Sheet**: full-screen PIN-gated view (default PIN 1234, changeable per restaurant in Prep → Planning) — tasks + recipe cards only, NO costs/inventory levels/editing; staff mark tasks prepped with their name
- **One-day overrides**: add one-off item / par-for-date / remove-for-date, each with note + date, applied at list generation
- **Projected sales**: manual daily entry per restaurant (Toast import deferred — needs user's Toast export/API details)
- **AI Par Advisor**: analyzes 45d of counts/prep/sales-usage/projections via gpt-5.4, returns advisory par recommendations with reasoning; manager applies/dismisses one tap; sparse history → trends only, no firm recs
- **Prep reporting**: per-item counted/prepped/used/sent-to-service over date ranges (`GET /api/reports/{rid}/prep`); ownership rollup strip per store (`GET /api/owner/prep-summary`)
- **Sous AI guardrail**: system prompt now explicitly read-only — never claims changes were made (fixes Jeff's Issue #1)
- Backend workflow verified end-to-end via script; UI verified via screenshots; fixed React 19 useEffect-returns-Promise crash in EveningCount

## Implemented (2026-09-17, iteration 3 — Standing Prep Items & Vessels)
- **Prep items** (`prep_items` collection, "Add Prep Item" in Prep List tab): reference an **inventory control number** (e.g. raw tomatoes → sliced tomatoes in 1/6 pans) or an **existing prep recipe**; each carries a standard vessel (17 presets: hotel pans 1/9–full, Cambros 2–22 qt, deli containers, squeeze bottles, custom) with editable capacity in the source item's portion unit, a par (vessels on hand), and a **Daily / One-off schedule selector** (inline toggle on the standing-items table)
- **Vessel-native workflow**: evening count counts these items in vessels; list generation plans `ceil((par − counted)×2)/2` vessels (half-vessel steps); completion deducts `vessels × capacity` portions of the raw inventory item and stocks prep inventory in vessel units; daily items auto-generate, one-off items add to a specific day via "+ Add to date" (duplicate-add rejected)
- Recipe-governed prep items override the recipe's own list entry (no duplicates); overrides (par/remove) now target prep items too; prep report and deduction log include prep items; staff sheet shows vessel tasks with no cost/par/capacity leakage
- Verified end-to-end via script on papa_leonis + screenshots of the modal and count screen

- Sales Tracking period now defaults to the **Wednesday–Tuesday workweek** (backend seed + fallback + UI); preset buttons "This Workweek"/"Last Workweek" plus explicit custom start/end range; "Start Next Workweek" rolls a fresh 7-day period

## Implemented (2026-09-17, iteration 4 — Bert's real data import)
- Wiped ALL Bert's sample data (items, purchases, dishes, prep workflow, projections, chat) and imported the YTD purchasing analysis workbook (`/app/scripts/import_berts_ytd.py`, reusable for other stores)
- **351 items** live (116 coded from Par Guide with suggested pars + proposed-code items; 91 code collisions merged as extra vendor lines), **235 flagged `needsReview`** — amber REVIEW pill + "Needs review only" filter in Item Setup; saving an item clears the flag
- Vendor SKUs wired from Multi-Vendor Sourcing + Items Needing Codes sheets; last-known prices attached; storage areas normalized (+ new "Unassigned" area)
- **Approximate price history**: 466 estimated first/last purchase lines (invoice # YTD-EST-FIRST/LAST) so Price History trends/alerts work — 156 vendor/desc rows couldn't be matched to a code and were skipped. To be replaced by real invoice-line imports (US Foods/PFG CSVs) later; no invoice-number collisions
- Portion sizes intentionally empty per user decision — recipe costing shows $0 until portions are entered
- Dishes/recipes now 0 at Bert's — menu + prep recipes need rebuilding against real control codes

## Implemented (2026-09-17, iteration 5 — Real invoice history)
- Imported **6,469 real invoice lines across 258 invoices ($540,305.87, Jan–Sep 2026)** for Bert's: PFG CustomerFirstInvoiceExport (1,400 lines) + 250 US Foods InvoiceDetails CSVs (5,069 lines) via `/app/scripts/import_invoices.py` (reusable: `python3 /app/scripts/import_invoices.py <rid> <pfg.csv|-> <usf_dir|->`)
- Removed all 466 YTD-EST estimated lines — Price History now shows true invoice data
- Matching: 2,828 by vendor SKU, 644 by exact name, 2,997 fuzzy; **321 items got SKU/price/pack data backfilled** from invoices; **931 lines unmatched** (items not in the catalog, e.g. pizza liners, cakes — written to review CSV, can be code-assigned later)
- Script routes by ship-to: 731 lines destined for Rudd's/Papa Leoni's were skipped (their catalogs aren't imported yet)

## Implemented (2026-06-21, iteration 6 — Order Approval Chain + mobile/selector fixes)
- **Purchase Orders module** (new "Purchase Orders" tab + `purchase_orders` collection): full approval chain Draft → Pending Approval → Approved/Rejected → Sent to Supplier → Received. Endpoints `GET/POST /api/orders/{rid}`, `PUT`, `POST .../submit|approve|reject|reopen|send|receive`, `DELETE`, and `GET /api/owner/orders`. Receiving a delivery adds received qty to `items.currentStock` (verified: WI-001 2→4).
- **Order Generator → Create PO**: each vendor banner has a "Create PO" button that spins a draft PO from that vendor's suggested order lines and jumps to the Purchase Orders tab (double-click guarded).
- **Manager / Owner role toggle** inside the tab gates approve/reject; status filter bar; inline reject-reason and receive (per-line qty) forms; person attribution + full status history per PO.
- **Owner Dashboard**: "Purchase Orders Awaiting Your Approval" panel lists pending POs across all locations with one-tap approve/reject.
- **Mobile fix**: Enter Counts now renders a card list below the `md` breakpoint (no more horizontal table overflow); table retained on desktop.
- **Selector fix**: storage-area dropdown / pills no longer render empty parentheses (e.g. "Unassigned ()") when an area has no prefix.
- Testing: 5/5 new backend pytests (`/app/backend/tests/test_purchase_orders.py`) + full frontend E2E all PASS (iteration_3).

## Implemented (2026-06-21, iteration 7 — PO Email, Receipt Match, Reorder + Toast sample reviewed)
- **PO Email Send** (Emergent-managed Resend): approved/sent POs can be emailed to a supplier. Recipient resolves server-side from a per-vendor contact (or a typed override that's saved only after a successful send); body is a server-side template (`_po_email_html`) passing the vendor/line-items/total. `POST /api/orders/{rid}/{oid}/email` (approved→sent, records `emailedTo`/`emailedAt`). Follows the Resend guardrail gate (`_assert_safe_email`). Env: `EMERGENT_EMAIL_KEY`, `EMAIL_FROM_NAME`.
- **Supplier Order Emails registry** in Item Setup (`vendor_contacts` collection, `GET/PUT /api/vendor-contacts/{rid}`): saved address per vendor prefills the PO email form; editable at send.
- **Order Receipt Match**: the receive form takes an optional invoice #; `receive_order` matches that invoice's Invoice-Master lines (qty + unit cost) against the PO by control number via `_match_invoice`, storing `receiptMatch` and flagging discrepancies. Receipt still adds received qty to inventory (now via a single bulk_write).
- **Reorder From History**: `POST /api/orders/{rid}/reorder-last` clones the most recent non-rejected PO for a vendor into a fresh Draft (per-vendor reorder bar in the PO tab).
- **Toast projection sample reviewed** (screencapture PDF): confirmed the data shape (per-day projected net sales + Proj. range, Sep 21–27). Held per user — Toast to be wired when the API feed is ready.
- Testing: 11/11 new backend pytests (`/app/backend/tests/test_po_new_features.py`) + 5/5 prior PO tests + full frontend E2E all PASS (iteration_4).

## Implemented (2026-06-21, iteration 8 — Discrepancy Report, PO PDF, Vendor Scorecard)
- **Ownership Discrepancy Report** (`GET /api/owner/discrepancies`): running list of received POs whose invoice match flagged qty/price differences, across all locations — panel on the Ownership dashboard (`owner-discrepancies`).
- **PO PDF** (reportlab, `GET /api/orders/{rid}/{oid}/pdf`): server-generated formatted purchase-order PDF; a "PDF" button on every PO card opens it, and the supplier email embeds a first-party https "Download Purchase Order (PDF)" link (built from X-Forwarded-Host; attachments aren't supported by the managed Resend proxy). PDF layout verified visually.
- **Vendor Scorecard** (`GET /api/owner/vendor-scorecard`): per-vendor performance across all locations — received orders, avg lead time (sentAt→receivedAt), price-accuracy %, avg price variance, total spend — table on the Ownership dashboard (`owner-vendor-scorecard`).
- **Toast**: still held — awaiting API access/credentials (data shape known from the reviewed projection dashboard).
- Testing: 4/4 new backend pytests (`/app/backend/tests/test_po_pdf_owner.py`) + all prior + full frontend E2E all PASS (iteration_5).
- Known note: PO PDF endpoint is public (no PIN gate); order ids carry ~40 bits of randomness. Acceptable under the current PIN-only model; revisit with signed URLs when RBAC lands.

## Implemented (2026-06-23, iteration 9 — Auto Price Update, Discrepancy Drill-Down, Scorecard Trends)
- **Auto Price Update** (`POST /api/orders/{rid}/{oid}/apply-prices`): on a received PO with flagged price discrepancies, an "Update saved prices to invoice" button (with a confirm) sets the item's vendor SKU price to the invoice cost (`priceSource='invoice'`), keeping future order estimates accurate. Verified WI-001 PFG 28.0→27.5.
- **Discrepancy Drill-Down**: clicking a flagged delivery on the Ownership dashboard jumps to that location's Purchase Orders tab and highlights/scrolls to the exact PO (receipt-match panel shows PO vs invoice side by side). Fixed a nav bug where the loc-change effect reset the tab (now threaded via `pendingTabRef`).
- **Vendor Scorecard Trends**: scorecard returns `leadTrend`/`priceVarTrend` (last-45d vs prior-45d) rendered as up/down/flat arrows (▲ worse / ▼ better).
- **Toast**: still held — awaiting API access/credentials.
- Testing: 5/5 new backend pytests (`/app/backend/tests/test_po_apply_prices_trends.py`) + all prior + full frontend E2E PASS (iteration_6); drill-down fix retest PASS (iteration_7).

## Security Audit + SEC-001 fix (2026-06-23, iteration 10)
- Ran full security audit. Verdict FAIL (pre-fix). Findings:
  - **SEC-001 [HIGH] — FIXED**: PO supplier-email built the "Download PDF" link from the caller-controllable `X-Forwarded-Host` header (host-header injection → attacker link in a trusted-brand email). Fix: link now derived only from a server-configured `PUBLIC_APP_URL` env var (validated https + host check); `email_order()` no longer reads request headers; link omitted if unset. Verified 8/8 (iteration_8) incl. spoofed-header send + full regression.
  - **CORS hardening — FIXED**: `allow_credentials` set to False (no cookie auth in use).
  - **SEC-002 [HIGH] — ACCEPTED RISK (deferred)**: no authn/authz on PO/owner/state/apply-prices/vendor-contacts endpoints — this is the user's explicit PIN-only/RBAC-deferred product decision. Revisit when RBAC lands.
  - **SEC-003 [MEDIUM] — OPEN**: unauthenticated costly LLM/email endpoints lack rate limiting (tied to the no-auth decision). Backlog.
  - Hardening backlog: per-store PIN provisioning (remove default 1234), managed secret store + key rotation, NoSQL operator coercion on untyped body/params.

## Known Notes / Tech Debt
- PUT collection sync is delete+insert (no transaction); acceptable at current scale, revisit with transactions if write volume grows
- AI key balance: Profile → Manage plan → Universal Key → Add Balance if AI responses stop
- Prep apply-sales draws down bulk on-hand, not individual containers

## Backlog
- **P0**: Toast POS integration — automatic projected sales/usage pull via API (sample dashboard reviewed; data shape = per-day projected net sales + range). Awaiting API feed/credentials.
- **P0**: Scheduling module (shift planner + labor-cost % vs sales) — currently a placeholder (kept as placeholder per user)
- **P1**: Checklists & compliance; SOP library; training module — kept as placeholders for now
- **P1**: Role-based auth (Ownership/Manager/Staff) — deferred; PIN-only per user
- **P2**: split server.py (~1700 lines) — extract routes/orders.py (PO/email/reorder/receipt-match ~450 lines), plus routes/prep.py, staff.py, ai.py, seeds.py, calc.py
- **P2**: `_match_invoice` keeps last unit cost when an invoice has multiple rows for one control number — consider weighted-avg or mixed-price flag
- **P2**: prep-list regenerate endpoint that snapshots draft to history before rebuilding

## Next Tasks
1. User review of initial build → recommendations for format/feature changes
2. Scheduling module build-out
3. Real data import for the three locations
