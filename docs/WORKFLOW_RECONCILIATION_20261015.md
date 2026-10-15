# Inventory workflow checkpoint and remaining work

**Current local slice:** [submitted source-capture recovery](SOURCE_CAPTURE_RECOVERY.md)
now covers manual entries and file-upload identities. Local validation passes
776 frontend tests, 741 offline cases, the strict build, and 36 manual/native
capture cases. Independent review remains pending; a new draft PR requires the
owner's requested prompt before push. No new hosted window or deployment change
is part of this slice.

**Latest same-day result:** the separately approved hosted backup/index window
completed and closed at 2:14 p.m. EDT. Fresh application backup/restore and the
exact index application passed; all writers are restored and the accounting
control remains $212. See [execution evidence and remaining gates](HOSTED_INDEX_WINDOW_20261015.md).
The hold/window/index-next-step language below is historical.

**Later same-day update:** PR34 merged as `ce7eb27`, both Render services were
verified live, and the owner lifted the broad hosted-test hold. See the
[hosted recovery checkpoint](PR34_HOSTED_RECOVERY_CHECKPOINT.md) for eight passed
scoped database observations and remaining live-test limits. No maintenance
window is active; writer suspension, fresh backup/restore and exact index
application retain separate gates. The reconciliation below preserves the
earlier assessment and hold, not the current execution status.

October 15, 2026. Source baseline: `16e21c51cb9a1a60c59a5c2ec54765ecc5509692`
(PR33 merge). This reconciliation is local documentation only. No application,
SQL, test implementation, credential or deployment changes are included.

Subsequent owner approval authorized the local
[submitted-correction recovery implementation](SUBMITTED_CORRECTION_RECOVERY.md).
The matrix and proposal below preserve the reconciliation-time assessment;
use that linked checkpoint for this slice's implementation and test status.
Hosted testing remains held.

Published as [draft PR34](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/34).
Its original head `4ad1a9b` passed all four CI jobs. The owner subsequently
approved the independent review's confirmed-discard, API replay-ownership and
scoped key-lookup amendments. Use the linked implementation checkpoint for their
current validation. The historical proposal below is not a new approval gate;
merging and hosted execution remain separate approvals.

## Current decision and evidence boundaries

**Hosted testing remains on owner hold.** No current maintenance window exists.
Do not pause the API or Toast jobs, run hosted backup/restore or cancellation
tests, prepare/apply the source index, or change connections under this checkpoint.
The earlier maintenance window is closed. Future execution requires fresh writer
verification and a new approved window; index application additionally requires
approval of its exact generated plan.

The owner confirmed on October 15 that **Companion writes to a local copy and has
not migrated to Supabase**. Exclude it from the current hosted writer list on
that basis; recheck before a future window or integration. This is owner-supplied
deployment information, not proof from Companion's source files. No Companion
configuration, data or code was changed.

Keep current Render/Supabase deployment and connection choices during build.
Credential rotation is deferred at the owner's request. The separately reviewed
restricted deployed-role cutover remains a pre-operations gate; local restricted
credentials do not establish the deployed API identity. Login/PIN redesign,
broad UI rework and cross-repository integration remain separate workflows.

## Merged source and validation

[PR33](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/33) merged from
`f65b552f5e5b95f4dcd22ef1a8338f04367d7f3f` at the baseline above.
The GitHub PR metadata and all four jobs in each run were rechecked read-only:

- [Amended-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38679694060): success.
- [Merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38680039543): success.

The PR records 689 frontend tests plus production build, 741 offline cases and
79 disposable PostgreSQL cases. These are prior CI results, not newly executed
tests for this documentation change. Local encrypted export/restore and
fingerprint-path checks are detailed in
[the PR33 checkpoint](FINGERPRINT_PATH_DIAGNOSTICS_CHECKPOINT.md).
Passing CI does not lift the hosted hold or establish operational acceptance.

## October 15 writer and frontend configuration review

These are point-in-time observations from the preceding read-only review and
the separately owner-approved frontend cleanup, not new hosted probes here.

| Entry point | Evidence and current disposition |
| --- | --- |
| Render `jaymax-api` | Known API writer. Recorded database connection still uses `postgres` on transaction-pooler port 6543. No connection or API environment edit was made in the cleanup. |
| Two Toast ingestion jobs | Known scheduled producers: Bert's/Rudd's and Papa Leoni's. Their previously recorded configuration remains the maintenance-plan starting point, subject to fresh verification. No jobs were paused in the October 15 review. |
| Companion | Local copy only, per owner confirmation; no current Supabase migration. Future integration must re-establish writer ownership. |
| Render static frontend | An API client, with no independent direct Supabase writer identified. Two accessible Render workspaces contained only the known API/static pair; the second workspace had no services. |
| Two older accessible Sites | Runtime environment-variable lists were empty. This excludes configured runtime variables in those two sites; it does not prove that all possible integrations or hardcoded clients are absent. |
| SQL editor, scripts, other accounts/platforms | Not exhaustively attributable from service listings or a point-in-time session snapshot. No claim of a complete writer drain is made. |

The current published HTML, asset manifest, listed JavaScript/CSS and source maps,
and service worker were scanned: no matches to the saved database credentials or
the checked generic secret patterns were found. The frontend bundle points to
`jaymax-api`. The displayed current build logs had no checked secret-pattern
matches. This is scoped negative evidence, not a guarantee covering all secrets,
historical builds/logs or unknown assets. The JavaScript source map is public.

With owner approval, eight backend-only variables were removed from **only**
Render's `JayMax-Concepts-` static service:
`ANTHROPIC_API_KEY`, `AUTH_REQUIRED`, `AUTH_SECRET`, `BOOTSTRAP_TOKEN`,
`DATABASE_URL`, `EMAIL_FROM_ADDRESS`, `PUBLIC_APP_URL`, `RESEND_API_KEY`.
`CI` and all 17 `REACT_APP_*` settings were retained. Render's **Save only**
action was used, and absence of the eight keys was verified after page reload.
No deployment was triggered. This removes future build access; it does not
rewrite historical builds or revoke any credential.

A prior dashboard tool-output capture exposed a database credential, as already
reported to the owner. Rotation remains recommended and explicitly deferred;
no secret value is reproduced in this guide, and no rotation is claimed.

## Reconciliation of the original review

`INVENTORY_REVIEW_STATUS.json` and the original foundation documents are dated
historical evidence. Their original totals, source hashes and line anchors are
not recomputed or promoted to current acceptance here. The table below identifies
implemented replacements and narrower remaining work at PR33. **Implemented**
means source and named checks exist, not that every browser/deployment path is
accepted. This is a scope review, not a fresh execution of all named suites.

| Original finding | Implemented boundary at this baseline | Remaining acceptance or design |
| --- | --- | --- |
| R01–R02: task constraint and daily/bulk list collision | Native dated lists, execution, assignment and staff production replace covered legacy operations; installed-schema holds/archive reads preserve old rows. | Complete operating acceptance and future employee mapping. Do not repair the legacy archive into a second live ledger. |
| R03: split prep stock/log writes | Native batch, waste, container and staff-decision transactions; legacy stock readers/writers held after cutover. | Additional operating acceptance and unsupported historical corrections. |
| R04: receiving partial commit | Native invoice-linked receiving and versioned order commands with retry/rollback guards. | Less common splits/multi-pack business cases and any legacy operational recovery need specific acceptance, not a blanket rewrite. |
| R05: mixed units | Separate native purchased/count profiles; canonical menu ingredient identities and explicit unit validation; unknown conversion confirmation. | Full cross-screen physical/menu contract audit. Do not reinterpret legacy implicit portions as verified physical facts. |
| R06: lost invoice mapping | Retained sources, immutable received purchases, correction lineage and current-source lookup across captured files. | Broader supplier-format/business-policy cases and source-capture recovery. |
| R07: failed-save data loss | Covered forms retain failed drafts; initial purchase submission retains exact body/key across same-tab reload and same-user sign-in. | Submitted correction and capture persistence remain separate. Other command families need their own recovery inventory. |
| R08: incomplete browser backup | Native encrypted backup, fingerprint verification, disposable recovery, guarded export/cleanup and bounded diagnostics exist. | Hosted cancellation/fresh-window backup acceptance held; managed platform recovery and backup operations remain separate. Browser JSON is not disaster recovery. |
| R09: repeated sales deductions | Sales-to-actual-stock deduction is outside the approved accounting model. | Future versioned Toast analytical evidence and completeness; no Track 1 deduction. |
| R10: global supplier/store identity | Shared canonical product/SKU links and local availability with revisioned item edits. | Reviewed global product/pack amendments and duplicate identity policy. No automatic product merge. |
| R11: invalid recipes/unknown costs | Menu graph/source/yield validation and incomplete-cost presentation; native recipe/batch quantity guards. | Complete remaining legacy/backend cost paths and full mapping audit. Prep monetary valuation is unselected. |
| R12: lost financial/source facts | Raw fields retained; exact purchase amounts, received dates, signed credits, separate tax/fees and immutable corrections. | Additional invoice policies/multi-pack cases and location business-date decisions. |
| R13: mutable closed reports | Explicit-value Track 1 snapshots and prep analytical snapshots retain historical facts; changed sources make analytical evidence stale. | Future historical sales/recipe analytics and a reviewed prep costing policy. |
| R14: whole container-group deletion | Measured native fill/send/return/unpack and paired waste/reversal; source allocation and timeline guards. | Remaining live operating acceptance and eventual service-consumption semantics. Movement is not sales consumption. |
| R15: adapter metadata loss | Targeted item/settings/null/price/unit round trips, shared catalog mapping and revisioned partial saves. | Broader field-by-field compatibility audit; do not declare every legacy field lossless. |
| R16: mutable prep counts | Immutable issued sheets, submissions, manager decisions and native observation history; legacy sessions archived/held. | Independent employee identity and wider recovery/operating acceptance. |
| R17: partial concurrency coverage | Catalog/menu/order revisions, native transaction locks, request identities, dependency review, source and accounting guards. | Correction/capture recovery, supplier outbox and other unsupported command surfaces. Local concurrent tests are distinct from a live concurrent-first-post trial. |
| R18: hard deletion/history | Purchased retirement, order archive, immutable journals, retained recipe references and planning history. | Reviewed global identity/pack amendments and prep count-scope retirement. Retired purchased stock still counts physically. |
| R19: reproducibility and deployment drift | Ordered migration constants, reconciliation/readiness tooling, native installation and local recovery evidence; additive hosted adapter exists. | Source index remains unapplied in the recorded hosted checkpoint; fresh hosted qualification, restricted-role deployment gate and managed recovery remain held/separate. |
| R20: late reads replace drafts | Scoped responses, revisioned editor saves and initial purchase pending journal protect covered flows. | Command-specific persistence beyond initial posting; browser restart/new-tab recovery is not guaranteed. |

Evidence entry points:
[menu contract](MENU_RECIPE_INTEGRITY.md),
[order commands](ORDER_COMMAND_INTEGRITY.md),
[supplier prices](SUPPLIER_PRICE_HISTORY.md),
[cutover and dependency review](CUTOVER_RECONCILIATION_CHECKPOINT.md),
[current-source live recovery](LATEST_SOURCE_RECOVERY.md),
and [repeatable selected checks](REVIEW_TESTING.md).

Source/test anchors include `backend/legacy_prep_views.py`,
`backend/prep_correction_review.py`, `backend/tests/test_combined_prep_cutover.py`,
`backend/tests/test_prep_correction_review.py`, `backend/tests/test_native_purchases.py`,
`backend/tests/test_posted_invoice_corrections.py`,
`frontend/src/components/ManualPurchaseEntry.js`,
`frontend/src/components/PurchaseImportsTab.js` and
`frontend/src/lib/pendingPurchases.js`. Existing test bodies and the selected CI
profile were inspected; test presence is not a fresh pass claim.

## Recommended next local slice: submitted invoice-correction recovery

Implement this only after the owner accepts this proposed scope. No runtime fix
is included in the documentation reconciliation.

`PurchaseCorrectionReview` currently keeps its submitted correction in a
component `useRef`; it freezes and retries that body/key while mounted.
`pendingPurchaseJournal` persists **initial posting**, not correction commands.
A remount loses the correction request's local retry evidence. This does not
prove a duplicate database write: the server's existing identity, predecessor,
review-hash and transaction guards remain in force. It is an unresolved
operator-recovery gap after an uncertain save.

Proposed acceptance for one focused slice:

1. Retain the submitted correction's exact body/key, actor, location, document,
   initial batch, predecessor and review hash before sending. Fail safely if
   persistence is unavailable; never silently send an unretained command.
2. Restore only for the same actor/location. Show the frozen original review;
   require a fresh saved-outcome read before any explicit retry. Never auto-post.
3. Distinguish own saved correction, later replacement, competing correction,
   uncommitted request, changed source/period and unavailable/malformed evidence.
   A fresh read alone is not permission to erase an uncertain command or create
   another key. Preserve existing server checks and late-commit safety.
4. Local fictional component and disposable-database checks cover loss before
   commit, loss after commit, reload/sign-in, exact retry, competing/later
   correction, storage failure and actor/location changes. Reversal/replacement
   must occur once; a retry must not repeat the financial effect. Preserve
   received dates, separate tax/fees and closed-period lineage.
5. Record local results, review independently, and prompt before a new draft PR.
   Live browser/transport acceptance stays deferred while hosted testing is held.

Manual source capture also retains its request only in memory; file uploads hold
a `File` and key in a ref. Follow that as a separate slice: file bytes, retention
and privacy require their own design rather than placing arbitrary attachments
in the initial-post journal. Supplier outbox, broad UI changes and new integrations
should not be bundled into correction recovery.

## Later gates and sequence

- Finish command-specific recovery, then audit remaining canonical fields,
  unit/cost completeness and retirement rules against concrete acceptance cases.
- Resume the hosted backup/index workflow only after the owner lifts the hold,
  writer completeness is reconfirmed and a new maintenance window is approved.
  Generate a fresh backup/verified disposable restore and present the exact index
  plan before application. Do not reuse an old window or infer approval from CI.
- Coordinate credential rotation and restricted-role deployment with affected
  consumers before operational use. Keep the current build connection standard
  until separately approved.
- Keep UI redesign and Companion/Scheduling/Operations/Analytics adoption in
  separate coordinated workflows. Toast sales explain consumption; they never
  replace the purchased-item physical accounting baseline.

Track 1 remains purchased-item opening count plus received purchases minus closing
count, with explicit count values. Track 2 prep/waste and Track 3 sales explain it.
No accounting writeback from either explanatory track is authorized.

## Documentation verification

The generated migration/feature guides still match their source constants
(`python tools/review_contracts.py --check`). New relative Markdown links and
the listed source/test anchors were checked for existence. `git diff --check`
passed. No frontend, backend or database suites were rerun for these prose-only
changes; the CI results above belong to the merged PR33 source. No GitHub push,
PR creation or hosted action is part of this reconciliation.
