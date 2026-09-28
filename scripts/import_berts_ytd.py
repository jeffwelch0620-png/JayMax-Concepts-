"""One-time import: Bert's YTD purchasing analysis -> live data.
Wipes berts sample data (items, purchases, dishes, prep workflow, projections) and imports:
- 116 coded items (Par Guide, with suggested pars) + 326 proposed-code items (needsReview flag)
- vendor SKUs from Multi-Vendor Sourcing + Items Needing Codes
- approximate purchase history (first/last price points) from Item Price Changes
Run: python3 /app/scripts/import_berts_ytd.py <path-to-xlsx>
"""
import openpyxl, re, sys, uuid
from pymongo import MongoClient

XLSX = sys.argv[1] if len(sys.argv) > 1 else "/tmp/berts_ytd.xlsx"
RID = "berts"

env = {}
for line in open("/app/backend/.env"):
    if "=" in line:
        k, v = line.strip().split("=", 1)
        env[k] = v.strip('"')
db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]

UOM = {"GA": "gal", "LB": "lb", "OZ": "oz", "EA": "each", "GR": "g", "GM": "g", "KG": "kg",
       "CT": "ct", "DZ": "dozen", "QT": "qt", "PT": "pt", "L": "l", "ML": "ml", "#": "each"}

def parse_pack(s):
    s = (s or "").strip().upper()
    m = re.match(r"^(\d+)\s*/\s*([\d.]+)\s*([A-Z# ]+?)\s*$", s)
    if m:
        return int(m.group(1)), float(m.group(2)), UOM.get(m.group(3).strip(), "each")
    m = re.match(r"^([\d.]+)\s*([A-Z# ]+?)\s*$", s)
    if m:
        return 1, float(m.group(1)), UOM.get(m.group(2).strip(), "each")
    return 1, 0, "each"

AREA_MAP = {"counter": "Counter", "prep room": "Prep Room", "walk-in": "Walk-in", "office": "Office",
            "salad bar room": "Salad Bar Room", "shed": "Shed"}
def norm_area(a):
    return AREA_MAP.get(str(a or "").strip().lower(), "Unassigned")

def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0

wb = openpyxl.load_workbook(XLSX, data_only=True)

# ---- price change rows keyed by (vendor, UPPER desc) ----
price_rows = [list(r) for r in wb["Item Price Changes"].iter_rows(min_row=5, values_only=True) if r[0] and r[1]]
price_by_key = {}
for r in price_rows:
    price_by_key[(str(r[0]).strip(), str(r[1]).strip().upper())] = {
        "firstDate": str(r[3])[:10], "lastDate": str(r[4])[:10], "lastPack": str(r[6] or ""),
        "firstPrice": num(r[7]), "lastPrice": num(r[8]), "times": int(num(r[15])), "ytd": num(r[16])}

# ---- multi-vendor map: (vendor, vendor desc upper) -> internal code ----
mv_rows = [list(r) for r in wb["Multi-Vendor Sourcing"].iter_rows(min_row=5, values_only=True)
           if r[0] and re.match(r"^[A-Z]{2,3}-\d+", str(r[0]))]
code_for_vendor_desc = {(str(r[2]).strip(), str(r[3]).strip().upper()): str(r[0]).strip() for r in mv_rows}

# ---- coded items from Par Guide ----
pg_rows = [list(r) for r in wb["Par Guide Starter"].iter_rows(min_row=5, values_only=True) if r[0]]
items = {}
for r in pg_rows:
    code = str(r[0]).strip()
    name = str(r[1] or "").strip()
    area = norm_area(r[2])
    pack = str(r[4] or "").strip()
    pc, uq, uuom = parse_pack(pack)
    vendors = [v.strip() for v in str(r[5] or "").split(",") if v.strip()]
    last_from = str(r[11] or "").strip()
    last_price = num(r[10])
    skus = []
    for v in (vendors or [last_from or "US Foods"]):
        skus.append({"id": "vs_" + uuid.uuid4().hex[:8], "vendor": v, "vendorSku": "", "packDescription": pack,
                     "purchaseUnit": "case", "packCount": pc, "unitQty": uq, "unitUOM": uuom,
                     "price": last_price if v == last_from else 0, "priceUpdatedAt": str(r[4])[:10] if v == last_from else "",
                     "priceSource": "ytd_analysis" if v == last_from else "", "available": True, "preferred": v == last_from})
    if skus and not any(s["preferred"] for s in skus):
        skus[0]["preferred"] = True
    items[code] = {"controlNumber": code, "name": name, "storageArea": area, "active": True, "countActive": True,
                   "orderEnabled": True, "salesTracked": False, "itemType": "portion", "purchaseUnit": "case",
                   "packCount": pc, "unitQty": uq, "unitUOM": uuom, "portionSize": 0, "portionUOM": "",
                   "par": num(r[9]), "currentStock": 0, "lastCounted": "", "vendorSkus": skus,
                   "needsReview": False, "needsPortion": True}

# ---- proposed-code items ----
nc_rows = [list(r) for r in wb["Items Needing Codes"].iter_rows(min_row=5, values_only=True) if r[0]]
for r in nc_rows:
    code = str(r[0]).strip()
    desc = str(r[1] or "").strip()
    vendors = [v.strip() for v in str(r[4] or "").split(",") if v.strip()]
    sku_nums = [s.strip() for s in str(r[3] or "").split(",") if s.strip()]
    area = norm_area(r[5])
    pr = None
    for v in vendors:
        pr = price_by_key.get((v, desc.upper()))
        if pr:
            break
    pack = (pr or {}).get("lastPack", "")
    pc, uq, uuom = parse_pack(pack)
    skus = []
    for i, v in enumerate(vendors):
        sku = sku_nums[i] if i < len(sku_nums) else (sku_nums[0] if sku_nums else "")
        skus.append({"id": "vs_" + uuid.uuid4().hex[:8], "vendor": v, "vendorSku": sku, "packDescription": pack,
                     "purchaseUnit": "case", "packCount": pc, "unitQty": uq, "unitUOM": uuom,
                     "price": (pr or {}).get("lastPrice", 0), "priceUpdatedAt": (pr or {}).get("lastDate", ""),
                     "priceSource": "ytd_analysis" if pr else "", "available": True, "preferred": i == 0})
    if code in items:  # collision with coded item -> merge vendors, keep coded record
        items[code]["vendorSkus"].extend(skus)
        items[code]["needsReview"] = True
        continue
    items[code] = {"controlNumber": code, "name": desc.title(), "storageArea": area, "active": True, "countActive": True,
                   "orderEnabled": True, "salesTracked": False, "itemType": "portion", "purchaseUnit": "case",
                   "packCount": pc, "unitQty": uq, "unitUOM": uuom, "portionSize": 0, "portionUOM": "",
                   "par": 0, "currentStock": 0, "lastCounted": "", "vendorSkus": skus,
                   "needsReview": True, "needsPortion": True}

# ---- approximate purchase history (first/last price points) ----
purchases = []
unmatched = 0
for r in price_rows:
    vendor, desc = str(r[0]).strip(), str(r[1]).strip().upper()
    code = code_for_vendor_desc.get((vendor, desc))
    if not code:
        hit = next((c for c, it in items.items() if it["name"].upper() == desc), None)
        code = hit
    if not code:
        hit = next((c for c, it in items.items() for s in it["vendorSkus"] if s["vendor"] == vendor and desc in it["name"].upper()), None)
        code = hit
    if not code:
        unmatched += 1
        continue
    pr = price_by_key[(vendor, desc)]
    for tag, d, price in (("FIRST", pr["firstDate"], pr["firstPrice"]), ("LAST", pr["lastDate"], pr["lastPrice"])):
        if not d or d == "None" or not price:
            continue
        purchases.append({"id": "pl_" + uuid.uuid4().hex[:8], "invoiceId": "ytd-est", "invoiceDate": d,
                          "invoiceNumber": f"YTD-EST-{tag}", "vendor": vendor, "controlNumber": code,
                          "itemName": items[code]["name"], "qty": 1, "unit": "case",
                          "unitCost": price, "extendedCost": price})

# ---- wipe + insert ----
WIPE = ["items", "purchases", "dishes", "adjustments", "reporting_periods", "prep_stock", "prep_logs",
        "prep_count_sessions", "prep_lists", "prep_items", "prep_overrides", "projected_sales",
        "par_recommendations", "chat_messages"]
for coll in WIPE:
    n = db[coll].delete_many({"restaurantId": RID}).deleted_count
    print(f"wiped {coll}: {n}")

docs = [dict(v, restaurantId=RID) for v in items.values()]
db.items.insert_many(docs)
if purchases:
    db.purchases.insert_many([dict(p, restaurantId=RID) for p in purchases])

AREAS = [{"name": "Salad Bar Room", "prefix": "SB"}, {"name": "Shed", "prefix": "SH"}, {"name": "Office", "prefix": "OF"},
         {"name": "Prep Room", "prefix": "PR"}, {"name": "Walk-in", "prefix": "WI"}, {"name": "Counter", "prefix": "CT"},
         {"name": "Unassigned", "prefix": "NA"}]
db.areas.update_one({"restaurantId": RID}, {"$set": {"restaurantId": RID, "list": AREAS}}, upsert=True)

print(f"items inserted: {len(docs)} (needs review: {sum(1 for d in docs if d['needsReview'])})")
print(f"estimated purchase lines: {len(purchases)} (unmatched vendor/desc rows skipped: {unmatched})")
print(f"items with a priced preferred vendor: {sum(1 for d in docs if any(s['price'] for s in d['vendorSkus']))}")
print("done")
