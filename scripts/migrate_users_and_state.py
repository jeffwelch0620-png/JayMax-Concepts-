"""Transform the MongoDB users/state_versions/areas/sales_periods export into SQL for
the Phase 2 tables (app_users, store_state -- supabase/schema.sql (phase2 migrations)).
Reads the JSON backup, writes a .sql file -- doesn't connect to Postgres directly.
See docs/SUPABASE_MIGRATION_PLAN.md ("Phase 2", chunk 1).

Run: python scripts/migrate_users_and_state.py <backup_dir> [out.sql]

Users keep their Mongo id and PBKDF2 hash, so passwords and already-issued session
tokens keep working after cutover. Re-running is safe: every statement upserts.
The sales period's dishSales keys are remapped to Postgres dish uuids (see
migrate_adjustments_and_periods.py), so run this AFTER migrate_dishes.py is applied.
"""
import json
import sys
from pathlib import Path

try:
    from scripts.migrate_adjustments_and_periods import dish_sales_sql, mongo_dish_index
except ImportError:  # run directly as `python scripts/migrate_users_and_state.py`
    from migrate_adjustments_and_periods import dish_sales_sql, mongo_dish_index

STORE_ID_MAP = {"berts": "berts", "rudds": "rudds", "papa_leonis": "papa", "comm": "comm"}
USER_ROLES = {"owner", "manager", "staff", "readonly"}


def sql_str(v):
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"

def sql_json(v):
    return "NULL" if v is None else sql_str(json.dumps(v)) + "::jsonb"

def sql_text_array(values):
    return "ARRAY[" + ", ".join(sql_str(v) for v in values) + "]::text[]" if values else "'{}'::text[]"

def iso(v):
    # bson.json_util writes datetimes as {"$date": ...}; the app itself stores ISO strings.
    return v.get("$date") if isinstance(v, dict) else v

def load(backup_dir, name):
    path = backup_dir / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else []


def build_users_sql(users):
    statements = []
    for u in users:
        email = (u.get("email") or "").strip().lower()
        if not email or not u.get("passwordHash") or u.get("role") not in USER_ROLES:
            print(f"  SKIP user (missing email/hash or unknown role): {u.get('id')}")
            continue
        created = iso(u.get("createdAt"))
        statements.append(
            "INSERT INTO app_users (id, email, password_hash, role, locations, created_at) VALUES "
            f"({sql_str(u['id'])}, {sql_str(email)}, {sql_str(u['passwordHash'])}, {sql_str(u['role'])}, "
            f"{sql_text_array(u.get('locations') or [])}, {sql_str(created) + '::timestamptz' if created else 'now()'}) "
            "ON CONFLICT (id) DO UPDATE SET email=EXCLUDED.email, password_hash=EXCLUDED.password_hash, "
            "role=EXCLUDED.role, locations=EXCLUDED.locations;"
        )
    return statements


def build_store_state_sql(versions, areas, sales_periods, dish_index=None):
    state = {}
    def row(rid):
        store_id = STORE_ID_MAP.get(rid)
        if not store_id:
            print(f"  SKIP store state (unknown store '{rid}')")
            return None
        return state.setdefault(store_id, {"revision": 0, "areas": None, "sales_period": None})
    for v in versions:
        if (r := row(v.get("restaurantId"))) is not None:
            r["revision"] = int(v.get("revision") or 0)
    for a in areas:
        if (r := row(a.get("restaurantId"))) is not None:
            r["areas"] = a.get("list")
    for sp in sales_periods:
        if (r := row(sp.get("restaurantId"))) is not None:
            r["sales_period"] = {k: v for k, v in sp.items() if k not in ("_id", "restaurantId")}
    def sales_period_sql(sp):
        if sp is None:
            return "NULL"
        rest = {k: v for k, v in sp.items() if k != "dishSales"}
        return f"({sql_json(rest)} || jsonb_build_object('dishSales', {dish_sales_sql(sp.get('dishSales') or {}, dish_index or {})}))"
    return [
        "INSERT INTO store_state (store_id, revision, areas, sales_period) VALUES "
        f"({sql_str(store_id)}, {r['revision']}, {sql_json(r['areas'])}, {sales_period_sql(r['sales_period'])}) "
        "ON CONFLICT (store_id) DO UPDATE SET revision=GREATEST(store_state.revision, EXCLUDED.revision), "
        "areas=EXCLUDED.areas, sales_period=EXCLUDED.sales_period, updated_at=now();"
        for store_id, r in sorted(state.items())
    ]


def main():
    backup_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not backup_dir or not backup_dir.exists():
        print("Usage: python scripts/migrate_users_and_state.py <backup_dir> [out.sql]")
        sys.exit(1)
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else backup_dir / "migrate_users_and_state.sql"

    users = load(backup_dir, "users")
    versions, areas, sales_periods = (load(backup_dir, n) for n in ("state_versions", "areas", "sales_periods"))
    print(f"Loaded {len(users)} users, {len(versions)} state_versions, {len(areas)} areas, "
          f"{len(sales_periods)} sales_periods from {backup_dir}")

    dish_index = mongo_dish_index(load(backup_dir, "dishes"))
    statements = build_users_sql(users) + build_store_state_sql(versions, areas, sales_periods, dish_index)
    out_path.write_text("BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;\n", encoding="utf-8")
    print(f"Wrote {len(statements)} statements to {out_path}")


if __name__ == "__main__":
    main()
