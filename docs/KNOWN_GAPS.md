# Known Gaps & Roadmap

## Known gaps / limitations
- **No authentication / RBAC** (SEC-002). All APIs are open; PO approval separation is not
  enforced server-side. Highest-priority gap before multi-user rollout.
- **No rate limiting** on AI (`/api/ai/chat`) or supplier email (SEC-003) — cost/DoS risk.
- **Default staff PIN `1234`** when a store hasn't set one.
- **Toast POS integration not built** — projected sales are entered manually. Data shape is
  known (per-day projected net sales + range) from a reviewed Toast dashboard; blocked on
  Toast API access/credentials.
- **Scheduling, Checklists/Compliance, SOPs, Training** are placeholders (Scheduling tab exists as a stub).
- **Vendor scorecard trends** need real received-PO history spanning ≥2×45-day windows to populate arrows.
- **PO PDF endpoint is public** (no PIN gate). Order ids carry ~40 bits of randomness;
  acceptable under PIN-only, revisit with signed URLs once RBAC lands.
- **`server.py` is large (~1,880 lines)** — should be split into route modules
  (routes/orders, prep, staff, ai, seeds; lib/calc).
- **Imports depend on external spreadsheets/CSVs** not shipped here.
- **`receiptMatch` keeps the last unit cost** when an invoice has multiple rows for one
  control number (no weighted average / mixed-price flag).
- **Wildcard CORS** origin in config (functionally fine now; tighten in production).

## Roadmap (prioritized)
- **P0** Toast POS live feed → Prep planning (blocked on API access).
- **P0/P1** RBAC (Ownership/Manager/Staff) with server-side approval gating.
- **P1** Rate limiting + input size caps on AI/email; per-store PIN provisioning.
- **P1** Order history/analytics; weekly ownership digest email (discrepancies + scorecard).
- **P2** Scheduling (labor % vs sales); Checklists/Compliance; SOP library; Training.
- **P2** Refactor `server.py` into route modules; signed PO-PDF URLs.
