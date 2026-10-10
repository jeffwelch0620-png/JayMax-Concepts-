# History reads and deployment review - October 8, 2026

Subsequent local checkpoint: the separate deployment slice now reconciles and
tests the 29-file chain, whole restore and owner-backed Track 1 transactions.
See [deployment reconciliation](DEPLOYMENT_RECONCILIATION_CHECKPOINT.md). The
source-only/pending statements below describe the earlier PR16 snapshot. Hosted
validation, remaining continuation integration and safe history paging stay open.

## Implemented scope

Staff prep-count setup reads current products and unit profiles directly. It no
longer builds unused recipe adoption, ingredient, or legacy-source reviews. Sheet
histories, decisions, pending boundary conflicts, scope changes and unit-version
holds are read in batches. Individual command review and acceptance validation
remain in place. Final decisions retain their original history and review hashes.

Container contents use batches of ordinary PostgreSQL rows for fills, movements
and paired waste observations. Exact Decimal values and timestamps survive the
driver conversion; nested PostgreSQL composite records are deliberately avoided.
Current container profile checks reuse the loaded definition and unit snapshots.
Lot totals group the complete recorded container balances by source batch.

The history helpers have these query budgets for both one and 300 roots:

| Helper | Budget and boundary |
|---|---|
| `fill_states` | Five queries with the waste schema installed and nonempty fills; includes the schema probe. Every movement and waste pair is retained. |
| `details` | Seven queries for pending sheets when current definitions are supplied. Loading definitions separately adds the readiness probe and two queries. Finalized-only history needs three queries; an empty list needs one. |

These budgets cover these helpers, not the entire container setup route. Shared
recipe mapping and batch source/ancestry validation still contain repeated reads.
Response size, Python memory and PostgreSQL work still grow with retained history.
The query budgets are regression checks, not measured production latency claims.

## Paging must preserve balances and unresolved work

No history cutoff or paging is introduced in this correction. Discarding older
fills or movements before calculating contents would understate stock and can
alter review hashes. Discarding pending sheets by age could hide unresolved work.

Next, separate current balances and unresolved work from historical evidence
retrieval. Add stable cursor paging for completed records and an explicit detail
read for full immutable history. Keep all unresolved sheets accessible regardless
of age. For containers, calculate complete balances before selecting a display
page and preserve frozen conversions, lot dependencies and full command review.
Change the API and UI together, with old-history and pending-command checks.

## Migration and runtime role review

The separately preserved local deployment-readiness continuation names 28 native
migrations. This draft already includes `20261008_container_waste_corrections.sql`,
which is absent from that plan. Reconcile the continuation before publishing or
running a deployment bundle. The reconciled bundle has 29 native migrations:
insert this waste correction after the existing waste and staff-production
migrations, immediately before `20261007_native_private_access.sql`. Keep that
access-hardening migration last; alphabetical date ordering is unsafe.

The final permission migration revokes native schema/object access from PUBLIC
and existing Supabase `anon` and `authenticated` roles. It also revokes execution
of the named public Toast security-definer RPCs. It preserves backend owner
access. It does not grant a separate runtime role or override every creator's
default privileges. The new waste-reversal helper is an invoker function with
explicit client execution revocations; replaced trigger functions preserve
their existing ACLs.

The preserved read-only inspector checks effective inherited client privileges,
PUBLIC grants, functions, private RLS, validated constraints, disabled triggers
and object ownership. Its backend ownership check is not proof that an ordinary
nonowner runtime role can complete the application's transactions. Catalog
presence is not evidence of the applied migration's checksum.

Before operational release, reconcile the exact migration file hashes and order,
validate the combined chain and restore on disposable PostgreSQL, and exercise
the intended backend connection role. Then complete isolated hosted recovery,
Supabase exposed-schema review, pool recycling and browser acceptance. Existing
read-only hosted inspection and earlier local recovery evidence do not prove
this newly combined 29-file bundle or a hosted restore.

## Accounting and release boundaries

Validation: 18 distinct selected backend checks passed across a 15-case regression
run and a four-case boundary/profile recheck, with one overlapping case. The
checks compare batched results with the former individual reads, including exact
waste quantities, pending command hashes, unit supersession, physical-boundary
conflicts, changed scope, rejection history and current profile review flags.
Existing author separation, immutable SQL seals, paired reversal, migration
upgrade and whole SQL restore checks pass. Query-budget checks use one and 300
roots. The first attempt exposed an asyncpg composite/domain decoding limitation
and an unsuitable timezone fixture; both are retained in the evidence package,
with passing checks for the corrected ordinary-row query and profile fixture.

No frontend source changed in this batch. Its prior 438-test/53-suite results in
both configurations and passing production build are previous checkpoint evidence,
not fresh reruns. These selected checks do not establish full backend coverage,
production latency, the combined 29-file migration bundle, or hosted acceptance.

Track 1 remains purchased-item physical inventory, received-date purchases and
explicit count values. Prep, container waste and sales explain usage without
changing that accounting baseline. Taxes and fees remain separate.

This correction adds no migration, changes no frontend contract, imports no
operational data and applies no hosted SQL. PR14, PR15 and PR16 remain draft and
unmerged. The newer local continuation is preserved separately. Login redesign
and shared-PIN individual identity remain deferred.
