# Posted invoice corrections

Local build implementation. Disabled by the existing feature flags until explicitly
enabled. No supplied supplier CSV or live database was used for this work.

Track 1 remains purchased inventory only, with explicit opening and closing count
values. Its food cost is opening value + net received purchase cost − closing value.
Prep, waste and sales explain this result and never post into this ledger.

## Workflow

1. Open the captured invoice in Invoice Master and select **Review correction**.
   Review uses the latest captured supplier version of the same invoice identity.
   If the supplier revised a billed amount, capture its balanced replacement file
   first. Supplier line amounts cannot be overwritten in the review form.
2. Confirm the received date, classification, item, observed quantity, unit,
   conversion and evidence on every source line. Current mappings are shown as
   starting values; they require fresh verification. Enter a correction reason.
3. **Preview invoice correction** shows all current entries to reverse and all
   replacement entries, source versions, tax/fee components, linked documents and
   closed periods affected by either the old or new inventory dates.
4. If a closed Actual Inventory period is affected, use its existing dashboard
   reopening preview. Reopening includes the entire later closed suffix. No
   invoice correction automatically reopens or rewrites a closed report.
   Refresh the invoice correction preview afterward; its earlier hash is stale.
5. Confirm reversal and replacement. Both sides are saved in one transaction.
   Interrupted requests freeze the exact reviewed body and retry key. Reopen the
   file to inspect the saved outcome rather than submitting a different review
   while its status is unknown.
6. Reclose reopened inventory periods oldest first. The original report snapshots
   remain immutable and the new generations retain replacement links. Scope
   handoffs continue to use their existing corrected-anchor rules.

## Accounting behavior

The original posting batch and its mappings remain unchanged. Each correction
reverses the entire currently effective document and posts its complete replacement.
The next correction reverses that replacement, not the original invoice again.

Example: an original receipt is 40 lb / $40. A quantity correction records −40 lb /
−$40 and +60 lb / +$40. Net purchases become 60 lb / $40. A second correction to
80 lb reverses the 60 lb entry and adds 80 lb; net purchases become 80 lb / $40.
Explicit count values stay unchanged, so only measured actual usage changes here.

A supplier reissue changing $40 to $50 records −$40 and +$50. A received-date
correction reverses the old entry at its original date and records the replacement
at the verified new received date. This can affect two count intervals. A food to
nonfood/fee/tax reclassification cancels the former food quantity and cost; its
replacement remains retained outside food facts. Header tax and fees stay separate.

The accounting view contains initial, reversal and replacement facts with unique
event IDs. Summing the signed quantities/costs gives net purchases for each item
and interval. The effective view supplies credit links and current mappings. It is
not a second balance to be combined with the signed ledger. Exact canceled mapping
pairs remain in reports for audit but do not create false outside-scope holds.

## Retained evidence and protections

- `purchasing.corrections`: initial posting link, previous correction link,
  replacement source version, balanced reconciliation, complete frozen review,
  fingerprint, reason, actor, time and retry identity.
- `purchasing.correction_lines`: complete exact reversal mapping references and
  complete replacement mapping references. All original source bytes, positional
  fields, unknown fields, typed versions, source totals and mapping decisions remain.
- `current_posting_lines`: the effective complete document dispositions, including
  nonfood/fee/tax lines. `current_purchase_facts`: effective food entries for matching
  receipt links. `actual_purchase_facts`: the additive signed accounting history.
- Identity/version, invoice-number and store locks serialize capture, posting,
  credits, corrections and period changes. Preview uses a read-only consistent
  snapshot; confirmation recomputes the plan under the store lock.
- Database guards recheck invoice identity, replacement lineage, source balance,
  current reconciliation, linked documents and both old/new closed dates. A deferred
  constraint requires the exact complete reversal and replacement at commit. Entries
  cannot be added to a correction after its transaction commits. Source replacement
  versions are sealed just like initial posted versions.
- Quantity and conversion inputs use bounded finite decimals. Original supplier
  food extensions determine cost; no latest vendor price or prep/sales deduction
  participates. Retry keys cannot be reused for another review. Successful read-back
  requires both complete sides and the matching saved plan.
- Existing manager/owner write permissions and store access apply. Staff/readonly
  cannot preview or save corrections. Login redesign remains separate future work.

## Deliberately held cases

Receipt corrections with effective linked price credits or explicitly linked returns
are held. Replacing their item/source identities can strand those links; this build
does not invent an automatic cross-document reconciliation policy. A price-credit
document itself can be corrected while its original effective receipt still matches.
New credits must reference a current receipt from the same location/vendor/item/unit.

Invoice identity changes (location, vendor, number, type, account or branch), a
changed canonical inventory unit, missing/invalid source fields, unexplained totals,
discount allocation or unsupported supplier adjustments require separate review.
Legacy closed periods remain held; reopening native periods does not reopen legacy
ones. An unchanged disposition with only a new note does not create a correction.
Physical returns without an explicit source link cannot be associated retroactively
by this workflow. Vendor/customer identity reconciliation, dependent-credit correction
bundles and manual/uncommon adjustments remain future work.

All lines of a document are reversed together. Thus even an unchanged line dated in
a closed period requires reopening that period when another line is corrected. This
keeps invoice reconciliation atomic and reviewable, at the cost of a broader reopen.
Canceled ledger entries also increase history/report size. Future analytics must
distinguish raw events from net totals; copying both current and signed views into a
combined report would double count purchases.

## Migration and local validation

Apply one-time migrations explicitly, in order, against a disposable database first:

1. `20261004_native_purchase_import.sql`
2. `20261004_actual_inventory_counts.sql`
3. `20261004_actual_inventory_corrections.sql`
4. `20261004_actual_inventory_scope_bridges.sql`
5. `20261004_posted_invoice_corrections.sql`

The fifth migration extends the existing purchase view while retaining its old
columns/types. Existing posting rows and frozen reports are not rewritten. Report
previews generated before it should be refreshed because the new event identifiers
are included in newly calculated hashes. All five migrations are transactional;
app startup does not apply any migration.

API routes under `/api/pg/purchases/{store}/documents/{version}`:

- `POST /correction-preview`: all verified line dispositions, USD, received date,
  reason; returns the complete comparison and hash without writing mappings.
- `POST /correct`: the same review, expected initial batch, expected predecessor,
  expected plan hash and a stable `Idempotency-Key` UUID.
- `GET /corrections`: immutable correction generations and frozen plans.

The existing capabilities response reports whether the correction schema exists.
The existing `PURCHASE_IMPORT_ENABLED` / `USE_PG` flags still govern access, and
`ACTUAL_INVENTORY_ENABLED` governs the connected count/report screens.

Local integration tests use invented invoices in fresh loopback PostgreSQL databases.
The correction tests cover successive generations, balanced source reissues, wrong
item remapping, nonfood reclassification, credits, received-date moves, reopen/reclose
preservation, stale reviews, retry/concurrency, forced faults, immutable history,
schema upgrade preservation, identity/total holds, direct SQL guards and sealing.
Frontend tests cover current-map verification, comparison holds, retry bodies,
editable failed previews, history and prevention of false success acknowledgements.

The local full-history backup/restore rehearsal is documented in
`NATIVE_BACKUP_RECOVERY.md`. Managed-platform recovery and deployment roles still
need verification before operational use. Review migration rollout; connect
manual/other-vendor purchases and operational unit adapters. No real invoice import,
live migration, push or PR is part of these build steps.
