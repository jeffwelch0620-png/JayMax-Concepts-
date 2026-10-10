"""Read-only batch dependency inventory. Existing correction previews remain authoritative."""
from fastapi import HTTPException
import prep_batches as batches
from purchase_api import serial
from purchase_parser import fingerprint


async def review(conn, store, event_id):
    await batches.ready(conn)
    selected = await conn.fetchrow('SELECT * FROM prep_inventory.batch_events WHERE store_id=$1 AND id=$2', store, event_id)
    if not selected:
        raise HTTPException(404, 'Batch is not at this location')
    # Historical edges deliberately stay visible, including released allocations.
    # UNION, rather than UNION ALL, terminates even if old roots reference one another.
    roots = await conn.fetch('''WITH RECURSIVE affected(root_id) AS (
        SELECT root_id FROM prep_inventory.batch_events WHERE store_id=$1 AND id=$2
        UNION
        SELECT child.root_id FROM affected a
        JOIN prep_inventory.batch_events source ON source.root_id=a.root_id AND source.store_id=$1
        JOIN prep_inventory.batch_movements m ON m.source_batch_id=source.id AND m.store_id=$1
        JOIN prep_inventory.batch_events child ON child.id=m.event_id AND child.store_id=$1
    ) SELECT root_id FROM affected ORDER BY root_id''', store, event_id)
    ids = [r['root_id'] for r in roots]
    history = [dict(r) for r in await conn.fetch('''SELECT id,root_id,revision,kind,product_id,base_unit,
        performed_at,business_date,review_hash FROM prep_inventory.batch_events
        WHERE store_id=$1 AND root_id=ANY($2::uuid[]) ORDER BY root_id,revision''', store, ids)]
    current = {r['root_id']: r for r in history}
    event_ids = [r['id'] for r in history]
    coverage = {}
    for family, table in [('waste','observations'),('containers','container_fills'),('tasks','execution_events'),
                          ('staffProduction','staff_production_decisions'),('periods','period_closures')]:
        coverage[family] = bool(await conn.fetchval('SELECT to_regclass($1) IS NOT NULL', 'prep_inventory.'+table))
    edges = [dict(r) for r in await conn.fetch('''SELECT m.id,m.event_id,m.source_batch_id,m.side,m.quantity,m.base_unit,
        e.root_id FROM prep_inventory.batch_movements m JOIN prep_inventory.batch_events e ON e.id=m.event_id
        WHERE m.store_id=$1 AND m.source_batch_id=ANY($2::uuid[]) ORDER BY e.root_id,e.revision,m.ordinal''', store, event_ids)]
    waste = []
    if coverage['waste']:
        waste = [dict(r) for r in await conn.fetch('''SELECT o.id,o.root_id,o.revision,o.kind,o.source_batch_id,o.performed_at,
            o.base_unit,NOT EXISTS(SELECT 1 FROM prep_inventory.observations n WHERE n.predecessor_id=o.id) AS current
            FROM prep_inventory.observations o WHERE o.store_id=$1 AND o.purpose='waste'
            AND o.source_batch_id=ANY($2::uuid[]) ORDER BY o.root_id,o.revision''', store, event_ids)]
    containers = []
    if coverage['containers']:
        import prep_containers
        rows = await conn.fetch('SELECT id FROM prep_inventory.container_fills WHERE store_id=$1 AND source_batch_id=ANY($2::uuid[]) ORDER BY recorded_at,id', store, event_ids)
        states = {s['fill']['id']:s for s in await prep_containers.fill_states(conn,store,[row['id'] for row in rows])} if rows else {}
        for row in rows:
            state = states[str(row['id'])]
            last = state['moves'][-1] if state['moves'] else None
            # Only name a candidate for the existing preview. Never promise a chain
            # of undos: the immutable undo itself becomes the latest movement.
            candidate = None
            if not state['voided']:
                if not last: candidate = 'void_fill'
                elif last['action'] in ('send','return','unpack'): candidate = 'undo'
                elif last['action'] == 'waste' and state.get('waste_history'): candidate = 'undo_waste'
            containers.append({**state, 'nextPreviewAction': candidate,
                'reviewNote': 'Preview the latest original movement at its original instant. Later allocation can still hold reversal.' if candidate else
                              'No supported next reversal is inferred. Preserve history and review recovery.'})
    tasks = []
    if coverage['tasks']:
        for row in await conn.fetch('''SELECT id,list_id,task_id,batch_root_id,batch_event_id,action,revision
            FROM prep_inventory.execution_events WHERE store_id=$1 AND batch_root_id=ANY($2::uuid[])
            AND action IN ('complete','link') ORDER BY list_id,revision''', store, ids):
            link = dict(row)
            progress = await conn.fetchval("SELECT to_regprocedure('prep_inventory.task_progress(uuid)') IS NOT NULL")
            acknowledged = row['batch_event_id']
            if progress:
                acknowledged = await conn.fetchval('''SELECT batch_event_id FROM prep_inventory.execution_events
                    WHERE store_id=$1 AND link_event_id=$2 AND action='reconcile' ORDER BY revision DESC LIMIT 1''', store, row['id']) or acknowledged
            tasks.append({**link, 'acknowledgedBatchId': acknowledged, 'currentBatchId': current[row['batch_root_id']]['id'],
                'needsReconciliation': acknowledged != current[row['batch_root_id']]['id'], 'reconciliationSupported': bool(progress)})
    decisions = []
    if coverage['staffProduction']:
        decisions = [dict(r) for r in await conn.fetch('''SELECT id,submission_id,batch_event_id,execution_event_id,decision
            FROM prep_inventory.staff_production_decisions WHERE store_id=$1 AND batch_event_id=ANY($2::uuid[]) ORDER BY recorded_at,id''', store, event_ids)]
    periods = []
    if coverage['periods']:
        import prep_period_journal
        # Conservative interval review matches saved period source-history inclusion,
        # including exact endpoints. Reopened snapshots remain visible as history.
        instants = [r['performed_at'] for r in history] + [r['performed_at'] for r in waste]
        rows = await conn.fetch('''SELECT c.*,EXISTS(SELECT 1 FROM prep_inventory.period_reopenings r
            WHERE r.store_id=c.store_id AND c.id=ANY(r.closure_ids)) AS reopened
            FROM prep_inventory.period_closures c JOIN prep_inventory.observations a ON a.id=c.opening_count_id
            JOIN prep_inventory.observations b ON b.id=c.closing_count_id WHERE c.store_id=$1
            AND EXISTS(SELECT 1 FROM unnest($2::timestamptz[]) t WHERE t BETWEEN a.performed_at AND b.performed_at)
            ORDER BY c.ordinal''', store, instants)
        for row in rows:
            periods.append({'id': row['id'], 'ordinal': row['ordinal'], 'reopened': row['reopened'],
                'freshness': await prep_period_journal.freshness(conn, dict(row)),
                'effect': 'Saved facts stay immutable; a correction can stale this interval. Reopen from the earliest affected active period and include following periods before replacement.'})
    try:
        await batches.predecessor(conn, store, event_id)
        gate = {'status': 'eligible_for_preview', 'reason': 'No current allocation hold. Review the proposed correction; this is not approval.'}
    except HTTPException as e:
        gate = {'status': 'held', 'reason': str(e.detail)}
    result = serial({'store_id': store, 'selectedEventId': event_id, 'currentEventId': current[selected['root_id']]['id'],
        'gate': gate, 'coverage': {k: 'installed' if v else 'not_installed' for k,v in coverage.items()},
        'lots': [{**r, 'recordedAllocatedQuantity': await conn.fetchval('SELECT prep_inventory.lot_used($1)', r['id'])} for r in current.values()],
        'batchHistory': history, 'preparedInputHistory': edges, 'wasteHistory': waste, 'containers': containers,
        'taskLinks': tasks, 'staffDecisions': decisions, 'savedPeriods': periods,
        'readOnly': True, 'track1Writeback': False, 'automaticCascade': False,
        'scope': 'Production/opening lot dependencies, including conservative historical descendants. Counts, recipe changes and purchased corrections use their separate workflows.'})
    return {**result, 'reviewHash': fingerprint(result).hex()}
