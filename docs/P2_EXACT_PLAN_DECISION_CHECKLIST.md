# P2 exact-plan owner decision checklist

**Template only. No approval, delivery version or executable plan SHA exists.**
Read the fixed section before the window. At decision time the operator fills
only the fresh section and presents it with the exact generated plan. Every
row must be Yes; blank, uncertain or No means no application. Approval of P1 or
this template is not P2 approval. No timely decision means restore writers and
close; never shorten verification or extend the window to obtain approval.

## Fixed reviewed scope

| Compare with the fresh plan | Reviewed value | Yes / No |
| --- | --- | --- |
| Accepted source | PR59 c3b429a plus separately reviewed documentation follow-up; all executable/source bindings unchanged | ____ |
| Raw SQL SHA-256 | `84814517f75bb58940a36facdbf5a7934036ff5b388e97a820038e837416506e` | ____ |
| Transaction-free body SHA-256 | `3a189a8b2a352cbd560cea88194dbde1940f160a54e7bcd4616d719c47b88c48` | ____ |
| Catalog SHA-256 | `8a18effb17929604c76817ed7478b112033df4886e4434c0c1e6a4cce01e8e17` | ____ |
| Table | One initially empty `purchasing.inventory_par_versions`: 17 columns, 17 constraints, three FKs | ____ |
| Unique index 1 | `inventory_par_versions_pkey` | ____ |
| Unique index 2 | `inventory_par_versions_predecessor_id_key` | ____ |
| Unique index 3 | `inventory_par_versions_request_key_key` | ____ |
| Unique index 4 | `inventory_par_versions_id_store_id_item_code_key` | ____ |
| Unique index 5 | `inventory_par_versions_store_id_item_code_revision_key` | ____ |
| Unique index 6 | `inventory_par_root` | ____ |
| Invoker function | One `purchasing.guard_inventory_par()`; no security-definer substitution | ____ |
| User triggers | `valid_inventory_par`, `immutable_inventory_par`, `retained_inventory_par` | ____ |
| Internal FK triggers | Exactly 12 | ____ |
| New-object security | RLS on; exact reviewed PUBLIC/existing anon/authenticated table/function revocations; **zero new policies or grants** | ____ |
| Ledger | Exactly one `reviewed_inventory_pars` entry; no prior ledger rewrite | ____ |
| Limits, seconds | Lock **5** / probe **20** / DDL **30** / idle transaction **120** / adapter work **600** | ____ |
| Preservation | Original rows, sequences, definitions, roles/memberships/access and ledger preserved outside the exact additive delta; no backfill or store-revision advance | ____ |
| Authority | Correct build target, separately approved active P1, full current source/catalog/drain qualification and private recovery custody | ____ |

The 17 columns and types remain enumerated in the
[single-source installation proposal](PAR_INSTALLATION_PROPOSAL_20261023.md).
Compare the generated catalog against the pinned reference, not this checklist
alone. Index attribute records are not extra table columns.

## Fresh decision fields — fill only from this window's authenticated evidence

| Required live binding | Fill at decision time | Yes / No |
| --- | --- | --- |
| Exact executable plan SHA-256 | ________________________________ | ____ |
| Exact target/project/database/actor binding, privately verified | ________________________________ | ____ |
| Delivery version, 14 digits | ______________ | ____ |
| Installed ledger count / maximum | count: ______ / max: ______________ | ____ |
| Delivery version strictly greater than that observed maximum | comparison: ____________________ | ____ |
| Encrypted backup artifact SHA-256 | ________________________________ | ____ |
| Backup archive SHA-256 | ________________________________ | ____ |
| Backup manifest SHA-256 | ________________________________ | ____ |
| Successful disposable restore receipt SHA-256 | ________________________________ | ____ |
| Source/plan/backup/manifest/restore bindings agree; owned cleanup passed | evidence: ______________________ | ____ |
| Quiet drain observation 1 / observation 2, UTC and Eastern | ______ / ______; separation: ____ s, at least 45 s | ____ |
| API suspended at captured commit; exact jobs 3/4 paused; no additional writers/queued work; no merges | captured states: ________________ | ____ |
| Original producer states and recovery operator are captured and available | private receipt: ________________ | ____ |
| Active window start / deadline | ______ / ______ UTC; ______ / ______ Eastern | ____ |
| Current time / remaining seconds at decision | time: ______; remaining: ______ s | ____ |
| Apply starts by relative 39:00; at least **1,215 s plus 45 s closing margin (1,260 s total)** remaining | projected start / remaining: ______ | ____ |
| Same reserve rule verified: 600 s work + 15 s cleanup + 600 s restoration + 45 s closure | remaining at apply start: ______ s; minimum **1,215 s plus 45 s closing margin (1,260 s total)** | ____ |
| No configuration/credential/source change invalidated the current packet | current private revision/digests: ______ | ____ |
| Owner explicitly approves this exact plan SHA before any DDL | owner decision / time: __________ | ____ |

At relative 39:00 a 60-minute window has 1,260 seconds remaining, leaving 45
seconds after the full operation, cleanup and restoration reserves. Recheck at
actual apply start; do not treat a decision-time measurement as a future guarantee.
The adapter's weaker technical deadline floor does not replace this operator rule.

## Outcome

- [ ] All rows Yes and exact P2 approval recorded: use only the reviewed guarded
  installer and one plan; independently verify the outcome before restoration.
- [ ] Any row No/unknown, approval absent, drift or insufficient time: no DDL;
  restore captured producer states and close P1.
- [ ] Ambiguous commit/response: preserve and reconcile that original plan;
  never resend SQL as a diagnostic. Keep the stated restoration deadline and
  report unresolved outcome; no unapproved repair, table drop or restore.

P3 fictional acceptance, R1 grants, S2a/S2 credentials and I1 provider/identity
changes remain separately held. Ordering manual; par editing frozen until P3.
