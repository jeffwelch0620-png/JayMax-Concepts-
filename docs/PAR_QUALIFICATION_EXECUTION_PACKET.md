# Reviewed par qualification operator handoff

## Scope

The [October 22 maintenance proposal](REVIEWED_PAR_MAINTENANCE_PROPOSAL_20261022.md)
now has a local, source-bound handoff builder and verifier:
[par_qualification_packet.py](../tools/ops/par_qualification_packet.py).
The proposed maximum 45-minute window covers controlled pause/drain, encrypted
backup, isolated local restore and read-only qualification. Schema application,
credential/grant changes, runtime cutover and live app acceptance remain held.

The tool only prepares or verifies public local files. It has no database,
credential loader, service-control, subprocess or command-execution capability.
It never runs the argv arrays stored in its output. Preparation does not grant
authority or claim that the resources, producers, backup or hosted plan are ready.
Generated packets deliberately keep all execution approvals false, window times
unbound, and `readyForHostedExecution` false. They are **supervised operator
handoffs, not an automatic maintenance controller or executable migration plan**.

## Prepare and verify locally

Use Python 3.12 or newer from the repository root. Select a new output file; an
existing file is refused to preserve earlier evidence. No credentials are needed.

```text
python tools/ops/par_qualification_packet.py prepare --output <new-local-packet.json>
python tools/ops/par_qualification_packet.py verify --packet <retained-local-packet.json> --packet-sha256 <exact-hash-returned-by-prepare>
```

Record the complete packet hash with the independently reviewed source revision.
Rerun verification before each later manual stage, including after waiting for
owner input. Any changed source, altered gate/template or stale packet holds.
The verifier accepts only the exact handoff derived from its pinned proposal and
current sources; editing a packet and recomputing its hash cannot add authority,
change cutoffs or introduce an apply command. Files alone cannot prove human
authorization; a successful verification is local source evidence only.

## Source integrity across checkouts

The current builder emits **v2** packets. The historical proposal and content-pin
manifest remain unchanged. Exactly two candidate tooling amendments are pinned
explicitly in the builder: `backend/deployment_readiness.py` and
`tools/ops/apply_reviewed_par_migration.py`. Each binds its historical content
hash and its new candidate content hash. Packets disclose those amendments and
`toolingReviewStatus: candidate_requires_independent_review`; this is not a claim
that the changed tooling has already been accepted or approved for hosted work.
Every other historical core source still requires its original content pin.
Old v1 packets and altered amendment hashes are refused. Do not rewrite earlier
packets, source audits, backup receipts or approval records to make them pass.

The original proposal's saved 49-source audit includes Windows newline bytes.
The [content pin manifest](PAR_QUALIFICATION_SOURCE_PINS.json) records those raw
digests and independent content digests for the same accepted PR53 source.
Generation verified the original raw digests locally and compared accepted Git
content for the Python/JSON entries. Outside the two explicit amendments above,
the builder permits only CRLF-to-LF equivalence for those text entries; other
whitespace or content edits hold. Amended text has its own exact content pin
with the same newline-only portability rule, never a blanket drift exemption.
All 31 SQL files retain their exact reviewed byte hashes. No SQL normalization,
catalog/security modification or installer-guard relaxation occurs.

Each output binds **all 56 actual local source-file byte hashes**, plus the exact
proposal bytes separately. Those include the 49 core sources (with two disclosed
candidate amendments), backup CLI,
new verifier/tests, offline CI selection, this guide, content pins and checkout
attributes. A newline change after creation invalidates that packet too. Moving
between checkouts may require a newly generated/reviewed packet; a matching
portable content baseline is not permission to reuse a different byte-bound hash.

The CLI requires Python 3.12 or newer. Older runtimes return a fixed held
receipt and exit 2 before argument processing or source/output file access.
Checkout attributes pin the portable core Python/JSON entries to LF, while
preserving each reviewed migration's existing exact LF or CRLF rule. Do not
apply LF normalization to SQL or rewrite historical raw hashes. Source content
pins establish equivalence; generated packets and installation-plan sourceHashes
still bind the actual local bytes. Generate and review fresh artifacts after
any checkout-byte change; old plans/packets are not portable approvals.

## Supervised stages and evidence

The packet contains separate argv templates for accepted backup `export`,
`verify-restore` and par `dry-run` entry points. All private paths/project details
remain placeholders; no DSN/password is embedded. Do not paste these as a batch.
Accepted CLI entry points do not themselves confer maintenance approval.

| Stage | Operator evidence required before invoking the template |
| --- | --- |
| Before any hosted step | Fresh owner writer/no-other-writes commitment, owner available for API suspend/resume, passing local resource/recovery-path checks, a separately approved new window and recorded Eastern/UTC deadline. Re-read exact producer bindings and capture original states. |
| Export, finished by minute 18 | API suspension evidence, only exact Toast jobs 3/4 disabled, strict full-visibility writer guard passed twice at least 45 seconds apart, HTTP/cron/downstream drain, and enough time for the full export budget and cleanup. Drain must pass by minute 8. |
| Restore, finished by minute 24 | Fresh encrypted archive/separate key with private ACLs; one owned UUID-named empty loopback PostgreSQL 17 target; captured original local role/database/server inventory. The operator owns local target creation, required NOLOGIN stubs and cleanup; this verifier does not automate that lifecycle. |
| Read-only qualification, finished by minute 34 | Verified restore equality/access guards and owned cleanup; new private v2 review bound to the active window, exact original/index receipts and hashes, fresh backup/restore and reviewed role groups. Allocate the candidate delivery version only after current ledger reconciliation. Keep the full 600-second operation plus at least 600 seconds for producer restoration. |
| Closure by minute 45 | Owned hosted clients closed; exact original producer states restored and verified; known outcome, cleanup and actual closure recorded. Escalate uncertainty before the deadline; no automatic extension/retry or platform/session termination. |

The static frontend/platform services remain running. The operator rechecks
each receipt's identity, timestamps, hashes and successful cleanup against the
active window; the local verifier does not validate arbitrary live-state claims.
Newly observed writers or changed source/deployment/baseline require review before
proceeding. Do not edit historical PR51 runners, change their stale pins or call
their expired-window controllers. Use the accepted component entry points only
within this freshly supervised scope and the proposal's unchanged safeguards.

Restore necessarily replays schema/ACL metadata and temporary role stubs **only
inside the separately approved isolated local rehearsal**, never Supabase grants
or schema. No restored app workflow, job, import or hosted restore is authorized.
Close serial stages early on any cutoff/refusal and restore original producers
after known owned cleanup. Preserve original errors and cleanup evidence.

After writers resume, the archive and any generated hosted plan become dated
qualification evidence. A later application requires fresh stop/drain/backup and
target reconciliation plus separate exact-plan-hash approval, including the new
objects' security statements. The current owner-connected build path stays
unchanged; O1 restricted-role adoption remains separate. Par editing is frozen,
ordering manual and Track 1 independent.

## Local validation

The fictional-only packet suite is included in the Windows offline CI profile.
It checks source/proposal drift, changed or rehashed authority/command fields,
JSON types/duplicates/nonfinite/size refusal, unsafe paths/links, evidence
preservation, newline portability with exact SQL, timing and CLI isolation.
Application/frontend/SQL behavior is unchanged. Fresh CI, publication and merge
remain separate gates; local validation is not a hosted maintenance rehearsal.
