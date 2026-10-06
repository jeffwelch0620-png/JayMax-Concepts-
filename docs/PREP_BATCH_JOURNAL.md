# Native prep batch journal: quantity pilot

This local milestone records measured preparation against approved immutable
recipe versions. It is a manager pilot, disabled by default. No live database
migration or real supplier invoice import accompanies it. The original review
and all preceding local changes remain pending a later PR.

## Relationship to the three tracks

Track 1 retains purchased items only, received-date purchases, physical count
quantities and explicitly confirmed count values. Its quantity and Food Cost
formulas do not depend on this journal. Batch entry, correction and void never
change actual purchase facts, actual counts, explicit values or legacy stock.

Track 2 gains a separate quantity explanation:

* Gross ingredient input, with an explicit measured or recipe-estimate basis.
* Measured usable output in the approved prepared output unit.
* Optional trim/loss already included in the gross ingredient input.
* Standard ingredient/output quantities scaled by an explicit planned batch count.
* Prepared ingredient source batches, preserving the actual producing recipe version.

Sixty pounds of gross protein producing forty-eight pounds of usable output
with twelve pounds of included trim creates a single sixty-pound explanation of
raw use and a forty-eight-pound prepared output. Trim is an annotation, never a
second twelve-pound withdrawal. Unknown trim is null; observed zero requires
its own evidence. Estimated gross input is visibly different from measurement.

One hundred twenty purchased appetizer pieces portioned into fifteen prepared
bags uses separate purchased-piece and prepared-bag identities. Both may use
`each`, but the journal never subtracts fifteen bags from 120 pieces to infer
105 pieces of loss. Mixed physical dimensions are not summed into a mass balance.

Standalone waste, prep physical counts, opening prep balances, service consumption,
unmapped byproducts and sales are future events. Existing lot balance is
**recorded unallocated output**, not measured current inventory. Do not use it
as a physical-stock report or assume that a missing event means zero consumption.

Track 3 remains a later Toast sales explanation. No sales import or application
is enabled by this milestone.

## Prepared source lots and stable relationships

Every prepared input selects a recorded producer batch at the same store with
the same stable prepared identity and canonical unit. Production must precede
consumption. Allocations cannot exceed recorded output, including allocations
already recorded at later times. One consumer's replacement can release its own
old allocation before allocating the replacement, all in one transaction.

An older physical lot remains usable after a new recipe version is approved,
provided the prepared identity and canonical unit agree. Its actual original
recipe/profile history remains intact. New batch entry uses the current reviewed
recipe and checks the entire standard ingredient ancestry for source changes.
Prepared input consumes that prepared lot only. It never withdraws the lot's raw
ingredients again or copies recursive history into every new JSON snapshot.

The current scope requires recorded producer lots. Preexisting stock requires
an explicit reviewed opening-balance event in a future step; it is never silently
invented. No negative allocation or zero-clamping workaround is used.

## Review, retry and correction

The manager previews a complete batch, explicitly reviews it, then saves using
the reviewed hash and a unique request key. Recipe/catalog changes and lot
balance changes invalidate the preview. Exact-key replay occurs before current
source checks, so an uncertain acknowledgment can safely replay even after the
record has been corrected. A changed payload with the same key is refused.

The UI keeps quantities as decimal strings. An uncertain save freezes editing
and refresh until the exact record is retried. Acknowledgments must match location,
record kind, predecessor and reviewed hash. Definite conflicts clear the review
and require a new preview.

Corrections append records. A replacement reverses precisely the predecessor's
applied quantities and records its complete replacement together. A void
reverses the predecessor without new applied quantities. Prior reversals are
never reversed again. Revision chains cannot fork or skip, and sealed events
cannot acquire later movements. All journal tables reject update/delete.

A producer already used by another batch is held for correction until those
dependent consumer records are resolved. This prevents rewriting nested prep
ancestry. Automatic dependency bundles and partial producer-lot adjustments are
future work. A void means an erroneous record, not spoiled food; real waste
requires a separate waste event. Voided records cannot be reopened in this pilot.

## Date policy, costs and limits

The user explicitly enters a timestamp with UTC offset, location IANA timezone
and matching calendar date. The first successful batch freezes the store's
calendar-day policy. This is a separate confirmed policy for prep analytics;
it does not alter Track 1's received-date/count cutoff rules. Repeated daylight
saving hours are distinguishable by offset. Overnight service-day policy needs
a separate deliberate change before operational rollout.

Corrections retain the original time/date, timezone and prepared identity. They
may use a newly reviewed recipe version for that identity. Date-moving,
identity-moving and coordinated dependent corrections are held. Raw ingredients
use verified same-dimension physical conversions; prepared inputs use the exact
approved unit profile. Raw cases, density and unverified container fill stay held.
Each recorded batch must confirm one usable output without recoverable byproducts.
Zero usable output / total-loss production belongs in the future waste workflow.

Batch costs explicitly remain `not_calculated`, amount null. The pending cost
policy has not been inferred from supplier prices. Track 1 Food Cost remains
available independently. Selecting an analytical batch costing method is a later
decision; it cannot revalue actual count facts.

## Schema and pilot enablement

Apply `20261005_prep_batch_events.sql` after the prep mapping foundation and its
native purchase/count/unit dependencies. It adds three private immutable tables:
`batch_policies`, `batch_events`, `batch_movements`. Input measurements, evidence,
approved definitions and actual source references are retained in reviewed event
snapshots; normalized movements provide exact signed quantity projections.

Store locking serializes trusted writes; shared catalog locks protect source
capture. Database seals check complete ingredient/output rows, matching reviewed
quantities, exact reversals and source allocation bounds. Anonymous/authenticated
public database roles receive no access. Trusted service-role design is still
a deployment gate. This is not a login/PIN redesign.

Recipe and batch child guards require both the creating transaction identifier
and its timestamp. An old restored transaction number alone cannot make a sealed
record writable in another cluster. Exact request keys are also serialized across
stores before store locking, so accidental cross-store key reuse returns a conflict.

Backend requires `USE_PG`, `PURCHASE_IMPORT_ENABLED`, `PREP_SETUP_ENABLED` and
`PREP_BATCHES_ENABLED`. Frontend requires `REACT_APP_NATIVE_PURCHASES`,
`REACT_APP_PREP_SETUP`, `REACT_APP_PREP_BATCHES`. All native/prep examples remain
false. Matching flags/schema are necessary before any deliberate local pilot.

When the full backend batch pilot is enabled, known legacy Mongo/Postgres prep,
portion/vessel, task-completion, sales-application and container-consumption
writers are held before stock/progress writes. Their replacement flows are
pending. Scheduling and Operations task portals are separate and unchanged.
Legacy balances/read screens are not adopted as native truth. Definition setup
alone does not block old production; complete operational cutover remains a gate.

The allocation seal currently examines a store's recorded producers. Optimize
affected-lot checking and pagination with meaningful volume tests before large
operational use. Shared catalog locks can briefly delay setup edits. These
tradeoffs favor auditable correctness during this build pilot.

## Verification and next step

The subsequent local waste and physical-count milestone is documented in
[PREP_WASTE_AND_COUNTS.md](PREP_WASTE_AND_COUNTS.md), behind its own disabled gate.
It extends shared source allocation with prepared waste and records physical
observations without resetting batch balances. Remaining variance and operational
cutover work below is still pending; the earlier paragraphs describe the batch pilot.

Invented-data checks cover unchanged Track 1 after entry/correction/void, nested
lots without repeated raw deductions, old-version lots, concurrent allocation,
stale previews, retries, append-only correction history, rollback, database seals,
timezone/DST, precise decimals and legacy writer holds. A whole-database isolated
restore must retain correction generations, source allocations and write guards.
Frontend component/adapter tests and an enabled-flag build accompany the package.
No browser visual or managed-platform recovery proof is claimed.

Next add standalone raw/prepared waste and physical prep counts, then align their
variance reports and replace remaining staff/task/container workflows. Resolve
date/cost/opening-stock policies before operational use; connect Toast after that.
