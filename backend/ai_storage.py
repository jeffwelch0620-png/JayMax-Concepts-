"""Explicit PostgreSQL chat storage availability; no grants or provider calls."""
from fastapi import HTTPException

async def capabilities(pool,store):
    async with pool.acquire() as conn,conn.transaction(readonly=True):
        rights={verb:bool(await conn.fetchval('SELECT has_table_privilege(current_user,$1,$2)','public.ai_chat_messages',verb)) for verb in ('SELECT','INSERT','DELETE')}
    return {'storeId':store,'basis':'ai_conversation_storage','historyAvailable':rights['SELECT'],
        'chatAvailable':rights['SELECT'] and rights['INSERT'],'clearAvailable':rights['DELETE'],
        'accounting':False}

async def require(pool,store,action):
    status=await capabilities(pool,store)
    if not status[action]:raise HTTPException(503,'Conversation storage is unavailable for this action. Existing history is retained; ask your manager to review AI setup.')
    return status
