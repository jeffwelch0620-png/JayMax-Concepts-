"""Measured container contents and internal service transfers; no accounting writes."""
import os
from workflow_integrity import conflict_transaction
from datetime import datetime, date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Header, HTTPException, Request
from pydantic import Field, model_validator, field_validator
import prep_mapping as mapping
import prep_batches as batches
import prep_observations as observations
from prep_openings import source_valid, activity_time
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint


class DefinitionIn(mapping.Strict):
    action: Literal['definition']
    predecessor_id: UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    capacity_unit: mapping.UNITS
    stated_capacity: Decimal | None = Field(default=None, gt=0, max_digits=28, decimal_places=12)
    brimful_capacity: Decimal | None = Field(default=None, gt=0, max_digits=28, decimal_places=12)
    usable_capacity: Decimal | None = Field(default=None, gt=0, max_digits=28, decimal_places=12)
    evidence: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def capacities(self):
        if self.usable_capacity is not None and self.brimful_capacity is not None and self.usable_capacity > self.brimful_capacity:
            raise ValueError('Usable capacity cannot exceed measured brimful capacity')
        return self


class ProfileIn(mapping.Strict):
    action: Literal['profile']
    predecessor_id: UUID | None = None
    definition_id: UUID
    product_version_id: UUID
    unit_profile_id: UUID
    usable_quantity: Decimal = mapping.POSITIVE
    evidence: str = Field(min_length=1, max_length=2000)
    product_fill_measured: Literal[True]


class FillIn(observations.Stamp):
    action: Literal['fill']
    profile_id: UUID
    source_batch_id: UUID
    label: str = Field(min_length=1, max_length=160)
    quantity: Decimal = mapping.POSITIVE
    contents_measured: Literal[True]


class MoveIn(observations.Stamp):
    action: Literal['send', 'return', 'unpack', 'void_fill', 'undo', 'undo_waste']
    fill_id: UUID
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=28, decimal_places=12)
    target_move_id: UUID | None = None

    @model_validator(mode='after')
    def shape(self):
        if self.action in ('send', 'return', 'unpack'):
            if self.quantity is None or self.target_move_id is not None: raise ValueError('Movement needs a measured quantity only')
        elif self.action in ('undo','undo_waste'):
            if self.quantity is not None or self.target_move_id is None: raise ValueError('Undo requires the latest original movement')
        elif self.quantity is not None or self.target_move_id is not None:
            raise ValueError('Void fill reverses an unused fill in full')
        return self


class WasteIn(observations.Stamp):
    action: Literal['waste']
    fill_id: UUID
    quantity: Decimal = mapping.POSITIVE
    compartment: Literal['storage','service']
    category: Literal['storage_spoilage','service_discard','other']
    contents_measured: Literal[True]

    @field_validator('contents_measured','calendar_date_confirmed',mode='before')
    @classmethod
    def explicit_measurement(cls,value):
        if value is not True: raise ValueError('Explicit measured loss and calendar confirmation are required')
        return value

    @model_validator(mode='after')
    def category_matches(self):
        if (self.category=='storage_spoilage' and self.compartment!='storage') or (self.category=='service_discard' and self.compartment!='service'):
            raise ValueError('Waste category must match its storage or service compartment')
        return self


Body = Annotated[DefinitionIn | ProfileIn | FillIn | MoveIn | WasteIn, Field(discriminator='action')]


class CommandIn(mapping.Strict):
    body: Body
    expected_review_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]

    @field_validator('reviewed', mode='before')
    @classmethod
    def explicit(cls, value):
        if value is not True: raise ValueError('Explicit review is required')
        return value


def enabled():
    return observations.enabled() and os.getenv('PREP_CONTAINERS_ENABLED', 'false').lower() == 'true'


async def ready(conn):
    await observations.ready(conn)
    if not await conn.fetchval("SELECT to_regclass('prep_inventory.container_moves') IS NOT NULL"):
        raise HTTPException(503, 'Native containers await schema setup')


async def hold_legacy(conn):
    if os.getenv('PREP_CONTAINERS_ENABLED', 'false').lower() == 'true' or await conn.fetchval("SELECT to_regclass('prep_inventory.container_moves') IS NOT NULL"):
        raise HTTPException(409, 'Legacy container/stock writes are held; use reviewed native prep facts')


async def current(conn, table, store, ident):
    row = await conn.fetchrow(f'SELECT * FROM prep_inventory.{table} WHERE id=$1 AND store_id=$2', ident, store)
    if not row: raise HTTPException(422, 'Container definition/profile is not at this location')
    if await conn.fetchval(f'SELECT 1 FROM prep_inventory.{table} WHERE predecessor_id=$1', ident):
        raise HTTPException(409, 'Container setup changed; select its current version')
    return dict(row)


def move_record(row):
    result = dict(row)
    # Preserve earlier reviewed movement JSON and exact retry acknowledgements.
    if result.get('compartment') is None: result.pop('compartment',None)
    return result


def contents_state(row, moves, history):
    storage = batches.exact_sum([row['base_quantity']] + [x['storage_delta'] for x in moves])
    service = batches.exact_sum(x['service_delta'] for x in moves)
    result = dict(fill=dict(row), moves=moves, storage=storage, service=service, allocated=batches.exact_sum([storage, service]), revision=len(moves), voided=any(x['action']=='void_fill' for x in moves))
    if history: result['waste_history'] = history
    return serial(result)


async def fill_states(conn, store, identities=None):
    rows = await conn.fetch('''SELECT * FROM prep_inventory.container_fills WHERE store_id=$1
        AND ($2::uuid[] IS NULL OR id=ANY($2)) ORDER BY recorded_at DESC,id''',store,identities)
    ids = [row['id'] for row in rows]
    moves, losses = {ident:[] for ident in ids}, {ident:[] for ident in ids}
    if ids:
        for move in await conn.fetch('''SELECT m.* FROM prep_inventory.container_moves m
            JOIN prep_inventory.container_fills f ON f.id=m.fill_id WHERE f.store_id=$1 AND f.id=ANY($2::uuid[])
            ORDER BY m.fill_id,m.revision''',store,ids):
            moves[move['fill_id']].append(move_record(move))
        if await conn.fetchval("SELECT to_regclass('prep_inventory.container_waste_links') IS NOT NULL"):
            links = await conn.fetch('''SELECT m.fill_id,l.* FROM prep_inventory.container_waste_links l
                JOIN prep_inventory.container_moves m ON m.id=l.move_id
                WHERE l.store_id=$1 AND m.fill_id=ANY($2::uuid[]) ORDER BY m.fill_id,m.revision''',store,ids)
            # Ordinary rows preserve Decimal/timestamp codecs, including custom numeric
            # domains that asyncpg cannot decode inside PostgreSQL composite records.
            events = {row['id']:dict(row) for row in await conn.fetch('''SELECT o.* FROM prep_inventory.observations o
                JOIN prep_inventory.container_waste_links l ON l.observation_id=o.id
                JOIN prep_inventory.container_moves m ON m.id=l.move_id
                WHERE l.store_id=$1 AND m.fill_id=ANY($2::uuid[])''',store,ids)}
            for row in links:
                link = dict(row); ident = link.pop('fill_id')
                losses[ident].append(dict(link=link,event=events[link['observation_id']]))
    return [contents_state(row,moves[row['id']],losses[row['id']]) for row in rows]


async def fill_state(conn, store, ident):
    states = await fill_states(conn,store,[ident])
    if not states: raise HTTPException(404, 'Filled container is not at this location')
    return states[0]


async def preview(conn, store, body):
    await ready(conn)
    action = body.action
    facts = {}
    sources = {}
    waste_plan = None
    if body.action in ('waste','undo_waste') and not await conn.fetchval("SELECT to_regclass('prep_inventory.container_waste_links') IS NOT NULL"):
        raise HTTPException(503, 'Direct container waste awaits schema setup')
    if action == 'definition':
        old = await current(conn, 'container_definitions', store, body.predecessor_id) if body.predecessor_id else None
        facts = body.model_dump(exclude={'action'}) | dict(root_id=old['root_id'] if old else None, revision=old['revision']+1 if old else 1)
        sources = {'prior': old}
        table = 'container_definitions'
    elif action == 'profile':
        definition = await current(conn, 'container_definitions', store, body.definition_id)
        product = await mapping.current_product(conn, store, body.product_version_id)
        unit = await mapping.current_profile(conn, store, body.unit_profile_id, body.product_version_id)
        old = await current(conn, 'container_profiles', store, body.predecessor_id) if body.predecessor_id else None
        if old and (old['container_root_id'], old['product_id']) != (definition['root_id'], product['product_id']):
            raise HTTPException(422, 'Fill profile revision must retain container and prepared identity')
        if not old and await conn.fetchval('SELECT 1 FROM prep_inventory.container_profiles WHERE container_root_id=$1 AND product_id=$2', definition['root_id'], product['product_id']):
            raise HTTPException(409, 'Revise the existing product fill profile')
        usable = mapping.times(body.usable_quantity, unit['base_units_per_source_unit'])
        # Capacity and food measurements can have different dimensions. A measured
        # product-specific profile is always required; density is never guessed.
        if definition['usable_capacity'] is not None and mapping.DIMENSIONS[definition['capacity_unit']] == mapping.DIMENSIONS[product['base_unit']]:
            capacity = mapping.times(definition['usable_capacity'], mapping.SIZES[definition['capacity_unit']])
            filled = mapping.times(usable, mapping.SIZES[product['base_unit']])
            if filled > capacity: raise HTTPException(422, 'Measured usable food fill exceeds the verified usable container capacity')
        facts = dict(predecessor_id=body.predecessor_id, root_id=old['root_id'] if old else None, revision=old['revision']+1 if old else 1,
                     definition_id=body.definition_id, container_root_id=definition['root_id'], product_version_id=body.product_version_id,
                     product_id=product['product_id'], unit_profile_id=body.unit_profile_id, source_unit=unit['source_unit'], base_unit=product['base_unit'],
                     factor=unit['base_units_per_source_unit'], usable_quantity=body.usable_quantity, usable_base_quantity=usable, evidence=body.evidence)
        sources = dict(definition=definition, product=product, unit=unit, prior=old)
        table = 'container_profiles'
    elif action == 'fill':
        profile = await current(conn, 'container_profiles', store, body.profile_id)
        definition = await current(conn, 'container_definitions', store, profile['definition_id'])
        product = await mapping.current_product(conn, store, profile['product_version_id'])
        unit = await mapping.current_profile(conn, store, profile['unit_profile_id'], profile['product_version_id'])
        await activity_time(conn, store, body.performed_at)
        lot = await conn.fetchrow('SELECT * FROM prep_inventory.batch_events WHERE id=$1 AND store_id=$2 AND product_id=$3', body.source_batch_id, store, profile['product_id'])
        if not lot or lot['kind']=='void' or await conn.fetchval('SELECT 1 FROM prep_inventory.batch_events WHERE predecessor_id=$1', lot['id']) or lot['performed_at'] > body.performed_at or not await source_valid(conn, dict(lot)):
            raise HTTPException(422, 'Choose current recorded prep output produced before filling')
        quantity = mapping.times(body.quantity, profile['factor'])
        available = await batches.available(conn, lot['id'], body.performed_at)
        if quantity > profile['usable_base_quantity']: raise HTTPException(422, 'Measured contents exceed the verified product fill limit')
        if quantity > available: raise HTTPException(409, 'Recorded lot lacks unallocated output for this fill')
        facts = dict(profile_id=body.profile_id, source_batch_id=body.source_batch_id, product_id=profile['product_id'], base_unit=profile['base_unit'],
                     label=body.label, quantity=body.quantity, factor=profile['factor'], base_quantity=quantity, performed_at=body.performed_at,
                     business_date=body.business_date, timezone_name=body.timezone_name, note=body.note)
        sources = dict(profile=profile, definition=definition, product=product, unit=unit, lot={k:lot[k] for k in ('id','review_hash','performed_at','product_id','base_unit')}, available=available)
        table = 'container_fills'
    else:
        state = await fill_state(conn, store, body.fill_id)
        fill = state['fill']
        if state['voided']: raise HTTPException(409, 'Fill was voided; its history remains unchanged')
        if body.timezone_name != fill['timezone_name']: raise HTTPException(422, 'Retain the container location timezone')
        q = mapping.times(body.quantity, Decimal(fill['factor'])) if body.quantity is not None else None
        storage, service = Decimal(state['storage']), Decimal(state['service'])
        ds, dv = Decimal(0), Decimal(0)
        if action == 'send': ds, dv = q.copy_negate(), q
        elif action == 'return': ds, dv = q, q.copy_negate()
        elif action == 'unpack': ds = q.copy_negate()
        elif action == 'waste':
            if body.compartment=='storage': ds = q.copy_negate()
            else: dv = q.copy_negate()
        elif action == 'void_fill':
            if state['moves'] or body.performed_at != datetime.fromisoformat(fill['performed_at']): raise HTTPException(409, 'Void fill requires no movements and its original physical instant')
            ds = Decimal(fill['base_quantity']).copy_negate()
        else:
            extended = action == 'undo_waste' and await conn.fetchval("SELECT to_regprocedure('prep_inventory.can_reverse_container_waste(uuid,uuid)') IS NOT NULL")
            if extended:
                target = next((move for move in state['moves'] if move['id'] == str(body.target_move_id)), None)
                if not target or not await conn.fetchval('SELECT prep_inventory.can_reverse_container_waste($1,$2)', body.fill_id, body.target_move_id):
                    raise HTTPException(409, 'Choose an unreversed container loss with no later quantity-changing dependencies')
            else:
                target = state['moves'][-1] if state['moves'] else None
            allowed = ('waste',) if action=='undo_waste' else ('send','return','unpack')
            if not target or target['id'] != str(body.target_move_id) or target['action'] not in allowed:
                raise HTTPException(409, 'Undo requires an eligible original movement; older waste corrections require the correction migration')
            if body.performed_at != datetime.fromisoformat(target['performed_at']): raise HTTPException(422, 'Undo retains the original movement instant')
            ds, dv = Decimal(target['storage_delta']).copy_negate(), Decimal(target['service_delta']).copy_negate()
        if action not in ('undo','undo_waste','void_fill') and body.performed_at < max(datetime.fromisoformat(x['performed_at']) for x in [fill]+state['moves']):
            raise HTTPException(422, 'Movement must follow recorded container activity')
        after_storage, after_service = batches.exact_sum([storage,ds]), batches.exact_sum([service,dv])
        if min(after_storage, after_service) < 0: raise HTTPException(409, 'Movement exceeds recorded contents in its source location')
        if action == 'undo_waste' and batches.exact_sum([after_storage, after_service]) > Decimal(fill['base_quantity']):
            raise HTTPException(409, 'Waste reversal would exceed the original measured fill')
        lot = await conn.fetchrow('SELECT * FROM prep_inventory.batch_events WHERE id=$1', UUID(fill['source_batch_id']))
        if not await source_valid(conn, dict(lot)) or lot['kind']=='void' or await conn.fetchval('SELECT 1 FROM prep_inventory.batch_events WHERE predecessor_id=$1', lot['id']):
            raise HTTPException(409, 'Source lot changed; review dependencies before moving contents')
        delta = batches.exact_sum([ds,dv])
        if action != 'undo_waste' and delta > 0 and delta > await batches.available(conn, lot['id'], body.performed_at): raise HTTPException(409, 'Released output has since been allocated; undo is held')
        if action=='waste':
            profile = await conn.fetchrow('SELECT * FROM prep_inventory.container_profiles WHERE id=$1',UUID(fill['profile_id']))
            obs = observations.WasteIn(**body.model_dump(exclude={'action','fill_id','compartment','contents_measured'}),source_kind='prepared',
                product_version_id=profile['product_version_id'],profile_id=profile['unit_profile_id'],source_batch_id=lot['id'],
                source_unit=profile['source_unit'],factor=Decimal(fill['factor']),measurement_basis='measured',already_included_in_batch=False)
            waste_plan = await observations.preview(conn,store,'waste',obs,container_fill_id=body.fill_id)
        elif action=='undo_waste':
            link = await conn.fetchrow('SELECT * FROM prep_inventory.container_waste_links WHERE move_id=$1',UUID(target['id']))
            if not link: raise HTTPException(409, 'Waste movement lacks its paired journal entry; review recovery')
            waste_plan = await observations.preview(conn,store,'waste',old_id=link['observation_id'],
                change=observations.ChangeIn(kind='void',reason=body.note),container_fill_id=body.fill_id)
            sources['undo_of_command_id'] = str(link['command_id'])
        facts = dict(fill_id=body.fill_id, revision=state['revision']+1, action=action, quantity=body.quantity,
                     target_move_id=getattr(body,'target_move_id',None), storage_delta=ds, service_delta=dv, performed_at=body.performed_at,
                     business_date=body.business_date, timezone_name=body.timezone_name, note=body.note)
        if action=='waste': facts['compartment'] = body.compartment
        elif action=='undo_waste': facts['compartment'] = target['compartment']
        sources.update(before=state, after=dict(storage=after_storage, service=after_service), available=await batches.available(conn, lot['id']))
        table = 'container_moves'
    if isinstance(body, observations.Stamp):
        policy = await conn.fetchval('SELECT timezone_name FROM prep_inventory.batch_policies WHERE store_id=$1', store)
        if policy != body.timezone_name: raise HTTPException(409, 'Use the confirmed location calendar-day timezone')
    # Keep numeric representations aligned with PostgreSQL numeric::text.
    for k,v in facts.items():
        if isinstance(v, Decimal): facts[k] = format(v,'f')
    plan = serial(dict(store_id=store, action=action, table=table, body=body.model_dump(mode='json'), facts=facts, sources=sources, accountingEffect='none', consumptionEffect='none'))
    if waste_plan: plan.update(waste=waste_plan['review'],wasteReviewHash=waste_plan['reviewHash'],wasteEffect='measured_loss' if action=='waste' else 'reverse_loss')
    return dict(review=plan, reviewHash=fingerprint(plan).hex())


async def setup(conn, store):
    await ready(conn)
    foundation = await mapping.setup(conn, store)
    definitions = [dict(x) for x in await conn.fetch('SELECT d.*,NOT EXISTS(SELECT 1 FROM prep_inventory.container_definitions n WHERE n.predecessor_id=d.id) AS current FROM prep_inventory.container_definitions d WHERE store_id=$1 ORDER BY name,revision,id', store)]
    profiles = [dict(x) for x in await conn.fetch('SELECT d.*,NOT EXISTS(SELECT 1 FROM prep_inventory.container_profiles n WHERE n.predecessor_id=d.id) AS current FROM prep_inventory.container_profiles d WHERE store_id=$1 ORDER BY root_id,revision', store)]
    current_definitions = {d['id'] for d in definitions if d['current']}
    current_products = {d['id'] for d in foundation['products']}
    current_units = {(u['id'],u['product_version_id']) for u in foundation['profiles']}
    for p in profiles:
        p['reviewNeeded'] = not (p['current'] and p['definition_id'] in current_definitions
            and str(p['product_version_id']) in current_products
            and (str(p['unit_profile_id']),str(p['product_version_id'])) in current_units)
    fills = await fill_states(conn,store)
    batch = await batches.setup(conn, store)
    contents_by_lot = {}
    for state in fills:
        contents_by_lot.setdefault(state['fill']['source_batch_id'],[]).append(state)
    for lot in batch['lots']:
        contents = contents_by_lot.get(lot['id'],[])
        storage = batches.exact_sum(Decimal(s['storage']) for s in contents)
        service = batches.exact_sum(Decimal(s['service']) for s in contents)
        lot.update(containerStorage=storage,containerService=service,totalRemainingRecordedQuantity=batches.exact_sum([Decimal(lot['remainingRecordedQuantity']),storage,service]))
    return serial(dict(store_id=store, definitions=definitions, profiles=profiles, fills=fills, products=foundation['products'], units=foundation['profiles'], lots=batch['lots'], policy=batch['policy'], directWasteSupported=bool(await conn.fetchval("SELECT to_regclass('prep_inventory.container_waste_links') IS NOT NULL")),
        directWasteCorrectionSupported=bool(await conn.fetchval("SELECT to_regprocedure('prep_inventory.can_reverse_container_waste(uuid,uuid)') IS NOT NULL")),
        quantityBasis='Uncontained lot output plus recorded container contents; service transfers are not consumption'))


def install_routes(router, context):

    async def ctx(request, store, write=False):
        actor, pool = await context(request,store,write)
        if not enabled(): raise HTTPException(503, 'Native containers await enablement')
        return actor, pool

    @router.get('/{store_id}/prep-containers')
    async def get(store_id: str, request: Request):
        _, pool = await ctx(request,store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True): return await setup(conn,store_id)

    @router.post('/{store_id}/prep-containers/preview')
    async def review(store_id: str, body: Body, request: Request):
        _, pool = await ctx(request,store_id,True)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True): return await preview(conn,store_id,body)

    @router.post('/{store_id}/prep-containers/commands')
    async def save(store_id: str, body: CommandIn, request: Request, key: UUID = Header(alias='Idempotency-Key')):
        actor, pool = await ctx(request,store_id,True)
        digest = fingerprint(body.model_dump(mode='json'))
        async with pool.acquire() as conn:
            async with conflict_transaction(conn):
                await ready(conn)
                await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', str(key))
                await lock_store(conn,store_id)
                prior = await conn.fetchrow('SELECT * FROM prep_inventory.container_commands WHERE request_key=$1', key)
                if prior:
                    if prior['store_id'] != store_id or prior['recorded_by'] != actor or prior['request_fingerprint'] != digest: raise HTTPException(409, 'Request key already belongs to another container command')
                    command = dict(prior)
                    replayed = True
                else:
                    await conn.execute('LOCK TABLE public.items,public.store_items,public.dishes,public.dish_lines,public.prep_items IN SHARE MODE')
                    plan = await preview(conn,store_id,body.body)
                    if plan['reviewHash'] != body.expected_review_hash: raise HTTPException(409, 'Container facts changed; refresh and review again')
                    ident, child_id = uuid4(), uuid4()
                    command = dict(await conn.fetchrow('''INSERT INTO prep_inventory.container_commands(id,store_id,action,result_id,review_snapshot,review_hash,recorded_by,request_key,request_fingerprint)
                        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *''', ident,store_id,body.body.action,child_id,plan['review'],bytes.fromhex(plan['reviewHash']),actor,key,digest))
                    facts = plan['review']['facts'].copy()
                    if 'root_id' in facts and facts['root_id'] is None: facts['root_id'] = str(child_id)
                    types = {'quantity','factor','base_quantity','usable_quantity','usable_base_quantity','storage_delta','service_delta','stated_capacity','brimful_capacity','usable_capacity'}
                    values = [UUID(v) if k.endswith('_id') and v else Decimal(v) if k in types and v is not None else datetime.fromisoformat(v) if k=='performed_at' else date.fromisoformat(v) if k=='business_date' else v for k,v in facts.items()]
                    columns = ['id','command_id','store_id'] + list(facts)
                    table = plan['review']['table']
                    await conn.execute(f"INSERT INTO prep_inventory.{table}({','.join(columns)}) VALUES({','.join('$'+str(n) for n in range(1,len(columns)+1))})",child_id,ident,store_id,*values)
                    if body.body.action in ('waste','undo_waste'):
                        p = plan['review']
                        obs = await observations.persist(conn,store_id,dict(review=p['waste'],reviewHash=p['wasteReviewHash']),key,digest,actor)
                        await conn.execute('''INSERT INTO prep_inventory.container_waste_links(command_id,store_id,move_id,observation_id,undo_of_command_id)
                            VALUES($1,$2,$3,$4,$5)''',ident,store_id,child_id,UUID(obs['event']['id']),UUID(p['sources']['undo_of_command_id']) if body.body.action=='undo_waste' else None)
                    await conn.execute('UPDATE public.store_state SET revision=revision+1 WHERE store_id=$1',store_id)
                    replayed = False
                plan = command['review_snapshot']
                result = dict(await conn.fetchrow(f"SELECT * FROM prep_inventory.{plan['table']} WHERE id=$1",command['result_id']))
                if plan['table']=='container_moves': result=move_record(result)
                fill_id = result['id'] if plan['table']=='container_fills' else result['fill_id'] if plan['table']=='container_moves' else None
                reply = dict(command=command,result=result,current=await fill_state(conn,store_id,fill_id) if fill_id else None,replayed=replayed)
                if command['action'] in ('waste','undo_waste'):
                    link = await conn.fetchrow('SELECT * FROM prep_inventory.container_waste_links WHERE command_id=$1',command['id'])
                    reply.update(waste_link=dict(link),waste_event=dict(await conn.fetchrow('SELECT * FROM prep_inventory.observations WHERE id=$1',link['observation_id'])))
                return serial(reply)

    return router
