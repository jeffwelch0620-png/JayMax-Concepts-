# Legacy prep operating reads and correction review

October 8 reconciliation: this retained work now combines with the current PR16
integrity and deployment fixes. See [the current checkpoint](CUTOVER_RECONCILIATION_CHECKPOINT.md).
The October 7 branch, evidence and remaining-work text below is preserved history.

The next local checkpoint completes count/list archive boundaries and records a
combined synthetic trial in [Prep cutover trial](PREP_CUTOVER_TRIAL.md). This document
retains the first boundary checkpoint and its remaining-work assessment.

Local continuation of draft PR #16, October 7, 2026. Branch:
`codex/legacy-cutover-continuation`; baseline:
`67546fa79de3b7a9aff2715063b36d1ba7f3fe44`. These changes are outside
[PR #16](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/16), which
remains draft and unmerged. No operational migration, import or enablement.

## Finding and local fix

Legacy prep stock, logs, counts and lists are not the native journals. Container
and staff-count migrations preserve original rows and freeze their writers, but
old stock/report/dashboard readers could still display those rows as current.
Native batches also previously held old stock writers primarily through a feature
flag; turning that flag off before container migration could restart a parallel
legacy stock ledger.

`backend/legacy_prep_views.py` now detects installed native batch/container schema
or requested flags. It holds legacy stock writes even with flags off. The app's
legacy prep-state response remains successful for location loading, but stock and
logs are **null**, with an explicit unavailable status; the legacy inventory screen
shows that status instead of zero balances or stock actions. Existing native
container screens still use their own reviewed journal.

Prep reports, owner prep summaries and old AI par advice additionally detect
native observation/count/planning/day-list cutover. Reports and AI generation/apply
return 410; owner prep figures return null with an unavailable status. The owner
dashboard clears old prep figures on refresh and shows failures explicitly. General
owner/AI context does not infer prep shortfalls or zero on-hand from missing legacy
stock. Original rows remain available to database review and existing native setup
diagnostics; no historical values are promoted automatically.

## Endpoint disposition

Paths below are relative to `/api`; location authorization remains in the existing
middleware. This matrix identifies the operating boundary, not a claim that every
old endpoint is removed.

| Family | Present boundary | Remaining work |
| --- | --- | --- |
| `pg/prep/{store}/state` | Stock/logs unavailable after batch/container cutover; app still loads. | Native combined operating read model, with measured counts and expected balances kept distinct. |
| `pg/prep/{store}/complete`, `apply-sales`, `use-container` and stock helpers | Native flag **or installed schema** holds parallel stock writers. | Toast consumption remains future Track 3; service movement is not consumption. |
| `reports/{rid}/prep`, `owner/prep-summary` | Historical report blocked or explicitly unavailable once relevant native schema/flags exist. | Design native period/cost summaries without guessing valuation or counting the same batch twice. |
| `owner/summary`, general AI context | Legacy prep stock omitted after stock cutover; prep-low unknown. Track 1 native summaries stay independent. | Other legacy recipe-cost and waste estimates remain labeled; native operational analytics are incomplete. |
| `ai/par-advisor/{rid}`, `.../{recommendation}/apply` | Generation and application held after reporting cutover, before contacting AI. | Native evidence-backed par recommendations; retained recommendations are not current approval evidence. Dismissal/history remain available. |
| Legacy count sessions/lines | Existing staff-count schema/flag holds prep writes; retained read endpoints still exist. | Explicit archival labeling and removal of remaining operational fallback screens. |
| Legacy prep lists/versions/overrides | Existing day-task schema/flag holds writers; native UI uses reviewed dated lists when enabled. | Retained GET contracts still need archive labeling and capability-aware UI handling with flags off. |
| Legacy prep items and dish recipe definitions | Readable for source mapping; planning writers have existing schema/flag holds; source edits require native re-review. | Continue catalog/menu/source-edit audit rather than treating metadata as stock. |
| Legacy staff prep sheet/completion | Existing native staff-task hold; native assignments/submissions use explicit date, track and immutable IDs. | Verified employee account mapping remains deferred; shared PIN/name is claimed identity. |
| Purchased-item counts, receipts and period close | Native reviewed Track 1 workflows and their existing holds. | Combined recovery/enablement trial; no prep or sales deduction into accounting. |

Mongo fallback code still exists for `USE_PG=false`. It is not a second source to
merge or keep synchronized. The production cutover must select PostgreSQL as the
authoritative mode, verify backend/frontend configuration together, and prevent
return to Mongo mode. This patch does not remove Mongo bootstrap or all fallback
routes; that remains an explicit cutover task.

## Historical correction dependencies

These are existing source/probe-backed constraints. No automatic cascade was added.

| Record to change | Review process / hold |
| --- | --- |
| Received invoice / purchased count | Use signed invoice correction or immutable count replacement. Review affected closed periods through existing reopen/scope workflows; taxes and fees remain separate. |
| Native production batch | Select current version. Any downstream prepared-input, waste or container allocation holds replacement/void. Resolve supported dependent records first; never change purchased stock. |
| Opening prep stock | Whole-count opening decision has its own void workflow. Allocated opening lots hold changes; it is not a production batch. |
| Prep count observation | Immutable replacement/void. When used as an opening count, resolve downstream lot use before correction. |
| Container send/return/unpack | Only supported latest original movement can be undone, at its original physical instant. An unpack reversal is held if its released lot has since been allocated. |
| Container waste | Use paired latest waste reversal; generic observation correction is held. Allocation and waste observation reverse together. |
| Accepted staff production | Staff decision stays immutable. Manager changes the current batch using supported replacement/void, then reconciles task progress. A void reopens the task rather than claiming completed production. |
| Changed recipes, units, roster or assignments | Review pinned source versions and affected pending submissions. Never reinterpret earlier quantities using newly edited units or silently relink an accepted decision. |

Do not promise an arbitrary historical correction is possible. Later container
activity, source-lot use and period dependencies can leave a change held until a
reviewed recovery workflow exists. The next useful implementation is a read-only
dependency review showing affected records and supported reverse order; a broad
automatic cascade would be unsafe and is not implemented.

## Combined trial before operational enablement

Use disposable synthetic data and a restored copy first: received purchase,
explicit-value purchased count, prep opening, released plan/assignment, partial
staff production acceptance, container movement/waste, manager count acceptance,
period explanation, supported batch correction/task reconciliation and restore.
Confirm exact retries, flag-off holds, unavailable old reads and unchanged Track 1
results. Exercise flags off, missing prerequisites and source-version changes.

Take a verified database snapshot, stop operating traffic, install migrations in
dependency order and verify private permissions before enabling matching flags.
This patch's schema probes are not an online migration synchronization protocol.
Managed-platform bootstrap/permissions and live-browser behavior still require
their own trial. Scheduling, Operations, analytics and Toast remain future modules.

## Validation

Local test evidence and the new snapshot are recorded in
`INVENTORY_REVIEW_STATUS.json` after verification. Tests use invented rows in
disposable loopback PostgreSQL and mocked/component frontend requests. They are
not production or managed-platform proof.
