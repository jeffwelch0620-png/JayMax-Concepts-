# Paired measured container waste — October 7, 2026

Publication note: this document preserves its pre-publication local milestone.
The verified continuation is now published in [draft PR #16](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/16);
see the [checkpoint README](STAFF_WORKFLOW_CHECKPOINT_README.md). No operational
migration or enablement occurred. Historical local-status statements below refer
to the original snapshot, which is preserved unchanged.

This local continuation adds direct measured storage/service waste and paired
reversal to the [container ledger](PREP_CONTAINER_INTEGRITY.md). It remains
uncommitted and unpublished on `codex/staff-prep-count-continuation`, starting
from PR #15 publication commit `ae10c8cab319b7f1ed842711076bacd132653f43`.
PR #15 is unchanged. No operational migration, enablement, deployment or real
invoice import occurred. Earlier snapshots are retained unchanged.

## One measured loss, two linked records

Managers review the original fill, measured discarded quantity in its original
food unit, storage/service compartment, category, physical timestamp, confirmed
location calendar date/timezone and evidence. The frozen fill profile supplies
the product identity and exact conversion; subsequent profile edits do not
reinterpret existing food. Storage spoilage requires storage, service discard
requires service, and other accepts either compartment. Measurement and calendar
confirmation require actual boolean true. Unknown quantities cannot become zero.

One transaction appends the contents movement, matching waste observation and
immutable link. Reducing a reservation releases exactly the quantity withdrawn
by its matching waste event. A fully allocated lot can therefore record direct
container waste without creating available food, a second loss or a new batch.
Failures roll back both records and their link. Exact decimal arithmetic is used
throughout, including scientific notation returned for very small quantities.

For example, a lot of 48 units completely filled into a container has zero
uncontained output. Discarding 8 stored units leaves 40 contents and records
8 waste; uncontained output remains zero. Sending 10 to service and discarding
3 there leaves 30 stored and 7 in service, with 11 total measured waste.

Track 1 purchased-item counts, received-date purchases, explicit inventory values
and Food Cost remain independent. This is Track 2 evidence explaining measured
loss. No purchased stock deduction, inventory revaluation or monetary waste cost
is inferred. Service transfers are not consumption or proof of a Toast sale.
Physical counts remain independent observations; recorded contents are not a
replacement for counting what is physically present.

## Corrections and retries

An erroneous waste movement can be reversed only together with its
original linked observation at the original physical instant. Both journals
retain the original entry and append its correction. The reversal restores the
recorded quantity in the original compartment and voids the matching loss.
An undo cannot itself be undone. A corrected measured loss uses a fresh review.
With `20261008_container_waste_corrections.sql` installed, later storage/service
transfers and reversals of those transfers permit an earlier waste correction.
The original target remains unreversed and the restored total cannot exceed the
original measured fill. Later waste, unpacking, quantity corrections, voids and
changed source lots still hold earlier corrections for dependency review.
Without this migration, the earlier latest-only waste rule remains. A broader
historical quantity-dependency correction workflow remains future work.

Standalone waste correction routes and controls reject container-linked events.
Private SQL guards reject orphan movements, unpaired observations, incorrect
source/unit/conversion/category, forged links and late links to sealed commands.
Location serialization, original request keys/fingerprints, immutable history
and reviewed source revisions protect concurrent allocation and exact retries.
Physical-time allocation guards prevent future unpacking from funding earlier
prep, fills or waste.

The UI reviews both effects and validates the matching contents and journal
acknowledgement before success. Lost responses retain the exact request for
retry through component remount. This cache is not durable through full reload
or logout. Late responses from a previous location/session are ignored. The
native view displays linked history and routes its correction to paired reversal.

## Additive schema and installation boundary

Recipe removal checks retained operating references before cascading deletes can
reach the legacy stock/log hold triggers. Direct, targeted and collection deletion
return 422 and retain recipe lines, stock, captured raw history and revisions even
when the container feature flag is off. Older-code rollback must preserve these
rows and honor schema holds; clearing references is not an approved workaround.

`20261007_container_waste.sql` follows the existing container and observation
migrations and preserves their immutable data. The new private link table uses
store-scoped foreign keys, immutable history and deferred transaction seals.
New nullable movement fields are omitted from historical ordinary movement JSON,
and empty loss history is omitted, preserving existing reviewed commands and
pending previews. An additive upgrade test verifies retry of prior ordinary
commands after migration. Application database connections must be drained and
recycled after DDL to avoid stale asyncpg row/statement caches.

Apply `20261008_container_waste_corrections.sql` after the direct-waste migration.
It adds a private invoker eligibility function and replaces the movement guard,
retaining original facts, receipt hashes and pending latest-waste preview shape.
PUBLIC, anon and authenticated receive no function grant. Upgrade and whole SQL
restore checks cover the function, original retry, pending preview and retained pair.
The separately preserved local deployment bundle still needs this new migration
added and its ordered migration/recovery rehearsal repeated before hosted use.

No new feature pair is added. The existing container/observation dependencies
apply; all fourteen native feature pairs remain false in example files. The UI
requires installed direct-waste capability before presenting the new actions.
Existing manager/location authorization is reused. Shared PIN redesign remains
deferred; selected roster names remain claimed identity rather than proof of
employee identity or manager authority.

## Evidence and remaining scope

Current synthetic evidence: **390 frontend tests / 47 suites**, **44 selected
backend checks**, **23 offline route/schema checks**, and a production build with
three existing hook-dependency warnings. Backend checks include measured loss,
latest reversal, frozen conversions, competing requests, replay, partial-write
rollback, direct SQL guard probes, additive upgrade and whole SQL restore with
private ACL checks, plus existing container/observation boundary regressions.
The disposable PostgreSQL cluster is outside synced folders and stopped after
testing. Initial fixture/cache and decimal-representation failures are retained
alongside their corrected final passing results.

These results are local source/component/disposable-database evidence, not
live-browser or operational/managed-platform proof. Review totals remain seven
fixed, twelve open and one intentionally deferred. Broader legacy retirement,
historical correction dependencies, sales consumption, container asset/refill/
mixing workflows, employee account mapping and production recovery remain open.

Next: immutable staff production submissions and manager acceptance using the
stable native assignments, with measured production recorded only once on
acceptance and no effect on Track 1 accounting.
