"""Transform the MongoDB prep_count_sessions/prep_lists export into SQL for the new
Supabase schema (count_sessions/count_lines, prep_lists/prep_list_lines). Reads the
JSON backup, writes a .sql file -- doesn't connect to Postgres directly, applied via
the Supabase MCP tools. See docs/SUPABASE_MIGRATION_PLAN.md (step 3).

Run: python scripts/migrate_counts_and_prep_lists.py <backup_dir> [out.sql]

Recipe references resolve by (store_id, name) against the already-migrated dishes,
same pattern as migrate_dishes.py. prep_lists.generatedFrom (a Mongo
prep_count_session id) resolves by (store_id, count_date, count_type) against the
count_sessions this script itself generates -- unique within the current data.

Known gap, not handled here: Mongo's per-session `revisions[]` (archived snapshots
from earlier submit/reopen cycles) has no home in the new schema and is NOT migrated
-- only the current/latest state of each count session is carried over. In the actual
data this is redundant anyway (each revision duplicates the final submitted state),
but flagging it: a session with genuinely divergent history would lose that history.
"""
import json
import sys
from pathlib import Path

STORE_ID_MAP = {"berts": "berts", "rudds": "rudds", "papa_leonis": "papa"}
TRACK_TO_COUNT_TYPE = {"daily": "nightly_prep", "bulk": "commissary"}


def sql_str(v):
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"

def sql_num(v):
    return "NULL" if v is None else str(v)

def sql_bool(v):
    return "TRUE" if v else "FALSE"


def main():
    backup_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not backup_dir or not backup_dir.exists():
        print("Usage: python scripts/migrate_counts_and_prep_lists.py <backup_dir> [out.sql]")
        sys.exit(1)
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else backup_dir / "migrate_counts_and_prep_lists.sql"

    sessions = json.loads((backup_dir / "prep_count_sessions.json").read_text())
    prep_lists = json.loads((backup_dir / "prep_lists.json").read_text())
    dishes = json.loads((backup_dir / "dishes.json").read_text())
    print(f"Loaded {len(sessions)} prep_count_sessions, {len(prep_lists)} prep_lists, {len(dishes)} dishes from {backup_dir}")

    mongo_dish_id_to_key = {}
    for d in dishes:
        store_id = STORE_ID_MAP.get(d["restaurantId"])
        if store_id:
            mongo_dish_id_to_key[d["id"]] = (store_id, d["name"])

    # mongo prep_count_session id -> (store_id, count_date, count_type), for prep_lists.generatedFrom
    mongo_pcs_id_to_key = {}

    session_rows = []
    line_selects = []
    skipped_sessions = 0
    for s in sessions:
        rid = s["restaurantId"]
        store_id = STORE_ID_MAP.get(rid)
        if not store_id:
            print(f"  SKIP prep_count_session (unknown store '{rid}'): {s.get('id')}")
            skipped_sessions += 1
            continue
        count_type = TRACK_TO_COUNT_TYPE.get(s.get("track"))
        if not count_type:
            print(f"  SKIP prep_count_session (unknown track '{s.get('track')}'): {s.get('id')}")
            skipped_sessions += 1
            continue
        mongo_pcs_id_to_key[s["id"]] = (store_id, s["date"], count_type)
        session_rows.append(
            f"({sql_str(store_id)}, {sql_str(s['date'])}, {sql_str(count_type)}, "
            f"{sql_str(s.get('countedBy'))}, {sql_str(s.get('status'))}, {sql_str(s.get('submittedAt'))}, "
            f"{sql_str(s.get('createdAt'))})"
        )
        for e in s.get("entries", []):
            on_hand = e.get("onHand")
            status = "counted" if on_hand is not None else "not_counted"
            dish_select = "NULL"
            if e.get("recipeId"):
                target = mongo_dish_id_to_key.get(e["recipeId"])
                if target:
                    t_store, t_name = target
                    dish_select = f"(SELECT dish.id FROM dishes dish WHERE dish.store_id = {sql_str(t_store)} AND dish.name = {sql_str(t_name)})"
                else:
                    print(f"  WARN entry references unresolved recipeId '{e['recipeId']}' in session {s['id']}")
            line_selects.append(f"""INSERT INTO count_lines (session_id, dish_id, status, qty, note, saved_by, updated_at)
SELECT cs.id, {dish_select}, {sql_str(status)}, {sql_num(on_hand)}, {sql_str(e.get('note'))}, {sql_str(e.get('savedBy'))}, {sql_str(e.get('savedAt') or s.get('createdAt'))}
FROM count_sessions cs WHERE cs.store_id = {sql_str(store_id)} AND cs.count_date = {sql_str(s['date'])} AND cs.count_type = {sql_str(count_type)};""")

    list_rows = []
    task_selects = []
    skipped_lists = 0
    for pl in prep_lists:
        rid = pl["restaurantId"]
        store_id = STORE_ID_MAP.get(rid)
        if not store_id:
            print(f"  SKIP prep_list (unknown store '{rid}'): {pl.get('id')}")
            skipped_lists += 1
            continue
        from_count_select = "NULL"
        if pl.get("generatedFrom"):
            target = mongo_pcs_id_to_key.get(pl["generatedFrom"])
            if target:
                t_store, t_date, t_type = target
                from_count_select = f"(SELECT cs.id FROM count_sessions cs WHERE cs.store_id = {sql_str(t_store)} AND cs.count_date = {sql_str(t_date)} AND cs.count_type = {sql_str(t_type)})"
            else:
                print(f"  WARN prep_list {pl['id']} references unresolved generatedFrom '{pl['generatedFrom']}'")
        list_rows.append(
            f"({sql_str(store_id)}, {sql_str(pl['date'])}, {from_count_select}, {sql_str(pl.get('status'))}, "
            f"{sql_str(pl.get('releasedAt'))}, {sql_str(pl.get('releasedBy'))}, {sql_str(pl.get('generatedAt'))})"
        )
        for t in pl.get("tasks", []):
            recipe_select = "NULL"
            if t.get("recipeId"):
                target = mongo_dish_id_to_key.get(t["recipeId"])
                if target:
                    t_store, t_name = target
                    recipe_select = f"(SELECT dish.id FROM dishes dish WHERE dish.store_id = {sql_str(t_store)} AND dish.name = {sql_str(t_name)})"
                else:
                    print(f"  WARN task references unresolved recipeId '{t['recipeId']}' in list {pl['id']}")
            batches_planned = t.get("batchesPlanned") or 0
            batches_done = t.get("batchesDone") or 0
            done = batches_planned > 0 and batches_done >= batches_planned
            task_selects.append(f"""INSERT INTO prep_list_lines (list_id, recipe_id, task_type, name, yield_uom, yield_qty, par, on_hand, uncounted, needed_units, batches_planned, batches_done, vessel_name, note, done, done_by_name, done_at, removed)
SELECT pl.id, {recipe_select}, {sql_str(t.get('taskType'))}, {sql_str(t.get('name'))}, {sql_str(t.get('yieldUOM'))}, {sql_num(t.get('yieldQty'))}, {sql_num(t.get('par'))}, {sql_num(t.get('counted'))}, {sql_bool(t.get('uncounted'))}, {sql_num(t.get('neededUnits'))}, {sql_num(t.get('batchesPlanned'))}, {sql_num(t.get('batchesDone'))}, {sql_str(t.get('vesselName'))}, {sql_str(t.get('note'))}, {sql_bool(done)}, {sql_str(t.get('doneBy'))}, {sql_str(t.get('doneAt'))}, {sql_bool(t.get('removed'))}
FROM prep_lists pl WHERE pl.store_id = {sql_str(store_id)} AND pl.prep_date = {sql_str(pl['date'])};""")

    sql = ["-- Generated by scripts/migrate_counts_and_prep_lists.py -- review before applying.\n"]
    sql.append(
        "INSERT INTO count_sessions (store_id, count_date, count_type, counted_by_name, status, submitted_at, created_at) VALUES\n"
        + ",\n".join(session_rows) + ";\n"
    )
    sql.append("\n".join(line_selects) + "\n")
    sql.append(
        "INSERT INTO prep_lists (store_id, prep_date, from_count, status, released_at, released_by, created_at) VALUES\n"
        + ",\n".join(list_rows) + ";\n"
    )
    sql.append("\n".join(task_selects))

    out_path.write_text("\n".join(sql), encoding="utf-8")
    print(f"Wrote {len(session_rows)} count_sessions ({skipped_sessions} skipped), {len(line_selects)} count_lines, "
          f"{len(list_rows)} prep_lists ({skipped_lists} skipped), {len(task_selects)} prep_list_lines -> {out_path}")


if __name__ == "__main__":
    main()
