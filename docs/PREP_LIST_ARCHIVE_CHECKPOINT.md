# Stored prep-list history without inferred tracks

October 8, 2026. Extends local commit
`66e60679566a253798fc858eb94a87dc18f1bbb9`. No Supabase query or permission change,
real invoice import, deployment flag-file change, push, merge or publication.
Track 1 remains purchased physical inventory with explicit count values and
received-date purchases. This history view cannot post inventory or Food Cost.

## Gap and selected approach

The old date/track lookup excludes lists with NULL `count_type`. Its operational
adapter defaults missing tracks to daily, converts quantities to floats, and
joins current recipe metadata. Reusing that adapter for historical evidence would
guess a classification and could change the meaning or precision of stored data.

`GET /api/pg/prep-list-archive/{store}` reads stored parent and line rows directly.
It has its own URI so it cannot collide with the old list-ID update route.
Existing manager and location gates apply; staff, readonly and anonymous callers
do not gain historical access. The endpoint requires PostgreSQL mode and has no
mutation routes. Login/PIN redesign remains outside this checkpoint.

| Stored count type | History classification | Track label |
| --- | --- | --- |
| `nightly_prep` | Daily Prep | daily |
| `commissary` | Bulk Prep | bulk |
| NULL | Unclassified | NULL |
| Any other recorded type | Other recorded type | NULL |

Raw `countType`, all stored header fields and all stored line fields remain in
the response. Every envelope/record is labelled `legacy_prep_archive`,
`archived=true`, `operational=false`. Decimal quantities serialize as exact strings,
including scientific notation when Python's Decimal uses it. NULL remains NULL;
the interface displays it as “Not recorded.” No current price, recipe, staff or
inventory joins reinterpret old rows. Historical recipe IDs remain stored
references, not proof that today's recipe has the same specification.

Date and classification filters are bound parameters. Pagination uses ordered
`(prep_date,id)` keys and a bounded page size (default 50; API maximum 200).
Continuation references must belong to the selected store and filters. Each
page reads its headers and lines in one read-only repeatable-read transaction.
This is page-level consistency, not a snapshot shared across separate requests.
The native cutover retains database write guards on old prep lists/lines;
before cutover, a legacy writer may change data between page requests.

The old schema permits only one list per store/date, regardless of track. That
constraint is preserved. The new native dated prep workflow has separate reviewed
identities and track keys. Expanding historical uniqueness or automatically
moving unclassified rows into that workflow would be a separate mapping decision.

## Manager interface

Prep now includes a PostgreSQL History subtab beside current dated prep work.
Managers can filter dates/types, refresh, load additional pages and expand raw
headers/lines. No generate, edit, assign, complete or inventory controls appear
in this view. Text is rendered through React escaping, including historical notes.

Malformed responses, floating-point quantities, wrong-location records, repeated
pages, missing archive labels and operational records are held. Loading or failed
reads cannot appear as confirmed empty history. An additional-page failure keeps
already confirmed rows and offers the same continuation for retry. Changing filters
clears earlier results; switching locations invalidates pending responses.

## Validation

Four selected backend cases pass in `prep-archive-final-v2.xml` (65.70 seconds),
without failures, errors or skips. Three run through the full native schema and
the candidate's nonowner NOLOGIN role selected with SET ROLE on pool acquisition.
The fourth uses the owner-backed disposable preinstallation fixture to check
legacy compatibility. This does not validate an ordinary hosted LOGIN connection.

The cases cover all stored classifications, raw header/line equality, large and
tiny decimal precision, NULL preservation, date/type filters, ordered pagination,
invalid and wrong-store continuations, manager/location restrictions, denied
mutation methods and legacy table write permissions. A populated physical report
and all eight accounting fact fingerprints remain unchanged after archive reads;
no native task assignments are created. Preinstallation current reads still work,
and confirmed empty history remains distinct from failure.

All 469 frontend tests in 57 suites pass in `prep-archive-frontend.txt`
(80.427 seconds), including eight history component cases and one real API-adapter
case. The production build passes in `prep-archive-build.txt` with the existing
PurchaseOrdersTab/StaffTab hook warnings and Node `fs.F_OK` deprecation warning.
Component tests and compilation do not establish live browser or Data API behavior.

Diagnostics are retained: `prep-archive-reproduction` fails during invented fixture
seeding because it tried multiple lists on one store/date; `reproduction-v2` reaches
the old overlapping archive URI and receives 405. Fixtures now use separate dates,
and the archive has a dedicated URI. `prep-archive-final` passes three role cases
but fails preinstallation with 503: that inherited fixture mocked the pool function,
while this router's bound callable reads the module's live pool. The test now binds
its own disposable live pool as well. No application guard, schema constraint or
permission was weakened to correct these test setups.

`verify_prep_archive_inputs.py` is a read-only, database-free checkpoint helper.
It verifies unchanged permissions, all 29 migration hashes, all 94 function and
123 relation contracts, the previous package hash, and every protected original
continuation byte/hash plus its 40 pending paths. The matrix pin remains
`0e2ad01e3806853f7c1f71e57f3970e7034791af1c369bac6825191e02d745fa`.
Existing SELECT rights on prep lists/lines suffice; this step adds no grants.

The local test server is stopped after validation. Only invented local data is
used. The package retains passing and failed evidence and chains to the preceding
task-cutover package. The complete backend suite and GitHub CI are not claimed.

## Remaining work and merge hold

This closes the unclassified prep-list access review from the preceding checkpoint.
Remaining routes and minimum grants still need review, followed by approved hosted
catalog reconciliation and an ordinary runtime LOGIN/pool trial. Browser/Data API,
full managed recovery, matched flags and sequential PR stack revalidation remain
open. Account/bootstrap and push subscription privileges remain separately scoped.
**Continue holding merges.** This checkpoint does not change the hosted baseline
or authorize operational release.
