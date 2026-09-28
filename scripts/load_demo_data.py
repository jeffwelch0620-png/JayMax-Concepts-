#!/usr/bin/env python3
"""Load the sanitized DEMO dataset into an isolated database.

Safe by design:
  * Writes only to the DB named by DB_NAME (use a throwaway like 'berts_demo').
  * Touches only documents scoped to restaurantId == 'demo_diner'.
  * Never modifies operational data.

Usage:
    MONGO_URL="mongodb://localhost:27017" DB_NAME="berts_demo" \
        python scripts/load_demo_data.py
"""
import json
import os
import sys
from pathlib import Path

try:
    from pymongo import MongoClient
except ImportError:
    sys.exit("pymongo is required: pip install pymongo")

DEMO_RID = "demo_diner"
DATA_FILE = Path(__file__).resolve().parent.parent / "sample-data" / "demo_dataset.json"


def main():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "berts_demo")
    if not mongo_url:
        sys.exit("Set MONGO_URL (and optionally DB_NAME, default 'berts_demo').")
    if db_name in ("berts_ops", "production", "prod"):
        sys.exit(f"Refusing to load demo data into '{db_name}'. Use a demo DB name.")

    data = json.loads(DATA_FILE.read_text())
    client = MongoClient(mongo_url)
    db = client[db_name]

    total = 0
    for collection, docs in data.items():
        if collection.startswith("_") or not isinstance(docs, list):
            continue
        col = db[collection]
        # idempotent: clear only demo-scoped docs we manage
        col.delete_many({"restaurantId": DEMO_RID})
        if docs:
            col.insert_many([dict(d) for d in docs])
        total += len(docs)
        print(f"  {collection}: loaded {len(docs)}")

    print(f"Done. {total} demo docs loaded into DB '{db_name}' (restaurantId='{DEMO_RID}').")
    print("Tip: add a 'demo_diner' entry to RESTAURANTS in backend/server.py to see it in the UI.")
    client.close()


if __name__ == "__main__":
    main()
