import asyncio
import os
from datetime import date
from pathlib import Path
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "jaymax_test")
os.environ.setdefault("AUTH_SECRET", "test-secret-for-pg-route-authorization")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException
from fastapi.responses import Response
from starlette.requests import Request

import server
import db_pg


class FakeTransaction:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.rolled_back = exc_type is not None
        self.committed = exc_type is None


class FakeConnection:
    def __init__(self, fetchrow_results=(), fetch_results=()):
        self.fetchrow_results = list(fetchrow_results)
        self.fetch_results = list(fetch_results)
        self.queries = []
        self.tx = FakeTransaction()

    def transaction(self):
        return self.tx

    async def execute(self, query, *args):
        self.queries.append((query, args))
        return "UPDATE 1"

    async def fetchrow(self, query, *args):
        self.queries.append((query, args))
        return self.fetchrow_results.pop(0) if self.fetchrow_results else None

    async def fetch(self, query, *args):
        self.queries.append((query, args))
        return self.fetch_results.pop(0) if self.fetch_results else []

    async def fetchval(self, query, *args):
        self.queries.append((query, args))
        return 0


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    async def acquire(self):
        return self.conn

    async def release(self, conn):
        assert conn is self.conn


def make_request(path, method="GET", user=None, revision=None):
    user = user or {"id": "staff-1", "email": "staff@example.test", "role": "staff", "locations": ["papa_leonis"]}
    token = server._token(user)
    headers = [(b"authorization", ("Bearer " + token).encode())]
    if revision is not None:
        headers.append((b"if-match", f'"{revision}"'.encode()))
    return Request({
        "type": "http", "method": method, "path": path, "query_string": b"",
        "headers": headers,
        "scheme": "http", "server": ("testserver", 80), "client": ("127.0.0.1", 1),
    })


def test_pg_paths_apply_store_and_staff_authorization(monkeypatch):
    assert server._path_rid("/api/pg/prep/papa/complete") == "papa_leonis"
    assert server._path_rid("/api/pg/prep/comm/complete") == "comm"

    async def no_activity(*args):
        return None

    monkeypatch.setattr(server, "_record_activity", no_activity)

    async def invoke(path, method, user):
        request = make_request(path, method, user)
        return await server.collaboration_security(request, lambda _: asyncio.sleep(0, result=Response(status_code=204)))

    papa_user = {"id": "staff-1", "email": "staff@example.test", "role": "staff", "locations": ["papa_leonis"]}
    denied = asyncio.run(invoke("/api/pg/prep-items/berts", "GET", papa_user))
    assert denied.status_code == 403

    allowed = asyncio.run(invoke("/api/pg/preplists/papa/generate", "POST", papa_user))
    assert allowed.status_code == 204

    denied_write = asyncio.run(invoke("/api/pg/items/papa", "POST", papa_user))
    assert denied_write.status_code == 403


def test_prep_item_update_rejects_cross_store_inventory_source(monkeypatch):
    conn = FakeConnection(fetchrow_results=[None])
    monkeypatch.setattr(db_pg, "pool", lambda: FakePool(conn))
    body = server.PgPrepItemIn(
        name="Prep item", sourceType="item", itemCode="berts_WI-001",
        vesselName="Pan", vesselCapacity=1, parVessels=2,
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.pg_update_prep_item("papa", "prep-1", body))

    assert exc.value.status_code == 404
    assert len(conn.queries) == 1
    assert "store_id=$1 AND item_code=$2" in conn.queries[0][0]


def test_prep_list_generation_checks_and_creates_inside_transaction(monkeypatch):
    plist = {
        "id": "list-1", "prep_date": date(2026, 9, 29), "count_type": "nightly_prep",
        "status": "draft", "released_at": None, "released_by": None,
    }
    conn = FakeConnection(fetchrow_results=[plist])
    monkeypatch.setattr(db_pg, "pool", lambda: FakePool(conn))

    result = asyncio.run(server.pg_generate_prep_list("berts", {"date": "2026-09-29", "track": "daily"}))

    assert result["regenerated"] is False
    assert conn.tx.committed
    assert "pg_advisory_xact_lock" in conn.queries[0][0]
    assert "count_type=$3" in conn.queries[1][0]


def test_task_completion_locks_task_and_commits_as_one_unit(monkeypatch):
    plist = {
        "id": "list-1", "store_id": "berts", "prep_date": date(2026, 9, 29),
        "count_type": "nightly_prep", "status": "released", "released_at": None, "released_by": None,
    }
    task = {
        "id": "task-1", "recipe_id": None, "prep_item_id": None, "batches_planned": 2,
        "batches_done": 0, "task_type": "batch", "name": "Dough", "yield_uom": "batch",
        "yield_qty": 1, "par": 0, "on_hand": None, "uncounted": False, "needed_units": 0,
        "done_by_name": None, "done_at": None, "note": None, "vessel_name": None, "removed": False,
    }
    conn = FakeConnection(fetchrow_results=[plist, task], fetch_results=[[]])
    monkeypatch.setattr(db_pg, "pool", lambda: FakePool(conn))

    result = asyncio.run(server.pg_complete_task(
        "berts", "list-1", "task-1", server.PgTaskCompleteIn(batches=1, doneBy="Alex")))

    assert result["list"]["id"] == "list-1"
    assert conn.tx.committed
    locked_selects = [query for query, _ in conn.queries if "FOR UPDATE" in query]
    assert len(locked_selects) == 2
    assert any(query.startswith("UPDATE prep_list_lines") for query, _ in conn.queries)


def test_revision_update_uses_atomic_compare_and_swap(monkeypatch):
    class Versions:
        current = {"restaurantId": "papa_leonis", "revision": 7}
        query = None

        async def find_one(self, query, projection):
            return dict(self.current)

        async def find_one_and_update(self, query, update, **kwargs):
            self.query = query
            if query.get("revision") != self.current["revision"]:
                return None
            self.current["revision"] += update["$inc"]["revision"]
            return dict(self.current)

    versions = Versions()
    monkeypatch.setattr(server, "db", type("Database", (), {"state_versions": versions})())
    request = make_request("/api/state/papa_leonis/items", "PUT", revision=7)

    revision = asyncio.run(server._check_and_bump_revision("papa_leonis", request))

    assert revision == 8
    assert versions.query["revision"] == 7


def test_pg_pool_reads_database_url_after_environment_is_loaded(monkeypatch):
    calls = {}

    async def create_pool(url, **kwargs):
        calls["url"] = url
        return object()

    monkeypatch.setenv("DATABASE_URL", "postgresql://configured-after-import")
    monkeypatch.setattr(db_pg.asyncpg, "create_pool", create_pool)
    monkeypatch.setattr(db_pg, "_pool", None)

    asyncio.run(db_pg.init_pool())

    assert calls["url"] == "postgresql://configured-after-import"


def test_pg_staff_management_routes_require_manager_like_mongo_counterparts(monkeypatch):
    # These handlers must enforce the manager role themselves (as their Mongo twins do),
    # not rely solely on the middleware -- which is bypassed when AUTH_REQUIRED=false.
    conn = FakeConnection()
    monkeypatch.setattr(db_pg, "pool", lambda: conn)
    staff = make_request("/api/pg/staff/papa/members", "POST")
    member = server.PgStaffMemberIn(name="Cook")
    calls = [
        server.pg_set_staff_pin("papa", server.PgStaffPinIn(staffPin="4321"), staff),
        server.pg_create_staff_member("papa", member, staff),
        server.pg_update_staff_member("papa", "s1", member, staff),
        server.pg_delete_staff_member("papa", "s1", staff),
        server.pg_create_staff_task("papa", server.PgStaffTaskIn(taskType="prep", title="Mop", dueDate="2026-10-01"), staff),
        server.pg_delete_staff_task("papa", "t1", staff),
    ]
    for call in calls:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(call)
        assert exc.value.status_code == 403
    assert conn.queries == []
