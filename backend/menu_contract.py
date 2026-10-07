"""Validated legacy menu definitions; no accounting or native prep stock writes."""
from typing import Literal
from uuid import UUID, uuid4
import math

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UNITS = {'lb', 'oz', 'kg', 'g', 'gal', 'qt', 'pt', 'cup', 'fl oz', 'l', 'ml', 'each', 'ct', 'dozen'}


class DishLineIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_type: Literal['item', 'prep']
    item_code: str | None = None
    prep_dish_id: str | None = None
    qty: float = Field(gt=0, allow_inf_nan=False)
    uom: str | None = None

    @field_validator('qty', mode='before')
    @classmethod
    def not_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError('Ingredient quantity must be a number, not a boolean')
        return value

    @model_validator(mode='after')
    def one_source(self):
        if self.source_type == 'item':
            valid = self.item_code and self.item_code.strip() and self.prep_dish_id is None
        else:
            valid = self.prep_dish_id and self.prep_dish_id.strip() and self.item_code is None
        if not valid:
            raise ValueError('Select exactly one ingredient matching its source type')
        return self


class DishIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str | None = None
    client_id: str | None = Field(default=None, min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    menu_code: str | None = None
    recipe_type: Literal['menu', 'prep'] = 'menu'
    price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    target_pct: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    yield_qty: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    yield_uom: str | None = None
    prep_par: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    procedure: str | None = None
    equipment: str | None = None
    shelf_life: str | None = None
    menu_category: str | None = None
    description: str | None = None
    photo_url: str | None = None
    portion_note: str | None = None
    frequency: str | None = None
    lines: list[DishLineIn] = Field(min_length=1, max_length=500)

    @field_validator('price', 'target_pct', 'yield_qty', 'prep_par', mode='before')
    @classmethod
    def not_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError('Recipe numeric fields cannot be booleans')
        return value

    @field_validator('id')
    @classmethod
    def canonical_id(cls, value):
        return str(UUID(value)) if value is not None else None

    @field_validator('name')
    @classmethod
    def named(cls, value):
        if not value.strip():
            raise ValueError('Recipe name is required')
        return value.strip()

    @model_validator(mode='after')
    def yield_contract(self):
        if self.recipe_type == 'prep':
            if self.yield_qty is None or self.yield_uom not in UNITS:
                raise ValueError('Prep recipes need an explicit positive yield and supported yield unit')
        elif self.yield_qty not in (None, 1) or self.yield_uom not in (None, 'each'):
            raise ValueError('Menu definitions are one serving (yield 1 each)')
        return self


async def lock(conn, store_id):
    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1,0))", 'menu-definitions:' + store_id)


async def prepare(conn, store_id, bodies, replace=False):
    """Resolve the entire submitted graph before writing headers, lines or revisions."""
    if len(bodies) > 1000:
        raise HTTPException(422, 'Review at most 1000 recipe definitions per replacement')
    existing = {str(row['id']): dict(row) for row in await conn.fetch('SELECT * FROM dishes WHERE store_id=$1', store_id)}
    graph = {} if replace else {key: {'recipe_type': row['recipe_type'], 'yield_qty': row['yield_qty'], 'yield_uom': row['yield_uom'], 'lines': []} for key, row in existing.items()}
    if not replace:
        for line in await conn.fetch('SELECT l.* FROM dish_lines l JOIN dishes d ON d.id=l.dish_id WHERE d.store_id=$1', store_id):
            graph[str(line['dish_id'])]['lines'].append(dict(line))
    item_codes = {row['item_code'] for row in await conn.fetch('SELECT item_code FROM store_items WHERE store_id=$1', store_id)}
    identities, clients, resolved = set(), {}, []
    for body in bodies:
        if body.id and body.id not in existing:
            raise HTTPException(422, 'Recipe ID does not belong to this restaurant')
        identity = body.id or str(uuid4())
        if identity in identities or (body.client_id and body.client_id in clients):
            raise HTTPException(422, 'Duplicate recipe ID or temporary recipe identity')
        if body.client_id:
            if body.client_id in existing or _is_uuid(body.client_id):
                raise HTTPException(422, 'Temporary recipe identity must not impersonate a saved recipe')
            clients[body.client_id] = identity
        identities.add(identity)
        resolved.append(body.model_copy(update={'id': identity}))
    for index, body in enumerate(resolved):
        lines = [line.model_copy(update={'prep_dish_id': clients.get(line.prep_dish_id, line.prep_dish_id)}) for line in body.lines]
        body = body.model_copy(update={'lines': lines})
        resolved[index] = body
        graph[body.id] = {'recipe_type': body.recipe_type, 'yield_qty': body.yield_qty, 'yield_uom': body.yield_uom, 'lines': [line.model_dump() for line in lines]}
    for identity, node in graph.items():
        if not node['lines']:
            raise HTTPException(422, 'Retained recipes need at least one ingredient; repair or explicitly remove incomplete definitions')
        if node['recipe_type'] == 'prep' and (node['yield_qty'] is None or not math.isfinite(float(node['yield_qty'])) or node['yield_qty'] <= 0 or node['yield_uom'] not in UNITS):
            raise HTTPException(422, 'Retained prep recipes need an explicit positive yield and supported yield unit')
        for line in node['lines']:
            if not math.isfinite(float(line['qty'])) or line['qty'] <= 0:
                raise HTTPException(422, 'Retained ingredient quantities must be finite and greater than zero')
            if line['source_type'] == 'item':
                if line['item_code'] not in item_codes or line['prep_dish_id'] is not None:
                    raise HTTPException(422, 'Ingredient must be a purchased product linked to this restaurant')
                if line.get('uom') not in (None, 'portion'):
                    raise HTTPException(422, 'Inventory recipe quantities are portions; do not silently reinterpret an explicit physical unit')
            elif line['source_type'] == 'prep':
                target = str(line['prep_dish_id']) if line['prep_dish_id'] else None
                if line['item_code'] is not None or target not in graph or graph[target]['recipe_type'] != 'prep':
                    raise HTTPException(422, 'Sub-recipe must be a retained prep recipe at this restaurant')
                if line.get('uom') not in (None, graph[target]['yield_uom']):
                    raise HTTPException(422, 'Sub-recipe quantity unit must match its defined yield unit')
            else:
                raise HTTPException(422, 'Invalid retained ingredient source type')
    # Leaf-first traversal handles unsorted graphs without Python recursion limits.
    dependencies = {identity: {str(line['prep_dish_id']) for line in node['lines'] if line['source_type'] == 'prep'} for identity, node in graph.items()}
    parents = {identity: set() for identity in graph}
    for identity, children in dependencies.items():
        for child in children:
            parents[child].add(identity)
    ready = [identity for identity, children in dependencies.items() if not children]
    visited, depth = set(), {identity: 1 for identity in graph}
    while ready:
        identity = ready.pop()
        visited.add(identity)
        for parent in parents[identity]:
            depth[parent] = max(depth[parent], depth[identity] + 1)
            if depth[parent] > 100:
                raise HTTPException(422, 'Recipe nesting exceeds the supported depth of 100')
            dependencies[parent].remove(identity)
            if not dependencies[parent]:
                ready.append(parent)
    if len(visited) != len(graph):
        raise HTTPException(422, 'Circular prep recipe reference; no recipe changes were saved')
    return resolved, existing


def _is_uuid(value):
    try:
        UUID(value)
        return True
    except ValueError:
        return False
