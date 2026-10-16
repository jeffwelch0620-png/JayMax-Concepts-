# PR39 merge and scoped backend acceptance

October 16, 2026. The owner approved merging PR39 and proceeding with the next
step. PR39 merged normally as `fafa95e4a50297c61ec36035099bc6890f915925`, from
reviewed head `9298503db708c42f50778076441e47849f02dcb7`; no protection bypass
was used.

## Deployment and CI

- [Reviewed-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38969105939)
  passed all four checks, including the Windows ACL tests that timed out locally.
- [Merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38971290919)
  completed successfully on exact merge `fafa95e`.
- Render API deploy `dep-db99l1m1egvs73cj6d50` was observed Live on the exact
  merge after automatic deployment, duration 2m40s. No manual deployment or
  settings change was performed. Frontend source is unchanged from PR38.
- The first ownership read overlapped deployment and failed. Its explicit retry
  succeeded after the API was Live. That initial request is not counted as a
  functional acceptance failure or as a successful read.

## Fictional scope and method

Only the existing Bert's fictional supplier planning price is edited:
`berts_WI-003`, `TEST ONLY Protein - UI 20261010`, PFG SKU
`TEST-ONLY-PROTEIN-20261010`. The existing menu record is
`TEST ONLY Editor Acceptance - UI 20261010`. No recipe or other setup record is
created, and no purchase, count, prep or waste command is submitted.

Baseline planning price is $70 per purchase unit, 80 portions, $0.875 per portion
and $0.875 fictional menu cost. The real deployed ownership read shows Bert's
13.0% estimated recipe-cost average, $145 last count value and $182 net received
food. The independent historical closed Food Cost control is $212.00.

The staged sequence is blank price, explicit `0E-10`, then restoration to $70.
Deployed ownership UI reads are separate from the read-only database/context
observer. The latter verifies its item/recipe/owner-view/context helper source
against the merge, reads a certificate-verified live snapshot in read-only
transactions, and assembles context locally. It never calls a hosted AI endpoint
or sends data to an external LLM; no hosted-AI runtime pass is claimed.

The observer pins 82 protected relations, native summaries, historical reports,
recipe rows, unrelated supplier rows, existing price events and store payloads.
Only the fixture's planning price/provenance/history, its save audit timestamps
and expected Bert's catalog revisions may change. Audit timestamp projections
must reconstruct a row hash present in the original baseline; this does not
ignore changes to other item/supplier business fields.

## Acceptance checkpoint

All four checkpoints passed: baseline, blank, explicit zero and restoration.
The deployed owner view shows the blank-price recipe estimate unavailable with
the intended review notice. Explicit zero restores a known estimate (11.2%
Bert's average), with zero item/menu cost in the read-only observation. Restoring
$70 restores $0.875 per portion/menu and the fresh-page 13.0% average (8.8% for
the fictional menu item). Physical count value/received food remain $145/$182.
The merged-source item/menu estimates and locally assembled context preserve
Unknown separately from zero. No hosted AI endpoint was exercised.

Each read-only checkpoint verified 82 protected relations and the unchanged
$212.00 historical Food Cost control. Exactly three expected price-history
events and three catalog revision increments accompany the three UI saves.
Recipe rows, physical profiles, global prices and unrelated records remain
unchanged; only the fixture's documented price/provenance/history and audit
timestamps changed. All observer connections closed. The original $70 fixture
price is restored; no test relay, override or permission change was used.

The first observer attempts held on a transient connection error, an incomplete
local read-profile flag, and overly strict audit-timestamp comparisons. The local
read profile and comparison were corrected without changing hosted settings or
data. Initial failed reports remain retained; they are not successful acceptance
checkpoints. The observer's exact-phase checks, source hashes and accounting
comparisons remain in force.

Successful evidence checkpoints (all October 16, UTC filename timestamps):

| Phase | Evidence file | Planning price | Menu cost | Historical Food Cost |
| --- | --- | --- | --- | --- |
| Before | `pr39-backend-before-20261016T215435708361Z.json` | 70 | 0.875 | 212.00 |
| Blank | `pr39-backend-blank-20261016T221719325290Z.json` | unknown | unknown | 212.00 |
| Zero | `pr39-backend-zero-20261016T222042438096Z.json` | 0.0000000000 | 0 | 212.00 |
| Restored | `pr39-backend-restored-20261016T222328902075Z.json` | 70 | 0.875 | 212.00 |

Evidence outside Git: `pr39-backend-<phase>-*.json`, saved `pr39-owner-*-ui-20261016.txt`
and screenshots, plus `pr39-render-api-live-20261016.png`. Local follow-up fixes
and their separate validation are described in
[the next candidate's checkpoint](PLANNING_COST_FEEDBACK_FOLLOWUP.md).

Restricted runtime-role cutover remains open before operational use. No connection,
schema, hosting or security-setting change is part of this acceptance test.
