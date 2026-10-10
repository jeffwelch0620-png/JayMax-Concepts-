# PR18 conversion review and CI follow-up

October 10, 2026. Follow-up to the independent review of head `84c7e95`.
PR18 remains a draft. Merge, test deployment and live acceptance are separate
decisions; this package changes no hosting, connection settings or hosted schema.

## Review dispositions

| Review item | Resolution |
| --- | --- |
| Unknown supplier conversion cannot be confirmed in Item Setup | Reuse the existing **Invoice Master → Verified inventory units** workflow. Each native supplier row links to its saved item and supplier product in the current restaurant. |
| Stored factor can disagree with edited pack metadata | Show the non-blocking notice **Stored conversion differs from pack details: confirm or keep** for positive stored factors and complete, compatible physical packs. No value is rewritten. |
| No repository CI | Add pull-request/main checks with read-only permissions and SHA-pinned actions: all native frontend tests, strict production build, selected offline backend checks, and disposable PostgreSQL accounting/restore checks. |
| Fragile component API mocks | Add a complete shared mock with disabled native flags, safe empty read defaults and explicitly configured writes; migrate CatalogSetup tests. |
| Fictional live item/count walkthrough incomplete | Keep it pending until an approved merge reaches the Render test deployment. Local tests and CI do not substitute for this walkthrough. |

## One confirmation history

`vendor_items.base_per_purchase_unit` is catalog metadata. A stored null remains
null through ordinary edits, including pack edits. A verified native purchase
conversion is a separate, location-specific **unit profile**, saved by the
existing `/api/pg/purchases/{store}/unit-profiles` route. It records the authenticated
confirming actor, server timestamp, evidence, immutable revision and saved-source
fingerprint, with safe idempotent retries. Confirmation does not create purchases
or alter an existing accounting fact. The profile's actor and timestamp are now
visible in the review history.

The linked review selects purchase purpose and the saved supplier product but
leaves the factor blank. Enter a physically verified measurement and evidence,
then confirm it explicitly. Pack metadata is a reference, never automatic proof.
The existing workflow also permits an evidenced measured conversion when catalog
pack metadata is incomplete; incomplete review inputs cannot save a profile.
Confirmed profiles suggest invoice quantities, and each invoice line still needs
its own review. Changed source metadata makes an earlier profile stale and requires
a new review. Historical profiles and accounting snapshots remain preserved.

New items/SKUs and changed pack/source fields must be saved before following the
link. This prevents confirming against a fingerprint of older saved metadata.
The Item Setup draft stays in the App's restaurant-specific cache when navigating
to Invoice Master. Successful confirmation refreshes the shared saved revision.
Focus is scoped to the original restaurant and is applied only once, so a review
refresh cannot replace entered evidence or a confirmed factor.

The notice compares matching dimensions (mass, volume or count) in the item's
fixed catalog base unit, allowing floating-point representation noise. Missing,
nonpositive, nonfinite or incompatible pack fields do not imply a factor. This is
an advisory comparison of catalog values, not an accounting calculation or a
second confirmation ledger. Ordinary saves retain the stored factor.

## Validation

The focused supplier-review, draft/navigation and receiving checks pass **38
tests in four suites**. All **522 frontend tests in 63 suites** pass with the
native feature profile. Selected offline backend checks pass **211 tests and
323 subtests**, with no skipped checks. The strict production build also passes
in GitHub's fresh Linux install. The local database selection passed 25 cases
and seven subtests; the added unknown-factor case required an explicit fixture
revision row and then passed in its corrected focused rerun. The complete CI
selection reruns all 26 database cases together, with no skipped cases accepted.

The existing PurchaseOrdersTab and StaffTab hook warnings were corrected using
stable refresh callbacks. Changing a toast callback does not cause extra order
reads. CI uses `CI=true` so frontend build warnings are failures. Dependency-level
deprecations and backend lifecycle warnings are tracked separately from failures.

CI follows the existing Yarn 1.22.22 lockfile rather than adding an npm lockfile.
The backend runs the existing selected review runner, extended with the unknown
catalog-factor confirmation and stale-source/fixed-unit guards. Its disposable
PostgreSQL service contains fictional fixtures only. See
[repeatable checks](REVIEW_TESTING.md) for exact scope and local commands.

GitHub's Linux runner exposed checkout normalization of pinned SQL bytes.
`.gitattributes` now preserves the already-reviewed CRLF/LF bytes by file on
both platforms; no SQL body, manifest hash or drift guard was changed. Offline
Windows ACL and process-witness tests run on Windows with canonical disposable
scratch paths. The ordinary-role recovery fixture uses its own invented password
so it can run against password-authenticated PostgreSQL rather than relying on
the local cluster's trust authentication. No application credential is involved.

The authoritative result for the current branch head is the combined **Inventory
CI** status in [PR18 checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/18/checks).
Earlier failed setup attempts remain in the run history. These are selected
backend acceptance checks, not the entire historical backend suite. The local
test server was shut down after its owned run and its database/role inventory
matched the opening inventory. Local compilation was interrupted when available
memory became very low; the passing fresh GitHub production build supplies the
build evidence. Deployed UI acceptance remains pending.

## Next acceptance checkpoint

After CI passes and a merge is explicitly approved, repeat the Bert's fictional
item save through the deployed UI. Establish the labelled purchased-inventory
scope; complete counts with explicit values, received purchases, return/credit,
period close/reopen, prep explanations, staff submissions and manager review.
Track 1 remains the accounting baseline; prep/waste and sales only explain it.
Record deployed results separately from local tests and CI. Broad UI rework and
final hosting/access decisions remain later workflows.
