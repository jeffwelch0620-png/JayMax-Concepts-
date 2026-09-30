"""Transform the MongoDB purchase_orders/vendor_contacts export into SQL for the Phase 2
PO schema (supabase/schema.sql (phase2 migrations)). Reads the JSON backup, writes a
.sql file -- doesn't connect to Postgres directly.
See docs/SUPABASE_MIGRATION_PLAN.md ("Phase 2", chunk 2).

Run: python scripts/migrate_purchase_orders.py <backup_dir> [out.sql]

Each order keeps its "po_..." id (as purchase_orders.ref), so PDF links already sent in
supplier emails keep working. Re-running is safe: orders already present are skipped
(ON CONFLICT (ref) DO NOTHING), supplier emails are upserted.

An order left in the transient 'receiving' state (a receipt that crashed mid-way) is
migrated as 'sent' so it can be received again -- flagged in the output.
"""
import json
import sys
from pathlib import Path

STORE_ID_MAP = {"berts": "berts", "rudds": "rudds", "papa_leonis": "papa", "comm": "comm"}
STATUSES = {"draft", "pending", "approved", "sent", "received", "rejected"}


def sql_str(v):
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"

def sql_text(v):
    # For NOT NULL DEFAULT '' columns: never NULL.
    return "'" + str(v or "").replace("'", "''") + "'"

def sql_num(v):
    try:
        return str(float(v))
    except (TypeError, ValueError):
        return "0"

def sql_ts(v):
    v = v.get("$date") if isinstance(v, dict) else v
    return f"{sql_str(v)}::timestamptz" if v else "NULL"

def sql_json(v):
    return "NULL" if v is None else sql_str(json.dumps(v)) + "::jsonb"

def load(backup_dir, name):
    path = backup_dir / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else []


def build_po_sql(po):
    rid = po.get("restaurantId")
    store_id = STORE_ID_MAP.get(rid)
    if not store_id or not po.get("id"):
        print(f"  SKIP purchase order (unknown store '{rid}' or no id): {po.get('id')}")
        return None
    status = po.get("status")
    if status == "receiving":
        print(f"  WARN {po['id']} was stuck in 'receiving' -- migrated as 'sent' so it can be received again")
        status = "sent"
    if status not in STATUSES:
        print(f"  SKIP purchase order {po['id']} (unknown status '{status}')")
        return None
    vendor = po.get("vendor") or "Unassigned"
    header = (
        "INSERT INTO purchase_orders (ref, store_id, vendor_name, vendor_id, status, created_by, note, total, "
        "created_at, submitted_at, approved_by, approved_at, rejected_reason, sent_at, received_at, "
        "invoice_number, receipt_match, emailed_to, emailed_at, history) VALUES ("
        f"{sql_str(po['id'])}, {sql_str(store_id)}, {sql_text(vendor)}, "
        f"(SELECT id FROM vendors WHERE lower(name)=lower({sql_text(vendor)}) LIMIT 1), {sql_str(status)}, "
        f"{sql_text(po.get('createdBy'))}, {sql_text(po.get('note'))}, {sql_num(po.get('total'))}, "
        f"COALESCE({sql_ts(po.get('createdAt'))}, now()), {sql_ts(po.get('submittedAt'))}, {sql_str(po.get('approvedBy'))}, "
        f"{sql_ts(po.get('approvedAt'))}, {sql_str(po.get('rejectedReason'))}, {sql_ts(po.get('sentAt'))}, "
        f"{sql_ts(po.get('receivedAt'))}, {sql_str(po.get('invoiceNumber'))}, {sql_json(po.get('receiptMatch'))}, "
        f"{sql_str(po.get('emailedTo'))}, {sql_ts(po.get('emailedAt'))}, {sql_json(po.get('history') or [])}"
        ") ON CONFLICT (ref) DO NOTHING RETURNING id"
    )
    lines = po.get("lines") or []
    if not lines:
        return header + ";"
    values = ",\n  ".join(
        f"({i}, {sql_str(l.get('controlNumber'))}, {sql_str(f'{rid}_' + str(l.get('controlNumber')))}, "
        f"{sql_text(l.get('name'))}, {sql_text(l.get('vendorSku'))}, {sql_num(l.get('qty'))}, "
        f"{sql_text(l.get('purchaseUnit') or 'case')}, {sql_num(l.get('unitCost'))}, {sql_num(l.get('lineTotal'))}, "
        f"{sql_num(l.get('receivedQty'))})"
        for i, l in enumerate(lines)
    )
    return (
        f"WITH po AS ({header})\n"
        "INSERT INTO purchase_order_lines (po_id, position, control_number, item_code, name, vendor_sku, qty, unit, "
        "unit_price, extended, received_qty)\n"
        "SELECT po.id, l.position, l.control_number, (SELECT code FROM items WHERE code = l.item_code), l.name, "
        "l.vendor_sku, l.qty, l.unit, l.unit_price, l.extended, l.received_qty\n"
        f"FROM po, (VALUES\n  {values}\n) AS l(position, control_number, item_code, name, vendor_sku, qty, unit, "
        "unit_price, extended, received_qty);"
    )


def build_vendor_contacts_sql(contacts):
    out = []
    for vc in contacts:
        store_id = STORE_ID_MAP.get(vc.get("restaurantId"))
        vendor = (vc.get("vendor") or "").strip()
        if not store_id or not vendor:
            print(f"  SKIP vendor contact (unknown store or no vendor): {vc.get('restaurantId')}/{vendor}")
            continue
        out.append(
            "INSERT INTO store_vendor_contacts (store_id, vendor, order_email) VALUES "
            f"({sql_str(store_id)}, {sql_text(vendor)}, {sql_text(vc.get('orderEmail'))}) "
            "ON CONFLICT (store_id, vendor) DO UPDATE SET order_email=EXCLUDED.order_email, updated_at=now();"
        )
    return out


def main():
    backup_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not backup_dir or not backup_dir.exists():
        print("Usage: python scripts/migrate_purchase_orders.py <backup_dir> [out.sql]")
        sys.exit(1)
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else backup_dir / "migrate_purchase_orders.sql"

    orders, contacts = load(backup_dir, "purchase_orders"), load(backup_dir, "vendor_contacts")
    print(f"Loaded {len(orders)} purchase_orders, {len(contacts)} vendor_contacts from {backup_dir}")
    statements = [s for s in (build_po_sql(po) for po in orders) if s] + build_vendor_contacts_sql(contacts)
    out_path.write_text("BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;\n", encoding="utf-8")
    print(f"Wrote {len(statements)} statements to {out_path}")


if __name__ == "__main__":
    main()
