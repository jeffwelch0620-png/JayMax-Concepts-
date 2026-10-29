"""Evening prep count zones: where prepared food is kept, in walk order (Bert's Salad Bar:
Walk-in, Cooler, Below bar, Salad station). Zone quantities add up to the one count line."""
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, field_validator
import prep_mapping as mapping
from actual_inventory_api import location_code
from purchase_api import serial
from purchase_parser import fingerprint


class ZoneQuantity(mapping.Strict):
    zone_code: str = Field(min_length=1, max_length=60)
    quantity: Decimal = Field(ge=0, max_digits=28, decimal_places=12)

    @field_validator('quantity')
    @classmethod
    def finite(cls, value):
        if not value.is_finite(): raise ValueError('Use a finite decimal')
        return value


class ZoneIn(mapping.Strict):
    name: str = Field(min_length=1, max_length=120)
    product_ids: list[UUID] = Field(default_factory=list, max_length=500)

    @field_validator('name')
    @classmethod
    def named(cls, value):
        if not value.strip(): raise ValueError('Name each zone')
        return value.strip()


class ZoneLayoutIn(mapping.Strict):
    note: str = Field(min_length=1, max_length=2000)
    zones: list[ZoneIn] = Field(min_length=1, max_length=50)


async def installed(conn):
    return await conn.fetchval("SELECT to_regclass('prep_inventory.count_zone_quantities') IS NOT NULL")


async def get_layout(conn, store, layout_id=None):
    if not await installed(conn): return None
    header = await conn.fetchrow('''SELECT * FROM prep_inventory.zone_layouts WHERE store_id=$1
        AND ($2::uuid IS NULL OR id=$2) ORDER BY revision DESC LIMIT 1''', store, layout_id)
    if header is None:
        if layout_id: raise HTTPException(422, 'Zone layout not found at this location')
        return None
    zones = await conn.fetch('SELECT * FROM prep_inventory.zone_layout_zones WHERE layout_id=$1 ORDER BY walk_position', header['id'])
    placed = await conn.fetch('SELECT * FROM prep_inventory.zone_layout_placements WHERE layout_id=$1 ORDER BY zone_code,item_position', header['id'])
    return serial({'header': dict(header), 'zones': [{**dict(z), 'product_ids': [p['product_id'] for p in placed if p['zone_code'] == z['zone_code']]} for z in zones]})


async def proposed_layout(conn, store):
    """Start from the previous layout; prepared items it does not place go to a Walk-in zone.
    Nothing is saved until a manager confirms it."""
    previous = await get_layout(conn, store)
    products = [str(r['id']) for r in await conn.fetch('SELECT id FROM prep_inventory.products WHERE store_id=$1 ORDER BY created_at,id', store)]
    zones = [{'name': z['name'], 'product_ids': [p for p in z['product_ids'] if p in products]} for z in (previous or {}).get('zones', [])]
    placed = {p for z in zones for p in z['product_ids']}
    missing = [p for p in products if p not in placed]
    if missing:
        walk_in = next((z for z in zones if z['name'].lower() == 'walk-in'), None)
        if walk_in is None: walk_in = {'name': 'Walk-in', 'product_ids': []}; zones.insert(0, walk_in)
        walk_in['product_ids'] += missing
    return {'zones': [z for z in zones if z['product_ids']]}


async def save_layout(conn, store, actor, body, key, digest):
    prior = await conn.fetchrow('SELECT * FROM prep_inventory.zone_layouts WHERE request_key=$1', key)
    if prior:
        if prior['store_id'] != store or prior['request_fingerprint'] != digest:
            raise HTTPException(409, 'This request key was used for a different record. Check the saved outcome before retrying.')
        return await get_layout(conn, store, prior['id'])
    products = {r['id'] for r in await conn.fetch('SELECT id FROM prep_inventory.products WHERE store_id=$1', store)}
    zones = [z for z in body.zones if z.product_ids]
    codes = [location_code(z.name) for z in zones]
    if len(set(codes)) != len(codes): raise HTTPException(422, 'Give each zone a distinct name')
    for zone in zones:
        if len(set(zone.product_ids)) != len(zone.product_ids): raise HTTPException(422, f'List each prepared item once in {zone.name}')
        if not set(zone.product_ids) <= products: raise HTTPException(422, f'{zone.name} lists a prepared item from another location')
    if not products <= {p for z in zones for p in z.product_ids}:
        raise HTTPException(422, 'Place every prepared item in at least one zone')
    revision = await conn.fetchval('SELECT coalesce(max(revision),0)+1 FROM prep_inventory.zone_layouts WHERE store_id=$1', store)
    layout_id = await conn.fetchval('''INSERT INTO prep_inventory.zone_layouts(store_id,revision,note,request_key,request_fingerprint,confirmed_by)
        VALUES($1,$2,$3,$4,$5,$6) RETURNING id''', store, revision, body.note, key, digest, actor)
    for position, (zone, code) in enumerate(zip(zones, codes), 1):
        await conn.execute('INSERT INTO prep_inventory.zone_layout_zones(layout_id,zone_code,name,walk_position) VALUES($1,$2,$3,$4)',
                           layout_id, code, zone.name, position)
        await conn.executemany('''INSERT INTO prep_inventory.zone_layout_placements(layout_id,store_id,zone_code,product_id,item_position)
            VALUES($1,$2,$3,$4,$5)''', [(layout_id, store, code, p, n) for n, p in enumerate(zone.product_ids, 1)])
    return await get_layout(conn, store, layout_id)


def placements(layout):
    found = {}
    for zone in layout['zones']:
        for product in zone['product_ids']: found.setdefault(product, []).append(zone['zone_code'])
    return found


def zone_total(product_name, placed, zones):
    """Checks one count line's zones against the layout and returns its total."""
    given = [z.zone_code for z in zones]
    if len(set(given)) != len(given) or set(given) != set(placed):
        raise HTTPException(422, f'Enter one quantity (0 if empty) for each zone of {product_name}')
    return sum((z.quantity for z in zones), Decimal(0))


def layout_digest(body, actor):
    return fingerprint({'body': body.model_dump(mode='json'), 'actor': actor, 'kind': 'prep_zone_layout'})
