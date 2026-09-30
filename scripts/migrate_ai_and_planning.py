"""Transform the MongoDB chat_messages/projected_sales/par_recommendations export into SQL
for ai_chat_messages and the Phase 2 tables in
supabase/schema.sql (phase2 migrations). Reads the JSON backup,
writes a .sql file -- doesn't connect to Postgres directly.
See docs/SUPABASE_MIGRATION_PLAN.md ("Phase 2", chunk 5).

Run AFTER migrate_dishes.py has been applied:
  python scripts/migrate_ai_and_planning.py <backup_dir> [out.sql]

Par recommendations point at a Mongo dish id; each is remapped to the Postgres dish uuid
by (store_id, name). One whose recipe no longer resolves is skipped (reported) -- it
could never be applied anyway. Re-running is safe: chat history is replaced per store,
projections and recommendations upsert.
"""
import json
import sys
from pathlib import Path

try:
    from scripts.migrate_adjustments_and_periods import mongo_dish_index, sql_str, sql_text, sql_num, iso, load
except ImportError:  # run directly as `python scripts/migrate_ai_and_planning.py`
    from migrate_adjustments_and_periods import mongo_dish_index, sql_str, sql_text, sql_num, iso, load

STORE_ID_MAP = {"berts": "berts", "rudds": "rudds", "papa_leonis": "papa", "comm": "comm"}


def sql_ts(v, default="now()"):
    v = iso(v)
    return f"{sql_str(v)}::timestamptz" if v else default


def build_chat_sql(messages):
    by_store = {}
    for m in messages:
        store_id = STORE_ID_MAP.get(m.get("restaurantId"))
        if not store_id or m.get("role") not in ("user", "assistant") or not m.get("content"):
            print(f"  SKIP chat message (unknown store/role or empty): {m.get('restaurantId')}/{m.get('role')}")
            continue
        by_store.setdefault(store_id, []).append(
            f"({sql_str(store_id)}, {sql_str(m['role'])}, {sql_str(m['content'])}, {sql_ts(m.get('ts'))})")
    out = []
    for store_id, rows in sorted(by_store.items()):
        out.append(f"DELETE FROM ai_chat_messages WHERE store_id = {sql_str(store_id)};")
        out.append("INSERT INTO ai_chat_messages (store_id, role, content, ts) VALUES\n  " + ",\n  ".join(rows) + ";")
    return out


def build_projections_sql(projections):
    out = []
    for p in projections:
        store_id = STORE_ID_MAP.get(p.get("restaurantId"))
        if not store_id or not p.get("date"):
            print(f"  SKIP projection (unknown store or no date): {p.get('restaurantId')}/{p.get('date')}")
            continue
        out.append(
            "INSERT INTO store_sales_projections (store_id, date, amount, note, entered_by, updated_at) VALUES "
            f"({sql_str(store_id)}, {sql_str(str(p['date'])[:10])}::date, {sql_num(p.get('amount'))}, "
            f"{sql_text(p.get('note'))}, {sql_text(p.get('enteredBy'))}, {sql_ts(p.get('updatedAt'))}) "
            "ON CONFLICT (store_id, date) DO UPDATE SET amount=EXCLUDED.amount, note=EXCLUDED.note, "
            "entered_by=EXCLUDED.entered_by, updated_at=EXCLUDED.updated_at;")
    return out


def build_par_recs_sql(recs, dish_index):
    out = []
    for r in recs:
        store_id = STORE_ID_MAP.get(r.get("restaurantId"))
        target = dish_index.get(r.get("recipeId"))
        if not store_id or not r.get("id") or not target or r.get("recommendedPar") is None:
            print(f"  SKIP par recommendation {r.get('id')} (unknown store, or recipe '{r.get('recipeId')}' doesn't resolve)")
            continue
        status = r.get("status") if r.get("status") in ("pending", "applied", "dismissed") else "pending"
        # INSERT ... SELECT: no row at all if the dish isn't in Postgres (instead of a NOT NULL failure).
        out.append(
            "INSERT INTO par_recommendations (id, store_id, recipe_id, recipe_name, current_par, recommended_par, "
            "reasoning, status, created_at, applied_at) "
            f"SELECT {sql_str(r['id'])}, {sql_str(store_id)}, d.id, {sql_text(r.get('recipeName'))}, "
            f"{sql_num(r.get('currentPar'))}, {sql_num(r['recommendedPar'])}, {sql_text(r.get('reasoning'))}, "
            f"{sql_str(status)}, {sql_ts(r.get('createdAt'))}, {sql_ts(r.get('appliedAt'), 'NULL')} "
            f"FROM dishes d WHERE d.store_id = {sql_str(target[0])} AND d.name = {sql_str(target[1])} "
            "ORDER BY d.created_at LIMIT 1 "
            "ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status, applied_at=EXCLUDED.applied_at;")
    return out


def main():
    backup_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not backup_dir or not backup_dir.exists():
        print("Usage: python scripts/migrate_ai_and_planning.py <backup_dir> [out.sql]")
        sys.exit(1)
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else backup_dir / "migrate_ai_and_planning.sql"

    chats, projections, recs, dishes = (load(backup_dir, n) for n in
                                        ("chat_messages", "projected_sales", "par_recommendations", "dishes"))
    print(f"Loaded {len(chats)} chat_messages, {len(projections)} projected_sales, {len(recs)} par_recommendations, "
          f"{len(dishes)} dishes from {backup_dir}")
    statements = (build_chat_sql(chats) + build_projections_sql(projections)
                  + build_par_recs_sql(recs, mongo_dish_index(dishes)))
    out_path.write_text("BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;\n", encoding="utf-8")
    print(f"Wrote {len(statements)} statements to {out_path}")


if __name__ == "__main__":
    main()
