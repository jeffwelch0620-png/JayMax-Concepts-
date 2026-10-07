# Dated prep drafts and overrides — October 7, 2026

This local continuation connects reviewed standing prep plans to dated Track 2
drafts. It is uncommitted, unpublished and gated. PR #14 remains the earlier draft
checkpoint; no additional push, enablement, real import or operational database
change is part of this milestone.

The earlier prep-list generator still relied on mutable legacy recipes, implicit
vessel quantities, an ambiguous daily/bulk key and independently edited day
overrides. A missing evening count could become zero and inflate a to-par task.
Regeneration and list edits lacked complete revision and request evidence.

## Reviewed draft behavior

- A stable list identity is unique by **store, service date and daily/bulk track**.
  Daily and bulk drafts can coexist on the same date. Changes append immutable
  list versions and sealed task sets; neither older versions nor their overrides
  are overwritten or deleted.
- Every task pins the standing planning version, prepared product, producing
  recipe and verified output unit. The active plan scope is captured, including
  omitted/on-demand items. Changed or retired plans, changed recipes/ingredients
  and obsolete conversions require review before scheduled tasks can be generated.
- The manager explicitly chooses the weekday or weekend par group. No business
  weekend or service-boundary rule is silently invented. Recurring schedules use
  the actual service calendar date, with Monday=0 through Sunday=6.
- To-par tasks use the explicitly selected **latest current native physical prep
  count from the previous calendar day**. Corrected, voided, older and cross-store
  counts are held. Original observation timestamps and confirmed location timezone
  remain in the review evidence; a count is not a stock movement.
- Physical quantities compare in the prepared product's fixed base unit. Missing
  counts and products absent from an earlier count scope remain **unknown**, not
  zero. An explicit measured zero is valid. Deficit is max(target minus counted,
  zero), with exact decimal calculations and no floating-point conversion.
- Recurring fixed output uses its reviewed standing quantity and does not depend
  on a physical count. On-demand and out-of-schedule items remain omitted unless
  a reviewed day override includes them.
- Day overrides can set a target par, set an output quantity or omit an item.
  Each references the exact current standing plan and has its own reason. They
  are saved atomically inside the dated draft, independent of the usual standing
  par. An outdated override must be explicitly removed/reviewed; it is not silently
  rebound to a newer recipe or unit.
- Deficits that cannot be represented exactly within 12 decimal places in the
  selected unit remain unresolved. A reviewed fixed output quantity can resolve
  them; no container rounding, whole-batch rounding or guessed conversion occurs.
  Drafts may retain unresolved quantities for review, and always report that they
  are awaiting staff release. Saving them records no production.

## Save and database integrity

Preview and save require the observed `If-Match` revision, with zero meaning no
saved draft. Save requires explicit review, a matching preview hash and a UUID
request key. Catalog/store locks protect source review and atomic insertion.
Stale edits conflict. Exact retries return both the originally acknowledged
version and the currently saved version. Actor identity comes from the authorized
account rather than a typed browser name.

Database constraints preserve location/product/recipe/unit identity, finite
nonnegative quantities, exact unit multiplication, the complete active planning
scope and matching task snapshots. They reject post-commit task insertion, partial
task sets, fabricated zero stock, contradictory schedules/overrides and quantities
that differ from the measured deficit. Metadata and task insertion failure rolls
back the version, list identity and store revision together. History is immutable.

The editor retains inputs, reviewed previews and exact uncertain save requests per
store/date/track during signed-in navigation. Editing inputs invalidates the
preview; a rejected stale save requires refresh and another review. Unconfirmed
previews/acknowledgements cannot enable a save or announce success. Current replay
state is displayed, and late responses cannot alter another day or location.
Drafts do not persist across logout or app reload.

## Migration and publication boundaries

`20261007_prep_day_tasks.sql` follows the reviewed prep planning, native batch/count
observation and shared catalog migrations. It retains **every original field** of
legacy lists, lines and day overrides as immutable raw JSON and freezes their
old tables. The old generate/edit/add/release/complete/override writers are also
held after schema installation, including with the new flag disabled. Existing
reads remain historical reference; no legacy field is automatically adopted.

`PREP_DAY_TASKS_ENABLED` requires reviewed planning and native observations, including
their prep setup/batch/catalog/purchase/actual-inventory dependencies. Corresponding
frontend flags are required. All repository example flags stay **false**. Disabling
the flag does not reopen a frozen legacy writer or provide a schema rollback.

This milestone supplies **reviewed drafts only**. Staff assignment, release,
completion, production-event linkage, partial completion, staff prep counts and
verified container execution remain subsequent work. Native dated drafts do not
create batches, waste, stock deductions, purchase facts or Food Cost entries.
Physical purchased-item counts and received purchases remain Track 1's accounting
baseline; this workflow explains and plans Track 2.

## Validation and remaining review

The cumulative local review package contains exact source hashes, full patch,
backend/SQL/component/build results, whole SQL restore proof and the preceding
snapshot. Fixtures are invented and use a disposable loopback PostgreSQL cluster
outside synced Documents/Drive. No real invoice or operational record was imported.

Validation passed: 312 frontend tests across 38 suites, 20 selected backend checks
(ten dated-draft, eight standing-planning and two observation-boundary checks),
23 offline checks and the production build with three existing hook warnings.
The review package also retains the earlier eight-check focused draft run and
separate direct-database guard verification. Earlier milestone evidence remains
in its unchanged nested snapshot rather than being claimed as rerun here.

The original review remains six fixed within their stated scope, thirteen open
and one Toast item deferred. R01/R02 now have a separate reviewed native draft
path and legacy holds; they are not closed because the complete task execution
acceptance remains unfinished. R07/R17 are narrowed for this save/metadata surface,
while release/completion, staff counts, containers and durable reload recovery
remain open. Checks are local evidence, not browser, managed-platform or production
proof.

Next: add versioned manager release/reopen commands and immutable task execution
that links once to reviewed native production evidence, then staff count and
container workflows. Release must reject unresolved or changed source versions;
completion must never deduct Track 1 accounting stock.
