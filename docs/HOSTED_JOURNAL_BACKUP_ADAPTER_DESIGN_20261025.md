# Hosted journal backup adapter: local design proposal

October 25, 2026. **Design only. No implementation, network check or live change.**

Accepted local baseline: PR73 merge `afe4891670a2250ce10ee27a4ce5eae1252d5329`,
tree-identical to reviewed `7d0ed3be4faf9be90ead99d091d7167b401ff25f`
(tree `2343aa85c72d3d6b130106b614ff499bed4acc22`).
[Reviewed-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40249207186)
and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40249573863)
each passed all four checks. Those are PR73 implementation receipts, not tests of
an adapter proposed here. Current Render, Supabase, credentials and writers have
not been inspected. Existing holds remain; no maintenance window is active.

## Recommendation

Add a **separate profile-aware backup adapter and manual CLI**. Keep the frozen
six-schema engine/reader and PR73's loopback/managed-marker protections unchanged.
Make the schema profile explicit, version the seven-schema envelope/receipt, and
qualify the consuming maintenance workflow before it accepts that receipt.

One bounded local implementation slice should deliver the profile/manifest rules,
seven-schema export and isolated restore, failure/cleanup controls, a typed receipt
validator and fictional tests. It must have no automatic hosted activation or
application startup hook. Return for review/push approval before publishing it.
Any real export, local restore of hosted data, service controls or installation
still requires its own exact approved packet. This design is not that packet.

### Why a new adapter is necessary

| Accepted source evidence | Consequence for this design |
| --- | --- |
| `hosted_backup.SCHEMAS` is fixed to six application/ledger schemas; export refuses unclassified schemas. | Installing `operations` makes the frozen exporter refuse subsequent exports. A supported hosted seven-schema path and consumer transition are mandatory before H2. Completing P1 first does not protect later routine or S2/par recovery. |
| `fingerprint`, `fingerprint_batched`, `dependencies`, `open_backup` and `verify_restore` use that fixed scope. | A wrapper around the old export call or a renamed manifest cannot produce a seven-schema proof. New scope-aware paths are required; no monkeypatch, AST/source rewrite or temporary reassignment of global `SCHEMAS`. |
| PR73's local recovery code refuses managed schemas/roles and any non-loopback source. | Keep those protections. Do not add an `allow_hosted` bypass or point that prototype at Supabase. Hosted routing and owned restore/bootstrap require separate policies. |
| Par/index backup bindings validate fresh manifest, restore, migration and source/ledger fingerprints; the calibration packet pins six-schema commands/scopes. | A new archive alone does not update those consumers. New profile-aware receipt/consumer contracts must be reviewed; frozen plans must not be silently rebased or handed downgraded evidence. |
| The legacy restorer preserves ownership/ACL intent and requires separately prepared roles/dependencies; PR73 used `--no-owner` with matching ownership facts. | Declare the new restore mode and required owner/role provisioning explicitly. Neither existing result proves password reconstruction, arbitrary cross-cluster recovery or full Supabase recovery. |

## Proposed files and preserved boundaries

Names below are proposed, not files already implemented:

| New file | Responsibility |
| --- | --- |
| `backend/application_backup_profiles.py` | Immutable schema/format/limit specifications; strict profile selection and envelope dispatch. No configuration reads or network. |
| `backend/hosted_journal_backup.py` | Seven-schema discovery, dependency assessment, snapshot export, catalog/row/sequence comparison, authenticated envelope and isolated restore. Explicit profile context in each scope-sensitive function. |
| `backend/hosted_journal_backup_cli.py` | Manual opt-in orchestration; verified private configuration, target/approval/source bindings, custody and safe diagnostics. No URL/password command argument, automatic retry or live default. |
| `backend/journal_backup_receipts.py` | Independent receipt/profile/source/window/digest validation for newly reviewed consumers. No SQL apply or reinterpretation of old packets. |
| `backend/tests/test_hosted_journal_backup.py` and `test_journal_backup_receipts.py` | Fictional offline/owned-PostgreSQL tests, fault injection and compatibility oracles. Hosted-looking strings are never real network test targets. |

Preserve the bytes of `hosted_backup.py`, `hosted_backup_cli.py`, native/par
installers, their source pins and PR73's local adapter. Prefer the new engine over
changing a frozen shared helper. If a shared dependency truly needs modification,
return with the exact impact/requalification plan instead of editing old pins.
No FastAPI route, frontend, feature flag, role, grant, policy, timezone, schema,
Toast schedule, Render service setting or credential change belongs to this slice.

Reuse only demonstrably scope-independent reviewed helpers, such as identifier
quoting, private-directory verification, cleanup error preservation, target/TLS
validation and owned subprocess control. The existing relation-fingerprint helper
can be reused with an explicitly supplied relation inventory if its same-snapshot
oracle tests pass. Its export diagnostic ContextVar, if used, needs a per-call
token and reset on every exit; that is not permission to change schema globals.
Do not refactor the frozen engine merely to share code. New scope-aware catalog,
dependency, envelope and restore paths remain independent and source-pinned.

## Explicit profiles and archive compatibility

| Profile | Required schema set, in canonical order | Format and reader |
| --- | --- | --- |
| `legacy6` | `public`, `purchasing`, `actual_inventory`, `prep_inventory`, `integrations`, `supabase_migrations` | Existing `jaymax-encrypted-application-backup-v1`; delegate validation to the unchanged legacy reader. A new CLI may dispatch to the unchanged legacy exporter when its target/scope is valid. |
| `receiving7` | The same six plus `operations` | Proposed `jaymax-encrypted-application-backup-v2` with an explicit `receiving7` profile and profile digest; new strict reader and restore path. The old reader must continue to refuse it. |

The operator chooses the expected profile **before** connecting. Discovery only
checks that choice. Never downgrade `receiving7` to `legacy6` because `operations`
is missing, silently omit it because it is empty, or mark it as a provider-managed
schema. Requesting `legacy6` on a source containing `operations` must hold. Extra
unclassified application schemas hold; future scheduling/analytics namespaces
need a reviewed profile extension rather than an all-schema wildcard.

Every table/column in an included application namespace is copied, including raw
vendor source bytes, fields without UI mappings, decimal values, receipts,
immutable count/prep/correction history and the migration ledger. Track 1 remains
purchased-item counts plus received purchases minus closing counts, with explicit
count values and taxes/fees separate. Restore is not a synchronization writer and
must never feed recovered rows back into the hosted app.

Captured catalog/row fingerprints prove fidelity to the captured source, not
deployment correctness or permission approval. A backup must not silently omit
a new column/table merely because a screen does not use it. H2/H3 installation
qualification still separately compares the reviewed receiving manifest, guards,
permissions and actual runtime roles.

### Proposed authenticated v2 manifest

Encrypt the complete archive and private manifest using the existing reviewed
authenticated-encryption approach. A cleartext status/header must contain no
project, role, employee, SQL, path, DSN or credential detail. Reject duplicate JSON
keys, unsupported versions/algorithms, nonfinite values and malformed bounds.

Required fields should bind:

- Exact format, profile ID, ordered schemas and independently expected profile digest.
- Expected source/project binding held privately, database/major/patch metadata,
  maintenance transport/session proof and capture time. No password/token hashes.
- Accepted toolchain/source hashes and complete migration-file/ledger fingerprints.
- All scoped relation data/count/sequence and catalog/ACL/default-ACL fingerprints,
  retaining the current canonical row algorithm and portable comparison ordering.
- Database/schema ownership and required role names/attributes/memberships without
  password hashes, plus the independently reviewed dependency bootstrap contract.
- Archive digest/size and supported limits; no successful partial-scope flag.

Public receipts carry only minimized identifiers, profile/source/digest bindings,
counts, timings, phase outcomes and safe error classes/SQLSTATE. Actual data,
definitions and private bindings remain encrypted or in the protected owner record.
An archive's self-reported profile/facts cannot replace the caller's independently
expected profile, source binding and artifact digest.

## Export state machine

1. **Inactive by default.** Require a fresh explicit execution packet, its verified
   hash/scope/deadline, an expected profile and protected existing maintenance
   configuration. No import-time dotenv/network activity, application-URL fallback
   or automatic attempt. A local fictional receipt cannot activate hosted export.
2. Validate private-file ACL/custody and the exact expected project/endpoint before
   connection. First receiving implementation should use the existing opt-in native
   IPv6/TLS maintenance path. Keep Render/app pooler settings unchanged; no paid
   IPv4 purchase or hosting move. No silent transport fallback. A later alternate
   transport needs its own reviewed binding and tests.
3. Establish one bounded owned connection. Verify effective database/login/session
   identity, TLS certificate/hostname verification, read-only settings and client/
   server limits. Existing owner credentials are not rotated, created or switched
   by this adapter; S2a prerequisites must be dealt with separately before an
   administrative hosted window. Close/hold on any target/binding mismatch.
4. Validate the explicit schema profile and current out-of-scope dependencies.
   Provider namespace presence is a classification fact, not permission to copy
   provider data or execute its definitions. Hold unknown dependencies.
5. Capture all application facts and the `pg_dump` archive in **one repeatable-read,
   read-only snapshot**, including all seven namespaces for `receiving7`. Do not
   append a second uncoordinated operations-only dump. Normalize deparser/session
   settings and use the existing canonical row-hash algorithm/portable ACL ordering.
   A role unable to read complete RLS-protected scope must hold rather than export
   a policy-filtered subset and call it complete.
6. Recheck sequence and relevant global role/configuration facts. These are not
   assumed snapshot-atomic with all application rows. Installation qualification
   needs a fresh approved writer-drained window; routine snapshots must disclose
   their consistency limits and hold on observed sequence/configuration drift.
7. Encrypt into a fresh protected partial artifact, authenticate/read back its
   manifest/archive digest, close the snapshot, connection and owned subprocesses,
   clean plaintext partials, and only then atomically publish the final filename.
   Preserve the first failure and bounded cleanup categories; uncertain publication
   is not a verified backup. Retained partial/key state is reported safely.
8. Emit `exported_not_restore_verified` with profile/source/artifact bindings. A
   separate successful isolated restore receipt is necessary for installation
   recovery qualification. No export result may claim operational release.

Keep existing ceilings: connection 20 s, command 60 s, subprocess 240 s, total
export at most 600 s, owned cleanup 5 s, archive 64 MiB and envelope 192 MiB.
Do not increase a server/session limit or tool timeout silently. Preserve tighter
phase/query limits where applicable. Oversize data holds pending a separately
reviewed streaming design; no plaintext fallback, truncation or dropped columns.
Local PostgreSQL rehearsals retain the 1 GiB/15-percent start gate; design work
today starts no server and needs no new memory threshold.

## Managed dependencies and isolated restore

Managed recovery remains separate. `auth`, Storage objects, Vault, cron schedules,
Realtime/platform configuration, global role secrets and provider recovery keys
are not included in an application-scope success claim.

The adapter must assess dependencies from **all seven** namespaces, including
relations, types, defaults, constraints, policies, rewrites, triggers and functions.
Approved dependency metadata/definitions need independent reviewed bindings; do
not accept an arbitrary current function merely because its name looks familiar.

Preserve the existing narrowly supported extension families (`uuid-ossp`, `pgcrypto`,
`pg_trgm`, `citext`, `btree_gist`, `btree_gin`) only at reviewed, locally available
versions and the approved extension namespace. Auth helper support is limited to
reviewed zero-argument SQL/non-definer `uid`, `role`, `jwt` signatures/definitions.
Unknown signatures, changed approved definitions, missing extension versions or
unclassified cross-schema references hold. This is dependency bootstrap for
application objects, not restoration of the Auth service or all managed schemas.

Restore sequence:

1. Authenticate the envelope, expected project/profile/source/toolchain/artifact
   bindings and complete scope **before any restore SQL**. Reject a seven-schema
   envelope offered as v1/six-schema proof. Never reinterpret PR73's local-only
   rehearsal format as a hosted recovery artifact.
2. Require a fresh UUID-named owned loopback recovery database and verified dedicated
   test cluster/control binding. Refuse remote/control/source/nonempty targets,
   including existing functions, types, schemas or default ACLs. Names alone are
   not cluster attestation. Capture original local role/database inventory.
3. Specify ownership mode in the manifest/receipt. Prefer ownership-preserving
   restore with the same-named database/schema owner roles prepared separately as
   reviewed local stubs. Do not silently add `--no-owner` or remap owners to force
   equality. If an explicit no-owner mode is proposed later, independently bind
   that transformation and compare against its approved expectation.
4. Prepare only approved missing NOLOGIN role/dependency stubs on the dedicated
   disposable server. Never copy passwords, enable real logins, assume source
   superuser/BYPASSRLS attributes, alter an unrelated existing role or provision
   roles on the hosted project. Role-password and managed-service reconstruction
   remain unverified. A required role collision/incompatible owner holds.
5. Bootstrap only the reviewed local extension/helper dependencies after the empty
   target gate. Those expected `auth`/extension stubs are permitted in this new
   owned restore context; do not disable PR73's managed-marker refusal to obtain
   that behavior. Its local tools remain unchanged and may legitimately refuse a
   cluster that now contains such stubs.
6. Restore application objects transactionally with stop-on-error, preserving
   grants/policies and original source data. A failed disposable restore is held
   and cleaned as an owned test target, never exposed to application users.
7. Compare complete seven-schema data/catalog/sequence/ACL/ownership facts, raw
   invoice bytes and ledger histories. Check operations FKs, all six guards,
   correction history and exact old-key replay against the newer record using
   a separately verified local connection context. Do not use disabled-guard
   shortcuts or claim R1 LOGIN qualification from a NOLOGIN/SET ROLE fixture.
8. Emit a typed verified-application-restore receipt. Clean only owned objects,
   partial files and temporary stubs, restore the captured local inventory and
   stop the owned server. Never DROP a hosted schema, overwrite operational data
   or assume that an older app deployment reverses a database installation.

Cross-cluster application recovery with pre-provisioned owner/role stubs must be
tested explicitly before it is claimed. Same-cluster fictional replay is useful
but insufficient. Neither path proves real password restoration or full hosted
service recovery. Actual restricted operational/accounts LOGIN use remains R1.

## Consumer transition: part of the H2 gate

| Consumer | Current contract | Proposed transition / hold |
| --- | --- | --- |
| Manual backup workflow and CLI | Frozen six-schema export/reader and explicit direct-maintenance option. | New manual CLI selects the expected profile. Preserve v1 archive validation unchanged; use v2 receipt for seven-schema recovery. Never auto-detect/downgrade scope. |
| P1/par qualification packet | `par_qualification_packet.py` pins old source/commands; `hosted_reviewed_pars.py` validates archive/restore/migration facts. | Finish the retained six-schema workflow before H2, or create a newly reviewed profile-aware consumer with new source/window bindings. Do not rewrite old pins or hand v2 facts to a frozen plan. Any remaining six-only step stays held post-H2. |
| Source-index/other additive maintenance | `hosted_additive_index.py` also validates the old backup/restore binding. | Classify active/manual use. A post-H2 invocation requires a reviewed v2 consumer; keep unused commands explicitly held. No index SQL change belongs to this design. |
| S2 / R1 recovery packets | Fresh credential/consumer and recovery evidence are independent approval requirements. | Select the actual installed schema profile in the new packet. No credential cutover may rely on an older six-schema artifact that omits an installed journal. |
| Read-only calibration | `read_only_probe.py` pins an application/backup scope without operations. | Retain its scoped historical meaning. Introduce a newly reviewed seven-schema observation profile if used for receiving qualification; an old pass cannot certify journal coverage. |
| Routine/scheduled backups, coworkers or scripts | No current schedule/writer/consumer inventory was inspected. | Inventory privately under a separately approved check; do not assume none exist. Every relevant consumer must be supported or explicitly held before H2. No new schedule or notification is created now. |
| Future H1/H2 receiving installer | Not implemented as a hosted executor in PR73. | Its new guard must demand a matching profile/source/window/restore receipt and ledger/catalog baseline. The local adapter is not a hosted executor. |

Proposed v2 receipt binds profile/profile digest, archive/encrypted digest, accepted
toolchain/source hashes, capture/window/target binding, restore receipt digest,
full fact scope, major-version result and cleanup status. Verify it against the
caller-held expected artifact/packet. Reject cross-profile substitution, stale
windows, changed source/configuration or incomplete cleanup. Never project seven
schemas down to six and sign a legacy-looking receipt to bypass a consumer guard.

Keep a consumer coverage matrix in the eventual executable packet: each row is
supported and tested, completed before H2, or explicitly held with owner acceptance.
A successful new export alone does not close this matrix. No active required
backup path may be left using the refusing six-schema exporter after installation.

## Proposed fictional acceptance and approval sequence

The next implementation should test at least these independent conditions:

| Group | Required evidence |
| --- | --- |
| Profile/format compatibility | Legacy v1 still opens unchanged; seven-schema v2 succeeds only with exact profile; old reader refuses v2; wrong/missing/extra schema, duplicate JSON, changed format/digest and downgrade all hold. |
| Before-connect policy | Missing approval/configuration/private-file protection, wrong project/role/endpoint/URL options, stale source/packet, TLS mismatch and transport fallback refuse. Fictional hosted-looking inputs never cause real DNS/network requests. |
| Snapshot/fidelity | Six-schema facts match the frozen oracle in the same fictional snapshot. Seven-schema dump includes all operations rows/guards/policies, raw source bytes, precise decimals, ledger entries and sequences; a schema appearing/disappearing or observed sequence/config drift holds. |
| Dependencies | Approved extension/helper fixtures restore; unsupported signature/definition/version/cross-schema dependency holds. The owned bootstrap policy does not weaken PR73 guards or treat managed data as recovered. |
| Restore/authority | Fresh owned target, required owner/role stubs, actual FK/guard/ACL equality, old-key/newer-correction replay; remote/control/source/function-only/nonempty target and missing/incompatible role/owner refuse. Separate same-cluster and cross-cluster claims. |
| Failure and custody | Cancellation/timeout/cleanup failures preserve first error and safe stage metadata; dump/connection is reaped/closed; no final usable filename on failure, no plaintext/key leakage, wrong key/tampering holds. Close-after-success failure is not reported as complete. |
| Consumer binding | Wrong profile, stale artifact/window/source hash, missing ledger coverage, partial restore and old six-schema receipt presented post-install hold. Every enabled consumer row has explicit evidence. |
| Regression | Frozen source/SQL/archive format and loopback/marker guards stay byte-unchanged; native/par source checks and appropriate offline/disposable tests pass. No UI/authentication/stock-writer change. |

Use only labelled fictional records locally: Bert's / October 25 / Bulk Prep journal,
representative source-byte/decimal/ledger rows and synthetic account/role fixtures.
Test production routing/TLS validation separately from the mocked connection
boundary that reaches owned PostgreSQL. No test-only environment switch, URL
rewrite or live-target override may be accepted by the production CLI. Mocked TLS
or hosted-looking fixtures are not proof of a real Supabase handshake.

Sequence:

1. **This local design:** review document, source inventory and proposed interfaces.
   No application code, tests requiring PostgreSQL or hosted packet is created.
2. **Separate local implementation approval:** build the new adapter/CLI/receipt
   contract and fictional tests; preserve frozen code. Update JMax and prompt
   before a draft PR push. CI/review/merge remain their own gates.
3. **Hosted prerequisites:** S2a before administrative windows, P1 if retained on
   six-schema tooling, then the reviewed hosted adapter and consumer transition.
   Keep R1 local design parallel; actual R1 qualification blocks H3 until proven.
4. **Separate bounded hosted proof approval:** bind the private target/configuration,
   accepted code/profile, current dependencies/consumers/writers and budgets, then
   propose precisely read-only source access, protected local export and owned
   isolated restore. No standing/expired window or PR merge approves this attempt.
5. **Receiving H0-H3:** proceed only under the respective approvals. H2 needs the
   adapter/consumer gate; H3 needs R1 plus post-install recovery and approved flag/
   build sequencing. Restore original writer states by the approved hard deadline
   even if a subsequent gate is withheld; never wait indefinitely with services paused.

Current decision requested: approve only the bounded local implementation and
fictional testing described above. No hosted source, service, credential, grant,
policy, schema, application connection, paid network option or flag change is
authorized or executed by preparation of this design.
