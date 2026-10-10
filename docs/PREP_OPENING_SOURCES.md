# Opening prep sources

[Saved analytical periods](PREP_PERIOD_JOURNAL.md) now provide local reviewed-zero
scope additions, immutable period snapshots and controlled reopening. Those
actions never create stock sources or bypass opening-lot dependency protections.

This local manager workflow establishes preexisting prep before any recorded
production or waste history. It derives the whole opening from a complete
physical prep count and requires separate review/approval. The existing native
purchase, prep setup, batch and observation gates apply; all example flags stay
false. Apply `20261005_prep_opening_sources.sql` after the three prep migrations.
Only disposable synthetic PostgreSQL databases have been migrated here.

## Quantity and accounting boundary

The reviewed count supplies exact canonical quantities and verified profiles.
There is no editable opening-quantity field. Every positive count line becomes
one opening source lot. Zero lines remain part of the full count and decision,
without zero or artificial positive lots. Scope must still cover all currently
defined prepared identities at the store; a stale/incomplete scope is held.

Opening sources have a distinct `opening` discriminator in the shared lot/event
journal and no producing recipe. They consume no raw inventory, add no production
and assume no current recipe or purchase price. Original producing recipe and
analytical cost remain unknown. These sources cannot establish historical raw
ingredient attribution from today's recipe. Track 1 purchases, purchased-item
counts, explicit accounting values and Food Cost remain unchanged.

For example, an opening count of 50 lb makes 50 lb available for recorded prep
allocation. A later nested batch using 20 lb and measured prepared waste of 5 lb
leave 25 lb recorded unallocated output. The count-period report already carries
50 lb in its opening count; it excludes the opening source from production, even
if the opening cutoff is before all exact-time activity. It therefore records
25 lb depletion, 20 lb nested use and 5 lb waste without a second raw withdrawal
or additional Food Cost deduction.

## Commissioning and dates

Only one active opening decision is allowed per store. It uses a current,
unvoided full prep count and an explicit confirmation that recorded activity has
not begun. Existing production or waste history blocks new opening establishment,
including voided history: deleting its effect is not permission to silently
reinitialize stock. Counts alone do not create or reset source lots.

Once an opening is active, production/waste cannot be backdated before its
physical instant. Its count is before same-instant operational activity.
The existing calendar-day/IANA timezone policy applies. Period comparisons
cannot begin before an active opening or proceed with a stale opening anchor.
Opening sources themselves are omitted from production and boundary activity
totals because the physical count already contains that quantity.

This is a commissioning workflow, not historical backfill, transfers, an ongoing
count adjustment or a count-scope handoff. Those need deliberate future events.

## Corrections and dependency protection

An opening decision can be voided only as a whole, after resolving any remaining
nested prep or waste allocations. The void atomically reverses every positive
opening source; it does not report waste. Prior decisions and source movements
remain immutable. Individual opening lots cannot be changed through the production
batch correction route.

To fix an unused opening, void its decision, correct the original count and
establish a fresh full opening. This is allowed only while no production or waste
history exists. Each void is terminal; re-establishment is a separate reviewed
initial decision, not reopening a void or silently changing its quantity.

A used opening count cannot be corrected or voided until its dependent prep/waste
records are resolved. Both API review checks and deferred database allocation
guards enforce this. If an unused count is corrected first, the old opening becomes
stale: its sources are hidden/ineligible and new activity is held until the
opening is voided and re-established. Resolving dependencies later does not grant
historical reinitialization permission; reconciliation after activity remains
a separate future workflow.

## Schema, approval and recovery

One new immutable private table, `opening_decisions`, retains the full source
count, all derived lot plans, actor, note, reviewed hash and exact request key.
The batch journal gains typed source/count/decision references. Production
continues to require a recipe; opening sources require a matching physical count
line and creating decision. Opening movements are output/reversal only and have
no recipe/input rows. The existing shared lot allocation projection includes
both opening and production sources and all nested use/waste.

Database seals require every positive count line and exact derived quantities,
complete void reversals, source/profile identity and same-store/date references.
Decision children must be created in the decision's transaction, checked by
transaction identifier and timestamp. Facts reject updates/deletes. A store lock
serializes initial establishment, count corrections and allocations. Exact-key
retry precedes current-state checks; conflicting payloads or stale previews fail
without partial writes. Uncertain UI saves freeze editing/refresh until the same
request is acknowledged. Public/anonymous/authenticated SQL access remains revoked.

The manager screen previews derived quantities, shows explicit zeros as no lots,
requires approval, distinguishes opening sources from production in allocation
menus, and retains decision history. No automated stock reset or inferred cost
is added. All 14 private prep tables and the same source/period projections are
included in synthetic whole-database restore checks. Current/earlier check evidence
is distinguished in the cumulative package; no browser visual check or managed
platform recovery proof is claimed.

## Remaining work

Historical reconciliation, count-scope handoffs, transfers, saved analytical period
closures and operating-screen/staff/task/container cutover remain pending.
Pagination and store-wide allocation volume tests are still required before
operational enablement. Batch costing remains unselected.

Future sales comparisons follow [Toast comparison rules](TOAST_COMPARISON_RULES.md).
Toast is not connected, no POS data has been imported, and these rules do not
turn sales estimates into Track 1 accounting facts or measured kitchen consumption.
