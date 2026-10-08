# Manager definitions, roster and retained history

Later task retirement and archive permissions are covered by the
[task cutover checkpoint](RUNTIME_TASK_CUTOVER_CHECKPOINT.md). This document
preserves the earlier manager evidence and permission matrix as a historical
checkpoint.

October 8, 2026. This checkpoint extends the local runtime-permission candidate
from `a85ef65f156e02d5b344867b52c479566386056e`. No hosted query, grant/policy change,
real invoice import, feature-flag file change, push, merge or publication occurs
in this step. Track 1 remains purchased physical inventory with explicit count
values and received-date purchases; prep and sales explain that accounting track.

## Findings and changes

Roster creation accepted `active=false` but always inserted `TRUE`. The local
route reproduction confirmed the wrong active state. Creation now persists the
submitted boolean. Update/delete routes accept typed UUID path parameters so
malformed IDs receive validation errors before reaching SQL. Roster identifiers
remain stable through edits and deactivation. Referenced identities must be
deactivated rather than deleted; native assignment foreign keys remain intact.
This does not redesign login, shared PINs or the roster's role labels.

The retention proof here covers native UUID task assignments. Legacy
`public.staff_tasks.assigned_to` and `completed_by` are text fields, not roster
foreign keys. Those legacy task routes have no candidate grants and still need
separate mapping/retirement review; do not infer identity from matching names.

Recipe deletion checks seven retained operating references before removing the
definition: count lines, prep items, prep-list lines, prep logs, recipe stock,
prep overrides and par recommendations. The old candidate could not read four
of those tables. A local history probe failed on `prep_list_lines`; source review
confirmed the deletion guard needs all four reads. Item deletion already retires
the store item through UPDATE and retains its identity; it needs no new DELETE.

The existing unused-recipe and unused-roster deletion commands also need narrow
DELETE permission. The candidate now adds only the following rights:

| Object | Added permission | Purpose |
| --- | --- | --- |
| `public.prep_list_lines` | SELECT | Retained prep-list reference check. |
| `public.prep_recipe_stock` | SELECT | Retained stock reference check. |
| `public.prep_overrides` | SELECT | Retained planning override check. |
| `public.par_recommendations` | SELECT | Retained recommendation reference check. |
| `public.dishes` | DELETE | Remove an unused definition after graph/history/revision checks. |
| `public.staff_members` | DELETE | Remove an unused roster identity after history checks. |

These are dedicated backend-role grants and policies, not grants to the database
PUBLIC role or to browser/employee database clients. The candidate now names
25 public-schema tables. Policies permit the trusted server to operate across
stores; application manager and location gates remain necessary. Native journal
DELETE, TRUNCATE, DDL, ownership, grant delegation and RLS bypass remain excluded.
The six preserved native capture/dictionary tables remain SELECT only. No native
INSERT/UPDATE/EXECUTE permissions changed in this checkpoint.

Unused recipe deletion retains the current API's hard-delete behavior. Its seven
public history checks are application safeguards, not universal database
immutability against arbitrary SQL by the backend role. Direct SQL through that
role can bypass those application checks. Native journals have their separate
database guards and denied deletion rights. Universal soft retirement or database-enforced
definition retention would require a separately reviewed schema/UI change.

The independent catalog reference's **94 function contracts and 123 relation
fingerprints remain unchanged**, as do all source SQL hashes. Only its deliberately
reviewed permission-matrix pin changes from
`a31366bdd6fd2094db36e1101ec86b231865d0c3ca33862e4e765758efc468a3` to
`f2e134445020d7464ef90f4a156e1c26a941d92803bdb299b8b985726b10eae8`.
The target database did not supply a replacement baseline.

## Local validation

All eight corrected manager cases pass in `runtime-manager-final-v2.xml`
(259.01 seconds; seven retained-reference subtests also pass). All seven selected
profile, fixture-safety and database verifier cases pass in
`runtime-manager-verifier.xml` (439.27 seconds). These include read-only row/catalog
preservation and holds on missing/excessive rights, column ACLs, memberships,
grant options, ownership, function/trigger changes, RLS and policy drift.
All seven selected existing workflow regressions pass in
`runtime-manager-workflow-regression.xml` (3,959.77 seconds). The run spans the
disconnect/reconnect interval; its full elapsed time and output are retained.
A local read-only activity sample after reconnect showed responsive ClientRead
sessions with no sampled database lock wait. No uninterrupted-run or cause claim
is made from that sample.

Those regressions cover physical corrections/period replay, staff count and
production, order receiving, separate planning-price adoption, supplier contacts,
container-waste correction and prep analytics/reopening. Expected Track 1 reports
and facts remain intact, including the separate physical fixture's $60 earlier/
$21 final reports and staff fixture's $55 report.

**22 selected local checks pass**, with no failures, errors or skips in those
three final evidence sets. The two-case composition probe is retained separately
and is not counted again. This is not a full-suite, GitHub CI, actual hosted LOGIN,
browser/Data API or managed-platform recovery result. Existing multipart/FastAPI
deprecation warnings remain. The dedicated test server is stopped after the run.

The eight new manager cases exercise:

- Recipe creation, ingredient/price edits and unused deletion, with missing/stale
  revisions and wrong-location IDs held; physical reports and eight accounting
  fact fingerprints remain unchanged.
- Each of the seven retained reference types through single deletion, granular
  changes and full replacement. Replacement keeps the other six recipes so the
  intended reference is checked independently; definitions, references, revision
  and accounting fingerprints must survive rejection.
- Dependent prep-unit validation and rollback; concurrent edits with one accepted
  revision and one conflict; staff/readonly/wrong-location manager writes held.
- An invented late DELETE trigger failure after upsert/line writes, proving the
  entire transaction and revision roll back. Only the local fixture owner installs
  that trigger; it is removed before the clean permission verifier runs.
- Store-specific supplier price/provenance/unit-profile preservation and item
  retirement, keeping the other location and physical accounting unchanged.
- Inactive creation, UUID validation, edit/delete of an unused identity, role/store
  denials, retained assignment history after deactivation, and foreign-key rejection
  of direct deletion of a referenced identity.
- Simultaneous assignment and roster deletion. Either assignment wins and deletion
  conflicts, or deletion wins and assignment is held; no orphan is permitted.

All database fixtures use the full reviewed 29-migration chain and the candidate
nonowner role on invented UUID-named loopback PostgreSQL 17.11 databases. They use
administrator connections with SET ROLE on acquisition and an invented NOLOGIN
role; this is not actual hosted LOGIN/pool authentication evidence. The menu,
catalog and roster success requests use scoped manager tokens. Native assignment
requests use an owner token; denial checks include a manager scoped to the other
store. This does not establish every manager-facing route or a full suite/CI result.

Retained diagnostics are separate from successful evidence:

- `runtime-manager-reproduction`: two failures. The menu test reused a bulk
  replacement that correctly rejected preseeded retained history; that was a test
  assumption error. Roster creation returned active=true for active=false, a real
  application defect.
- `runtime-manager-permission-reproduction`: one failure on the local history
  SELECT probe for `prep_list_lines` under the old candidate.
- `runtime-manager-candidate`: eight setup holds on permission-matrix drift. The
  pin-update command lacked the test dependency path and failed before changing
  the pin; the runner proceeded against the old pin. The environment was corrected
  and only the matrix pin deliberately updated. No schema/function reference was
  relaxed or regenerated; earlier attempts are not counted as passing tests.
- `runtime-manager-final`: six cases passed and two failed. Empty stale replacement
  met the retained-history guard before its revision check. A reused catalog helper
  assumed fixed revision numbers after physical setup. The tests now retain all
  seeded definitions for the stale-only check and read/use current returned catalog
  revisions. The two targeted cases pass in `runtime-manager-composition-probe`;
  no application guard was relaxed to obtain that result. The complete corrected
  manager run is recorded separately as `runtime-manager-final-v2`.

## Review handoff and remaining work

The chained review package includes this checkpoint, committed changes, exact
matrix/reference, test output/XML and its own byte/hash manifest. Packaging checks
the protected original continuation's 40 pending paths against the preserved
snapshot, including the binary tracked patch and untracked source bytes. Prior
packages and diagnostics remain separate. Credentials, private dumps and real
invoice source files are excluded.

Review the remaining routes and unused privileges before a hosted permissions
trial. Then reconcile hosted additions with an approved reference and prove a
separately authenticated backend runtime LOGIN/pool, with original-row/ledger
reconciliation. Browser/Data API exposure, managed Auth/Storage/Vault recovery,
matched frontend/backend flags and publication/review remain open. The independent
deployment owner-access hold remains. **Continue holding merges.**
