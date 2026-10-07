# Measured prep containers and internal service transfers — October 7, 2026

Publication note: this document preserves its pre-publication local milestone.
The verified continuation is now published in [draft PR #16](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/16);
see the [checkpoint README](STAFF_WORKFLOW_CHECKPOINT_README.md). No operational
migration or enablement occurred. Historical local-status statements below refer
to the original snapshot, which is preserved unchanged.

This document records the earlier container checkpoint. The subsequent
[paired direct waste milestone](CONTAINER_WASTE_INTEGRITY.md) supersedes its
manual unpack/standalone-waste workaround. Native staff reads and assignments
are also now implemented locally; staff production submissions remain pending.

This continues locally on `codex/staff-prep-count-continuation`, from PR #15's
publication commit `ae10c8cab319b7f1ed842711076bacd132653f43`. The previous staff-count
snapshot is retained unchanged. No new PR, operational migration, real invoice
import, feature enablement or deployment is included.

## Capacity, contents and accounting

Container definitions have stable roots and immutable revisions. Stated capacity,
measured brimful capacity and measured usable capacity are separate nullable
fields with an explicit physical unit and evidence. Unknown remains unknown.
Usable capacity cannot exceed a measured brimful capacity. A manufacturer's
volume, a label such as “pan”, or a legacy `size` is never an actual food quantity.
No reference kitchen dataset or real supplier data is imported in this milestone.

A separate measured product fill profile pins a container definition version,
prepared product version, approved food unit conversion, measured usable food
limit and evidence. A pound of protein in an eight-liter container requires a
food-specific measurement; volume does not imply mass and density is not guessed.
Where both capacity and food have the same physical dimension, their exact unit
sizes also constrain the profile. New fills require current reviewed definitions
and profiles. Existing contents retain their original identity, unit and factor
when a later definition or conversion is revised.

A fill records one actual measured quantity from one current native prepared lot,
its physical timestamp, location calendar date/timezone, label and evidence.
It must fit both the measured product fill limit and unallocated source output.
It reserves existing prepared output; it does not create a second batch or raw
withdrawal. Partial fills are supported. Blank, zero, negative or nonfinite fills
and quantities with more than 16 whole or 12 fractional input digits are held.
Calculated base quantities can retain additional precision without float math.

Each filled container has an independent generated identity. Labels are display
references, not a physical asset registry. Combining lots, refilling the same
identity, splitting identities and cross-location transfers remain separate work.

Track 1 purchased-item counts, received-date purchase facts, explicit inventory
values, Food Cost and separate tax/fee accounting remain independent. Track 2
containers explain the whereabouts of prepared output. Toast sold portions will
be Track 3 theoretical evidence; moving a container to service is not proof of a
sale, actual consumption, waste or a second accounting expense.

## Partial movements and corrections

`send` moves a measured amount from recorded storage to service. `return` moves
it from service to storage. Both preserve total contents and the source lot
reservation. `unpack` releases a measured stored amount to its original lot's
uncontained pool. Sending, returning and unpacking create no consumption or waste.
The screen displays uncontained output, container storage, service contents and
their exact combined remaining recorded quantity. These are allocation projections;
physical prep counts remain separate observations and do not reset this ledger.

For a discarded tracked amount, return it from recorded service if necessary,
unpack the measured amount, then record standalone measured prep waste from its
original lot at the same physical instant or later. Do not use unpack as a waste
entry. A direct linked container-waste command is still pending, as is verified
sales/consumption allocation. Until those exist, the recorded service balance
must not be presented as available physical food or completed variance coverage.

An unused erroneous fill can be voided in full at its original physical instant.
An erroneous latest send, return or unpack can be undone by an immutable reversal
at that movement's original instant. Earlier history remains intact. An undo
cannot erase subsequent movements; the source location cannot become negative.
Undoing unpack is held if released output has been reallocated. Correct quantities
are then entered through a fresh reviewed movement. An undo cannot itself be
undone by this command; a new measured movement is required.

Normal movement timestamps must follow recorded container activity. Calendar
dates follow the already confirmed location timezone. Overnight business-day
policy remains unselected. Allocation availability is checked from the intended
physical instant through subsequent recorded activity, so a future unpack cannot
fund a backdated fill, nested prep or waste. Database timeline guards enforce this
across every participating journal even when the container screen is disabled.
Equal physical timestamps are evaluated together; this is not a subsecond ordering
or an adoption of an overnight operating-day policy.

## Transactions, source history and legacy holds

Commands retain the reviewed submitted body, sources, exact derived facts, actor,
review hash, request key and fingerprint. Each transaction appends exactly one
immutable result, with matching typed facts and submitted measurements. Store
coordination serializes fills with nested prep and standalone waste. Competing
allocations cannot double-use recorded output. Database checks reject fabricated
balanced transfers, incorrect conversions, overdraw, orphan commands, historical
mutation and late child inserts. A filled source batch or opening count cannot be
corrected while its output is reserved. No balance is maintained by mutable JSON.

`20261007_prep_containers.sql` is additive after native mapping, batch and waste/
count observations. For the complete build, retain the established opening,
period, planning, execution and staff-count migration chain as well. SQL recovery
captures all installed tables, functions, triggers and private ACLs. Application
and fixture connections must be recycled after schema changes. This document is
not an operational bootstrap or approval to apply migrations to a live database.

Before installing the native ledger, the migration locks and preserves every
original `prep_recipe_stock` and `prep_logs` field in private raw snapshots.
Original rows remain and their writes are frozen. They are not promoted into
measured native balances or events. Native mode uses reviewed opening/production
facts. Legacy PostgreSQL batch/item stock writers, sales deductions and container
use routes are held before writes after schema installation, including with
flags off. Mongo-only mode and every other legacy reader are not claimed retired.

Backend `PREP_CONTAINERS_ENABLED` and frontend `REACT_APP_PREP_CONTAINERS` require
native prep observations and remain false in examples. The native Inventory & Log
screen shows measured containers when enabled. Owner/manager authorization and
location checks are reused; this does not redesign login/PIN access or expose
container execution to shared-PIN staff. Staff assignment/authorization is next.

## Drafts, retries and verification limits

Drafts and frozen uncertain commands survive navigation in the current App
instance. An exact retry returns its original command/result alongside current
container state. The acknowledgement checks request identity, reviewed snapshot,
result fields and balanced immutable history before clearing the draft. Newer
current history does not change what the original request saved. Changed source
previews are rejected; a definitive rejection requires an explicit revise action
and fresh review. Late location responses and cleared-session callbacks cannot
clear or resurrect another draft. Reload/logout recovery remains separate work.

Verification uses invented data and disposable loopback PostgreSQL outside synced
Documents/Drive. Component/adapter tests exercise exact quantities, review,
partial sends, malformed reads, uncertain outcomes, remount, explicit revision,
location changes and session clearing. Backend checks exercise reservations,
returns/unpack, dependency holds, competing writes, immutable correction, SQL
guards, accounting independence, role/location gates and whole SQL restore.
Final verification passed 363 frontend tests across 44 suites, 56 distinct
backend checks across a 55-check clean run and a separate opening-source probe,
23 offline checks, whole SQL restore and production build with three existing hook
warnings. Retained earlier attempts are recorded in the checkpoint package. They do not establish live-browser, managed-platform or production proof.

Review totals remain seven fixed, twelve open and one deferred. R16 stays fixed
within its native count boundary; partial container safeguards advance R03, R07,
R15, R17 and R19 without closing broader legacy cutover, durable recovery or full
operating acceptance. Next: staff task access and assignment, followed by remaining
service/waste integration, deployment rehearsal and deferred Toast integration.
