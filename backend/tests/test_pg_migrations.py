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
