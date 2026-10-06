# Future sales expectations and measured prep depletion

This is the proposed integration contract for a later Toast build, not a running
connector or a claim about Toast endpoint behavior. No sales are imported here.
Actual vendor API schemas, access and event semantics must be verified during
that build. These rules preserve the user's independent three inventory tracks.

| Track | Authority | Role in comparison |
| --- | --- | --- |
| 1 actual inventory | Purchased-item physical counts, net received purchases, explicit inventory values | Accounting baseline and Food Cost; never modified by prep/sales |
| 2 prep | Measured prep counts and outputs, recorded measured/estimated ingredients, nested use and waste | Count-derived depletion, yield and loss explanations |
| 3 sales | Retained POS source facts plus reviewed serving/recipe mappings | Theoretical service demand, planning and explanatory variance |

## Retain sales facts before deriving expectations

Retain complete original responses, source object/line IDs, vendor location IDs,
source timestamps/timezones, revisions and status fields, including unmapped
fields. Map vendor locations explicitly to native stores. Capture and normalize
separately from producing analytical expectations, with complete sync-window,
pagination, retry and source-version evidence. A successful empty page is not
proof of a complete period. Exact source identities must prevent duplicate
capture/replay from producing duplicate portions or usage.

Preserve signed corrections and prior source generations. Define how fulfillment,
voids, returns, refunds, comps and modifiers affect portion expectations before
turning them into quantities. A financial refund does not by itself prove food
was unserved or returned to physical stock. Retain monetary components separately;
do not infer consumption or kitchen waste from refunded dollars.

## Effective mappings and conversions

Map sold menu/modifier identities to reviewed, versioned portion/component
definitions for the relevant store and service time. Freeze the effective
definition and exact serving conversion in each generated expectation. A later
recipe, item name, portion or price change cannot silently reprice/reinterpret
past service expectations. Unknown modifiers, missing recipes or incompatible
units create a visible mapping gap; they must never become zero expected use.

The theoretical prepared demand for a mapped item is net eligible sold portions
multiplied by its frozen prepared base quantity per portion. Raw expectations
require their own frozen raw/recipe expansion and yield assumptions. Each raw
path must be attributed once; direct ingredients and nested recipes must not
both deduct the same producer's raw ingredients. Unknown original recipes for
opening stock remain unknown and cannot be imputed from the current standard.

Demand-based pars may use theoretical portions with separately stated historical
yield and waste assumptions. They do not create purchases or measured stock.

## Same period, separate measures

Use the same native store, aware count instants and exact-time cutoffs as the
Track 2 comparison. POS business dates alone cannot resolve count-time boundaries
or overnight service policy. Preserve event time and any source business date;
do not adopt a received invoice date as a sales date or change Track 1 boundaries.

The existing report gives:

```
prep observed depletion = opening prep count + recorded usable production - closing prep count
service-or-unrecorded-loss = depletion - recorded nested prep use - recorded prepared waste
```

Once required sales, mapping and operational coverage is confirmed, compare the
second quantity with theoretical service demand. Any resulting difference remains
an explanatory variance, not proof that the entire difference was waste. Show
recorded waste separately rather than deducting it twice. Include measured and
estimated ingredient input separately so recipe estimates do not acquire the
authority of physical measurements.

An expected closing quantity may then use opening physical prep plus recorded
production minus nested use, recorded separate waste and theoretical service
demand. Label it theoretical. A later physical count is an observation; it does
not reset source-lot availability or rewrite previous expectations.

## Coverage and correction rules

Final comparison eligibility must explicitly cover sales sync completion,
location/time alignment, relevant menu/modifier mappings, unit conversions,
production completeness and any required transfers/adjustments. Coverage is per
period and affected item; one complete product must not hide another product's
gap. Missing coverage leaves the affected expected amount/variance null with a
reason. Zero expected use requires complete evidence of no applicable demand.

Late POS facts, void/status changes, recipe remapping and count/prep corrections
must identify affected analytical periods. Current projections refresh using
effective source generations; future saved closures must become stale and follow
a reviewed reopen/replacement process. Original report/source generations remain
recoverable. Adjacent analytical periods must share count scope and cutoff choices
or use an explicit reviewed handoff. Never silently refill earlier expectations
using the latest recipe or current menu price.

The Track 1 Food Cost numerator remains its purchased-inventory calculation.
Any future POS revenue denominator needs a separately selected revenue/component
policy. This contract does not adopt a revenue rule or alter invoice tax/fee
retention. Analytical prep costing is also unselected.

## Completion checks for the later integration

Use invented/test-source cases to prove duplicate ingestion, out-of-order
corrections, unknown modifiers, split locations, recipe changes, refunds without
physical returns, exact cutoffs/DST, partial sync, nested raw attribution and
unchanged Track 1. Then rehearse whole-database recovery including original POS
bytes, mappings, expectation generations and analytical reports. Operational
access/configuration, retention and actual API behavior remain part of that
future build.
