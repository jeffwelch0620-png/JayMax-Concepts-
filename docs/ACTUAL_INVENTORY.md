# Track 1: physical purchased inventory and explicit count values

User decisions confirmed 2026-10-04: count purchased inventory items only; use
explicitly confirmed count values for Food Cost. Prep and sales remain separate
explanations and cannot write or revalue this accounting baseline.

This extends the local `codex/postgres-invoice-capture` branch. Both purchase and
actual-inventory features remain disabled by default; there is no live migration,
real invoice import or operational deployment.

## The calculation

For each purchased food inventory item in a confirmed count scope:

```text
Actual usage = opening physical quantity + net received purchase quantity - closing physical quantity
Actual Food Cost = opening confirmed value + net received food purchase cost - closing confirmed value
```

Each quantity is converted to the same fixed store/item inventory unit using the
conversion confirmed with that count or purchase. Count values are the total USD
value of the physically counted inventory, excluding taxes and fees; they are
not per-case prices and are not calculated from current supplier/recipe prices.
The value/evidence note records the manager's basis for the explicitly confirmed
count value. Determining that value remains a human responsibility in this method.

Example: opening 2 cases × 20 lb = 40 lb, valued at $60; receipts 2 cases × 20 lb =
40 lb, food amount $40; closing 1.5 cases × 20 lb = 30 lb, valued at $45.
Actual usage is **50 lb**, and actual Food Cost is **$55**. Prep production, sales,
waste explanations, item portion specifications and a later $9,999 supplier price
do not change those numbers. Different units are never summed into a single total
quantity; only comparable item quantities and USD values are aggregated.

Price-only credits affect net food cost with zero physical quantity. Physical
returns reduce quantity and cost. No recorded waste is subtracted again from
count-based depletion. Sales revenue and Food Cost percentages are outside this
step; it supplies actual food usage and dollar cost, not a fabricated sales ratio.

## Scope and count facts

`actual_inventory.scopes` and `scope_items` retain a store's confirmed purchased
food inventory universe, inventory units, source item names and all raw stock
locations to include. Scope choices use registered raw items, including inactive
or sales-tracking-disabled items. Prepared items are excluded. An item being
eligible does not itself classify it as food; the reviewer chooses the full food
scope. Food purchases outside that scope make the report incomplete and block
closing until the scope/counts are reconciled.

Scopes are immutable versions. Two counts from different versions cannot be
silently compared. `ACTUAL_INVENTORY_SCOPE_HANDOFFS.md` describes reviewed
same-boundary handoffs with unchanged carried balances and explicit zero
additions/removals. Nonzero historical scope reconciliation remains separate.
Canonical inventory units are shared with purchases and cannot drift with a
changed case pack or recipe portion. New count units require an explicit factor.

`count_snapshots` and `count_lines` retain physical dates, receipt timing,
measured quantities, observed units, frozen conversion factors, explicit values,
confirmation and notes. All scope items appear exactly once. Blank quantities,
blank values and unconfirmed entries remain incomplete, never zero. A genuine
zero is explicitly entered as quantity 0/value 0. Positive inventory with an
explicitly confirmed zero value is retained as the reviewer's decision.

Incomplete snapshots can be saved without allowing a complete Food Cost report.
A recount appends a new snapshot referencing the previous one. Superseded
unclosed counts cannot be used for a new period. Counts referenced by a closed
period requires reviewed reopening before a linked recount. See
`ACTUAL_INVENTORY_CORRECTIONS.md` for suffix reopening and replacement reports.
Posted-invoice reversal rules remain a later step. Scope/item facts and count/posting history
reject update/delete, and closed count children cannot be extended.

## Received-date boundaries

The receipt date remains the accounting date. This version requires each full
count to state either **before all receipts** or **after all receipts** on its
physical count date. No clock time or time zone is invented.

- Before receipts on a date places the count boundary at the start of that date.
- After receipts on a date places it after that date's receipts, represented by
  the next date as an exclusive boundary.
- The period includes receipts on/after the opening boundary and before the
  closing boundary. Adjacent periods cannot include the same received date twice.

A count taken between deliveries is not supported by this daily convention and
must remain unclosed until receipt/cutoff precision is resolved. Users must not
select a before/after convention that misrepresents the actual physical count.

## Reports and period close

Report preview uses a consistent database snapshot and reads only frozen count,
scope and posted native purchase facts. The report identifies every purchase line
used, its count IDs, receipt window, quantity/cost components, errors, warnings
and a fingerprint. Missing confirmed rows or out-of-scope food purchases block
the overall actual Food Cost total. Negative usage/cost is displayed as an overage
for explicit review; it is not clamped to zero.

Closing uses the same store revision lock as purchase posting, recomputes the
report and rejects a fingerprint change since preview. The reviewer confirms the
counts/values and that all received purchases/credits in the window have been
reviewed and posted. This is necessary because an uncaptured supplier invoice or
an unreviewed file without a received date cannot be inferred into a period.

`period_closures` freezes each report generation and its source references. Closing reads back
the saved result before success. Duplicate keys return the identical saved record;
changed bodies are rejected. Periods cannot overlap or skip an interval between
active closed periods. The previous closing snapshot must be the next opening
snapshot, preserving both its physical quantity and its confirmed value.

Database guards block late native food receipt/return/credit mappings and batches
in closed windows, including mappings entered before closing but posted later.
Captured source files remain retained when such a posting is rejected. Reviewed
suffix reopening permits late postings, with original reports retained and
oldest-first linked replacements required. Closing
does not write sales counts, prep stock or the legacy reporting-period array.

## App connection

With both frontend flags enabled, Enter Counts provides scope confirmation,
physical count entry, incomplete saves and append-only recounts. The dashboard
provides actual usage/Food Cost previews and immutable closed reports. In Sales
Tracking, native mode shows expected usage and removes its old count entry and
accounting close controls. The separate sales workflow cannot close Track 1.

The original dashboard/count flows remain available when the feature flags are
disabled. Ordering/live-stock estimates, historical price widgets, owner rollups,
staff portal counts and PO receiving still use their previous adapters. They do
not automatically consume these count snapshots. Connect those through verified
unit adapters before operational cutover; copying base quantities into old case /
portion fields would recreate unit drift. The new accounting screen is separate
from those operational estimates.

## Disposable setup and checks

1. Use an empty disposable PostgreSQL database containing the public reference
   schema, then apply `20261004_native_purchase_import.sql` and
   `20261004_actual_inventory_counts.sql`, followed by
   `20261004_actual_inventory_corrections.sql` and
   `20261004_actual_inventory_scope_bridges.sql` and
   `20261004_posted_invoice_corrections.sql`, in that order. Posted invoice
   corrections are described in `POSTED_INVOICE_CORRECTIONS.md`.
2. In the test backend, set `USE_PG=true`, `PURCHASE_IMPORT_ENABLED=true` and
   `ACTUAL_INVENTORY_ENABLED=true` with its disposable database and existing test
   authentication. Actual inventory refuses to run without native purchases.
3. Build the test frontend with `REACT_APP_NATIVE_PURCHASES=true` and
   `REACT_APP_ACTUAL_INVENTORY=true`, plus the test backend URL. Keep all flags
   false in the operational application until remaining cutover gates are done.

```text
python -m pytest --noconftest backend/tests/test_native_purchases.py backend/tests/test_actual_inventory.py backend/tests/test_actual_inventory_corrections.py backend/tests/test_actual_inventory_scope_bridges.py backend/tests/test_posted_invoice_corrections.py -q
npm test -- --watchAll=false --runInBand PurchaseImportsTab.test.js ActualInventoryTab.test.js
npm run build
```

The database tests require a loopback `NATIVE_PURCHASE_TEST_DSN` pointing to a
`native_purchase_test_*` control database and a test role allowed to create/drop
disposable databases. Every database fixture contains invented data only. Include
both private schemas (`purchasing`, `actual_inventory`) in a native backup/restore
check. The existing in-app backup is not a complete backup of these schemas.

Before operational enablement: verify deployed schema/role access and restore;
finish nonzero historical scope reconciliation and remaining staff/legacy routing.
Posted-invoice corrections, manual/other-vendor capture, reviewed physical units and
invoice-linked PO receiving and corrected-invoice PO reconciliation are now
implemented locally. Mixed/nonfood order support remains pending; see
[units and receiving](NATIVE_UNITS_AND_ORDER_RECEIVING.md). Prep and
Toast variance integration follows these accounting facts without rewriting them.
Database-owner direct inserts can bypass application review; production least-
privilege role design is still a deployment gate. Original review findings remain
preserved, and this change does not claim to fix every legacy workflow.
