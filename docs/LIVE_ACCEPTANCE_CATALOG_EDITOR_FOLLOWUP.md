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

The local follow-up keeps the catalog revision inside the retained form and
passes it through `App` into `useStoreState.save`. Existing item editors capture
the revision when opened; new-item forms capture it on their first edit.
A stale or unverifiable form is refused without clearing entries. Cancel and
reopen explicitly loads the latest saved item; new drafts can also be cancelled.
An unchanged revision still saves normally, while an unseen server-side change
remains protected by the existing revisioned route. No automatic merge or
conversion recalculation is added.

This is deliberately conservative: any change to the restaurant's global
revision can require reopening the form, even when another item changed.
Field-level merging can be evaluated later rather than silently rebasing today.

## Validation and release status

The focused catalog, save-integrity, App and store suites pass **95 tests**.
All **527 tests across 63 suites** pass with the reviewed native feature profile.
The strict production build passes with `CI=true` and ESLint enabled.
The follow-up is local on `codex/catalog-editor-revision-integrity`, based on
`85cf2b7`; it is unpushed and has not been deployed. Hosted catalog acceptance
must be rerun after a separately approved PR and test deployment.

## Remaining workflow

1. Review and publish the narrow catalog fix when approved; require Inventory CI.
2. Rerun the two-tab catalog conflict test on the deployed fix.
3. Finish independent posting retry acceptance and verify one persisted outcome.
4. Test employee authorization separately when the authentication workflow resumes.
5. Rework the growing setup screen in the later UI workflow.

Cross-tab owner labels briefly survived a session that native reads rejected.
Normal owner sign-in restored reads and the same saved analytical snapshot.
Record this for the later session/UI workflow; the exact initial cause is not
proven. Current hosting, Supabase connections and hosted schema are unchanged.
