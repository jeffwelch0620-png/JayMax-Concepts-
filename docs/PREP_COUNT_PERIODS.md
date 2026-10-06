# Count-aligned prep quantity comparison

This local manager pilot compares two physical prep counts against recorded
production, nested prep use and standalone waste. It is a read-only projection
over existing PostgreSQL facts, with no new tables or migration. The existing
native purchase, prep setup, batch and observation flags must all be enabled;
all example settings remain false. No operational data is imported.

## What the quantities mean

For each stable prepared identity in the common counted scope:

```
observed depletion = opening prep count + recorded usable production - closing prep count
remaining depletion = observed depletion - recorded nested prep use - recorded prepared waste
```

The remaining depletion is labeled **service use or unrecorded loss**. It can
contain portions served, unrecorded production or use, count error and loss.
Production completeness is unverified. Service usage is not yet captured and
Toast is not connected, so final expected closing quantity and unexplained
variance remain null. Neither a zero remainder nor an empty activity list proves
complete records or zero waste. Negative quantities are retained with conflict
flags rather than clamped to zero or called a favorable variance.

Example: opening 10 lb, recorded production 48 lb and closing 23 lb gives
35 lb observed depletion. Recorded nested use of 20 lb and separate waste of
5 lb leave 10 lb service use or unrecorded loss. Recorded output availability is
a separate lot projection; the physical count never resets it.

Raw purchased-item explanations aggregate gross recorded batch ingredient use
and standalone raw waste by immutable item code and canonical unit. Measured
and recipe-estimated use remain separate. Included trim is displayed as an
annotation already inside gross input, never a second deduction. Missing trim
measurements are counted explicitly; the annotated total is not a complete
loss estimate. A 60 lb gross input, 12 lb included trim and 3 lb separate raw
waste explains 63 lb raw use, not 75 lb. Nested batches do not repeat the raw
use of their producer, including when the producer was before this period.

No cross-unit grand total, current supplier price, accounting value, percentage
variance or allocation of costs is invented. Track 1 remains opening purchased
count plus net received purchases minus closing purchased count, with explicit
inventory values for Food Cost. This comparison writes no purchases, counts,
lot balances, accounting reports, legacy stock or period closures.

## Counts and exact-time cutoffs

Select two current, unvoided physical prep count generations at the same store.
The closing instant must be later. Both must have the exact same frozen stable
product scope, canonical units and timezone policy. Profile revisions and names
may differ because each count retains its verified conversion. Scope changes
require a future reviewed scope handoff; items cannot silently disappear or be
treated as zero. Activity outside the common counted scope is held.

At each count choose whether the observation occurred **before all** or
**after all** batch/waste activity with that exact timestamp, then explicitly
confirm both choices. There is no inferred default or mid-activity cutoff.
Activities strictly between the instants always belong to the period.

| Count cutoff | Activity exactly at opening | Activity exactly at closing |
| --- | --- | --- |
| before all | Included | Excluded |
| after all | Excluded | Included |

The response includes the effective event references tied to each boundary,
including excluded ones. For adjacent periods the shared physical count must
use the same cutoff as both the earlier closing and later opening, assigning
tied activity once. The API does not persist/enforce adjacent period chains;
the user must maintain that choice until a later closure workflow exists.
If the count occurred between events at the same instant, resolve the source
timing first. Timestamp comparisons use aware UTC instants, not rounded dates;
the prep calendar-day/IANA policy remains unchanged.

## Corrections, backfill and freshness

The report uses one repeatable-read database snapshot. Each batch/waste chain
contributes only its latest effective nonvoid generation and its applied rows.
It never adds all signed historical generations inside the reporting period.
Corrections retain their original performed instant: a later recorded
correction or backfill therefore belongs to the original activity period.
Voids remove erroneous activity, preserving its history elsewhere.

Original count IDs that were superseded or voided are rejected. Refresh count
choices and select current generations. Source IDs, revisions, review hashes,
chosen cutoffs and calculation-policy version form the response hash. A refresh
after relevant backfill/correction changes that hash. Subsequent catalog names,
prices or recipes do not reinterpret frozen records.

This is a current projection, not a saved period closure. The hash is a
comparison fingerprint, not an attestation of complete records. Previously
viewed results do not live-update when another person changes data; rerun the
comparison. The manager UI clears results and timing confirmation after any
selection change and shows errors rather than an empty successful report.

## Interfaces and verification

Manager Item Setup includes a gated comparison panel. The backend routes are:

- `GET /api/pg/purchases/{store}/prep-periods/counts`
- `POST /api/pg/purchases/{store}/prep-periods/preview`

Both use existing manager/store authority. The POST computes a read-only
snapshot and is not a save. Inputs require distinct count IDs, explicit
opening/closing cutoff enums and literal confirmed timing. Decimal quantities
stay strings in the UI and exact decimals during aggregation; dynamic precision
retains tiny amounts beside large values.

Invented-data checks cover accounting independence, nested raw-use exclusion,
trim once, partial service coverage, tied cutoffs and adjacent additivity,
effective replacements/voids, late backfill, stale/foreign/changed-scope counts,
negative conflicts, measured/estimated separation, catalog drift and feature
gating. Fresh whole-database recovery compares the same report and fingerprint
after restoring all 13 private prep tables. Component/adapter checks and an
enabled-flag production build are retained in the local cumulative package.
No live database migration, supplied invoice import, browser visual check or
managed-platform recovery proof is claimed.

## Next decisions and work

Define service-use attribution alongside sales expectations, with explicit
completeness by location and period and reviewed source identities for duplicate
prevention. This report already measures prep depletion through physical counts.
Toast will provide Track 3 theoretical portions and usage for comparison;
any measured service-use source must remain distinguishable from that estimate.

Reviewed commissioning sources are now implemented locally in
[Opening prep sources](PREP_OPENING_SOURCES.md). They are excluded from production
because the physical opening count already carries their quantities. Proposed
[Toast comparison rules](TOAST_COMPARISON_RULES.md) keep future sales expectations
separate from physical depletion and accounting. [Saved analytical periods](PREP_PERIOD_JOURNAL.md)
now add local immutable snapshots, verified-zero scope additions, source staleness,
suffix reopening and adjacent-cutoff enforcement. Nonzero historical opening
reconciliation, scope retirement, transfers and adjustment workflows remain pending. An expected-stock report
should remain incomplete whenever any required event stream is missing.
Analytical costing remains unselected and separate from Track 1 values.
Staff/task/container replacement and the legacy operational read-screen cutover
remain pending before enabling these workflows operationally.
