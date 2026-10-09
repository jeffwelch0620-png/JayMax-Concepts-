"""Versioned manual sales forecasts; no inventory or accounting writeback."""
import hashlib,json,re
from datetime import date
from decimal import Decimal
from typing import Annotated
from pydantic import BaseModel,BeforeValidator,Field
from fastapi import HTTPException
from purchase_api import serial

def number(value):
    if isinstance(value,bool):raise ValueError('A forecast amount must be a number')
    return value

class ForecastIn(BaseModel):
    date: date
    amount: Annotated[Decimal,BeforeValidator(number)] = Field(ge=0,max_digits=12,decimal_places=2,allow_inf_nan=False)
    note: str = Field(default='',max_length=2000)
    enteredBy: str = ''  # Compatibility input; PostgreSQL attributes the signed actor.

def version(store,day,row):
    value={'storeId':store,'date':str(day),'stored':serial(dict(row)) if row else None}
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def document(rid,row):
    return {'restaurantId':rid,'storeId':row['store_id'],'date':str(row['date']),
        'amount':str(row['amount']),'note':row['note'],'enteredBy':row['entered_by'],
        'updatedAt':serial(row['updated_at']),'sourceVersion':version(row['store_id'],row['date'],row),
        'basis':'manual_sales_forecast','accounting':False}

def reviewed(rid,store,day,row):
    return {'restaurantId':rid,'storeId':store,'date':str(day),'sourceVersion':version(store,day,row),
        'projection':document(rid,row) if row else None,'basis':'manual_sales_forecast','accounting':False}

async def review(pool,rid,store,day):
    async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):
        row=await conn.fetchrow('SELECT * FROM public.store_sales_projections WHERE store_id=$1 AND date=$2',store,day)
        return reviewed(rid,store,day,row)

async def save(pool,rid,store,body,expected,actor):
    if expected is None:raise HTTPException(428,'Review this date and supply its forecast version before saving')
    expected=expected.strip('"')
    if not re.fullmatch('[a-f0-9]{64}',expected):raise HTTPException(422,'Supply the reviewed forecast version')
    async with pool.acquire() as conn,conn.transaction():
        # Serialize same-date inserts as well as updates. No table-wide lock or
        # extra stores UPDATE privilege is needed. Row locks cover existing data.
        await conn.execute("SET LOCAL statement_timeout='20s'")
        await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))','manual_forecast:'+store+':'+str(body.date))
        row=await conn.fetchrow('SELECT * FROM public.store_sales_projections WHERE store_id=$1 AND date=$2 FOR UPDATE',store,body.date)
        if expected!=version(store,body.date,row):raise HTTPException(409,'This forecast changed. Refresh its date and review your draft before saving')
        values=(store,body.date,body.amount.quantize(Decimal('.01')),body.note,actor)
        if row:
            row=await conn.fetchrow('UPDATE public.store_sales_projections SET amount=$3,note=$4,entered_by=$5,updated_at=clock_timestamp() WHERE store_id=$1 AND date=$2 RETURNING *',*values)
        else:
            row=await conn.fetchrow('INSERT INTO public.store_sales_projections(store_id,date,amount,note,entered_by) VALUES($1,$2,$3,$4,$5) RETURNING *',*values)
        return {'ok':True,**reviewed(rid,store,body.date,row)}
