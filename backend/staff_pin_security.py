"""Shared-PIN checks are portal access, never personal authentication.

The SQLite counter coordinates workers sharing one instance filesystem. It is
not a distributed counter across replicas; see docs/STAFF_PIN_SECURITY.md.
"""
import asyncio
from contextlib import closing
from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import time

from fastapi import HTTPException


def configured_pin(value):
    return value if isinstance(value, str) and re.fullmatch(r'[0-9]{4,8}', value) else None


def store_key(store):
    # Callers supply the canonical store. Client attribution may have already
    # been rewritten by server/proxy middleware, so it cannot define this budget.
    return hashlib.sha256(json.dumps(['staff-pin-store-v1', store], separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class Reservation:
    key: str
    expires: float


class PinAttemptLimiter:
    def __init__(self, path, *, limit=5, window=60, capacity=10000, clock=time.time):
        self.path = Path(path)
        self.limit, self.window, self.capacity, self.clock = limit, window, capacity, clock

    def reserve(self, key):
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path, timeout=0.25)) as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE IF NOT EXISTS attempts (key TEXT PRIMARY KEY, expires REAL NOT NULL, count INTEGER NOT NULL)')
                now = self.clock()
                db.execute('DELETE FROM attempts WHERE expires<=?', (now,))
                row = db.execute('SELECT expires,count FROM attempts WHERE key=?', (key,)).fetchone()
                if row and row[1] >= self.limit:
                    raise HTTPException(429, 'Too many staff PIN attempts. Try again later.',
                                        headers={'Retry-After': str(max(1, int(row[0] - now) + 1))})
                if row is None:
                    if db.execute('SELECT count(*) FROM attempts').fetchone()[0] >= self.capacity:
                        raise HTTPException(429, 'Staff PIN attempts are temporarily limited.',
                                            headers={'Retry-After': str(self.window)})
                    expires = now + self.window
                    db.execute('INSERT INTO attempts VALUES(?,?,1)', (key, expires))
                else:
                    expires = row[0]
                    db.execute('UPDATE attempts SET count=count+1 WHERE key=?', (key,))
                db.commit()
                return Reservation(key, expires)
        except (OSError, sqlite3.Error):
            raise HTTPException(503, 'Staff PIN verification is temporarily unavailable.') from None

    def refund(self, reservation):
        try:
            with closing(sqlite3.connect(self.path, timeout=0.25)) as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('UPDATE attempts SET count=count-1 WHERE key=? AND expires=? AND count>0',
                           (reservation.key, reservation.expires))
                db.execute('DELETE FROM attempts WHERE key=? AND count=0', (reservation.key,))
                db.commit()
        except (OSError, sqlite3.Error):
            # Failure to retain the attempt state never allows an unchecked PIN.
            raise HTTPException(503, 'Staff PIN verification is temporarily unavailable.') from None


limiter = PinAttemptLimiter(Path(tempfile.gettempdir()) / 'jaymax-staff-pin' / 'attempts.sqlite3')


async def verify(request, store, supplied, load_pin):
    # Keep the request argument for the common route contract, but deliberately
    # do not use its headers, client address or session to partition PIN failures.
    ticket = await asyncio.to_thread(limiter.reserve, store_key(store))
    try:
        stored = configured_pin(await load_pin())
    except BaseException:
        await asyncio.to_thread(limiter.refund, ticket)
        raise
    if stored is None:
        raise HTTPException(403, 'Staff PIN portal is disabled. Ask a manager to set a PIN.')
    candidate = configured_pin(supplied)
    if candidate is None or not hmac.compare_digest(candidate, stored):
        return False
    # Successful checks do not consume the failure budget or erase prior failures.
    await asyncio.to_thread(limiter.refund, ticket)
    return True
