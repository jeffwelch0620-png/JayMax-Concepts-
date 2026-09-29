"""Transform the MongoDB items/purchases export into SQL for the new Supabase schema.
Reads from the JSON backup (scripts/export_mongo_backup.py output), writes a single
.sql file with INSERT statements -- doesn't connect to Postgres directly, since the
migration is currently applied via the Supabase MCP tools rather than a direct
DATABASE_URL connection. See docs/SUPABASE_MIGRATION_PLAN.md.

Run: python scripts/migrate_items_and_invoices.py <backup_dir> [out.sql]

Key transform decision: Mongo's `controlNumber` is scoped per restaurant, not
globally unique -- "WI-001" is three different real products across the three
restaurants in the current data. The new schema's `items.code` is a single global
primary key, so this generates `{restaurantId}_{controlNumber}` as the new code
rather than assuming any items are literally the same product across locations.
Recognizing genuine cross-location duplicates (e.g. consolidating two restaurants'
"Mozzarella Cheese" into one items row) is a real data-quality decision, not
something to guess at silently -- left as a manual follow-up, not part of this pass.
"""
import json
import sys
from pathlib import Path

# ---- Same costing math as backend/server.py's calc_ppu/item_derived (copied, not
# imported, since server.py has import-time side effects -- connects to MongoDB). ----
UOM_FAMILY = {"lb": "weight", "oz": "weight", "kg": "weight", "g": "weight",
              "gal": "volume", "qt": "volume", "pt": "volume", "cup": "volume", "fl oz": "volume", "l": "volume", "ml": "volume",
              "each": "count", "ct": "count", "dozen": "count"}
CONV_TO_BASE = {"lb": 16, "oz": 1, "kg": 35.27396195, "g": 0.03527396195,
                "gal": 128, "qt": 32, "pt": 16, "cup": 8, "fl oz": 1, "l": 33.814, "ml": 0.033814,
                "each": 1, "ct": 1, "dozen": 12}

def f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d

def calc_ppu(yq, yuom, ps, puom):
    yq, ps = f(yq), f(ps)
    if not yq or not ps:
        return 0.0
    fy, fp = UOM_FAMILY.get(yuom), UOM_FAMILY.get(puom)
    if fy and fp and fy == fp:
        pb = ps * CONV_TO_BASE[puom]
        return (yq * CONV_TO_BASE[yuom]) / pb if pb > 0 else 0.0
    return yq / ps

# Mongo `itemType` ("portion"/"usage") is about costing granularity, not what kind of
# item it is -- doesn't map onto the new schema's item_type enum
# (raw/prep/commissary/paper/chemical/other). Hand-classified from the name instead;
# review before relying on it for anything beyond this first migration pass.
ITEM_TYPE_OVERRIDES = {
    ("papa_leonis", "CT-001"): "paper",   # Pizza Boxes
    ("berts", "OF-001"): "paper",         # Paper Napkins
    ("rudds", "CT-001"): "paper",         # Pie Foil Tins
}
DEFAULT_ITEM_TYPE = "raw"

VENDOR_NAME_TO_ID = {"US Foods": "us_foods", "PFG": "pfg", "Sysco": "sysco", "Webstaurant": "webstaurant", "Other": "other"}

STORE_ID_MAP = {"berts": "berts", "rudds": "rudds", "papa_leonis": "papa"}  # Mongo -> Supabase store ids


def sql_str(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"

def sql_num(v):
    return "NULL" if v is None else str(v)

def sql_bool(v):
    return "TRUE" if v else "FALSE"

def item_code(rid, control_number):
    return f"{rid}_{control_number}"


def build_items_sql(items):
    items_rows, store_items_rows, vendor_items_rows = [], [], []
    for it in items:
        rid = it["restaurantId"]
        store_id = STORE_ID_MAP.get(rid)
        if not store_id:
            print(f"  SKIP (unknown store '{rid}'): {it.get('controlNumber')} {it.get('name')}")
            continue
        cn = it["controlNumber"]
        code = item_code(rid, cn)
        item_type = ITEM_TYPE_OVERRIDES.get((rid, cn), DEFAULT_ITEM_TYPE)
        base_unit = it.get("portionUOM") or "each"

        items_rows.append(
            f"({sql_str(code)}, {sql_str(it['name'])}, {sql_str(it.get('storageArea'))}, "
            f"{sql_str(base_unit)}, {sql_str(item_type)}, FALSE, {sql_str(f'migrated from Mongo {rid}/{cn}')})"
        )

        skus = it.get("vendorSkus") or []
        preferred = next((s for s in skus if s.get("preferred")), skus[0] if skus else None)
        count_unit = it.get("purchaseUnit") or "each"
        base_per_count_unit = calc_ppu(
            f(preferred.get("packCount", it.get("packCount"))) * f(preferred.get("unitQty", it.get("unitQty"))) if preferred else f(it.get("packCount")) * f(it.get("unitQty")),
            (preferred.get("unitUOM") if preferred else None) or it.get("unitUOM") or "each",
            it.get("portionSize"), it.get("portionUOM"),
        ) or 1  # base_per_count_unit has a > 0 check constraint; 1 is a safe fallback when data is incomplete

        store_items_rows.append(
            f"({sql_str(store_id)}, {sql_str(code)}, {sql_str(count_unit)}, {sql_num(round(base_per_count_unit, 4))}, "
            f"{sql_str(it.get('storageArea'))}, {sql_bool(it.get('countActive', True))}, "
            f"{sql_num(f(it.get('currentStock')))}, {sql_num(f(it.get('par')))}, "
            f"{sql_str(it.get('lastCounted') or None)}, {sql_str(it.get('lastCountedBy') or None)}, "
            f"{sql_str(it.get('lastCountedAt') or None)})"
        )

        for sku in skus:
            vendor_id = VENDOR_NAME_TO_ID.get(sku.get("vendor"))
            if not vendor_id:
                print(f"  SKIP vendor SKU (unknown vendor '{sku.get('vendor')}'): {code} {sku.get('vendorSku')}")
                continue
            sku_ppu = calc_ppu(f(sku.get("packCount")) * f(sku.get("unitQty")), sku.get("unitUOM") or "each",
                                it.get("portionSize"), it.get("portionUOM")) or None
            vendor_items_rows.append(
                f"({sql_str(vendor_id)}, {sql_str(sku.get('vendorSku') or sku.get('id'))}, {sql_str(sku.get('packDescription'))}, "
                f"{sql_str(code)}, {sql_str(sku.get('purchaseUnit') or count_unit)}, {sql_num(round(sku_ppu, 4) if sku_ppu else None)}, "
                f"{sql_num(f(sku.get('price')) or None)}, {sql_str(sku.get('priceUpdatedAt') or None)}, "
                f"{sql_str(sku.get('priceSource'))}, {sql_bool(sku.get('preferred'))}, {sql_bool(sku.get('available', True))})"
            )
    return items_rows, store_items_rows, vendor_items_rows


def build_invoices_sql(purchases):
    by_invoice = {}
    for p in purchases:
        by_invoice.setdefault(p["invoiceId"], []).append(p)

    # Mongo's invoiceId strings ("inv_INV-100234") aren't valid uuids, and the
    # Postgres invoices.id is uuid DEFAULT gen_random_uuid() -- rather than fabricate
    # ids, invoices are inserted plainly and invoice_lines look their parent up by the
    # natural key (store_id, vendor_id, invoice_number, invoice_date), which is unique
    # within this migration batch.
    invoice_rows, invoice_line_selects = [], []
    for inv_id, lines in by_invoice.items():
        first = lines[0]
        rid = first["restaurantId"]
        store_id = STORE_ID_MAP.get(rid)
        if not store_id:
            print(f"  SKIP invoice {inv_id} (unknown store '{rid}')")
            continue
        vendor_id = VENDOR_NAME_TO_ID.get(first["vendor"])
        if not vendor_id:
            print(f"  SKIP invoice {inv_id} (unknown vendor '{first['vendor']}')")
            continue
        total = sum(f(l.get("extendedCost")) or f(l.get("qty")) * f(l.get("unitCost")) for l in lines)
        invoice_rows.append(
            f"({sql_str(store_id)}, {sql_str(store_id)}, {sql_str(vendor_id)}, "
            f"{sql_str(first.get('invoiceNumber'))}, {sql_str(first['invoiceDate'])}, {sql_num(round(total, 2))}, 'mongo_migration')"
        )
        for l in lines:
            code = item_code(rid, l["controlNumber"])
            extended = f(l.get("extendedCost")) or f(l.get("qty")) * f(l.get("unitCost"))
            invoice_line_selects.append(
                f"""INSERT INTO invoice_lines (invoice_id, vendor_item_id, description, qty, purchase_unit, unit_price, extended)
SELECT inv.id, vi.id, {sql_str(l.get('itemName'))}, {sql_num(f(l.get('qty')))}, {sql_str(l.get('unit'))}, {sql_num(f(l.get('unitCost')))}, {sql_num(round(extended, 2))}
FROM invoices inv, vendor_items vi
WHERE inv.store_id = {sql_str(store_id)} AND inv.vendor_id = {sql_str(vendor_id)}
  AND inv.invoice_number = {sql_str(first.get('invoiceNumber'))} AND inv.invoice_date = {sql_str(first['invoiceDate'])}
  AND vi.vendor_id = {sql_str(vendor_id)} AND vi.item_code = {sql_str(code)}
LIMIT 1;"""
            )
    return invoice_rows, invoice_line_selects


def main():
    backup_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not backup_dir or not backup_dir.exists():
        print("Usage: python scripts/migrate_items_and_invoices.py <backup_dir> [out.sql]")
        sys.exit(1)
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else backup_dir / "migrate_items_and_invoices.sql"

    items = json.loads((backup_dir / "items.json").read_text())
    purchases = json.loads((backup_dir / "purchases.json").read_text())

    print(f"Loaded {len(items)} items, {len(purchases)} purchase lines from {backup_dir}")

    items_rows, store_items_rows, vendor_items_rows = build_items_sql(items)
    invoice_rows, invoice_line_selects = build_invoices_sql(purchases)

    sql = ["-- Generated by scripts/migrate_items_and_invoices.py -- review before applying.\n"]
    sql.append("INSERT INTO items (code, name, category, base_unit, item_type, is_high_value, notes) VALUES\n"
                + ",\n".join(items_rows) + "\nON CONFLICT (code) DO NOTHING;\n")
    sql.append("INSERT INTO store_items (store_id, item_code, count_unit, base_per_count_unit, storage_area, "
                "counted_nightly, current_stock, par, last_counted, last_counted_by, last_counted_at) VALUES\n"
                + ",\n".join(store_items_rows) + "\nON CONFLICT (store_id, item_code) DO NOTHING;\n")
    sql.append("INSERT INTO vendor_items (vendor_id, vendor_sku, vendor_description, item_code, purchase_unit, "
                "base_per_purchase_unit, price, price_updated_at, price_source, preferred, available) VALUES\n"
                + ",\n".join(vendor_items_rows) + ";\n")
    sql.append("-- Invoices get plain generated uuids; invoice_lines look their parent up by natural key (see below).\n")
    sql.append("INSERT INTO invoices (store_id, delivered_to, vendor_id, invoice_number, invoice_date, total, source) VALUES\n"
                + ",\n".join(invoice_rows) + ";\n")
    sql.append("\n".join(invoice_line_selects))

    out_path.write_text("\n".join(sql), encoding="utf-8")
    print(f"Wrote {len(items_rows)} items, {len(store_items_rows)} store_items, {len(vendor_items_rows)} vendor_items, "
          f"{len(invoice_rows)} invoices, {len(invoice_line_selects)} invoice_lines -> {out_path}")


if __name__ == "__main__":
    main()
