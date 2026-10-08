# Prep correction dependency review

October 8 reconciliation: container details now use the corrected batched read;
missing client coverage/malformed movement arrays hold review. See [the current
checkpoint](CUTOVER_RECONCILIATION_CHECKPOINT.md). The original implementation
contract and earlier evidence below are retained.

Local continuation of draft PR #16. Nothing in this checkpoint is pushed,
merged, deployed, enabled, migrated or imported into an operational database.

Managers selecting a batch replacement or void now receive a read-only dependency
review before the quantity preview becomes available. It shows current affected
lots, the original and reversed prepared-ingredient allocations, container fills
and ordered movements, waste history, task production links, immutable accepted
staff decisions, and saved analytical periods with their current/stale status.
Purchased inventory and Track 1 Food Cost are outside this workflow.

## Database contract

`GET /api/pg/purchases/{store}/prep-batches/{event}/correction-review` uses the same
manager/location authorization and native batch feature boundary as correction
previews. Its transaction is repeatable-read and read-only. No migration, new
feature flag, external lookup, journal entry or database mutation is added.

The recursive root graph retains historical descendants even after allocations
are reversed. An old edge is not automatically a current blocker. The selected
record's gate uses the existing batch predecessor/lot-allocation guard. Corrected,
voided and opening-source records remain held for production correction. An
unallocated current production batch is only **eligible for preview**: proposed
measurements, source validity, stale review and save-time guards still apply.

Installed optional journals are inspected even when their operating flags are off;
missing optional schema is explicitly marked `not_installed`. The manager cannot
infer an empty operational journal from that status. Conservative saved-period
impact includes activity at the opening/closing instants and preserves reopened
snapshots as history. Corrections never silently rewrite a saved report.

## Supported sequence and holds

Review downstream allocations before their source lot. Every dependent change
still needs its own existing preview and reviewed command. For containers, the
review names only the next candidate: void an unused fill, undo the latest original
send/return/unpack, or reverse the latest waste through its paired command.
Released output may have been allocated again, and an immutable undo becomes the
latest movement. The review does not promise a multi-step undo chain or an
arbitrary historical cascade.

After a supported production correction, reconcile task evidence explicitly.
Original staff decisions remain immutable. Reopen affected and following saved
analytical periods from the earliest affected active period before replacements;
the existing period workflow still verifies the chain and source history.

The UI clears earlier dependency/quantity evidence on refresh. Failed or malformed
responses hold correction preview, show the reason and preserve the form's reason.
Late responses from a former selection/location are ignored. An uncertain save
continues to use the existing exact-key/body retry contract.

## Validation and remaining work

Synthetic database checks cover a three-level prepared-input graph, downstream
voids releasing a source while retaining history, missing optional schema, invalid
identity, feature-off behavior and authentication. The combined day additionally
checks manager/location authorization, container/waste/task/staff links, stale
periods, reconciled batch identity and identical dependency results after whole
SQL restore. Track 1 remains the same $55 report throughout.

Component tests cover holds, failure/retry, acknowledgment identity, stale-location
responses and invalidation of an earlier quantity approval. Exact test results and
archive hashes are recorded in `INVENTORY_REVIEW_STATUS.json` and the local package.

This is a production/opening-lot dependency inventory, not a general correction
engine for counts, recipes, assignments or purchased invoices. It does not prove
live-browser or managed-platform behavior. Existing historical correction limits
and shared-PIN claimed identity remain. Next: intended-platform bootstrap,
configuration, private-role permissions and restore readiness before enablement.
