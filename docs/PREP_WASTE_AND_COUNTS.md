# Standalone waste and physical prep observations

This is a local quantity-only manager pilot following the prep batch journal.
It is disabled by default, uses invented test data, and remains uncommitted for
a later PR. No operational migration or real invoice import has occurred.

## Accounting boundary

Track 1 continues to use purchased items only: opening physical count plus net
received purchases minus closing physical count. Food Cost remains opening
confirmed inventory value plus received food purchase cost minus closing
confirmed inventory value. Received date is the record date; taxes, fees and
nonfood costs remain retained separately. Prep counts and waste never alter these
facts, explicit values or accounting reports.

Track 2 gains two distinct observations. Neither creates a current-price cost:
cost status remains `not_calculated`, amount null, until the batch costing method
is selected. Toast sales and service consumption remain separate future work.

## Waste: explain a loss once

Standalone raw waste records an explicitly measured purchased-item amount in a
verified physical unit. It is an explanation of actual inventory loss, not
another actual-inventory or Food Cost deduction. No raw stock balance is invented
or clamped to zero.

Standalone prepared waste identifies its actual producing batch, stable prepared
product, unit profile and measured amount. It reduces recorded output available
to other prep batches. Nested prep and prepared waste share one allocation limit
and store lock. Both use the same database projection regardless of whether the
observation screen is enabled later. Turning off the screen cannot hide committed
waste from a subsequent batch allocation.

Waste must be separate from gross batch input and included trim. The manager
explicitly confirms that distinction and provides disposal category/evidence.
The system cannot infer whether two separately entered descriptions represent
the same physical loss; identity and source-event policies for future staff/import
integrations must remain deliberate. Exact request-key retries prevent accidental
network duplication.

A 60 lb gross prep input, 48 lb usable output and 12 lb included trim still
explains one 60 lb raw use. Discarding a further 5 lb of the usable output is
a separate prepared-waste event, leaving 43 lb recorded output available. Using
20 lb in another batch leaves 23 lb. The producer's original raw withdrawal is
never repeated, and neither waste event adds another Food Cost deduction.

Prepared waste requires an active recorded source lot produced before disposal.
Older producing recipe versions remain historical facts when the stable product
and canonical unit match. Current verified product/unit definitions govern the
entered measurement. Preexisting unrecorded prep stock needs a future reviewed
opening-balance/source workflow; a physical count does not create those lots.

## Physical prep counts: observations without balance resets

An initial full count declares all currently defined prepared identities at the
store, excludes purchased/raw items, and retains the exact scope and verified
profile for each measured quantity. Every listed identity needs explicit evidence
and a quantity; observed zero is valid. Missing, blank, nonfinite and negative
quantities are held. A missing verified profile must be resolved before saving a
complete count. The first pilot supports up to 500 prepared identities per count.

Counts record what was physically present at the chosen instant. They do not
change batch allocations, erase waste/use, adjust source lots or infer missing
service usage. If 23 lb is recorded as unallocated output and the count observes
20 lb, both records remain. The 3 lb difference awaits an aligned variance report
and explanation rather than an automatic stock reset.

Count quantities preserve original measurement, factor, canonical quantity and
evidence. They carry no inventory valuation. Unit profiles, product/name versions
and source snapshots remain immutable; a subsequent rename or profile revision
cannot reinterpret an older count. New definitions invalidate uncommitted full
scope previews. A correction retains its original scope even when newer prepared
identities have since been added.

Only one original full count is allowed at an exact store/time instant. Correct
that record rather than adding competing originals. A later physical recount is
a new observation at its actual later time. A correction fixes the original
observation's facts at its original instant. Voids are terminal in this pilot;
reactivation and changing a count's time/scope require separate future workflows.

## Corrections, retries and database guards

Each observation is previewed and separately approved by a manager. Its hash
includes frozen definitions, scope and source allocation where relevant. Source,
profile, scope or allocation changes require a fresh review. The UI retains exact
decimal strings and keeps unknown measurements blank. Clear missing-count messages
explain that unknown is not zero.

Corrections append a new generation. Waste replacements reverse the predecessor's
one applied movement and record its replacement atomically. They can release
their own old source allocation before allocating the new amount. Count
replacements retain all prior generations and the original declared scope.
Void means an erroneous record; it is not itself waste reporting.

Corrections retain item identity and original time/date/timezone. They cannot
fork, skip revisions or reopen a void. A used/wasted producer cannot be changed
until its dependent records are resolved. A waste replacement may correct its
producer-lot selection within the same stable product and date, without changing
any producing batch's historical recipe or raw inputs.

Exact request keys serialize across stores before store locks. Replay precedes
current source checks, so acknowledgment retries still work after later changes
or voids. The UI freezes editing, journal switching and refresh during uncertain
saves and verifies returned location, purpose, predecessor, kind and reviewed
hash. Definite conflicts clear approval and require a new review.

Database seals check reviewed signed movements, exact reversals, measured separate
waste, count scope confirmation, frozen profile factors and complete count rows.
All facts reject update/delete; children can only be inserted in the creating
transaction, checked by identifier and timestamp. Small numeric quantities use
fixed decimal notation in fields compared with PostgreSQL numeric text, avoiding
scientific-notation seal conflicts without altering original source/request
snapshots. Chained standard-usage calculations allocate enough decimal precision
for the full supported quantity sizes, rather than silently rounding.

## Schema and enablement

Apply `20261005_prep_observations.sql` after the native purchase/count/unit,
prep mapping and prep batch migrations. It adds three private tables:
`observations`, `waste_movements`, `count_observations`. Observations retain a typed
waste/count purpose and complete review snapshots; normalized movements/count
rows support future variance without mutable stock balances. The batch migration
defines shared lot projection/validation functions, extended here to include waste.

Backend requires the native purchase, prep setup and batch gates plus
`PREP_OBSERVATIONS_ENABLED=true`; frontend requires the corresponding native,
setup and batch gates plus `REACT_APP_PREP_OBSERVATIONS=true`. All examples remain
false. Public/anonymous/authenticated database access is revoked. Production
service roles, login/PIN redesign and managed-platform recovery remain deployment
work, not completed by these quantity records.

Date entry follows the explicitly confirmed prep calendar-day/IANA timezone
policy; it does not change Track 1's received-date/count boundaries. Corrections
remain at their original timestamp, including UTC offset distinctions at repeated
daylight-saving hours. Overnight service-day reporting needs a deliberate policy
change. Shared catalog locks can delay setup edits briefly; pagination and
affected-lot performance need volume checks before operational use.

## Verification and next step

Invented fixtures exercise unchanged Track 1 through waste/count correction/void,
no automatic count resets, concurrent prep/waste allocation, source holds,
stale reviews, exact retries, complete counts and zero versus unknown, immutable
history/scope, transaction rollback, database factors/seals, tiny precise amounts
and independent feature flags. Whole-database restore compares observation and
batch projections and preserves all 13 private prep tables, correction generations,
waste allocations and write guards. Component/adapter checks and an enabled-flag
frontend build accompany the saved package. No browser visual or managed-platform
recovery proof is claimed.

The next local step is implemented in [Prep count periods](PREP_COUNT_PERIODS.md):
read-only count-aligned depletion with explicit cutoffs and effective backfill/
correction projections. Service completeness and final variance remain unknown.
Then add
opening prep sources, staff/task/container replacements, operational read-screen
cutover and later Toast. Byproducts, zero-output total loss, transfers and
date-moving/dependent correction bundles remain separate future work. Cost policy
selection remains open and does not limit Track 1's accounting independence.
