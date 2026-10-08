# Cutover and correction reconciliation - October 8, 2026

This local checkpoint builds on deployment reconciliation commit `98ff47a` and
the published PR16 corrections beneath it. Thirteen tracked source/test changes
and ten new source/document files were brought forward from the preserved
continuation using a three-way patch. They combined without conflicts. The
original 40-file continuation and its preservation snapshot remain unchanged.
Historical review-status JSON and README totals were not copied over the newer
review notes; this checkpoint does not close every original finding.

## Operating boundaries

Installed native prep batch/container schema retires legacy stock readers and
writers even with feature flags off. Stock and logs are unavailable rather than
reported as zero. Owner summaries and AI context retain that distinction. Old
prep reports and par advice are held before contacting AI or saving changes.

Installed native count/day-list schema retires old operating count/list screens
and their writers. Explicit archive reads preserve their evidence and label it
archived and non-operational. They respect location/date/track identity, exclude
purchased-item count history and do not create new sessions after cutover. Load
failures and late responses cannot silently restore stale lists or prior-location
figures. Failed override removal preserves the row.

This is a one-way schema boundary, not a flag-only rollback. Restoring older
application code must not reactivate the parallel legacy ledgers. Mongo code
still exists for explicit legacy mode; PostgreSQL remains the selected deployment
target. No automatic sync or promotion of retained legacy quantities is added.

## Correction review

Managers can inspect batch dependencies before proposing a replacement or void:
current lots, retained prepared-input edges, container balances/movements, paired
waste, task reconciliation, immutable staff decisions and stale saved periods.
The read uses a repeatable-read, read-only transaction and the same manager/location
boundary as correction preview. It never changes inventory, authorizes a correction
or performs a cascade. Existing quantity/source and save-time guards stay decisive.

Container histories use the new batched helper, preserving the older review order
and exact values. Other recipe/source and saved-period reads still need performance
review; this does not make the entire dependency graph constant-cost. Suggested
next actions are conservative, particularly after immutable movement undos. Use
the existing paired-waste preview for its full supported reversal checks.

The client holds missing journal coverage or malformed container movement arrays
before returning correction evidence. Refresh failures clear old approval evidence
and retain the reason. Location/record changes ignore late responses. Original
pending commands retain their key/body/hash and exact retry path.

## Combined synthetic day and recovery

The complete trial uses a separate counter and reviewer, satisfying the newer
self-review guard. Explicit purchased opening value $60 plus $40 food purchases
minus closing value $45 yields $55 actual Food Cost. Prep opening count 1 lb,
accepted production 2 lb, measured fill/service movements and 0.25 lb service
waste are followed by a second batch and closing prep count of 3.4 lb.

The unallocated second batch is corrected to 0.75 lb, its task link reconciled,
and the task explicitly finished. Recorded production becomes 2.75 lb. Observed
depletion is 0.35 lb; 0.25 lb is explained by recorded waste and 0.10 lb remains
service use or unrecorded loss. Sales coverage is absent, so no final variance
or prep monetary cost is asserted. The original saved analytical report remains
immutable and becomes stale. The entire Track 1 report remains unchanged at $55.

The trial includes the published waste correction and final private-access boundary.
Whole SQL restore preserves Track 1/prep reports, task progress, dependency reviews,
original staff acceptance replay, private table permissions and flag-off legacy
holds. The prior checkpoint separately verifies the full ordered 29-file migration
chain and ordinary owner-role Track 1 recovery; those are distinct evidence runs.

## Evidence and remaining scope

Nineteen distinct selected backend cases pass across the initial 12-pass run and
seven-case recheck, including inherited cases. The initial full-day fixture used
one identity to submit and approve a physical count and was correctly held with
403. It is preserved in the evidence package. The corrected fixture and count/
production author and staff-response regression checks pass.

Both final frontend configurations pass 454 tests across 54 suites: PostgreSQL
with native features held, and the purchase/count/catalog foundation configuration.
The earlier 452-test runs precede the two new malformed-response checks and are
retained separately. These are source tests, not live-browser or hosted proof.
The production build passes with the same three existing hook warnings in purchase
orders, scheduling and staff. No build was deployed or operational flags enabled.

The remaining schema reconciliation and managed-development tools still need
integration against this branch and its 29-file plan. Hosted roles, partial objects,
applied checksums, exposed schemas, isolated hosted recovery and browser acceptance
remain open. Safe history paging, residual batching, request-key namespaces and
other original review findings are separate work. Login redesign and future Toast,
Scheduling, Operations and wider analytics remain outside this checkpoint.

No hosted SQL, operational import, feature enablement, deployment, merge or PR push
occurred. All native flags remain false in examples. This checkpoint is local;
PR14-16 remain draft and unmerged. Track 1 accounting and separate taxes/fees stay
intact.
