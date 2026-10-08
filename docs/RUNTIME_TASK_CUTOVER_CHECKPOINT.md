# Retained employee tasks and archive permissions

October 8, 2026. Extends local commit
`24869fe703fad6051a076682d1cd043019ba81c3`. This step does not query or change
Supabase, import real invoices, edit deployment flags, push, merge or publish.
Track 1 remains purchased physical inventory with explicit count values and
received-date purchases. Prep and sales explain it without changing its facts.

## The remaining parallel task queue

The old PostgreSQL task portal uses `public.staff_tasks`, whose `assigned_to`
and `completed_by` fields are text. They do not identify a roster member or a
native assignment. Existing native task assignments use separate UUID identities
and reviewed versions. Matching names cannot establish that relationship.

The old manager and employee endpoints lacked a cutover boundary. The candidate
role lacked table grants, causing permission failures; an owner connection could
still expose the old queue as current work. A local reproduction confirmed the
owner read returned 200 after full native setup rather than the intended hold.
The reproduction failed on that read before attempting writes. Source inspection
identified the unguarded create/delete/completion/recurrence paths; final tests
exercise their rejection. No production write or external notification is used.

`legacy_staff_tasks.py` now retires the entire mixed count/prep queue when
`ACTUAL_INVENTORY_ENABLED` or `STAFF_PREP_TASKS_ENABLED` is requested, or either
`actual_inventory.staff_sheets` or `prep_inventory.task_assignments` is installed.
Installed schema remains a one-way boundary even with flags off. This deliberately
avoids treating half of an old mixed queue as a safe current operating workflow.
It can leave that queue unavailable while native features await enablement;
deployment readiness and matched flags must be resolved before staff rollout.

Current manager/inbox reads return 410. Create, delete, complete and recurring
task generation are held with 409 after the existing access/credential checks.
Manager `GET /api/pg/staff-tasks/{store}?archive=true` preserves the array shape,
adds `storeId`, and labels each historical row with `legacy_staff_task_archive`,
`archived=true`, `operational=false`, and `identityBasis=legacy_text`.
An employee inbox does not gain archive access. Archive reads do not manufacture
UUID assignments or rewrite historical names. Existing location and manager gates
still apply; this is not a login/PIN redesign.

Before either cutover flag or installed staff marker, the owner-backed legacy
queue retains its prior create/list/inbox/complete/recurrence/delete behavior.
The full-native candidate is not a grants profile for operating the old queue.
The new route guards do not impose universal immutability on arbitrary owner SQL;
the candidate denies legacy task/list INSERT, UPDATE and DELETE separately.

## Permission delta

| Object | Change | Reason |
| --- | --- | --- |
| `public.staff_tasks` | Add SELECT only | Explicit manager history after retirement. |
| `public.prep_lists` | Add SELECT only | Existing labeled legacy list archive reads the parent table and retained lines. |
| `public.prep_items` | Remove INSERT; retain SELECT and UPDATE | Legacy creation is retired; native workflows still need SHARE locks. |

There are now 27 individually named public-schema tables in this local profile.
These are trusted backend-role grants/policies, not grants to the database PUBLIC
role, employees, browser clients or a Supabase Data API role. Application store
gates remain necessary because the trusted server operates across locations.
The existing `retained_prep_metadata` trigger rejects prep-item DML. UPDATE is
required for the native `LOCK TABLE ... IN SHARE MODE` commands, so removing it
would break reviewed planning/production transactions even without data changes.

No native INSERT/UPDATE sets, read-only capture sets, function execution grants,
journal DELETE restrictions, DDL exclusions or delegation rules change. All 29
migration hashes, 94 function contracts and 123 relation contracts are unchanged.
Only the reviewed matrix pin changes from
`f2e134445020d7464ef90f4a156e1c26a941d92803bdb299b8b985726b10eae8` to
`0e2ad01e3806853f7c1f71e57f3970e7034791af1c369bac6825191e02d745fa`.
The target database has not supplied a new baseline.

The existing date/track prep-list archive does not return historical lists whose
`count_type` is NULL. These records remain stored and captured, but a separate
unclassified-history view still needs review. Do not label them daily or bulk by
inference. The task fixture preserves an unclassified inherited record and adds
a separate explicitly typed list to prove the candidate's archive parent/line
reads. This checkpoint does not claim complete access to all historical lists.

## Interface behavior

Operations requests history explicitly after a 410, requires archive labels,
shows historical status and entered names, and removes assignment/deletion
controls. Loading, failed requests and malformed archive responses cannot become
an empty operational task list. Refresh remains available. Late location responses
cannot replace the selected restaurant's queue or start an old-location archive
request. Delete errors are surfaced instead of escaping unhandled.

The employee portal shows the retirement message and retains direct Prep/Counts
navigation. Failed inbox refreshes clear stale completion controls. Locking or
unmounting invalidates pending inbox responses. Current prep and physical count
flows continue through their existing reviewed components. Shift scheduling,
training, compliance and SOP placeholders are unchanged.

## Source review of helper execution

All 19 granted native nontrigger helpers have direct Python or SQL references.
The package's `runtime-task-reviewed-delta.json` records paths without SQL bodies
or business data. Review includes their constraints, triggers and nested helpers:

| Helpers | Use |
| --- | --- |
| `purchasing.post_document`, `correct_document`, `validate_review` | Posting/correction commands and correction guards. |
| `purchasing.text_cells` | Source-cell CHECK constraints. |
| `purchasing.supplier_pack` | Shared catalog and supplier-price validation. |
| `actual_inventory.count_descends_from` | Physical correction/bridge lineage. |
| `prep_inventory.lot_remaining`, `lot_used`, `opening_source_valid`, `assert_lot_allocations` | Batch, opening and observation quantities/guards. |
| `prep_inventory.container_available_since`, `container_lot_timeline`, `assert_container_timeline`, `container_unit_scale`, `can_reverse_container_waste` | Container availability, timeline, capacity and waste reversal guards. |
| `prep_inventory.period_movements`, `period_sources_current` | Analytical closure calculations and source checks. |
| `prep_inventory.staff_sheet_current`, `task_progress` | Staff-sheet freshness and reviewed task production/progress. |

This is evidence of source references, not proof that every grant is the minimum
required for every runtime branch. No helper was revoked simply because it lacked
a direct Python call. Future permission reductions require trigger/helper closure
review and exercised transactions. Account/bootstrap and push-subscription routes
remain outside this inventory candidate: it grants neither `app_users` nor
`push_subscriptions` access. Do not add broad rights to bypass those deployment
gaps; login work is deferred and push delivery needs a separately scoped decision.

## Validation and remaining gates

**13 selected backend cases pass**: all four corrected task cases in
`runtime-task-final-v2.xml` (103.58 seconds), plus all nine profile, fixture-safety,
database-verifier and native staff/analytics cases from `runtime-task-final.xml`.
Those nine are selected from the earlier 13-case run described below; its failed
task case is retained as a diagnostic and excluded from successful evidence.
No failures, errors or skips occur in the selected final passing cases. This is
not a complete backend suite or GitHub CI result.

All **460 frontend tests in 55 suites** pass in `runtime-task-frontend.txt`
(159.705 seconds), including six new task cutover/error cases. The production
build passes in `runtime-task-build.txt` with unchanged PurchaseOrdersTab/StaffTab
hook warnings and a Node `fs.F_OK` deprecation warning. Backend multipart/FastAPI
deprecation warnings remain. Component tests and a build are not a live browser
or hosted Data API result.

The four corrected task cases cover owner-connection read/write retirement with
flags off, retained raw task rows and zero native assignments, populated physical
report/eight fact-fingerprint preservation, location/manager archive restrictions,
valid and invalid PIN behavior, typed list parent/line access, immutable prep-item
UPDATE rejection with SHARE locks, and preinstallation recurrence compatibility.
The native regressions exercise reviewed staff count/assignment/production and
saved analytical periods/reopening under the reduced candidate.

Preliminary evidence is retained: `runtime-task-reproduction` confirms the owner-read gap;
`runtime-task-candidate` passes three cases and fails an archive assertion that
incorrectly treated the existing list envelope as an array. The test is corrected
to check the real envelope and a seeded retained line; no API guard was relaxed.
`runtime-task-final` passes 12 of 13 cases in 880.56 seconds. Its remaining failure
exposes that the inherited list has a NULL track, rather than a permission error.
The corrected task fixture adds a separate typed list and preserves the original
unclassified row. The original attempt and all nine passing verifier/native
cases remain retained; only the four task cases need rerunning after that
fixture correction. No application or permission code changes for this repair.

The dedicated local PostgreSQL server is stopped after validation. All tests
use invented local fixtures. The role is NOLOGIN and selected with
SET ROLE on pool acquisition; owner connections are used only for the explicit
route-bypass probe and preinstallation compatibility. This is not actual hosted
LOGIN authentication, browser behavior or hosted recovery proof. Current changes
are committed locally and packaged with links/hashes to earlier evidence and the preserved original
40-path continuation. **Continue holding merges.**

Next: review unclassified list archive access and finish the remaining candidate
route/permission review, reconcile approved
hosted catalog differences against the frozen reference, and test an actual
ordinary runtime LOGIN/pool. Browser/Data API exposure, managed-platform recovery,
matched feature flags and sequential PR stack revalidation remain separate gates.
