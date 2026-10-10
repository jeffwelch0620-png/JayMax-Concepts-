# Native inventory displays and operating summaries

Local milestone, October 5, 2026. Default flags remain disabled. No operational
invoice import, live migration, deployment, commit, push or PR accompanies it.

## Accounting basis

Track 1 remains purchased items only. Actual usage is opening physical quantity
plus net received purchases minus closing physical quantity. Food Cost uses
explicit opening value plus net received food cost minus explicit closing value.
Tax, fees and nonfood are retained separately. Prep, waste and sales are separate
explanations; they cannot change the purchase/count ledger.

`GET /api/pg/purchases/{store_id}/operating-summary` is a read-only, repeatable-read
view. Its purchase window includes the as-of date and previous 29 calendar days,
using reviewed received dates. Signed reversals, replacements and credits are
included; supplier invoice dates and future receipts do not determine this total.
The default as-of date uses UTC; the response makes that convention explicit.

The physical position uses the latest unsuperseded count on or before the as-of
date within the current scope revision. Count date and receipt timing take
precedence over entry time. Only a complete count with confirmed explicit values
has an inventory total. A missing scope, missing count, incomplete replacement or
disabled actual-inventory workflow leaves the value unavailable. It does not
substitute an older scope/count, catalog price or zero. Missing native schema
returns a setup error.

The dated count is not live on-hand. Receipts alone cannot establish what remains
after consumption. Owner totals retain each store's count date and are unavailable
if any store lacks a confirmed value. Stores may have different count dates;
their aggregate is a sum of dated measurements, not simultaneous group stock.

## Screens and AI context

Item Setup shows the dated native count separately from catalog planning fields.
In actual mode the item adapter/server do not expose legacy stock as current stock,
and the old editable stock field is held. The dashboard uses Actual Inventory;
purchase-only mode displays the awaiting-count setup state. Old invoice arrays
are not fetched as native accounting purchases. The sales accounting calculator
is held until the separate sales explanation ledger is connected.

Owner cards show explicit dated count values, signed net received food purchases,
and unavailable automatic shortfall alerts. Recipe cost percentages and legacy
waste estimates are labeled estimates. Legacy vendor/discrepancy rollups are held
in native mode; per-order native comparisons remain available. AI context uses
the same native summary, retains dates and unknown states, and excludes legacy
stock and old invoice totals. Neither surface invents live stock or Food Cost.

## Ordering

Actual-mode ordering lists enabled purchased items and starts with blank
quantities. The user chooses a supplier, enters a quantity in that supplier's
purchase unit, supplies a planning note and confirms the quantities/units. Pars
and catalog prices are references. No portion-based conversion or automatic
shortfall calculation supplies an order quantity.

Only a draft PO is created; it does not post purchases or stock. A confirmed
response must match the restaurant, draft status and submitted item/unit/quantity
lines. A connection failure, server failure or malformed acknowledgment holds
further submission until the user checks Purchase Orders. Draft creation does not
yet have a durable idempotency key; refreshing the planner does not resolve an
uncertain outcome. That remains an operational limitation.

Flag-off workflows are retained. Frontend/backend flags must agree before cutover.
Scoped staff drafts and manager acceptance are now implemented; see
[staff count drafts](STAFF_COUNT_DRAFTS.md). Versioned prep/waste/Toast ledgers,
native comparison rollups, historical reconciliation and managed-platform
recovery remain future work.

## Validation and test location

Invented-data native checks cover signed received windows, store isolation,
explicit-value counts, scope changes, incomplete corrections, backdated/future
counts, real owner/API/AI reads and missing schemas. Frontend checks cover unknown
values, manual supplier-unit ordering, uncertain saves, owner labels, held legacy
rollups and flag-off compatibility. Current evidence is packaged separately from
earlier full-suite and restore evidence; no fresh full-suite or browser visual
validation is claimed.

Volatile local PostgreSQL files now use
`%LOCALAPPDATA%/JayMaxTests/postgres17/55439/data`, outside the synced Documents
workspace. The old stopped test folder is preserved to avoid triggering a mass
sync deletion. Durable test reports and review packages remain in the workspace.
