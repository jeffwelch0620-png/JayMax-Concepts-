"""Export every collection in the current MongoDB database to JSON, one file per
collection, before a destructive or risky operation (e.g. the Supabase migration).
This is a data snapshot, not a code snapshot -- use alongside a git tag/branch, not
instead of one.

Uses bson.json_util so ObjectIds/datetimes round-trip safely, unlike plain json.dumps.

Run from anywhere:
    python scripts/export_mongo_backup.py [label]

`label` (optional) is appended to the backup folder name, e.g.:
    python scripts/export_mongo_backup.py pre-supabase-migration
    -> backups/2026-09-29_143000_pre-supabase-migration/
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient
from bson import json_util

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / "backend" / ".env"

def load_env(path):
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')
    return env

def main():
    env = load_env(ENV_PATH)
    mongo_url, db_name = env["MONGO_URL"], env["DB_NAME"]
    label = sys.argv[1] if len(sys.argv) > 1 else ""

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    out_dir = ROOT / "backups" / (f"{stamp}_{label}" if label else stamp)
    out_dir.mkdir(parents=True, exist_ok=True)

    db = MongoClient(mongo_url)[db_name]
    collections = sorted(db.list_collection_names())
    if not collections:
        print(f"No collections found in '{db_name}' at {mongo_url} -- nothing to export.")
        return

    print(f"Exporting database '{db_name}' ({mongo_url}) -> {out_dir}")
    total_docs = 0
    for name in collections:
        docs = list(db[name].find({}))
        (out_dir / f"{name}.json").write_text(json_util.dumps(docs, indent=2), encoding="utf-8")
        total_docs += len(docs)
        print(f"  {name}: {len(docs)} document{'s' if len(docs) != 1 else ''}")

    print(f"\nDone -- {len(collections)} collections, {total_docs} documents total.")
    print(f"Backup folder: {out_dir}")

if __name__ == "__main__":
    main()
