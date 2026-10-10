# Changing the purchased-item count list without changing accounting balances

This local step supports a reviewed handoff from a closed period's old item list
to a newer list at the same physical count boundary. It retains the purchased-
items-only policy, explicit count values, received dates and separate taxes/fees.
Prep and sales remain explanations and cannot affect the handoff or Food Cost.

All feature flags remain disabled by default. No supplied invoice is imported,
no operational migration is applied and nothing is written to GitHub.

## The measured policy

- Retained item identities carry the exact canonical quantity and explicit total
  value from the old closing count to the new opening count.
- Added items require an explicitly confirmed zero quantity and zero value.
  Blank or unconfirmed fields cannot stand in for zero.
- Removed items require zero quantity and zero value in the old closing count.
  Keep a discontinued item on the count list until its remaining stock is gone.
- Dates and receipt timing must be identical. A count before receipts on one day
  and after receipts on the prior day cannot be treated as the same physical count
  merely because their date boundaries happen to match.
- The canonical store/item unit stays fixed. Different observed packages can be
  counted with reviewed conversions only when the resulting quantity and total
  value match exactly. Changing an item code does not prove the same item exists.

The handoff has no purchase, usage, waste, income or valuation-adjustment effect.
It records the change in list membership and carries the accounting balances.
This first version holds nonzero added stock, revaluations and item identity/unit
changes for explicit historical reconciliation. It does not invent an adjustment
to make two lists balance. Equal overall dollars alone are insufficient: each
retained item's quantity and value must match individually.

## Screen workflow

1. Complete and close the old-list period. Its closing count is the handoff source.
2. In Enter Counts, version the purchased-item list and document all raw stock
   locations. Use the list-version selector to choose the appropriate list for
   each physical count. Earlier versions remain available.
3. Record a complete new-list opening count at the same physical date and receipt
   timing as the old closing count. Enter the carried quantities/values and the
   explicitly measured zeros. Confirm each line and its evidence.
4. On the actual-inventory dashboard, choose that opening count under **Change the
   purchased-item list** and preview the handoff from the latest active period.
   Review carried, added and removed rows, their units, values and locations.
5. Record handoff evidence and confirm every row. Acceptance retains the plan,
   source count references, original values, reviewer and time. A failed response
   can retry the same body/key without recording a second handoff.
6. Use the accepted opening count and a later count of the same new-list version
   for the next period. Its report includes the handoff reference and frozen plan.

Each reporting period still compares counts in one list version. A handoff is the
reviewed boundary between periods; it does not sum incompatible lists within one
period. A configured newer version does not by itself change accounting scope.
Once accepted, the handoff cannot be bypassed by continuing the old version or
using an unrelated count with the same numerical balances.

Example: old closing food inventory is 30 lb valued at $45. The new list keeps
that 30 lb/$45 and adds a new purchased food item counted at 0/$0. The new opening
value remains $45. A $40 receipt of the new item after that boundary, followed by
a $30 closing value for it, creates $10 actual Food Cost for that item. The old
period remains unchanged. A receipt on the boundary date belongs to the next
period when both boundary counts are marked before all receipts that day.

If a removed item is purchased again, food purchases outside the next period's
list still hold its Food Cost report. The system does not silently ignore them.

## Corrections spanning list versions

The existing suffix-reopening process includes all later active periods across
list versions. Reopening the anchor makes its handoff historical. It does not
delete or mutate the handoff, source counts or original reports.

After reopening, append same-version/date/timing recounts for each affected side
of the boundary, if needed. Close the corrected old-version period first, review
a replacement handoff anchored to its new closure, then close the next reopened
period. The next opening must descend from that reopened period's original
opening count, preserving its identity and scope.

Even if balances did not change, reclosure requires a fresh reviewed handoff
anchored to the replacement report. A previous handoff cannot attach itself to a
new closure silently. Both generations remain available in handoff history.

Active handoff counts are protected from recounts until their anchor and later
periods are reopened. Only the handoff needed by the next reopened replacement
can be rebuilt while corrections remain pending; a pending old-version interval
cannot be remapped to a newly selected version. Earlier corrections must finish
before creating a new future list transition.

## Storage and migration

Apply to a disposable database, in this order:

1. `20261004_native_purchase_import.sql`
2. `20261004_actual_inventory_counts.sql`
3. `20261004_actual_inventory_corrections.sql`
4. `20261004_actual_inventory_scope_bridges.sql`

The fourth migration adds immutable `actual_inventory.scope_bridges`, the
`active_scope_bridges` view and `period_closures.opening_bridge_id`. Existing
count and report facts stay unchanged. An active bridge requires its anchor
closure to remain active. One accepted bridge belongs to one anchor generation.

The API and database guard both check scope chronology, complete confirmed rows,
the exact boundary, per-item balances and pending correction lineage. Handoff
acceptance uses the same store lock as purchase posting, counts, closing and
reopening, with a recomputed preview fingerprint and saved-plan read-back.

Database guards reject a partial or unmatched handoff even through a direct
insert. Manager/owner store authorization protects preview and acceptance.
Readonly and staff cannot approve a handoff. Existing database-owner privileges
remain subject to the deployment least-privilege review.

## Limits and validation

Nonzero historical additions, revaluations, changed item identities or canonical
units, and shifted count dates/timing require a separate reconciliation workflow.
The fifth migration adds posted-invoice reversal/remapping; see
`POSTED_INVOICE_CORRECTIONS.md`. Dependent-credit reconciliation, manual/other-vendor
capture, legacy backfill, operational/staff/PO adapters and deployment role/backup
checks remain pending.

Native backup coverage must include both private schemas, all bridge generations,
correction events, counts, reports and original invoice bytes. Legacy in-app
backup does not provide that coverage. Browser visual inspection is separate
from the interaction and production-build checks.
The local native recovery rehearsal now covers these generations; see
`NATIVE_BACKUP_RECOVERY.md`. Managed-platform deployment recovery remains a gate.

```text
python -m pytest --noconftest backend/tests/test_native_purchases.py backend/tests/test_actual_inventory.py backend/tests/test_actual_inventory_corrections.py backend/tests/test_actual_inventory_scope_bridges.py -q
npm test -- --watchAll=false --runInBand PurchaseImportsTab.test.js ActualInventoryTab.test.js
npm run build
```

Database fixtures are invented and isolated on loopback PostgreSQL. The new cases
cover zero additions/removals, new-item receipts, unit normalization, nonzero or
missing stock, per-item revaluations despite equal overall value, boundary/store
checks, retries, immutable plans, stale anchors, protected counts, bypass attempts,
multi-version corrections, pending-period lineage and direct database/role guards.
