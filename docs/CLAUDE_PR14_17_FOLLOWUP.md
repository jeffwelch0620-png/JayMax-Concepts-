# PR14-17 focused follow-up

The owner approved corrections after the independent review of
`PR14-17_codex_package.md`. The package was reviewed as source material; its
proposed changes were not applied wholesale. This continuation belongs on the
existing stacked draft PR17; it does not merge the stack or authorize operations.

## Implemented scope

- Stored base unit, count unit, count factor, and supplier purchase factor survive
  item edits regardless of native feature settings. An unavailable preferred
  supplier no longer determines the physical count conversion. New conversions
  still require the existing metadata/verified-profile review.
- Item setup computes changed definitions and explicit retirement codes. The new
  authenticated location-scoped change route requires the reviewed revision,
  rejects duplicate/overlapping commands, and applies all edits and retirements
  in one transaction. Existing shared-product and unit guards remain in force.
  It does not weaken the legacy full-replacement route's retirement semantics.
- A validated save receipt can clear the exact submitted draft after location
  navigation within the same login session. A remounted original form receives
  that confirmation only if it still displays the same submitted draft. Newer
  typing, another location, replacement sessions, and stale callbacks remain
  protected. Unconfirmed/failed writes retain their drafts. Returning locations
  reload saved state rather than copying an old response into a new scope.
- Missing prep progress, unknown/nonfinite/nonpositive reviewed production,
  missing assignment state, and missing linked completion evidence stop with
  review responses. Valid first assignments and positive measured production
  retain their existing workflow. These are defensive guards; ordinary valid
  database snapshots were not shown to suffer all of the synthetic failures.
- Initial load failures display their error and a location retry. The message
  explains the feature/schema compatibility hold rather than bypassing it.
- Migration order and feature pairing guides are generated from their canonical
  source constants and checked by an in-repository review runner. Selected
  offline and local database acceptance tests are documented for coworkers.

## Decisions retained or deferred

Track 1 uses purchased stock, explicit physical opening/closing values, and
received-date purchase costs. Taxes and fees remain separate. Prep and sales
explain Track 1 without changing its accounting baseline. Retired stock remains
countable while present; product and supplier identities and history survive.

The current Supabase hosted database, session-pooler connection, auxiliary account
connection, and private credentials remain as configured during build. There is
no paid IPv4 purchase, connection-role promotion/rotation, hosted migration, or
operational import in this correction. Coworker decisions on deployment/recovery
architecture are deferred. Existing local recovery tools remain available.

Live Render feature overrides still require a read-only comparison with the
matched testing profile. Missing flags in `render.yaml` establish a configuration
gap, not proof that dashboard overrides are absent. A retry banner does not fix
an incompatible live configuration. The owner confirmed automatic deployment is
on for an unused test application with no operational data.

Keep scoped recipe validation and known/unknown cost distinctions. Do not loosen
validation to save unrelated invalid definitions, reassign unavailable SKU history,
drop retired stock from counts, unblock destructive prep deletion, or classify
sales/prep estimates as accounting usage. Recipe diagnostics and known-cost
subtotal presentation can follow separately. Shared-PIN/authentication redesign
remains deferred during build and necessary before operational use. RLS/default
privileges and recovery-tool packaging require later coordinated review, not a
blanket security-definer change or moving only a few dependent files.

## Evidence and merge path

The final selected offline run passes 211 tests and 323 subtests. The complete
frontend passes 504 tests in 62 suites with flags unset, held, and native. The
optimized build passes with the two existing hook warnings. All 24 selected local
PostgreSQL cases and 7 subtests pass; database/role inventory is unchanged and
the owned test server stopped. No selected tests were skipped.

The initial offline attempt exposed two old login/bootstrap fixtures that mocked
the inventory pool while account routes use the account pool. They now mock the
account pool directly and pass even with an explicitly held account connection.
This changes test isolation, not application login or connection behavior. The
initial failed XML remains in the local package with the passing repeat.

The new regression checks cover supplier changes with native flags both on and
off, partial item submissions, original revision preservation, delayed confirmed
save receipts, A-to-B-to-A navigation, newer typing, replacement sessions, retryable
load errors, incomplete prep state, transaction rollback, retirement history,
and test-runner connection/skip guards. Combined accounting and recovery checks
remain selected acceptance evidence, not complete-suite or live Render proof.

Retain all failed attempts alongside corrected passing runs in the local review
package. Preserve the original 40-file local continuation byte-for-byte. No PR
merge is part of this checkpoint. After testing and live feature comparison,
review the stack in dependency order PR14, PR15, PR16, PR17, retargeting dependents
after their predecessors merge. Both sides of the new item API must ship together.
