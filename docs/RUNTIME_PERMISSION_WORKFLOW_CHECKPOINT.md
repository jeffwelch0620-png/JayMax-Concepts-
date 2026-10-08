# Runtime permission workflow checkpoint

October 8, 2026. Candidate grants and validation are local to unique disposable
PostgreSQL databases. No hosted database query, grant/policy change, feature-flag
file edit, push, merge or application publication occurred in this step.

## Candidate boundary

The earlier hosted workflows used the privileged database owner. The earlier
nonowner prototype covered staff production only and granted entire private
schemas. This candidate names individual objects from a frozen review manifest:
**78 native tables, seven views and 90 function names**, with SHA-256 hashes for
all 29 reviewed native migration files. Source/list drift holds the fixture.
Only non-trigger invoker functions are explicitly granted execution. No new
security-definer wrapper, schema ownership or default grant is introduced.

The candidate grants native SELECT and, except for the fixed base-unit dictionary,
INSERT per table. Views receive SELECT only. Private DELETE, TRUNCATE and DDL
remain unavailable. UPDATE is limited to these eight objects:

| Object | Reason | Integrity boundary |
| --- | --- | --- |
| `purchasing.import_files` | Serialize capture/reparse with row locks | Existing immutable-fact trigger rejects a rewrite. |
| `purchasing.document_identities` | Serialize document versions/posting/corrections | Existing immutable-fact trigger remains enabled. |
| `purchasing.document_versions` | Lock reviewed mappings and sealed source lines | Existing immutable-fact trigger remains enabled. |
| `purchasing.po_receipts` | Serialize receipt reconciliation | Existing immutable-fact trigger remains enabled. |
| `actual_inventory.scopes` | Scope-child sealing uses a row lock | Existing immutable-fact trigger remains enabled. |
| `actual_inventory.count_snapshots` | Count-child sealing uses a row lock | Direct rewrite is tested and rejected by the immutable-fact trigger. |
| `purchasing.store_vendor_items` | Store-specific supplier preferences and reviewed price adoption | Immutable price events remain separate from current editable settings. |
| `purchasing.store_supplier_contacts` | Current contact/version projection | Immutable contact events and request receipts remain separate. |

PostgreSQL requires UPDATE permission for `FOR UPDATE` / `FOR SHARE` row locks.
Consequently, the staff-only prototype's absence of all private UPDATE privileges
cannot support invoice posting and physical count sealing. The correction is a
specific lock permission plus the existing immutable trigger, rather than removing
the lock or transferring table ownership. Negative checks exercise real stored
invoice/count rows, so a trigger firing on zero rows cannot count as protection.

Twenty-one public tables have explicit privileges. Catalog/roster and current
store revisions allow their required edits; purchase-order draft lines allow
replacement/deletion while existing order guards protect approved/received content.
Existing invoices, invoice lines, reporting periods, prep logs, count sessions/
lines and legacy contacts are read-only. Activity logging allows SELECT/INSERT.
Existing staff-PIN lookup receives SELECT for compatibility; login redesign is
still deferred. Authentication/user-account tables are outside this candidate.

The public RLS policies name only the invented dedicated backend role. They allow
that trusted server role access across locations because shared catalog changes
coordinate revisions across stores. This is an application-authorized backend
model, not per-employee database RLS. It neither changes ordinary browser/client
policies nor proves that every existing legacy application route is covered.
Actual staff probes retain their application role/location checks and privacy tests.

## Validation sequence and evidence

The test fixture refuses non-loopback servers, non-UUID disposable database names,
unexpected role names or privileged role flags. Each acquired application
connection selects the invented nonowner role, checks its flags and verifies it
owns no private relations; restarted pools repeat that check. Migration/seed work
uses the separate administrator connection before runtime requests.

The selected workflows exercise:

- Purchase capture, raw PFG/US Foods bytes, received-date posting, physical returns,
  price credits, supplier reissues, explicit counts, physical period close/reopen,
  recounts, scope handoffs and original correction-key replay after a pool restart.
- Staff prep-count submission/independent acceptance and assignment/production/
  explicit finish, including current receipts and private staff responses on restart.
- Order editor independence, approval, receiving and preservation of purchase cost.
- Posting separately from store-scoped reviewed supplier-price adoption.
- Supplier-contact concurrent retry, stale edit and exact original-key replay.
- Container waste, transfer/undo and paired waste correction with Track 1 unchanged.
- Saved prep analytical periods, incomplete coverage, Track 1 separation and
  reopening the active suffix while preserving original report snapshots.

Early diagnostics are retained separately. The first selection accidentally matched
the module name and included inherited tests; its exact pytest child was stopped
and the runner stopped the dedicated local server. That interrupted trace is not
a completed test result. The first properly selected run caught a record-iteration
bug in the new test harness's role check; it was corrected without changing app
authorization. A later run passed staff and waste but held invoice posting because
the candidate lacked read access to `public.reporting_periods`. That dependency
is required by existing closed-period guards; only SELECT was added.

The same run also exposed partial-schema fixtures for order/price/contact tests.
The final permission migration correctly refused them. The fixtures now complete
the reviewed native chain as administrator before runtime grants, including the
container-waste correction helper. No production migration was weakened/replayed.
The final full-chain matrix passed **seven selected cases** in
`runtime-permissions-full-chain.xml`: physical accounting/corrections/replay,
staff counts/production, order receiving/independence, reviewed supplier prices,
supplier contacts, container waste corrections, and saved prep analytics/reopening.
Diagnostics are not overwritten or represented as successful runs. This is
selected local coverage, not a full-suite, hosted-role or GitHub CI claim.
Existing multipart and FastAPI lifecycle deprecation warnings remain.

The physical correction fixture verifies its expected $60 earlier-period and $21
final-period reports, five closure records, two active closures and exact original
correction-key replay after restarting its runtime pool. These are intentionally
different invented amounts from the retained hosted $55 fixture. The staff fixture
retains $55 through prep count and production activity. No hosted accounting fact
was read or changed during these local trials. The dedicated test server is stopped.

## Next work and limitations

This is a local candidate, not deployable hosted grant SQL. Remaining work includes
reviewing captured legacy-source INSERT access, unused per-object INSERT/EXECUTE
rights, the precise live function signatures/bodies, public catalog deletion and
other application routes, and connection/policy behavior with the final login role.
The shared read-only deployment inspector intentionally continues to hold a
nonowner connection without a separately reviewed grants model; this step does
not remove that gate.

Before hosted application, turn this tested candidate into a reviewed permission
matrix and read-only verifier, validate all remaining required routes, and then
run a bounded designated-hosted role trial with original-row/ledger reconciliation.
Browser/Data API exposure, full managed recovery, matched deployment flags and
publication/review of the local continuation remain release gates. Keep merges held.
Protected original source and the prior evidence packages remain chained in the
new snapshot; credentials, real invoice files and database archives are excluded.
