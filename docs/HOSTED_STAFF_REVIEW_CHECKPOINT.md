# Hosted staff count and independent-review checkpoint

October 8, 2026. Local continuation on `codex/deployment-reconciliation-review`.
PR14–16 were rechecked and remain open, draft and unmerged. No push, merge,
app publication, disk feature-flag change or database grant change occurred.

## Verified workflow

The actual application `server.app`, middleware, bearer role/location checks and
staff/manager routers ran locally through an ASGI HTTP client connected to the
designated existing Supabase build database. Signed synthetic identities used a
process-only random secret. Application startup hooks, login/bootstrap, external
POS calls and scheduled jobs were not invoked. Native flags were enabled only
inside the probe process. This is database-backed application-route evidence;
it does not prove a deployed browser session or actual account login.

The retained synthetic store `hosted_trial_f25b4c3f86f54351b88d27e3d3f2a802`
was checked for its exact invented build-test label before requests. Owner requests
targeted only that location. A staff request for Berts was denied before its handler.
No operational vendor file was imported and no existing journal record was deleted.

The issued sheet has two immutable submissions: an unknown quantity followed by
the measured **48.123456789012 lb** quantity. Acceptance of the unknown quantity
was held with 422. Read-only, wrong-location and staff-to-manager writes were
held with 403. Stale hashes and changed bodies on an existing request key were
held with 409. Two concurrent identical measured submissions reused one revision.
The original author could not approve the sheet, including after another staff
identity submitted a later revision. Both preview and attempted approval held.

An independent reviewer accepted the measured submission. Concurrent identical
approval retries reused one decision and one physical prep observation. SQL
verification confirmed two submissions, one decision, exact entered/base decimal
quantities, retained counter/reviewer attribution and no stored PIN. A staff retry
after acceptance returned its original submission plus the current decision.
Closing the entire pool and replaying through a new pool retained both immutable
receipts and the same observation. No audit identity appeared in the staff response.

The full Track 1 report remained unchanged before/after acceptance and after the
pool restart. Explicit purchased-inventory values still produce $60 opening +
$40 received purchases - $45 closing = **$55 Food Cost**. Prep observations remain
Track 2 explanatory facts; this trial does not establish complete sales coverage.

## Review finding and correction

The initial local application-route trial caught a staff response exposing
`reviewed_by` after acceptance. The shared recursive staff projection omitted that
field even though it hid submission and recording identities. Nested definition
records could likewise expose `confirmed_by` and `created_by`.

These three audit keys now join the existing private identity keys in the staff
projection. Database facts, manager responses, quantities, claimed counter names,
opaque review hashes and request fingerprints are preserved. Regression checks
assert privacy after actual acceptance and retry, as well as preservation of the
private reviewer attribution. No login/PIN design change was made.

Later local preservation checks held because the initially empty fixture created
the PFG and US Foods vendor identities. The reviewed global vendor-insert trigger
intentionally increments store catalog revisions. The fixture now supplies those
vendors before capturing its baseline, matching the hosted preflight where both
already exist. The original-data assertions were retained, not relaxed. All held
attempts and the diagnostic retry remain in the evidence package.

The final local run passed **seven selected cases**: the complete staff count
route/restart workflow; exact synthetic activity exclusions; nested staff identity
projection; accepted-count privacy/retry; task-history conflict; the inherited
production task-history conflict; and production projection/privacy/retry. This is
selected regression coverage, not a full-suite or hosted CI claim. Existing multipart
and FastAPI startup/shutdown deprecation warnings remain. No frontend code changed.

## Preservation and evidence

Read-only preflight and postflight confirmed all **40 original application/integration
table projections** and all **54 full migration-ledger fingerprints** unchanged.
Only the two previously recorded invented store/item identities and five exact new
synthetic activity actors were excluded from original-value comparisons. No prefix
or arbitrary-column exclusion was used. The new staff sheet, submissions, decision,
observation and **20 synthetic activity rows** remain as retained build-test history.

Redacted evidence outside Git:

- `hosted-staff-preflight-20261008.json`: original records/ledger preserved and both vendors present.
- `hosted-staff-review-20261008T183234056135Z.json`: complete workflow, pool restart and postflight.
- `hosted-staff-pr-status-20261008.json`: refreshed draft/unmerged PR14–16 metadata.
- `review-correction-tests/hosted-staff-final.xml` and its output: seven selected passes.
- The three earlier local staff attempts retain the caught projection error and fixture diagnosis.

The new source/evidence ZIP chains by SHA-256 to the preceding durable-hosted package.
Its builder verifies every entry and the untouched 40-path protected source snapshot.
It excludes credentials, real source rows, environment files and private database dumps.
The prior installed application backup/local restore remains the recovery evidence
for 118 tables and 54 ledger records; this step did not perform a new backup/restore.

## Remaining work and merge recommendation

The hosted connection is `postgres`: non-superuser, but with BYPASSRLS, CREATEDB,
CREATEROLE and ownership of all private application tables. There are 37 public
tables with RLS. This owner-role test cannot establish a dedicated ordinary backend
role's grants, RLS behavior or ability to execute all protected operations. No grants,
policies, role membership or ownership changed in this step.

Next, define the runtime role's exact permissions for catalog reads, native journal
writes, location revision locks and activity logging. Validate that design on a
disposable database before a bounded hosted trial. Keep migration/administration
authority separate from runtime access and retain private client-role denials.
Do not mark the ordinary-role gate passed from these owner-role results.

The browser controller failed before the Supabase tab could be inspected, including
after session reset. No dashboard setting was verified or changed. No usable public
Supabase API key was present in the reviewed connection configuration, so a real
Data API request was not performed. SQL client-role denial from the earlier probe
remains valid evidence, but actual exposed-schema settings and browser behavior
remain pending. Hosted staff task assignment/production and the deployed portal
walkthrough also remain separate from this hosted count acceptance trial.

Continue holding merges while those checks and publication/review of the local
continuation remain open. When ready, merge PR14, retarget/revalidate PR15, then
PR16, then the continuation. Full isolated managed Auth/Storage/Vault/settings
recovery and matched deployment flags remain release gates. Deferred login work,
Scheduling, Operations, analytics and real Toast ingestion retain their own scope.
