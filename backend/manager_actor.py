"""Current personal-account authority for the receiving manager journal only."""
import re
from fastapi import HTTPException

RESTAURANTS = {'berts': 'berts', 'rudds': 'rudds', 'papa': 'papa_leonis'}


async def resolve(request, store, decode, accounts, configured):
    if store not in RESTAURANTS:
        raise HTTPException(404, 'Restaurant is not available for manager notes')
    if not configured:
        raise HTTPException(503, 'Personal account verification is not configured')
    authorization = request.headers.get('authorization', '')
    claims = decode(authorization[7:]) if authorization.startswith('Bearer ') else None
    subject = claims.get('sub') if isinstance(claims, dict) else None
    if not isinstance(subject, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', subject):
        raise HTTPException(401, 'Personal sign-in required')
    try:
        row = await accounts().fetchrow('SELECT id, role, locations FROM public.app_users WHERE id=$1', subject)
    except Exception:
        raise HTTPException(503, 'Current manager account could not be confirmed') from None
    if not row or row['id'] != subject or row['role'] not in ('owner', 'manager'):
        raise HTTPException(403, 'Current manager or owner access required')
    if row['role'] != 'owner' and RESTAURANTS[store] not in (row['locations'] or []):
        raise HTTPException(403, 'Location access denied')
    return subject
