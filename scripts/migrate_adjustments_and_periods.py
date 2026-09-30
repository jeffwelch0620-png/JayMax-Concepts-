"""Transform the MongoDB adjustments/reporting_periods export into SQL for the Phase 2
columns (supabase/schema.sql (phase2 migrations)). Reads the JSON
backup, writes a .sql file -- doesn't connect to Postgres directly.
See docs/SUPABASE_MIGRATION_PLAN.md ("Phase 2", chunk 3).

Run AFTER migrate_dishes.py has been applied (dish ids are resolved against it):
  python scripts/migrate_adjustments_and_periods.py <backup_dir> [out.sql]

dishSales is keyed by dish id. Mongo dish ids ("dish_...") don't exist in Postgres --
migrated dishes got new uuids, matched by (store_id, name) as in migrate_dishes.py -- so
each key is remapped in SQL to the Postgres dish uuid; a key with no matching dish keeps
its old id (harmless: the app just won't show it). dish_sales_sql() is shared with
migrate_users_and_state.py for the current sales period.

Re-running is safe: each store's rows are deleted and re-inserted, like the app's own save.
"""
import json
import sys
from pathlib import Path

STORE_ID_MAP = {"berts": "berts", "rudds": "rudds", "papa_leonis": "papa", "comm": "comm"}
ADD_REASONS = {"transfer_in", "count_correction_add", "other_add"}


def sql_str(v):
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"

def sql_text(v):
    return "'" + str(v or "").replace("'", "''") + "'"

def sql_num(v):
    try:
        return str(float(v))
    except (TypeError, ValueError):
        return "0"

def sql_json(v):
    return sql_str(json.dumps(v)) + "::jsonb"

def iso(v):
    return v.get("$date") if isinstance(v, dict) else v

def load(backup_dir, name):
    path = backup_dir / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else []


def mongo_dish_index(dishes):
    """Mongo dish id -> (postgres store id, dish name)."""
    out = {}
    for d in dishes:
        store_id = STORE_ID_MAP.get(d.get("restaurantId"))
        if store_id and d.get("id") and d.get("name"):
            out[d["id"]] = (store_id, d["name"])
    return out


def dish_sales_sql(dish_sales, dish_index):
    """SQL jsonb expression for a dishSales map with Mongo dish ids remapped to Postgres uuids."""
    if not dish_sales:
        return "'{}'::jsonb"
    pairs = []
    for old_id, value in dish_sales.items():
        target = dish_index.get(old_id)
        key = (f"COALESCE((SELECT d.id::text FROM dishes d WHERE d.store_id = {sql_str(target[0])} "
               f"AND d.name = {sql_str(target[1])} LIMIT 1), {sql_str(old_id)})") if target else sql_str(old_id)
        if not target:
            print(f"  WARN dishSales key '{old_id}' matches no Mongo dish -- kept as-is")
        pairs.append(f"{key}, {sql_json(value)}")
    return "jsonb_build_object(" + ", ".join(pairs) + ")"


def build_adjustments_sql(adjustments):
    by_store = {}
    for a in adjustments:
        rid = a.get("restaurantId")
        store_id = STORE_ID_MAP.get(rid)
        if not store_id or not a.get("controlNumber") or not a.get("date") or not a.get("reason"):
            print(f"  SKIP adjustment (unknown store or missing item/date/reason): {a.get('id')}")
            continue
        created = iso(a.get("createdAt"))
        by_store.setdefault(store_id, []).append(
            f"({sql_str(store_id)}, {sql_str(a.get('id') or 'adj_migrated_' + str(len(by_store.get(store_id, []))))}, "
            f"{sql_str(a['controlNumber'])}, (SELECT code FROM items WHERE code = {sql_str(rid + '_' + a['controlNumber'])}), "
            f"{sql_str(str(a['date'])[:10])}::date, {sql_str(a['reason'])}, "
            f"{sql_str('add' if a['reason'] in ADD_REASONS else 'remove')}, "
            f"{sql_str('portion' if a.get('qtyBasis') == 'portion' else 'purchase')}, {sql_num(a.get('qty'))}, "
            f"{sql_text(a.get('note'))}, {sql_str(created) + '::timestamptz' if created else 'now()'})"
        )
    out = []
    for store_id, rows in sorted(by_store.items()):
        out.append(f"DELETE FROM adjustments WHERE store_id = {sql_str(store_id)};")
        out.append("INSERT INTO adjustments (store_id, ref, control_number, item_code, date, reason, direction, qty_basis, "
                   "qty, note, created_at) VALUES\n  " + ",\n  ".join(rows) + ";")
    return out


def build_reporting_periods_sql(periods, dish_index):
    by_store = {}
    for p in periods:
        store_id = STORE_ID_MAP.get(p.get("restaurantId"))
        if not store_id or not p.get("periodStart") or not p.get("periodEnd"):
            print(f"  SKIP reporting period (unknown store or missing dates): {p.get('id')}")
            continue
        saved = iso(p.get("savedAt"))
        by_store.setdefault(store_id, []).append(
            f"({sql_str(store_id)}, {sql_str(p.get('id') or 'period_migrated_' + str(len(by_store.get(store_id, []))))}, "
            f"{sql_str(p.get('name'))}, {sql_str(str(p['periodStart'])[:10])}::date, {sql_str(str(p['periodEnd'])[:10])}::date, "
            f"{sql_str(p.get('status') if p.get('status') in ('draft', 'closed') else 'closed')}, "
            f"{dish_sales_sql(p.get('dishSales') or {}, dish_index)}, {sql_json(p.get('itemCounts') or {})}, "
            f"{sql_str(saved) + '::timestamptz' if saved else 'NULL'})"
        )
    out = []
    for store_id, rows in sorted(by_store.items()):
        out.append(f"DELETE FROM reporting_periods WHERE store_id = {sql_str(store_id)};")
        out.append("INSERT INTO reporting_periods (store_id, ref, name, period_start, period_end, status, dish_sales, "
                   "item_counts, saved_at) VALUES\n  " + ",\n  ".join(rows) + ";")
    return out


def main():
    backup_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not backup_dir or not backup_dir.exists():
        print("Usage: python scripts/migrate_adjustments_and_periods.py <backup_dir> [out.sql]")
        sys.exit(1)
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else backup_dir / "migrate_adjustments_and_periods.sql"

    adjustments, periods, dishes = (load(backup_dir, n) for n in ("adjustments", "reporting_periods", "dishes"))
    print(f"Loaded {len(adjustments)} adjustments, {len(periods)} reporting_periods, {len(dishes)} dishes from {backup_dir}")
    statements = build_adjustments_sql(adjustments) + build_reporting_periods_sql(periods, mongo_dish_index(dishes))
    out_path.write_text("BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;\n", encoding="utf-8")
    print(f"Wrote {len(statements)} statements to {out_path}")


if __name__ == "__main__":
    main()
