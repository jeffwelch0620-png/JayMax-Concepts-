# Saved prep analytical periods

This local manager workflow saves reviewed quantity comparisons with immutable
count references, canonical quantities, effective activity, complete interval
history, source fingerprints, actor and reason. It adds two private tables:
`prep_inventory.period_closures` and `period_reopenings`. Apply
`20261005_prep_period_journal.sql` after the four existing prep migrations.
Only isolated synthetic databases have received these migrations. Existing
native/prep gates apply and the example flags remain disabled.

## Accounting boundary and incomplete coverage

These are analytical snapshots. Track 1 received purchases, purchased-item
physical counts, explicit values and Food Cost stay independent. No lot,
production, waste, purchase, valuation or legacy stock records are created by
saving or reopening a period. Reopening does not bypass the existing protection
of opening counts whose lots have dependent prep or waste.

The saved report retains opening + recorded production - closing depletion,
measured versus estimated nested use, standalone waste, gross raw explanations
and trim already included in gross use. Counts remain observations. Negative
differences remain visible. Service/sales coverage is incomplete; expected
closing stock and final unexplained variance remain null. Costs stay null with
`not_calculated`; no analytical valuation policy has been chosen.

## Continuous periods and deliberate scope additions

The first saved period selects two current complete physical counts. Each later
period must start at the exact current closing count of the prior active saved
period, with the same before-all/after-all cutoff. This assigns activity at a
shared timestamp once. Gaps, overlaps, stale counts and changed cutoff meanings
are held. Counts taken between activities sharing one timestamp require a
separate timing resolution.

If a later full count contains new stable prepared identities, the manager must
confirm each added identity was measured **zero at the opening boundary** and
retain evidence for each one. This is a separate analytical scope assertion,
not a retroactive edit of the physical count. The report retains both the
original physical opening scope and the expanded period scope. Existing opening
amounts and canonical units carry through exactly. A later closing quantity is
never used to infer a missing opening quantity.

For example: an old closing count holds 5 lb of protein. A newly listed sauce
was verified empty at that same boundary. The next period opens with the
unchanged 5 lb protein and the separately confirmed 0 sauce. It can compare
against the next full count without injecting a source lot or claiming new
production. The old count remains unchanged. Subsequent periods use the new full
count directly.

This step supports **additions from verified zero only**. It does not retire
items, accept nonzero missing opening stock, transfer inventory or reconcile
historical stock. Earlier recorded nonzero counts or prepared-item activity,
including retained corrected/voided history, block zero commissioning. Activity
at the opening instant is checked against the explicit cutoff. Missing evidence
is unknown, not zero. A manager assertion still requires an actual measurement;
software cannot prove a physical quantity.

## Drift, corrections and reopening

Saving does not prevent factual corrections. Every history read recomputes the
source fingerprint against the current facts. Late production/waste, corrections,
voids or changed count generations mark affected snapshots stale. The complete
interval history is fingerprinted, including voided generations and activity
tied to either boundary; voiding a backfill cannot silently make its historical
snapshot current again. Earlier stock evidence conflicting with an added zero
also invalidates the affected handoff. Unrelated outside-period activity does
not change the snapshot.

The earliest changed period and every following active period must be reopened
as one reviewed suffix, with reason and actor recorded. A shared count correction
affects both adjacent periods. The history shows individual source freshness
and whether a period's chain requires reopening. New closures are held while
any active period is stale. Original snapshots, reasons and source fingerprints
are never overwritten. Replacements append new snapshots in chronological
order using current count generations and reviewed scope evidence.

## Save, database and recovery controls

Preview runs in a single repeatable-read snapshot. Save serializes exact request
keys, locks the store, checks replay before current-source validation and
recomputes the reviewed fingerprint. Changed sources require a fresh preview.
Concurrent identical retries receive the same saved record; changed request
bodies or another journal action cannot reuse its key. An uncertain screen
acknowledgment freezes editing and refresh until the exact request is retried.
A definite conflict clears review and approval.

Database guards validate store/count identity, continuous chain, complete source
history, retained opening/closing quantities, canonical units, zero additions,
effective prep/waste totals and the complete reopening suffix. A deferred seal
checks that interval source history did not change within the save transaction.
Facts reject update/delete; public and employee database roles receive no access.
Runtime manager/store authorization remains the existing policy.

Whole-database backup/restore includes both tables and all earlier private prep
schemas. Current synthetic recovery proof and hashes are kept with the cumulative
local review package; earlier milestone evidence is retained separately.
Operational cutover, production-scale pagination/performance, managed-platform
recovery, historical reconciliation, retirement/transfers, complete service and
Toast mappings, and cost policy remain future work. No real invoice/POS data or
operational database changes are part of this step.
