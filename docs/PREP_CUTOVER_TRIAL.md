# Prep cutover and recovery trial

October 8 reconciliation: the trial now includes the published waste correction
and final private-access boundary, uses a separate counter and reviewer, and
preserves the latest staff-response/retry contracts. The dependency review is now
implemented. See [current evidence and next work](CUTOVER_RECONCILIATION_CHECKPOINT.md).
The older branch/checkpoint and next-implementation notes below are historical.

Local continuation on `codex/legacy-cutover-continuation`, based on
`67546fa79de3b7a9aff2715063b36d1ba7f3fe44`. PR #16 remains draft,
unmerged and unchanged. This checkpoint adds no migration or operational data.

## Remaining legacy read boundaries

The PostgreSQL prep-state response now carries separate count, list and reporting
availability. With native count/day-list schema installed, disabling feature flags
does not reactivate the old screens. The app holds the old count/list controls and
old day overrides/par advice while leaving projected-sales and PIN settings
available. Applying old AI advice is held before any local recipe-par save.

Legacy list/history/override endpoints reject normal operating reads after their
cutover. Explicit `archive=true` requests remain available through existing location
authorization; returned records are labeled `legacy_prep_archive`, archived and
non-operational. List lookup uses the original date and daily/bulk track, with no
fallback to another track. Count history excludes purchased-inventory count types.
The old session GET still creates legacy sessions before cutover; installed native
staff-count schema holds that operation, including calls for a new date.

Count/list load failures show the reason and retry action. Failed list loads cannot
offer generation or keep an earlier location's list. Late responses from a previous
location are ignored. Failed override removal preserves the row and reports failure.

The original legacy list constraint is unique on **location/date**, without track.
Its archived rows are preserved as they exist. Native dated lists use separate
location/date/track identities; the same-day daily/bulk separation is covered by
the existing native race/retry test. No legacy constraint was changed to make the
archive trial pass.

## Synthetic combined day

The integration test uses invented rows in an isolated loopback database. It joins
the existing workflows rather than promoting old prep data:

1. Establish explicit-value purchased-item opening/closing counts and a received
   purchase. Opening value $60 + food purchases $40 − closing value $45 produces
   **$55 actual Food Cost**. Taxes/fees remain outside food purchases.
2. Issue a manager prep-count sheet, submit a physical prep count of 1 lb and accept
   it as an observation. Commission that observation as opening prep stock.
3. Release the dated task, assign the cook and accept measured staff production of
   2 lb as partial progress. Create a measured container fill for that batch.
4. Send 1 lb to service, record 0.25 lb measured service waste, return 0.75 lb and
   unpack the remaining 1.75 lb. An attempted source-batch void is held while the
   container allocation exists.
5. Accept a distinct second production batch of 1 lb and accept a closing physical
   prep count of 3.4 lb. Save an analytical period snapshot.
6. Correct the unallocated second batch to 0.75 lb, reconcile its task link and
   explicitly finish. Reviewed task production totals 2.75 lb. The first batch's
   container/waste dependencies are not automatically erased or cascaded.
7. Refresh the prep comparison. Opening 1 + recorded production 2.75 − closing 3.4
   gives 0.35 lb observed depletion. Recorded waste explains 0.25 lb; the remaining
   0.10 lb is service use or unrecorded loss. It is **not a final variance**: sales
   remain disconnected and coverage is partial. Prep monetary cost is unknown.
8. Verify the earlier saved analytical snapshot retains its original facts and is
   marked stale after the correction. Track 1 Food Cost still equals $55, and its
   entire report remains unchanged.
9. Snapshot and restore the whole SQL database. Compare restored Track 1 and prep
   reports, task progress, and the original acceptance retry. Check private table
   permissions and flag-off legacy holds on the restored copy.

## Evidence and limits

The review status and verified local package record exact tests, hashes and restore
proof. Initial fixture failures remain alongside corrected runs; totals count
distinct passing checks rather than presenting the initial run as wholly passing.
The SQL dump and restore proof contain only synthetic trial data.

All fifteen native feature pairs remain false in examples. No real vendor file was
imported, no operational database was migrated, and nothing was deployed or pushed
after PR #16. Mongo fallback/bootstrap code still exists when `USE_PG=false`; the
configuration cutover must prevent returning to that mode. These tests do not prove
managed-platform permissions, live-browser behavior or unrestricted historical
correction. Shared PIN/name still represents claimed identity.

## Next implementation

Add a read-only correction dependency review that shows affected lots, container
movements, waste, task links and saved analytical periods before a manager attempts
a change. Show supported reverse order and unsupported holds without guessing an
automatic cascade. Then validate bootstrap, prerequisite flags and restore on the
intended managed platform before enabling operational workflows. Toast consumption,
Scheduling, Operations and wider analytics remain future integrations.
