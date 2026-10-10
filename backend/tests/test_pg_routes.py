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
    assert len(conn.queries) == 2
    assert "to_regclass('prep_inventory.planning_versions')" in conn.queries[0][0]
    assert "store_id=$1 AND item_code=$2" in conn.queries[1][0]


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
    assert "to_regclass('prep_inventory.day_list_versions')" in conn.queries[0][0]
    assert "pg_advisory_xact_lock" in conn.queries[1][0]
    assert "count_type=$3" in conn.queries[2][0]


def test_prep_list_generation_handles_recurring_items_and_overrides():
    recipe = {"id": "recipe-1", "name": "Sauce", "yield_uom": "qt", "yield_qty": 2, "prep_par": 3}
    prep_items = [
        {"id": "recipe-item", "schedule": "recurring", "recur_days": [0], "fixed_qty": 4,
         "recipe_id": "recipe-1", "container": "Deli", "par_weekday": 0, "par_vessels": 0, "name": "Sauce"},
        {"id": "vessel-item", "schedule": "recurring", "recur_days": [1], "fixed_qty": 3,
         "recipe_id": None, "container": "Pan", "par_weekday": 0, "par_vessels": 0, "name": "Garnish"},
    ]
    session = {"id": "session-1"}
    plist = {
        "id": "list-1", "store_id": "berts", "prep_date": date(2026, 9, 28),
        "count_type": "nightly_prep", "status": "draft", "released_at": None, "released_by": None,
    }
    conn = FakeConnection(fetchrow_results=[None, session, plist], fetch_results=[
        [recipe], prep_items, [{"type": "par", "recipe_id": "recipe-item", "prep_item_id": None, "par": 7, "note": "event"}],
        [], [],
    ])

    result = asyncio.run(server._pg_generate_prep_list_in_transaction(
        conn, "berts", "2026-09-28", "daily", "nightly_prep"))

    assert result["regenerated"] is True
    inserts = [(query, args) for query, args in conn.queries if query.startswith("INSERT INTO prep_list_lines")]
    assert len(inserts) == 1
    assert inserts[0][1][1] == "recipe-item"
    assert inserts[0][1][7] == 7
    assert inserts[0][1][10] == 7


def test_open_count_session_removes_stale_recurring_lines():
    session = {"id": "session-1", "status": "open", "count_date": date(2026, 9, 28),
               "counted_by_name": None, "submitted_at": None}
    recurring = {"id": "prep-1", "schedule": "recurring", "recipe_id": None, "container": "Pan",
                 "par_vessels": 2, "name": "Garnish"}
    conn = FakeConnection(fetchrow_results=[session], fetch_results=[[], [recurring], [], []])

    result = asyncio.run(server._pg_get_or_create_session(conn, "berts", "2026-09-28", "daily"))

    assert result["prepItems"] == []
    assert any(query.startswith("DELETE FROM count_lines") for query, _ in conn.queries)


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


def test_mongo_staff_pin_read_requires_manager_like_pg_counterpart():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.get_pin("papa_leonis", make_request("/api/staff/papa_leonis/pin")))
    assert exc.value.status_code == 403


class FakeStatePool:
    """Minimal in-memory stand-in for the store_state / app_users queries."""
    def __init__(self, revision=None, users=()):
        self.revision = revision
        self.users = {u["email"]: u for u in users}
        self.queries = []

    async def fetchval(self, query, *args):
        self.queries.append(query)
        if query.startswith("UPDATE store_state"):
            if self.revision is not None and self.revision == args[1]:
                self.revision += 1
                return self.revision
            return None
        if "ON CONFLICT (store_id) DO NOTHING" in query:
            if self.revision is None:
                self.revision = 1
                return 1
            return None
        if "ON CONFLICT (store_id) DO UPDATE" in query:
            self.revision = (self.revision or 0) + 1
            return self.revision
        if query.startswith("SELECT revision"):
            return self.revision
        if "count(*) FROM app_users" in query:
            return len(self.users)
        raise AssertionError(query)

    async def fetchrow(self, query, *args):
        self.queries.append(query)
        if "FROM app_users" in query:
            return self.users.get(args[0])
        raise AssertionError(query)


def revision_request(if_match=None):
    headers = [(b"if-match", f'"{if_match}"'.encode())] if if_match is not None else []
    return Request({"type": "http", "method": "PUT", "path": "/api/state/papa_leonis/areas", "query_string": b"",
                    "headers": headers, "scheme": "http", "server": ("testserver", 80), "client": ("127.0.0.1", 1)})


def test_pg_revision_matches_mongo_contract(monkeypatch):
    monkeypatch.setattr(server, "USE_PG", True)
    fake = FakeStatePool(revision=None)
    monkeypatch.setattr(db_pg, "pool", lambda: fake)

    # First write with If-Match "0" creates the row at revision 1.
    assert asyncio.run(server._check_and_bump_revision("papa_leonis", revision_request(0))) == 1
    # Matching If-Match bumps; stale If-Match is a 409 and leaves the revision alone.
    assert asyncio.run(server._check_and_bump_revision("papa_leonis", revision_request(1))) == 2
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server._check_and_bump_revision("papa_leonis", revision_request(1)))
    assert exc.value.status_code == 409 and "revision 2" in exc.value.detail
    assert fake.revision == 2
    # No If-Match: unconditional bump.
    assert asyncio.run(server._check_and_bump_revision("papa_leonis", revision_request())) == 3


def test_pg_login_uses_app_users_and_issues_same_token_shape(monkeypatch):
    monkeypatch.setattr(server, "USE_PG", True)
    row = {"id": "usr_abc", "email": "gm@example.test", "role": "manager", "locations": ["papa_leonis"],
           "password_hash": server._password_hash("correct horse battery")}
    monkeypatch.setattr(db_pg, "pool", lambda: FakeStatePool(users=[row]))

    ok = asyncio.run(server.auth_login(server.LoginIn(email=" GM@example.test ", password="correct horse battery")))
    assert ok["user"] == {"id": "usr_abc", "email": "gm@example.test", "role": "manager", "locations": ["papa_leonis"]}
    assert server._decode_token(ok["token"])["sub"] == "usr_abc"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.auth_login(server.LoginIn(email="gm@example.test", password="wrong password")))
    assert exc.value.status_code == 401


def test_pg_bootstrap_refuses_once_any_user_exists(monkeypatch):
    monkeypatch.setattr(server, "USE_PG", True)
    monkeypatch.setattr(server, "BOOTSTRAP_TOKEN", "boot")
    row = {"id": "usr_x", "email": "o@example.test", "role": "owner", "locations": [], "password_hash": "x"}
    monkeypatch.setattr(db_pg, "pool", lambda: FakeStatePool(users=[row]))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.auth_bootstrap(server.BootstrapIn(
            bootstrapToken="boot", email="new@example.test", password="a-long-enough-pass")))
    assert exc.value.status_code == 409


def test_legacy_mongo_route_families_are_refused_in_pg_mode(monkeypatch):
    async def no_activity(*args):
        return None

    monkeypatch.setattr(server, "_record_activity", no_activity)

    async def ok(_):
        return Response(status_code=204)

    async def invoke(path, method="POST"):
        return await server.collaboration_security(make_request(path, method), ok)

    monkeypatch.setattr(server, "USE_PG", True)
    for path in ("/api/prep/papa_leonis/complete", "/api/preplists/papa_leonis/generate", "/api/staff/papa_leonis/counts/save",
                 "/api/staff-tasks/papa_leonis", "/api/prep-items/papa_leonis", "/api/staff/verify"):
        assert asyncio.run(invoke(path)).status_code == 410, path
    # Postgres twins, and routes that are Postgres-aware themselves, pass through.
    assert asyncio.run(invoke("/api/pg/preplists/papa/generate")).status_code == 204
    assert asyncio.run(invoke("/api/reports/papa_leonis/prep", "GET")).status_code == 204
    monkeypatch.setattr(server, "USE_PG", False)
    assert asyncio.run(invoke("/api/preplists/papa_leonis/generate")).status_code == 204


def test_send_email_posts_to_resend_with_sanitized_headers(monkeypatch):
    import httpx
    import json as _json
    sent = {}

    def handler(request):
        sent["url"], sent["auth"], sent["body"] = str(request.url), request.headers["authorization"], _json.loads(request.content)
        return httpx.Response(200, json={"id": "email_123"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(server, "EMAIL_KEY", "re_test")
    monkeypatch.setattr(server, "EMAIL_FROM_ADDRESS", "orders@example.com")

    email_id = asyncio.run(server.send_email(to="rep@vendor.example", subject="PO for\r\nBcc: x@evil.example",
                                             html="<p>Order</p>", from_name='Bert\'s <script>"\r\nX-Evil: 1'))
    assert email_id == "email_123"
    assert sent["url"] == "https://api.resend.com/emails" and sent["auth"] == "Bearer re_test"
    assert sent["body"]["from"] == '"Bert\'s scriptX-Evil: 1" <orders@example.com>'
    assert sent["body"]["subject"] == "PO for Bcc: x@evil.example"
    assert sent["body"]["to"] == ["rep@vendor.example"]

    monkeypatch.setattr(server, "EMAIL_FROM_ADDRESS", "")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.send_email(to="rep@vendor.example", subject="s", html="<p>x</p>"))
    assert exc.value.status_code == 503 and "set EMAIL_FROM_ADDRESS on the server" in exc.value.detail


def test_cors_origins_tolerate_copy_paste_variants():
    assert server._cors_origins(' "https://jaymax-concepts.onrender.com/" , https://b.example ') == [
        "https://jaymax-concepts.onrender.com", "https://b.example"]
    assert server._cors_origins("") == ["*"]


def test_pg_pool_startup_never_hangs_and_retries_in_background(monkeypatch):
    attempts = []

    async def create_pool(url, **kwargs):
        attempts.append(kwargs.get("timeout"))
        if len(attempts) == 1:
            await asyncio.sleep(3600)  # an unreachable host that never answers
        return "pool"

    monkeypatch.setenv("DATABASE_URL", "postgresql://unreachable")
    monkeypatch.setattr(db_pg.asyncpg, "create_pool", create_pool)
    monkeypatch.setattr(db_pg, "CONNECT_TIMEOUT", 0.05)
    monkeypatch.setattr(db_pg, "RETRY_INTERVAL", 0.01)
    monkeypatch.setattr(db_pg, "_pool", None)
    monkeypatch.setattr(db_pg, "_retry_task", None)

    async def scenario():
        assert await db_pg.init_pool() is None       # returns instead of hanging
        await asyncio.wait_for(db_pg._retry_task, 2)  # background retry connects
        return db_pg._pool

    assert asyncio.run(scenario()) == "pool"
    assert attempts[0] == 0.05


def test_ai_errors_explain_the_setup_problem(monkeypatch):
    import anthropic
    import httpx2
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(HTTPException) as exc:
        server._ai()
    assert exc.value.status_code == 503 and "ANTHROPIC_API_KEY is missing" in exc.value.detail

    def status_error(cls, status, message):
        req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        resp = httpx2.Response(status, request=req, json={"type": "error", "error": {"message": message}})
        return cls(message, response=resp, body=None)
    cases = [
        (status_error(anthropic.AuthenticationError, 401, "invalid x-api-key"), "wrong or was revoked"),
        (status_error(anthropic.BadRequestError, 400, "Your credit balance is too low"), "out of credits"),
        (status_error(anthropic.NotFoundError, 404, "model not found"), "isn't available"),
        (status_error(anthropic.RateLimitError, 429, "slow down"), "rate limit"),
        (status_error(anthropic.BadRequestError, 400, "This API key is not scoped to a workspace, so this request must include the anthropic-workspace-id header"), "ANTHROPIC_WORKSPACE_ID"),
        (status_error(anthropic.InternalServerError, 500, "boom"), "(500): boom"),
        (status_error(anthropic.BadRequestError, 400, "fallbacks: unknown field"), "(400): fallbacks: unknown field"),
    ]
    for err, expected in cases:
        assert expected in server._ai_error_message(err)


def test_ai_client_sends_workspace_header_when_configured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_123")
    monkeypatch.setattr(server, "_ai_client", None)
    client = server._ai()
    assert client.default_headers.get("anthropic-workspace-id") == "wrkspc_123"
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID")
    monkeypatch.setattr(server, "_ai_client", None)
    assert "anthropic-workspace-id" not in server._ai().default_headers
    monkeypatch.setattr(server, "_ai_client", None)


def test_health_reports_database_connection(monkeypatch):
    monkeypatch.setattr(server, "USE_PG", True)
    monkeypatch.setattr(server.db_pg, "_pool", None)
    assert asyncio.run(server.health()) == {"status": "ok", "database": "not connected"}
    monkeypatch.setattr(server.db_pg, "_pool", object())
    assert asyncio.run(server.health()) == {"status": "ok", "database": "connected"}
