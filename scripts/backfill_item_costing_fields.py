"""Generates the backfill SQL for the costing-field schema extension added in Chunk 3
of the frontend wiring (see docs/SUPABASE_MIGRATION_PLAN.md). The already-migrated
items/store_items/vendor_items rows predate costing_type/pack_count/unit_qty/unit_uom/
portion_size/portion_uom/order_enabled/sales_tracked/needs_review -- this reads the
original Mongo export and writes UPDATE statements keyed by the same natural keys the
original migration used, rather than guessing defaults.

Run: python scripts/backfill_item_costing_fields.py <backup_dir> [out.sql]
"""
import json
import sys
from pathlib import Path

STORE_ID_MAP = {"berts": "berts", "rudds": "rudds", "papa_leonis": "papa"}

def sql_str(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"

def sql_num(v):
    return "NULL" if v is None else str(v)

def sql_bool(v):
    return "true" if v else "false"

def main():
    backup_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "backups")
    out_path = Path(sys.argv[2] if len(sys.argv) > 2 else "scripts/out_backfill_item_costing.sql")
    items = json.loads((backup_dir / "items.json").read_text(encoding="utf-8"))

    lines = ["BEGIN;"]
    for it in items:
        rid = it["restaurantId"]
        store_id = STORE_ID_MAP[rid]
        code = f"{rid}_{it['controlNumber']}"
        costing_type = it.get("itemType") or "portion"
        lines.append(
            f"UPDATE items SET costing_type={sql_str(costing_type)}, pack_count={sql_num(it.get('packCount'))}, "
            f"unit_qty={sql_num(it.get('unitQty'))}, unit_uom={sql_str(it.get('unitUOM'))}, "
            f"portion_size={sql_num(it.get('portionSize'))}, portion_uom={sql_str(it.get('portionUOM'))} "
            f"WHERE code={sql_str(code)};"
        )
        lines.append(
            f"UPDATE store_items SET order_enabled={sql_bool(it.get('orderEnabled', True))}, "
            f"sales_tracked={sql_bool(it.get('salesTracked', True))}, needs_review={sql_bool(it.get('needsReview', False))} "
            f"WHERE store_id={sql_str(store_id)} AND item_code={sql_str(code)};"
        )
        for sku in it.get("vendorSkus", []):
            lines.append(
                f"UPDATE vendor_items SET pack_count={sql_num(sku.get('packCount'))}, "
                f"unit_qty={sql_num(sku.get('unitQty'))}, unit_uom={sql_str(sku.get('unitUOM'))} "
                f"WHERE item_code={sql_str(code)} AND vendor_sku={sql_str(sku.get('vendorSku') or '')};"
            )
    lines.append("COMMIT;")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(items)} items' backfill statements to {out_path}")

if __name__ == "__main__":
    main()
