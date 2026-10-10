# Supplier contact integrity — local continuation, October 6, 2026

This follows [versioned order commands](ORDER_COMMAND_INTEGRITY.md) and remains
uncommitted on `codex/inventory-workflow-continuation`, after draft PR #14's
`a472c8674a7e3f173e838907e1b9d13d7665a028` checkpoint. No further push, merge,
operational migration or enablement is included.

## Identity and retained evidence

The old store contacts use a supplier **name** as their key and accept unversioned
upserts. Renaming a supplier can disconnect its address; two editors can overwrite
one another. The covered native workflow uses `(store_id, vendor_id)` instead.
Store order contacts remain separate from global vendor representative/contact
fields. There is no automatic fallback or synchronization between these records.

The additive migration copies every old contact row into an immutable raw JSON
snapshot, retaining its original name, address and timestamp. It does not infer a
supplier ID from a name, rewrite an invalid address, or discard an unmatched record.
An explicit reviewed command can associate a preserved record with a selected
supplier and a confirmed or corrected address. The original row remains available
as evidence. A source record can be assigned only once; a contact may have successive
reviewed corrections and source resolutions. Unresolved records remain visible in
the setup panel. This is lossless capture of existing contact configuration, not
invoice import or sending a supplier message.

## Covered save contract

- A read returns store-specific contacts, stable supplier IDs, current supplier
  names/status/metadata versions, and unresolved legacy records. Zero is an explicit
  contact version meaning there is no saved native contact yet.
- Saves require the observed contact version in `If-Match`, the observed supplier
  metadata version in the body, a durable UUID request key, and a nonblank reason.
  Missing contact versions return 428; stale contact or supplier versions return
  409. Unknown suppliers and legacy sources cannot create orphan contact records.
  Inactive suppliers are held pending status review. Conventional single ASCII email
  addresses are accepted; an explicit blank clears the address. Unsupported legacy
  address text is retained unchanged until a reviewed correction.
- Catalog and store locks protect identity/status validation and the full write.
  Contact projection, immutable event, optional legacy resolution and command
  acknowledgement commit together. A repeated identical key returns the original
  result plus the **current** contact separately. A changed request, actor or store
  cannot reuse the key. Supplier renames retain the same contact relationship.
- Contact changes advance that store's collection revision. They do not advance
  another store's revision or alter supplier representative fields, prices, purchase
  facts, inventory counts, stock, prep usage, sales usage or Food Cost.
- Database guards require the next contact version and a matching immutable event;
  projection identity cannot be reassigned or physically deleted. Clearing an address
  is another retained event. Events, command evidence, legacy snapshots and resolutions
  reject updates/deletes. Foreign keys bind each resolution and command to its own
  event/store/supplier or legacy source.
- The Setup panel retains each supplier's input and reason while switching suppliers.
  An uncertain save retains its exact key, payload and versions for retry, including
  tab remount within the signed-in session. It blocks edits/refresh while that request
  is unresolved. A confirmed stale rejection permits explicit refresh/review without
  clearing the entered email or reason. Acknowledgements must match store, supplier,
  email, next version and event before announcing success; replay displays current
  saved state. Late responses from another location are ignored. A confirmed save
  refreshes the location catalog; a failed refresh is reported separately.

Client drafts and retry state are held in session memory. Reload/logout persistence,
offline operation, SMTP/address-deliverability verification and a supplier email
outbox are not supplied by this milestone. Current manager/owner command privileges
are retained; the deferred login redesign is unchanged.

## Enablement and migration order

Apply `20261006_supplier_contacts.sql` after shared catalog, native receiving and
`20261006_order_commands.sql`. The covered rehearsal also includes price history.
`SUPPLIER_CONTACTS_ENABLED` requires the versioned order dependency chain; frontend
`REACT_APP_SUPPLIER_CONTACTS` requires the corresponding order/catalog/purchase flags.
Both examples remain **false**.

After installation, the old name-based table is retained and frozen. Legacy contact
read/write/email lookup helpers are held even when the new flag is off. Turning a
flag off does not reopen unversioned writes or silently fall back to a name lookup.
Before installation, the legacy workflow remains and is not claimed fixed. Enable
schema and flags together only after target grants and deployment rehearsal.

## Validation and remaining work

Invented contact addresses and disposable loopback PostgreSQL cover simultaneous
creation/retry, racing edits, stale versions, supplier rename, explicit clears,
store/accounting separation, preserved unmatched/invalid legacy records, explicit
mapping, immutable evidence, legacy/flag-off holds and whole SQL backup/restore.
Component checks cover acknowledgement/retry, retained supplier drafts, version
refresh, replay-current state and location isolation. Initial failed comparisons
and corrected final results are preserved in the local review package.

Validation passed: 292 frontend checks across 36 suites; 50 selected backend
functions, including seven contact checks, plus 21 menu validation subcases; 23
offline checks; and the production build with three existing hook warnings. The
full frontend run explicitly enables the native purchase/catalog/order/contact
test flags. Its first invocation omitted those flags and failed four native adapter
expectations; that result is retained alongside the passing native-mode run.

Final source hashes are recorded with the snapshot. These are local
source/component/disposable-database checks, not live-browser, operational or
managed-platform proof. Test database files remain outside synced Documents/Drive;
no real invoice data was imported and no supplier message was sent.

R17 remains open for other granular metadata and prep/list/container transitions.
R18 remains open for global product amendments/retirement and reviewed prep count
scope. The original 20-finding status is still six fixed, thirteen open and one Toast
item explicitly deferred. Next: inspect the remaining prep metadata and operating
transition boundaries, then complete the prep/task/count/container cutover while
keeping all explanatory usage independent of Track 1.
