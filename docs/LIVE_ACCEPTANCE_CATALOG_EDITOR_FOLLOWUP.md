# Live acceptance and catalog editor follow-up

## Deployed acceptance on October 10, 2026

PR18 is merged and both Render services were verified Live at `85cf2b7`.
These results use clearly labelled fictional Bert's records in the build database.

| Control | Observed result |
| --- | --- |
| Track 1 | $184 opening + $173 net received food purchases - $145 closing = **$212 actual Food Cost** |
| Accounting history | Close, reopen and reclose retained original and replacement results; both remain $212 |
| Track 2 prep | 8 opening portions + 96 produced - 20 closing = **84 observed depletion** |
| Waste explanation | 4 separately confirmed discarded portions; remaining **80 service use or unrecorded loss** |
| Gross input | 30 lb gross purchased protein includes 6 lb trim; trim is not deducted twice |
| Prep history | Current reviewed analytical snapshot, counts, batch and waste persisted after reload and renewed normal owner sign-in |
| Staff partial submission | Blank produce stayed uncounted; acceptance was held |
| Manager concurrency | Revision 2 acceptance refused after revision 3 submission; refreshed revision 3 accepted |
| Accepted count | October 10 explicit values: $20 produce + $20 appetizers + $105 protein = **$145** |
| Accounting independence | Original October 1-8 preview remained **$212** after prep/waste and staff writes |

Prep production completeness remains unverified and service/Toast coverage is
incomplete. Final expected stock and unexplained variance remain unavailable;
analytical costing is uncalculated. The 80 portions are not confirmed waste.
The staff workflow ran with an owner session still active. Submissions show
"Signed-in submission"; independent employee authorization is not proven.

## Catalog concurrency defect

Two owner-signed-in browser tabs opened `TEST ONLY Produce - UI 20261010`
(`SB-002`) at par 0. The first editor saved par 1. The second retained its older
form and saved par 2 after background polling advanced the store revision.
The save succeeded without a conflict and the authoritative read showed par 2.
The fictional par was restored to **0** and read back. Operational items were
not changed.

`SetupTab` retained its form across refreshes but did not retain its opening
revision. `App` sent item saves through the current store revision, bypassing
the existing original-revision guard after a successful background refresh.

The amended follow-up retains the original saved record and revision in both
item and recipe drafts. An ordinary save proceeds at the current collection
revision only if the edited record is unchanged. A changed or missing record
holds the save and preserves the draft. An unseen race still reaches the
existing store/server revision guard. New items use the latest collection and
available control number; unrelated revisions no longer force a restart.

Both editors offer **Reload latest and keep my changes**. This explicitly reads
latest data and stages independent edits without saving. Competing field edits
are named and retained for review. Pack, portion and supplier relationships, and
recipe ingredient/yield relationships, are reconciled together; arrays are
atomic. Recovery preserves latest metadata and unknown conversions and checks
recipes against the latest ingredient catalog. It does not recalculate a
conversion. [The review amendment](PR19_REVIEW_AMENDMENT.md) records the four
findings, tradeoffs and test coverage.

## Validation and release status

The amended catalog, recipe, save-integrity, App and store checks pass **125
focused tests across 7 suites**. All **553 tests across 65 suites** pass with the
reviewed native feature profile. The strict production build passes with
`CI=true` and ESLint enabled.
The original PR19 code checkpoint `6069ce6` passed 527 tests and a strict build;
the first pushed head `f68596d` added documentation, and its Inventory CI passed.
The review amendment stays on `codex/catalog-editor-revision-integrity`, based
on `85cf2b7`, in [draft PR19](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/19).
It has not been merged or deployed. Hosted item and recipe acceptance must be
rerun after a separately approved merge and test deployment.

## Remaining workflow

1. Review the amended item/recipe draft PR and require its current-head Inventory CI before approving a merge.
2. Rerun the two-tab item check and add the recipe conflict/recovery check on the deployed fix.
3. Finish independent posting retry acceptance and verify one persisted outcome.
4. Test employee authorization separately when the authentication workflow resumes.
5. Rework the growing setup screen in the later UI workflow.
6. Review cleanup of the labelled fictional fixtures before operational use, preserving this acceptance record.

Cross-tab owner labels briefly survived a session that native reads rejected.
Normal owner sign-in restored reads and the same saved analytical snapshot.
Record this for the later session/UI workflow; the exact initial cause is not
proven. Current hosting, Supabase connections and hosted schema are unchanged.
