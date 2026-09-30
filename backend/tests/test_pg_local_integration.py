"""End-to-end checks of the Phase 2 Postgres paths against a real, throwaway Postgres
loaded with supabase/schema.sql + supabase/pending/*.sql. Skipped unless TEST_PG_URL is
set -- never point it at the live Supabase project: every test wipes the tables it uses.

  TEST_PG_URL=postgresql://postgres@localhost:55432/jmax_test pytest tests/test_pg_local_integration.py
"""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "jaymax_test")
os.environ.setdefault("AUTH_SECRET", "test-secret-for-pg-route-authorization")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
REPO_ROOT = Path(__file__).resolve().parents[2]

import pytest
from fastapi import HTTPException

import server
import db_pg

PG_URL = os.environ.get("TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="TEST_PG_URL not set")

RESET = """
TRUNCATE purchase_order_lines, purchase_orders, store_vendor_contacts, store_state, app_users, adjustments,
         reporting_periods, count_lines, count_sessions, prep_logs, prep_items, dish_lines, dishes, store_items, vendor_items, items, vendors, stores CASCADE;
INSERT INTO stores (id, name) VALUES ('berts', 'Berts'), ('rudds', 'Rudds'), ('papa', 'Papa'), ('comm', 'Commissary');
INSERT INTO vendors (id, name) VALUES ('us_foods', 'US Foods');
INSERT INTO items (code, name, base_unit) VALUES ('papa_leonis_A1', 'Flour', 'lb');
INSERT INTO store_items (store_id, item_code, count_unit, base_per_count_unit, current_stock)
  VALUES ('papa', 'papa_leonis_A1', 'bag', 50, 2);
"""


def run(coro_fn):
    async def main():
        os.environ["DATABASE_URL"] = PG_URL
        await db_pg.init_pool()
        assert db_pg._pool is not None, "could not connect to TEST_PG_URL"
        try:
            await db_pg.pool().execute(RESET)
            return await coro_fn()
        finally:
            await db_pg.close_pool()
    return asyncio.run(main())


@pytest.fixture(autouse=True)
def pg_mode(monkeypatch):
    monkeypatch.setattr(server, "USE_PG", True)


def test_purchase_order_lifecycle_round_trips_through_postgres():
    async def scenario():
        rid = "papa_leonis"
        line = server.POLineIn(controlNumber="A1", name="Flour", vendorSku="F-50", qty=3, purchaseUnit="bag", unitCost=20)
        ghost = server.POLineIn(controlNumber="ZZ", name="Deleted item", qty=1, unitCost=5)
        po = await server.create_order(rid, server.POCreateIn(vendor="US Foods", createdBy="Ana", lines=[line, ghost]))
        oid = po["id"]
        assert oid.startswith("po_") and po["total"] == 65.0 and po["status"] == "draft"

        fetched = await server._get_po(rid, oid)
        assert fetched["lines"][0] == {"controlNumber": "A1", "name": "Flour", "vendorSku": "F-50", "qty": 3.0,
                                       "purchaseUnit": "bag", "unitCost": 20.0, "receivedQty": 0.0, "lineTotal": 60.0}
        assert fetched["restaurantId"] == rid and fetched["history"][0]["status"] == "draft"
        linked = await db_pg.pool().fetch(
            "SELECT control_number, item_code FROM purchase_order_lines ORDER BY position")
        assert [(r["control_number"], r["item_code"]) for r in linked] == [("A1", "papa_leonis_A1"), ("ZZ", None)]
        assert await db_pg.pool().fetchval("SELECT vendor_id FROM purchase_orders WHERE ref=$1", oid) == "us_foods"

        updated = await server.update_order(rid, oid, server.POCreateIn(vendor="US Foods", note="rush", lines=[line]))
        assert updated["note"] == "rush" and len(updated["lines"]) == 1 and updated["total"] == 60.0

        await server.submit_order(rid, oid, {"by": "Ana"})
        with pytest.raises(HTTPException) as exc:
            await server.approve_order(rid, oid, {"by": "ana"})
        assert exc.value.status_code == 403
        pending = await server.owner_orders()
        assert [p["id"] for p in pending] == [oid] and pending[0]["restaurantId"] == rid

        await server.approve_order(rid, oid, {"by": "Ben"})
        await server.send_order(rid, oid, {"by": "Ben"})
        received = await server.receive_order(rid, oid, {"by": "Cy", "lines": [{"controlNumber": "A1", "receivedQty": 3}]})
        assert received["status"] == "received" and received["lines"][0]["receivedQty"] == 3.0
        assert [h["status"] for h in received["history"]] == ["draft", "pending", "approved", "sent", "received"]
        assert "receiptStartedAt" in received and received["receivedAt"]
        stock = await db_pg.pool().fetchval(
            "SELECT current_stock FROM store_items WHERE store_id='papa' AND item_code='papa_leonis_A1'")
        assert float(stock) == 5.0
        # A second receipt can't claim the order: the sent -> receiving swap no longer matches.
        with pytest.raises(HTTPException) as exc:
            await server.receive_order(rid, oid, {"lines": []})
        assert exc.value.status_code == 400

        scorecard = await server.owner_vendor_scorecard()
        assert scorecard[0]["vendor"] == "US Foods" and scorecard[0]["receivedOrders"] == 1

        again = await server.reorder_last(rid, server.ReorderIn(vendor="US Foods", createdBy="Ana"))
        assert again["id"] != oid and again["lines"][0]["qty"] == 3.0 and again["status"] == "draft"
        assert [p["id"] for p in await server.list_orders(rid, status="draft")] == [again["id"]]
        await server.delete_order(rid, again["id"])
        assert await db_pg.pool().fetchval("SELECT count(*) FROM purchase_order_lines") == 1
        with pytest.raises(HTTPException) as exc:
            await server._get_po(rid, again["id"])
        assert exc.value.status_code == 404
    run(scenario)


def test_vendor_contacts_and_store_state_in_postgres():
    async def scenario():
        await server.put_vendor_contact("berts", {"vendor": "US Foods", "orderEmail": "orders@usf.example"})
        await server.put_vendor_contact("berts", {"vendor": "US Foods", "orderEmail": "new@usf.example"})
        assert await server.list_vendor_contacts("berts") == [{"vendor": "US Foods", "orderEmail": "new@usf.example"}]
        assert await server.list_vendor_contacts("rudds") == []

        state = await server._pg_get_store_state("papa_leonis")
        assert state["revision"] == 0 and state["areas"] == server.DEFAULT_AREAS
        from tests.test_pg_routes import revision_request
        await server.put_areas("papa_leonis", [{"name": "Shed", "prefix": "SH"}], revision_request(0))
        await server.put_sales_period("papa_leonis", {"periodStart": "2026-09-28", "dishSales": {"d": 2}}, revision_request(1))
        state = await server._pg_get_store_state("papa_leonis")
        assert state == {"revision": 2, "areas": [{"name": "Shed", "prefix": "SH"}],
                         "salesPeriod": {"periodStart": "2026-09-28", "dishSales": {"d": 2}}}
        with pytest.raises(HTTPException) as exc:
            await server.put_areas("papa_leonis", [], revision_request(1))
        assert exc.value.status_code == 409
    run(scenario)


def test_auth_bootstrap_login_and_create_user_in_postgres(monkeypatch):
    monkeypatch.setattr(server, "BOOTSTRAP_TOKEN", "boot")
    async def scenario():
        boot = await server.auth_bootstrap(server.BootstrapIn(
            bootstrapToken="boot", email="Owner@Example.test", password="owner-password-123"))
        owner = server._decode_token(boot["token"])
        assert owner["role"] == "owner" and boot["user"]["email"] == "owner@example.test"
        from tests.test_pg_routes import make_request
        req = make_request("/api/auth/users", "POST", {"id": owner["sub"], "email": owner["email"], "role": "owner", "locations": []})
        await server.auth_create_user(server.UserIn(email="gm@example.test", password="manager-password-1",
                                                    role="manager", locations=["papa_leonis", "nowhere"]), req)
        with pytest.raises(HTTPException) as exc:
            await server.auth_create_user(server.UserIn(email="GM@example.test", password="manager-password-1"), req)
        assert exc.value.status_code == 409
        login = await server.auth_login(server.LoginIn(email="gm@example.test", password="manager-password-1"))
        assert login["user"]["locations"] == ["papa_leonis"]
    run(scenario)


def test_migration_scripts_produce_sql_that_applies(tmp_path):
    import json
    (tmp_path / "users.json").write_text(json.dumps([{"id": "usr_1", "email": "a@example.test", "passwordHash": "pbkdf2$x$y",
                                                        "role": "owner", "locations": ["berts"]}]))
    (tmp_path / "state_versions.json").write_text(json.dumps([{"restaurantId": "berts", "revision": 4}]))
    (tmp_path / "purchase_orders.json").write_text(json.dumps([
        {"id": "po_old1", "restaurantId": "papa_leonis", "vendor": "US Foods", "status": "receiving", "total": 60,
         "createdAt": "2026-09-01T10:00:00+00:00", "history": [{"status": "draft"}], "note": "it's fine",
         "lines": [{"controlNumber": "A1", "name": "Flour", "qty": 3, "unitCost": 20, "lineTotal": 60}]},
        {"id": "po_old2", "restaurantId": "berts", "vendor": "Unassigned", "status": "draft", "lines": []},
    ]))
    (tmp_path / "vendor_contacts.json").write_text(json.dumps([{"restaurantId": "berts", "vendor": "US Foods", "orderEmail": "o@x.example"}]))
    sql_files = []
    for script in ("migrate_users_and_state.py", "migrate_purchase_orders.py"):
        out = tmp_path / (script + ".sql")
        subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script), str(tmp_path), str(out)], check=True, capture_output=True)
        sql_files.append(out.read_text())

    async def scenario():
        for sql in sql_files * 2:  # twice: re-running must be safe
            await db_pg.pool().execute(sql)
        po = await server._get_po("papa_leonis", "po_old1")
        assert po["status"] == "sent" and po["note"] == "it's fine" and po["lines"][0]["lineTotal"] == 60.0
        assert po["createdAt"].startswith("2026-09-01T10:00:00")
        assert await db_pg.pool().fetchval("SELECT count(*) FROM purchase_order_lines") == 1
        assert (await server._get_po("berts", "po_old2"))["lines"] == []
        assert await server._vc_email("berts", "US Foods") == "o@x.example"
        assert (await server._pg_get_store_state("berts"))["revision"] == 4
        assert await db_pg.pool().fetchval("SELECT role FROM app_users WHERE id='usr_1'") == "owner"
    run(scenario)


def test_adjustments_and_reporting_periods_replace_and_reload_in_postgres():
    from tests.test_pg_routes import revision_request
    async def scenario():
        rid = "papa_leonis"
        adjs = [{"id": "adj_1", "date": "2026-09-29", "controlNumber": "A1", "reason": "waste", "qtyBasis": "portion",
                 "qty": 2, "note": "dropped", "createdAt": "2026-09-29T20:00:00+00:00"},
                {"id": "adj_2", "date": "2026-09-30", "controlNumber": "GONE", "reason": "transfer_in", "qty": 1}]
        res = await server.put_collection(rid, "adjustments", adjs, revision_request(0))
        assert res == {"ok": True, "count": 2, "revision": 1}
        rows = await db_pg.pool().fetch("SELECT ref, item_code, direction, qty_basis FROM adjustments ORDER BY ref")
        assert [tuple(r) for r in rows] == [("adj_1", "papa_leonis_A1", "remove", "portion"), ("adj_2", None, "add", "purchase")]

        periods = [{"id": "period_1", "name": "Week 39", "periodStart": "2026-09-21", "periodEnd": "2026-09-27",
                    "dishSales": {"uuid-x": 12}, "itemCounts": {"A1": {"begin": 3}}, "savedAt": "2026-09-28T09:00:00+00:00",
                    "status": "closed"}]
        await server.put_collection(rid, "reportingPeriods", periods, revision_request(1))

        state = await server.get_state(rid)
        assert state["revision"] == 2 and state["items"] == [] and state["dishes"] == []
        assert state["adjustments"][0] == {**adjs[0], "createdAt": "2026-09-29T20:00:00+00:00"}
        assert state["adjustments"][1]["controlNumber"] == "GONE" and state["adjustments"][1]["qtyBasis"] == "purchase"
        assert state["reportingPeriods"] == [{**periods[0], "savedAt": "2026-09-28T09:00:00+00:00"}]

        # Replacing with a shorter list removes the rest; invalid rows are rejected before the revision moves.
        await server.put_collection(rid, "adjustments", adjs[:1], revision_request(2))
        assert [a["id"] for a in (await server.get_state(rid))["adjustments"]] == ["adj_1"]
        with pytest.raises(HTTPException) as exc:
            await server.put_collection(rid, "reportingPeriods", [{"id": "p", "periodStart": "", "periodEnd": "x"}], revision_request(3))
        assert exc.value.status_code == 400
        with pytest.raises(HTTPException) as exc:
            await server.put_collection(rid, "items", [], revision_request(3))
        assert exc.value.status_code == 400
        assert (await server._pg_get_store_state(rid))["revision"] == 3
        assert await server._adjustments_for(rid) == (await server.get_state(rid))["adjustments"]
    run(scenario)


def test_period_migration_remaps_mongo_dish_ids_to_postgres_uuids(tmp_path):
    import json
    (tmp_path / "dishes.json").write_text(json.dumps([{"id": "dish_old_pizza", "restaurantId": "papa_leonis", "name": "Pizza"}]))
    (tmp_path / "reporting_periods.json").write_text(json.dumps([
        {"id": "period_1", "restaurantId": "papa_leonis", "periodStart": "2026-09-21", "periodEnd": "2026-09-27",
         "dishSales": {"dish_old_pizza": 40, "dish_unknown": 1}, "itemCounts": {}, "status": "closed"}]))
    (tmp_path / "adjustments.json").write_text(json.dumps([
        {"id": "adj_1", "restaurantId": "papa_leonis", "date": "2026-09-29", "controlNumber": "A1", "reason": "waste", "qty": 1}]))
    (tmp_path / "sales_periods.json").write_text(json.dumps([
        {"restaurantId": "papa_leonis", "periodStart": "2026-09-28", "dishSales": {"dish_old_pizza": 5}}]))
    outs = []
    for script in ("migrate_adjustments_and_periods.py", "migrate_users_and_state.py"):
        out = tmp_path / (script + ".sql")
        subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script), str(tmp_path), str(out)], check=True, capture_output=True)
        outs.append(out.read_text())

    async def scenario():
        pizza = await db_pg.pool().fetchval(
            "INSERT INTO dishes (store_id, name) VALUES ('papa', 'Pizza') RETURNING id::text")
        for sql in outs * 2:
            await db_pg.pool().execute(sql)
        state = await server.get_state("papa_leonis")
        assert state["reportingPeriods"][0]["dishSales"] == {pizza: 40, "dish_unknown": 1}
        assert state["salesPeriod"] == {"periodStart": "2026-09-28", "dishSales": {pizza: 5}}
        assert [a["id"] for a in state["adjustments"]] == ["adj_1"]
    run(scenario)


def test_prep_report_aggregates_postgres_counts_and_logs():
    async def scenario():
        pool = db_pg.pool()
        sauce = await pool.fetchval(
            "INSERT INTO dishes (store_id, name, recipe_type, yield_uom) VALUES ('papa', 'Red Sauce', 'prep', 'qt') RETURNING id")
        await pool.execute("INSERT INTO dishes (store_id, name, recipe_type) VALUES ('papa', 'Pizza', 'menu')")
        dough = await pool.fetchval(
            "INSERT INTO prep_items (store_id, name, recipe_id, container) VALUES ('papa', 'Dough balls', $1, 'tray') RETURNING id", sauce)
        sess = await pool.fetchval(
            """INSERT INTO count_sessions (store_id, count_date, counted_by_name, status)
               VALUES ('papa', '2026-09-29', 'Ana', 'submitted') RETURNING id""")
        await pool.execute("INSERT INTO count_sessions (store_id, count_date, status) VALUES ('papa', '2026-08-01', 'open')")
        await pool.execute(
            """INSERT INTO count_lines (session_id, dish_id, status, qty, saved_by) VALUES ($1, $2, 'counted', 4, 'Ben'),
                      ($1, NULL, 'not_counted', NULL, '')""", sess, sauce)
        await pool.execute("INSERT INTO count_lines (session_id, prep_item_id, status, qty) VALUES ($1, $2, 'counted', 7)", sess, dough)
        await pool.execute(
            """INSERT INTO prep_logs (store_id, kind, dish_id, prep_item_id, produced, total_cost, usage, date) VALUES
               ('papa', 'batch', $1, NULL, 6, 12.5, '[]', '2026-09-29'),
               ('papa', 'batch', NULL, $2, 10, 3, '[]', '2026-09-29'),
               ('papa', 'sales_usage', NULL, NULL, 0, 0, $3::jsonb, '2026-09-29'),
               ('papa', 'container_use', $1, NULL, -2, 0, '[]', '2026-09-30'),
               ('papa', 'batch', $1, NULL, 99, 99, '[]', '2026-07-01')""",
            sauce, dough, [{"recipeId": str(sauce), "used": 1.5}])
        rep = await server.prep_report("papa_leonis", frm="2026-09-01", to="2026-09-30")
        assert [r["name"] for r in rep["recipes"]] == ["Red Sauce"]
        assert rep["recipes"][0] == {"recipeId": str(sauce), "name": "Red Sauce", "yieldUOM": "qt",
                                     "counts": [{"date": "2026-09-29", "onHand": 4.0, "by": "Ben"}],
                                     "produced": 6.0, "producedCost": 12.5, "usedBySales": 1.5, "sentToService": 2.0}
        assert rep["prepItems"] == [{"prepItemId": str(dough), "name": "Dough balls", "yieldUOM": "tray",
                                     "counts": [{"date": "2026-09-29", "onHand": 7.0, "by": "Ana"}],
                                     "produced": 10.0, "producedCost": 3.0}]
        assert rep["sessions"] == [{"id": str(sess), "date": "2026-09-29", "status": "submitted", "countedBy": "Ana", "revision": 1}]
        assert rep["totals"] == {"producedCost": 15.5}
    run(scenario)
