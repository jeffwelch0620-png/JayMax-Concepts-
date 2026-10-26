# PR74 review amendments: custody, timing and routine backups

October 26, 2026. Documentation only, on the existing draft PR74. Reviewed code:
`ad66f5efcbb9eb21a000ab90149856c56c7e3ec5`; accepted main remains PR73/`afe4891`.
The owner authorized these amendments and publication, not merge or hosted work.

## C1: required operator custody procedure

The [adapter design](HOSTED_JOURNAL_BACKUP_ADAPTER_DESIGN_20261025.md#required-operator-key-and-archive-custody-c1-october-26-amendment)
now requires verified separate key custody, successful restore before deletion of
the working key, private Boolean attestations, no shared key/archive/private-record
attachments, and retention/destruction that preserves known-good rollback sets.
The acceptance limitations and H1 checklist point to that procedure. Separate
directories on one machine are not independent custody. The CLI is unchanged;
operator attestations are not automated or new executable receipt fields.

Scoped application tables include account password hashes and currently plaintext
staff PINs. PIN hashing (the review's W4 label) remains separately planned release
work. Old archives retain those values after hashing is introduced. Reassess
custody then, and do not claim ordinary file deletion proves forensic erasure.
No key, archive or private operator record was transferred, deleted or uploaded.

## T1: capture-window interpretation and evidence

`journal_backup_receipts.validate()` checks the original capture window and the
expected restore-verification window. Both must still be active for installation
receipt use; a later verification window cannot revive an expired installation
baseline. Historical archival restore itself may run under a fresh execution
window without changing capture timestamps. The existing maximum is 2,700 seconds
(45 minutes). No timeout/window constant or source pin changed.

Observed current-code local evidence:

| Measurement | Seconds | What it establishes |
| --- | ---: | --- |
| Final independent-cluster end-to-end method | 24.569 | Fictional export, restore, receipt validation, data/guard/history/replay assertions; includes test work, not separate phase timings. |
| Final independent-cluster two-method suite | 40.178 | Includes the end-to-end and missing/LOGIN-role refusal cases; not a production maintenance duration. |

The source XML is `journal-final-database-20261026T030133209319Z.xml`, SHA-256
`312519cc203ff5f412daeec2baea3ae9b8ae51d25d298ad0fecb69b4c229876a`.
Its test-method times are 24.569 and 13.400 seconds; suite/setup overhead accounts
for the rest. The immutable original [evidence record](HOSTED_JOURNAL_BACKUP_ADAPTER_LOCAL_EVIDENCE_20261025.json)
retains its pre-publication checkpoint and original acceptance-document digest;
that digest describes the pre-amendment document, not today's revised text.

Separate export/restore phase durations, private custody/transfer time and hosted
margin were not measured. Do not subtract the local test time from 45 minutes and
call the result live headroom. Conservative planning uses the existing ten-minute
ceiling for each operation (20 total), a proposed minimum ten-minute reserve for
writer restoration, and at most fifteen minutes for all other tasks. No reserve
is automatically enforced by this documentation. The separately reviewed operator
packet must assign phase budgets, an earlier H2 cutoff and a writer-restoration
deadline; it must demonstrate fit before any pause. If fit cannot be established,
do not start. If remaining time becomes insufficient, restore writers and close
without applying; seek a new plan rather than extending the window silently.

## L1: proposed initial routine-backup policy

The design and acceptance consumer matrices now state that sequence advancement
during capture produces `sequence_changed_during_capture`. For initial post-H2
operation, propose separately approved writer-drained quiet windows. No routine
schedule is enabled or existing schedule inspected. Any later non-drained schedule
needs its own reviewed bounded retry/alert policy: a held capture is not a backup,
and a failed attempt cannot replace or destroy the last verified recovery set.

## Validation and remaining decisions

All executable, SQL, test, workflow and original frozen-source bytes remain
unchanged from `ad66f5e`. Local checks for this amendment verify Markdown links,
the saved XML/digests/timing interpretation and unchanged source trees; no local
server or hosted connection is needed for prose changes. Original code-head
[CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40263094348)
passed all four checks; the amended commit requires fresh CI and owner merge
approval. Original test counts overlap and are not new or additive amendment runs.

The consumer supported/completed/held matrix remains a hard pre-H2 gate. S2a,
retained six-schema P1 work and actual R1 before H3 remain separate reviewed
requirements. No window/packet has been activated. Hosted work and real credential,
grant, policy, schema, service, connection and activation changes stay on hold.
