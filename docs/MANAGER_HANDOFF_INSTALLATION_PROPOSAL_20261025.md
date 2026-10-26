# Manager handoff installation and acceptance proposal

October 25, 2026. **Local proposal only; inactive and not executable.**

PR72 is merged as `486767a1fd0a0223c97c9effa6fea53917d0db24`, tree-identical
to approved `5730b21a602a5e375738bf0fa38a884de051fc32` (tree
`fcdad3f38f89d3ebe0d34f6c1bcb37eb992f1edf`). All four
[approved-head CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40231545927)
and [merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40232202416)
passed separately. Render test deployment was approved; deployment completion,
current settings, database catalog and effective live roles were not inspected.

## Recommendation and present decision

Prepare **one feature-specific local installer/permission verifier and an explicit
encrypted recovery profile for this journal**, then rehearse them together on
fictional PostgreSQL. Review that work before requesting any hosted preflight.
Do not reopen S1 harness work or import Companion migrations to achieve this.
Existing personal Inventory authorization is the intended application path.

This proposal identifies the exact receiving delta and acceptance sequence. It is
not an exact executable hosted plan: private role/project bindings, a collision-free
delivery version, current writer/catalog evidence and a fresh recovery receipt must
be bound later. No current hosted state is inferred from local files or old windows.
The companion [source inventory](MANAGER_HANDOFF_INSTALLATION_SOURCE_PINS_20261025.json)
binds the accepted implementation and the relevant tooling that must be reviewed.
It is not an approval hash, executable packet or replacement for sealed par pins.
It records Git-blob and current worktree byte hashes separately; Windows checkout
line endings can differ. No raw-byte equivalence is inferred from a normalized
text comparison, and no historical sealed input is normalized or rewritten.

At this proposal's creation the owner approved preparation and JMax documentation
only. The owner subsequently approved the [bounded local tooling implementation
and fictional tests](MANAGER_HANDOFF_INSTALLER_LOCAL_ACCEPTANCE_20261025.md).
That local implementation does not authorize this live plan. Hosted execution,
service pauses, connection changes, credentials, grants, policies, timezone rows,
schema installation and feature activation remain held. No maintenance window is
active. No accounts, sample data or actual settings are created by this proposal.

## Findings that determine the order

| Finding in accepted source | Required treatment before live enablement |
| --- | --- |
| The migration starts with `CREATE SCHEMA operations`, has its own outer transaction, and adds no ledger row. | Refuse any existing namespace/name collision. A new adapter must preserve the raw migration, bind the precisely extracted transaction body, and atomically record the executed body in the reviewed migration ledger. Do not nest its `COMMIT` inside an installer transaction or use `IF NOT EXISTS` to accept partial installation. |
| `hosted_backup.SCHEMAS` lists six application/ledger schemas and excludes `operations`; its schema check refuses any unclassified application schema. | After H2 creates `operations`, the frozen hosted exporter refuses every later export, affecting six-schema-dependent par preparation, S2 backups and routine recovery. A reviewed/versioned **hosted** seven-schema export/restore adapter and its consumer transition are mandatory **before H2**, preserving the old six-schema reader. The new local-only profile is not that adapter. Doing P1 first alone does not protect later backups or waive this gate. Prefer a separate toolchain so frozen par source bytes remain valid; never classify the journal as managed or silently skip it. |
| PR72's restore test uses a whole fictional database dump, not the encrypted hosted exporter profile. | Keep its successful persistence proof, but do not claim encrypted journal recovery is already qualified. Rehearse an encrypted seven-schema export/restore with submitted/corrected notes and exact replay. |
| The historical runtime catalog profile omits `operations`; its account-table denial check does not qualify the new journal permissions. | Add a separate feature-local effective-role, RLS, ACL and guard assessment; do not silently widen historical native/par profiles or treat a prior pass as permission proof for this feature. |
| The route uses `db_pg.pool`; its actor resolver reads current `app_users` through `db_auxiliary.pool`. | Qualify the actual operational and accounts connections, not just named role metadata. Explicit separate auxiliary configuration is required; the generic unconfigured auxiliary fallback to the primary pool is not acceptable for this activation. Preserve existing login/notification duties. |
| `installed()` checks four RLS-enabled tables and six correctly wired triggers; it does not enforce non-owner runtime identity or fully validate ACLs/policies. | The future activation adapter must refuse privileged/current-owner/mismatched connections and require the independent manifest plus effective permissions. Do not describe PR72's route gate as a complete deployment verifier. |
| Capability flags are global, without a store-specific switch. | Propose one settings row for Bert's only. Other stores remain unavailable for this journal while settings are absent; owners may see the global tab and a held-state message. This is not a hidden per-store feature flag. Local tests cover the wider authority cases. |

No runtime/backup/installer changes above were made by the original documentation
work. The subsequent feature-local tools are recorded in the linked acceptance
record; the frozen backup/native/par sources remain unchanged.
The new recovery implementation must not monkeypatch global `SCHEMAS` or rewrite
sealed source pins. If a shared dependency really must change, return with its
exact effect on historical installers and a separately reviewed requalification
plan; unchanged JSON pins cannot make changed source bytes equivalent.

## Exact proposed database and configuration delta

### Structural installation

Only the accepted `migrations/20261025_manager_handoff_notes.sql` may supply the
structural body. Its raw SHA-256 is
`c36928e5520c18f96093c3e1eff21ca3287bc9e347d9a9dc8d9c0c21cb5f08f5`.
The independent structure reference SHA-256 is
`48d9d2a75f49aff531eef9d266375f4dd14a505bbc5cf5d74ff49240a7775826`.
The structure reference is comparison evidence, not an alternative installer.

| Object | Proposed change |
| --- | --- |
| `operations` | New private namespace, owned by the reviewed installer/schema owner; no runtime ownership or CREATE/delegation. |
| `operations.store_settings` | New store ID/timezone/revision configuration table, FK to existing `public.stores`. No seed in structural migration. |
| `operations.handoff_notes` | New unique store/date/track projection and immutable context; current-revision FK is deferred within the transaction. |
| `operations.handoff_note_revisions` | New append-only revision history, scoped to its header. |
| `operations.handoff_command_receipts` | New actor/store/request-key receipt journal referencing the accepted revision. |
| Three invoker trigger functions | `guard_handoff_header()`, `guard_handoff_history()`, `refuse_handoff_truncate()`, all in `operations`; fixed `pg_catalog` search path, no SECURITY DEFINER or callable privileged wrapper. |
| Six guards | Header/revision/receipt row guards plus one BEFORE TRUNCATE statement guard on each journal table. Require exact name/table/function/event wiring and enabled state. |
| RLS and client ACLs | Enable RLS on all four tables; preserve the migration's PUBLIC/client revocations. Explicit operational policies/grants are a separate reviewed payload below. |
| Existing migration ledger | Propose one new collision-free delivery row for this schema body in `supabase_migrations.schema_migrations`, with the exact executed SQL in `statements`. Bind version/name/body hash only after current ledger qualification. Preserve every existing row and ledger ACL. |

No changes to public catalog/recipe/unit identities, prep execution, counts,
purchases, Food Cost, taxes/fees, Toast jobs or Companion storage are proposed.
Do not apply all native/Companion SQL, reinstall par tables, renumber historical
migrations, extend the sealed 31-file installer or rewrite its source pins.

### Proposed effective permission delta

Bind the actual reviewed role names privately in the later executable packet.
**H3 requires R1-qualified restricted operational and accounts LOGINs, including
their actual running connection bindings. Until R1 is qualified, H3 is blocked.**
PR73's feature-local fictional qualification does not establish full native/account
permissions or today's live roles/connections; no new hosted inspection was done.
Creating a role, changing a password,
role attributes/membership/ownership or cutting over an app connection requires
its own explicit approval if the existing role cannot meet this matrix.

| Role class | Exact receiving access |
| --- | --- |
| Operational backend | `USAGE` on `operations`; `SELECT` on `store_settings`; `SELECT, INSERT, UPDATE` on `handoff_notes`; `SELECT, INSERT` on each of revisions and receipts. |
| Operational public dependency | Effective `public` USAGE and `SELECT(id, active)` on `public.stores`, with the existing qualified store-read policy. The existing application may already need broader store SELECT; this feature does not newly broaden it or remove unrelated required access. |
| Accounts/notification backend | No `operations` USAGE, object, function or column access. Existing `public.app_users` ID/role/locations reads and existing login/notification permissions remain under their separately reviewed profile. Do not narrow that login to the small fictional fixture. |
| PUBLIC, anonymous/browser and API service-role clients | No access to this private namespace, tables, columns, sequences or trigger functions. Verify effective access, inherited grants, default ACL effects and Data API exposure; do not expose `operations` in hosted API settings. |
| Installer/schema owner | Holds only reviewed administrative authority for the approved window. Never used by the running handoff route. |

For each receiving table propose one policy named `handoff_backend_v1`,
`AS PERMISSIVE FOR ALL TO <privately-bound operational role> USING (true)
WITH CHECK (true)`, matching the manifest's semantics. The same policy name is
scoped to each table. Table verbs still limit writes; these server-only policies
are not browser/store isolation policies. FastAPI resolves the current personal
subject/role/location and includes the store in each command/read. Reject extra
applicable PUBLIC, inherited, permissive or restrictive policies. Inspect owners,
memberships, grant options and column ACLs independently of RLS.

No DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN, schema CREATE, grant option,
sequence privilege or direct EXECUTE on the three trigger functions is proposed
for the operational runtime. Runtime must not own these objects or be superuser,
BYPASSRLS or able to assume a privileged role. Trigger execution under the
restricted role must pass the fictional and real connection checks; do not add
blanket function EXECUTE if a dependency fails.

The schema/settings/policy payloads must be separately enumerated and hashed.
If combined in one database transaction, every executed statement must also be
represented in the ledger/evidence contract; do not hide grants or a settings
INSERT behind a ledger receipt for the schema-only body. A version/name for any
additional ledger entry remains unallocated until that payload is implemented
and reviewed. Thus one schema ledger row is proposed, not a claim that it records
every possible future activation statement.

### First settings row and flags

Proposed row: `store_id='berts'`, `timezone_name='America/New_York'`, `revision=1`.
This timezone matches the fictional fixture and is a proposal for owner confirmation,
not current store metadata proof. Require existing active Bert's identity and an
absent settings row. Conflict or an already-used date/track holds the plan; never
upsert or overwrite existing configuration or a shared note. Seed no Rudd's/Papa
row and no account/roster/password/PIN/note as part of installation.

Accepted source defaults both `MANAGER_HANDOFF_NOTES_ENABLED` and
`REACT_APP_MANAGER_HANDOFF_NOTES` off; live flag values were not inspected.
Require both off/unset before qualifying this proposal. Later activation would
set only these two flags to `true`,
with existing PostgreSQL/signing/account configuration confirmed and unchanged.
The browser flag requires a frontend build/deployment; it is not a runtime toggle.
Build/test source must stay pinned. Enable the backend only after database and
actual-role checks pass, then publish the matching frontend. The transient old
client/new backend interval must have no test writes. Do not claim atomic activation.
Disabling reverses that exposure: server off first, then matching client rebuild.
Any redeployment/settings operation needs explicit approval; do not trigger it now.

## Ordered execution proposal and approval gates

The proposed hosted order is **S2a -> P1 (if still planned with six-schema tools)
-> reviewed hosted seven-schema adapter -> H0-H3**. S2a remains private by label,
requires its own consumer evidence and approval, and precedes this plan's future
administrative maintenance windows. This ordering does not authorize credentials,
restart the optional S1 harness or block continued local review/PR merge. It does
not rewrite a frozen par installer predicate. Any remaining six-schema-dependent
backup consumers must transition to a reviewed supported path, or be explicitly
held, before H2; completing P1 alone is not an alternative to the adapter gate.
Local R1 design can continue alongside this sequence, but actual R1 qualification
is a hard prerequisite of H3.

| Gate | Proposed work | Completion evidence / stop rule |
| --- | --- | --- |
| L0: current local proposal | Pin accepted sources, identify exact delta and missing tools, update JMax. | This document and source inventory only. No application code, SQL execution or hosted checks. |
| L1: separate local implementation approval | Implement the small feature installer/permission verifier, seven-schema encrypted recovery profile and activation role refusal; retain legacy archive compatibility and sealed par profiles. | Independent review, tests, fictional restricted LOGIN (not only SET ROLE), negative ACL/RLS/guard cases, encrypted restore with replay, failure/unknown-commit rehearsal, measured budgets and clean owned cleanup. Prompt before a new draft PR push. |
| Hosted recovery prerequisite: mandatory before H2 | Separately implement/review a versioned hosted export/restore adapter supporting the pre-install six-schema and post-install seven-schema profiles without weakening legacy archive validation. Rehearse supported managed dependencies and new journal recovery on fictional targets; bind consumer/runbook transition and exact installed-source compatibility. | The loopback-only adapter does not satisfy this gate. No H2 approval packet may be activated without this reviewed path and a post-install recovery plan; routine/par/S2 backup consumers must not be left on the refusing six-schema exporter. No hosted code or execution is implemented/approved by PR73. |
| H0: separately approved read-only preflight | Inspect current accepted deployments, actual primary/auxiliary role/project/TLS binding, catalog/schema/name/ledger collisions, resources and exact writers. | Masked evidence only; no role repair, settings writes, grants, activation or service pause. Bind the changed-source/backup/writer dependencies; any stale result must be refreshed. |
| H1: separately approved preparation window | Fresh writer confirmation and no-other-writes/no-merges commitment; capture then pause only approved writers; strict drain; fresh encrypted export and disposable local restore. | Restore proof covers the actual pre-install baseline. Fresh executable packet binds source/body hashes, role names, writer states, ledger/config baseline, backup and restoration deadline. Restore writers and close if a guard fails. |
| H2: exact-plan application approval | After the mandatory hosted seven-schema adapter/consumer gate, and under the still-valid drained baseline, apply only the reviewed transaction/payloads and ledger entries. | Recheck all guards immediately before execution; lock timeout 5 s and DDL statement ceiling 30 s are proposed limits to qualify locally, not silently increased permissions. All preexisting data/ledger/ACL invariants match before commit. Unknown commit acknowledgement means read-only reconciliation, never blind retry. |
| H3: separately approved activation and acceptance | Require completed R1 qualification of actual restricted operational and accounts LOGINs and running connection bindings, plus post-install recovery; approve flag/build sequencing and the fixed fictional acceptance scope below. | **Blocked until R1 is qualified.** Schema installation and local feature-only role tests do not satisfy it. Successful owner cases are not manager/staff or full production release acceptance. Close with flags off unless keeping them on was explicitly approved. |

H1/H2 may be proposed for one maintenance window after L1 timing results. Do not
reuse an expired window or name a guaranteed duration now. Budget the full existing
backup/restore limits, local memory checks and a fixed writer-restoration reserve
before starting. Capture original API state/commit and exact Toast identities,
schedule/role/command fingerprints. Last known writers were `jaymax-api` and Toast
jobs 3/4, with Companion local-only; this is historical, not fresh confirmation.
Never terminate Supabase platform sessions, silently pause another writer, change
job schedules or force a deployment to make a guard pass.

The local memory gate remains at least 1 GiB and 15% free before disposable
PostgreSQL; no local database is started by this proposal. Do not lower existing
tool/resource guards or close unrelated applications. Retain current Render and
Supabase app connection standards; no IPv4 purchase, hosting move or general
identity migration is bundled into this feature.

## Acceptance proposal: Bert's / October 25, 2026 / Bulk Prep

Use date `2026-10-25`, track `bulk`, canonical store `berts`, and clearly labelled
`TEST ONLY MANAGER HANDOFF 20261025` summary/next-shift text. This is intentionally
historical if executed later. Server creation/submission/correction times remain
actual timestamps. Require no existing note for that tuple before approval. If
one exists, stop and obtain approval for a different tuple; never edit or delete it.

The later packet must allocate and seal the note UUID, four command UUIDs/body
fingerprints, existing authorized actor ID and expected settings revision. No
password/token/PIN is placed in a public document. Only normal owner sign-in is
assumed available; the account holder handles credentials. No account creation,
role/location change or staff PIN activity is needed for this first profile.

### Fixed directed API profile for later approval

Propose at most **22 directed handoff API requests**, one existing-owner personal
sign-in if necessary, and **four newly accepted commands**. Ordinary frontend
asset/background reads must be enumerated/bounded in the later browser packet;
they are not authorized by this document. Unused calls cannot be reassigned.
Unexpected errors stop the sequence rather than authorize exploratory retries.
K1–K4 refer to sealed request keys, not fabricated values to paste into production.

| Step | Directed request / expected result |
| --- | --- |
| C01 | GET day/track: no current note; exact Bert's timezone/settings revision and authorized actor confirmed. |
| C02 | Create draft, K1, If-Match 0: revision 1, draft; one header, revision and receipt. |
| C03 | GET same day after reload: revision 1 and original text persist. |
| C04 | Save draft, K2, If-Match 1: revision 2, changed summary; original context unchanged. |
| C05 | GET same day: revision 2 persists. |
| C06 | Submit the already-saved content, K3, If-Match 2: revision 3 submitted; first-submit time recorded. |
| C07 | GET after reload: submitted revision 3. |
| C08 | Correct, K4, If-Match 3, explicit TEST ONLY reason: revision 4; first-submit time/context unchanged. |
| C09 | GET history: revisions 1–4/actions/actors/reasons/timestamps match; no hidden stock effect. |
| C10 | POST status for original K1/body/If-Match 0: saved accepted revision 1 and current revision 4. Status is a read, not a new command. |
| C11 | POST original K1/body/If-Match 0 exactly: replayed true, accepted 1/current 4; no extra revision/receipt. |
| C12 | POST changed content under K1: 409; all journal rows unchanged. |
| C13 | POST stale expected revision 1 with a new held test key: 409; current 4 unchanged. |
| C14 | GET history for an unallocated valid UUID within Bert's: 404, no foreign note content. |
| C15 | GET Rudd's day as owner: held for missing settings (503 if the proposed first-store state is exact); no other-store configuration is seeded. This proves fail-closed configuration, not manager cross-store authorization. |
| C16 | GET Bert's day without Bearer login: 401 and no note content. |
| C17 | POST otherwise-valid command without If-Match: 428, no journal write. |
| C18 | POST new draft dated tomorrow in the reviewed store timezone: 422, no row or receipt. |
| C19 | GET Bert's final day: current revision 4 and final text match. |
| C20 | GET final history: exactly four revisions remain. |
| C21 | POST status with a fresh unknown key and valid original-shaped request: unconfirmed, current 4; no new row. Unconfirmed is not proof an arbitrary in-flight command cannot still commit. |
| C22 | After approved closeout disables the server capability, one GET refuses 503. Then restore the client flag to matching off through the approved build sequence. |

Final acceptance state for this empty tuple: exactly one header, four revisions,
four receipts, no deleted evidence. Readiness labels report a manager's note only.
Counts, production/task completion, purchases, Track 1 values, pars and sales must
not be changed by these commands. Audit/session records created by normal login
or request middleware are expected control-plane effects, not note stock writes.
Compare bounded scoped stock/accounting facts before/after; unexplained concurrent
writer drift makes that comparison inconclusive and must not be waived.

Cross-store manager denial, staff denial, role/account revocation, settings races,
storage failure, after-commit dropped response and competing manager requests
remain **local fictional acceptance first**. Only label them hosted-passed after
the relevant account holder/transport controls and exact extra scope are approved.
Do not mutate real accounts or grant test permissions just to complete this profile.
The personal browser uses sessionStorage recovery, not a guaranteed shared-device
offline cache; closing/clearing the browser may lose recovery. A real network-drop
test needs its own controlled transport proposal; C10/C11 are saved-receipt tests,
not proof an actual dropped response occurred.

## Recovery and closeout

1. Before commit failure: rollback the new transaction; verify no receiving
   objects/rows/ledger residue, restore captured writer states, close owned clients.
2. Lost commit acknowledgement: mark outcome UNKNOWN. Keep the feature disabled;
   compare exact receiving catalog/ledger/settings/ACL facts read-only under the
   remaining approved window. Do not rerun CREATE SCHEMA or issue another key.
3. After a confirmed commit, prefer disable-and-investigate with journal/history
   retained. Do not DROP SCHEMA, delete revisions/receipts or restore a whole
   database over newer application writes under this plan. Destructive rollback
   or operational restore needs separate approval.
4. Encrypted seven-schema restore must reproduce notes, history, receipts,
   functions, six guards, RLS/policies, ownership/ACL intent and exact replay in an
   owned disposable PostgreSQL target. NOLOGIN stubs are not proof of real password
   or login recovery; verify that boundary explicitly. Managed Auth/Storage/cron/
   Vault recovery remains outside this application backup claim.
5. Restoring an older app commit alone does not reverse database installation.
   Keep flags off before any separately approved app rollback. Restore writers to
   captured states by the hard deadline even if feature acceptance is incomplete;
   do not leave API/Toast paused while waiting for another decision.
6. Record approved scope, actual start/end, source/body/catalog/role bindings,
   control restorations, final flags, journal counts, cleanup and all unrun cases.
   Update JMax with local, CI, merge, deployment, installation and live-acceptance
   evidence labelled separately. No operational-release or full Companion-parity
   claim follows from this narrow manager-note acceptance.

## Proposed next authorization

Local implementation/rehearsal of the bounded receiving installer, effective-role
check and journal-aware encrypted recovery profile has since been separately
authorized. Finish its local evidence and prompt before a new draft PR push.
Keep real credentials, grants, schema, hosted execution and connection/flag
changes held. Independent review/CI/merge and a later hosted-adapter proposal are
separate gates; local tools must not be pointed at Supabase.
