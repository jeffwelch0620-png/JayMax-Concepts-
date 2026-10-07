# Order commands and supplier metadata — local continuation, October 6, 2026

This milestone follows [supplier planning price history](SUPPLIER_PRICE_HISTORY.md)
and remains uncommitted on `codex/inventory-workflow-continuation`, after PR #14's
`a472c8674a7e3f173e838907e1b9d13d7665a028` checkpoint. No further PR, push, merge,
operational migration or feature enablement is part of this work.

## What changed

The old order endpoints read a status and later replaced lines or changed state
without checking that the read was still current. A submitted/approved order could
therefore change underneath its reviewer. Repeating a draft creation after a lost
response could also create another order. The gated PostgreSQL command path fixes
these boundaries for its supported workflow.

- Every order has a version. Draft edits and transitions require `If-Match` with
  the observed **order version**, not the store collection revision. Missing versions
  are held with 428; changed versions conflict with 409. Database triggers advance
  order/store versions for header and line changes, including native receiving and
  reconciliation. Versions may advance by several numbers within one command;
  clients compare versions rather than assuming an increment of exactly one.
- Creation, full draft replacement, submit, approve, reject, reopen, mark sent,
  archive and reorder each require a durable UUID request key. The fingerprint binds
  the store, actor, action, order, observed version and request. The catalog lock,
  store revision lock and order row lock protect validation and the complete write.
  Successful command evidence and a result snapshot commit in the same transaction.
  Concurrent repeats return the same result; changed requests cannot reuse a key.
- Header and line reads use one repeatable-read snapshot. Replay returns the original
  acknowledged result **and** the current order separately, so reconnecting after
  another reviewer advances the order does not display the old state as current.
- Draft/submit/approve/send validate canonical purchased-product identity, exact
  supplier SKU, current local alias, supplier purchase unit and availability. Quantity
  must be positive and finite; planning price may be unknown/null or a finite
  nonnegative decimal. The server takes product names from the catalog. Exact
  decimal strings survive the covered client/API path. Unknown price does not become
  $0 or a complete total; explicit zero remains known. Line estimates round to cents
  using half-up rounding, and totals are planning estimates, not invoice costs.
- State checks and dependent line writes are atomic. Only a current draft can be
  edited; non-draft content is guarded at the database boundary. Native delivery
  quantity bookkeeping remains allowed. Invalid lines, inactive suppliers, retired
  items, bad aliases/units and stale requests leave no partial command/header/lines.
- Creator and reviewer identities come from the authenticated session, not browser
  display names. An account cannot approve its own order. Existing orders have an
  unverified creator identity and are held at approval until rebuilt as a reviewed
  draft (for example through explicit reorder). No identity is fabricated in a
  migration. Current manager/owner authorization is retained; a broader approval
  permission and login redesign remains outside this milestone.
- Removing a draft/rejected order archives it, retains its lines/history and excludes
  it from active lists. A replay still confirms the archive. Direct physical deletion
  and edits to archived content are held. Reorder copies canonical identities and
  historical estimate amounts into a new reviewed draft and clears received quantity;
  it does not infer live stock, a new invoice price or an automatic quantity.
- Global supplier APIs now have a covered metadata boundary:
  owner vendor edits require the observed `catalog_version`, preserve identity and
  hold ambiguous duplicate names. Omitted contact/representative/active fields are
  retained; an explicitly supplied null can clear an optional field. Vendor changes take the catalog lock and bump
  store revisions in fixed order, invalidating stale whole-catalog saves. Duplicate
  supplier creation returns a conflict rather than silently replacing metadata.
  The normal catalog helper may create a missing supplier record during item saves;
  its database revision triggers also apply.
- The gated Purchase Orders screen supplies reviewed transitions, notes, archive,
  explicit reorder and the existing invoice-linked receiving/reconciliation panel.
  Owner overview links to the current versioned order review. Uncertain commands and
  draft creations retain the exact request for retry; mismatched acknowledgements
  do not announce success. Late results from another location are ignored. Notes
  and retry state are session state; no logout/reload/offline persistence is promised.
- Mark sent records state only. The old supplier-email write path is held before
  sending in this mode. A transactional delivery/outbox workflow is future work;
  no test or implementation action sends a message to a supplier.

## Accounting and enablement boundaries

Orders express purchasing intent. These commands do not add stock, purchase facts,
counts, prep consumption, sales deductions or accounting values. Native invoice
posting still records purchases with received dates and separate taxes/fees. Native
receiving links those existing facts and advances order versions without duplicating
the purchase cost. Track 1 remains independent of planning and explanation tracks.

Apply `20261006_order_commands.sql` after shared catalog and native receiving; the
covered test sequence also includes supplier price history. The migration adds order
versions, archive/actor fields, command evidence and supplier metadata versions. It
allows nullable order totals and line estimates on older bootstraps that required
them. It does not rewrite legacy order content or assign historical actors.

Backend `ORDER_WORKFLOW_ENABLED` requires the shared native catalog dependency
chain. Frontend `REACT_APP_ORDER_WORKFLOW` requires the corresponding native flags.
Both examples remain **false**. Once the command schema is installed, legacy order
writers are held even if the workflow flag is off; switching flags does not reopen
unversioned mutation. Before installation, the original legacy workflow remains and
is not claimed fixed. Rehearse flags, grants and schema order on the target platform.

## Validation and remaining work

Invented invoices, disposable loopback PostgreSQL and component/build checks cover
draft retries, exact/unknown/zero prices, edit/submit and approve/reject races,
authenticated attribution, archive/reorder retention, stale supplier/store revisions,
legacy/flag-off holds, native receiving without duplicate cost, and whole SQL recovery.
Initial results are retained, including the nullable-estimate bootstrap mismatch.
Validation passed: 282 frontend checks across 35 suites; 43 selected backend
functions plus 21 menu validation subcases; 23 offline checks; and the production
build with the same three existing hook warnings. Nine order checks were rerun
after the final reconnect read-back and optional supplier-field preservation
adjustments; these overlap the 43 functions, rather than adding nine to that total.
The retained first read-back rerun includes a corrected test comparison between
command and public-list response shapes. Final source hashes are in the local
review package; these checks do not
constitute browser, production or managed-platform proof. Test database files stay
outside synced Documents/Drive folders, and no real invoice is imported.

R17 and R18 remain open with narrower scope. Separate supplier contact records, other granular
metadata, prep/list/container transitions, shared product amendments, a supplier-mail
outbox, broader command privileges, durable client recovery across reload and full
operating cutover remain separate work. Dedicated draft-line editing UI can use the
new replace command but is not added here. This milestone covers the current order
review path and API, not every historical operating screen or every SQL writer.

Next: close remaining contact/metadata save boundaries, then the prep/task/count/
container operating workflow before Toast integration.
