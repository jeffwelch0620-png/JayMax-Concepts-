import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts import migrate_counts_and_prep_lists, migrate_items_and_invoices


def test_invoice_migration_generates_stable_sku_for_vendor_mismatch():
    items = [{
        "restaurantId": "berts", "controlNumber": "OF-001", "vendorSkus": [
            {"vendor": "Webstaurant", "vendorSku": "W-1"},
        ],
    }]
    purchases = [{
        "invoiceId": "inv-1", "restaurantId": "berts", "vendor": "US Foods",
        "controlNumber": "OF-001", "invoiceNumber": "INV-1", "invoiceDate": "2026-09-29",
        "itemName": "Paper Napkins", "qty": 1, "unit": "case", "unitCost": 10,
    }]

    placeholder = migrate_items_and_invoices.build_invoice_sku_placeholders(items, purchases)
    _, lines = migrate_items_and_invoices.build_invoices_sql(purchases)

    assert placeholder == migrate_items_and_invoices.build_invoice_sku_placeholders(items, purchases)
    assert "MIGRATION-berts-OF-001" in placeholder[0]
    assert len(lines) == 1
    assert "vi.vendor_id = 'us_foods' AND vi.item_code = 'berts_OF-001'" in lines[0]


def test_prep_list_migration_preserves_bulk_track(tmp_path, monkeypatch):
    (tmp_path / "prep_count_sessions.json").write_text("[]")
    (tmp_path / "dishes.json").write_text("[]")
    (tmp_path / "prep_lists.json").write_text(json.dumps([{
        "id": "list-1", "restaurantId": "berts", "date": "2026-09-29", "track": "bulk",
        "tasks": [{"taskType": "vessel", "name": "Tomatoes"}],
    }]))
    output = tmp_path / "migration.sql"
    monkeypatch.setattr(sys, "argv", ["migrate_counts_and_prep_lists.py", str(tmp_path), str(output)])

    migrate_counts_and_prep_lists.main()

    sql = output.read_text()
    assert "prep_lists (store_id, prep_date, count_type, from_count" in sql
    assert "'commissary', NULL" in sql
    assert "pl.count_type = 'commissary'" in sql


def test_users_and_state_migration_keeps_hashes_ids_and_maps_store_ids():
    from scripts import migrate_users_and_state as m
    users = [
        {"id": "usr_1", "email": " Owner@Example.test ", "passwordHash": "pbkdf2$s$d", "role": "owner",
         "locations": ["berts", "papa_leonis"], "createdAt": {"$date": "2026-09-01T00:00:00Z"}},
        {"id": "usr_2", "email": "bad@example.test", "passwordHash": "", "role": "owner"},
    ]
    sql = m.build_users_sql(users)
    assert len(sql) == 1
    assert "'usr_1', 'owner@example.test', 'pbkdf2$s$d', 'owner', ARRAY['berts', 'papa_leonis']::text[]" in sql[0]

    state = m.build_store_state_sql(
        [{"restaurantId": "papa_leonis", "revision": 7}],
        [{"restaurantId": "papa_leonis", "list": [{"name": "Shed", "prefix": "SH"}]}],
        [{"_id": {"$oid": "x"}, "restaurantId": "papa_leonis", "periodStart": "2026-09-28", "dishSales": {"d": 1}}],
    )
    assert len(state) == 1
    assert state[0].startswith("INSERT INTO store_state (store_id, revision, areas, sales_period) VALUES ('papa', 7,")
    assert '"prefix": "SH"' in state[0] and '"periodStart": "2026-09-28"' in state[0] and '"_id"' not in state[0]
