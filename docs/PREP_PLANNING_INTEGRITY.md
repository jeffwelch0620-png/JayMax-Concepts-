# Prep planning integrity — October 7, 2026

This is the next local continuation after supplier contacts. It is uncommitted,
unpublished and gated. PR #14 remains the earlier foundation checkpoint. Nothing
in this milestone enables an operational database, imports invoices or publishes
the app.

The standing prep editor previously reconstructed purchased item codes from local
display numbers, inferred daily/bulk from `made_at`, collapsed weekday and weekend
pars into one value, accepted unverified container capacities and physically
deleted standing definitions. Its granular writes lacked revision checks and
durable request acknowledgements. Those paths can drift from the independently
reviewed prep identities and physical units.

The new planner attaches settings to the existing `prep_inventory.products`
identity. Portioned inventory and batch recipes both use a reviewed producing
recipe; planning does not create another purchased-item identity or adopt a
container label as a conversion. This follows Track 2's explanatory role.

## What changed

- Immutable planning versions reference an exact reviewed recipe and a verified
  unit belonging to its output product version. Ancestry, ingredient, recipe and
  unit changes require review before another plan save. Existing historical
  versions remain readable and are marked for review when their definitions drift.
- Weekday and weekend pars are separate exact decimal quantities in that unit.
  Zero is explicit. Negative, missing and nonfinite pars are rejected. Recurring
  quantities must be positive; days are unique, Monday=0 through Sunday=6.
- Daily/bulk is an explicit planning field, independent of the store or production
  location. It does not establish a commissary transfer, purchase or receiving fact.
  Cross-location production and transfer accounting still need their own workflow.
- Supported schedules are daily to par, recurring fixed quantity and on demand.
  On demand does not silently create a dated task. Applying weekday/weekend groups
  to a service calendar is deferred to task planning; no automatic calendar rule
  is introduced here.
- Edits require the observed version in `If-Match`, a UUID request key, an explicit
  review and a reason. Catalog/store locks cover definition review and insertion.
  Concurrent stale edits conflict. Same-key retries acknowledge the original
  version and return the currently saved version separately. Actor identity comes
  from the authorized account, not a browser name.
- Retirement appends an inactive version while preserving the exact prior planning
  settings. Reactivation requires a fresh reviewed save against the retired version.
  This retires planning participation only; product identity, historical recipes,
  lots, counts and journals are not deleted or removed from count scope.
- Each committed metadata change advances its own store collection revision.
  Insert failures roll back the version and revision together. Other stores and
  Track 1 accounting records remain unchanged.
- The UI retains drafts and exact uncertain requests per product and location
  through signed-in navigation. A mismatched acknowledgement cannot clear a draft
  or announce success. Stale conflicts require explicit refresh and another review;
  current replay state is displayed without reinstating an older par. Late responses
  cannot update another location. These drafts do not persist across logout/reload.

## Schema and migration boundary

Apply `20261007_prep_planning.sql` only after the existing native purchase/count/unit,
reviewed prep mapping and canonical shared catalog migrations. It copies **all**
original `public.prep_items` fields into immutable raw JSON, without adopting their
pars, containers, source links, stock or schedule into the new planner.

The migration freezes insert/update/delete on the retained standing table. The old
POST/PUT/DELETE endpoints also return an explicit hold after schema installation,
even when the new feature flag is off. Reads and recipe-source review remain
available. With the new UI enabled, old standing add/schedule/delete controls are
read-only. A rejected removal no longer displays a successful deletion message.

Enablement requires `PREP_PLANNING_ENABLED`, `PREP_SETUP_ENABLED` and canonical
catalog mapping with its purchase/actual-inventory dependencies. Corresponding
frontend flags are required. All repository example flags remain **false**. An
installed schema with disabled flags intentionally holds old metadata writes;
disabling a flag is not a rollback plan. Whole SQL backup preserves original rows,
planning history, constraints, triggers and request evidence.

This migration does **not** modify the legacy task-type constraint, prep-list unique
key, daily overrides, list generation/release/completion, container calculations
or staff prep counts. New planning settings do not feed that legacy generator.
The native batch, waste, observation and period journals retain their existing
contracts. No new raw stock deductions, prep costs, purchase facts or Food Cost
calculations are introduced.

## Verification and next work

Local validation results and exact source hashes are saved in the cumulative
October 7 review package. Invented fixtures exercise parallel retry/edit races,
stale definitions and units, cross-store holds, retirement/reactivation, retained
legacy fields, flag-off holds, direct database constraints, transaction rollback,
store revision isolation, unchanged actual-inventory reports and whole SQL restore.
Earlier failed fixture setup attempts are retained with the final results.

The original review stays at **six fixed within their stated local scope, thirteen
open and one Toast item deferred**. R17 is narrowed for prep planning metadata;
R01/R02/R07/R18 still require broader operating and client acceptance. Validation
is local source/component/disposable PostgreSQL evidence, not live-browser,
managed-platform or production proof.

Next: connect reviewed planning versions to versioned dated prep tasks and overrides,
then address list editing/release/completion, staff counts and verified container
units. Every task must retain its planning/recipe/unit version; completion should
write Track 2 production evidence once and never deduct Track 1 accounting stock.
Finish those boundaries before adding Toast demand and variance explanations.
