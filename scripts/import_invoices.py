"""Import real invoice lines (PFG CustomerFirstInvoiceExport + US Foods InvoiceDetails CSVs)
into a restaurant's purchase history. Replaces YTD-EST estimated lines, matches rows to
items by vendor SKU then fuzzy name, updates vendor SKU/price data on matched items.
Run: python3 /app/scripts/import_invoices.py <rid> <pfg_csv_or_-> <usf_dir_or_-> [ship_filter]

`ship_filter` (default "BERT") is matched case-insensitively as a substring against the
PFG "Customer Name" / US Foods "ShipToName" columns to select this restaurant's lines out
of a multi-location export — pass it explicitly when importing for Rudd's/Papa Leoni's or
any other location; the default alone does not make this script reusable across stores.
"""
import csv, glob, os, re, sys, uuid
from collections import defaultdict
from pymongo import MongoClient

RID = sys.argv[1] if len(sys.argv) > 1 else "berts"
PFG_PATH = sys.argv[2] if len(sys.argv) > 2 else "-"
USF_DIR = sys.argv[3] if len(sys.argv) > 3 else "-"
SHIP_FILTER = (sys.argv[4] if len(sys.argv) > 4 else "BERT").upper()

env = {}
for line in open("/app/backend/.env"):
    if "=" in line:
        k, v = line.strip().split("=", 1)
        env[k] = v.strip('"')
db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]

UNIT_MAP = {"CS": "case", "LB": "lb", "EA": "each", "BX": "box", "BG": "bag", "CT": "ct", "GAL": "gal", "DZ": "dozen"}
def map_unit(u):
    return UNIT_MAP.get(str(u or "").strip().upper(), str(u or "").strip().lower() or "case")

def to_iso(mdy):
    parts = str(mdy or "").strip().split("/")
    if len(parts) != 3:
        return str(mdy or "").strip()
    m, d, y = parts
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

def num(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0

def qty_or_fallback(shipped, ordered):
    # A shipped qty of 0 (backorder) is real — only fall back to the ordered
    # qty when the shipped field itself is missing/blank from the CSV row.
    if shipped is not None and str(shipped).strip() != "":
        return num(shipped)
    return num(ordered)

STOP = {"AND", "THE", "OF", "IN", "A", "TO"}
def tokens(s):
    return {t for t in re.findall(r"[A-Z0-9]+", str(s or "").upper()) if len(t) > 1 and t not in STOP}
def norm_name(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())

# ---------------- parse inputs ----------------
def parse_pfg(path):
    rows, others = [], 0
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for o in csv.DictReader(fh):
            cust = (o.get("Customer Name") or "").upper()
            if SHIP_FILTER not in cust:
                others += 1
                continue
            rows.append({"vendor": "PFG", "vendorSku": (o.get("Product #") or "").strip(),
                         "description": (o.get("Product Description") or "").strip(),
                         "packDescription": (o.get("Pack Size") or "").strip(),
                         "qty": qty_or_fallback(o.get("Qty Shipped"), o.get("Qty Ordered")),
                         "unit": map_unit(o.get("UOM")), "unitCost": num(o.get("Unit Price")),
                         "extendedCost": num(o.get("Ext. Price")),
                         "invoiceNumber": (o.get("Invoice Number") or "").strip(),
                         "invoiceDate": to_iso(o.get("Invoice Date"))})
    return [r for r in rows if r["description"] and r["invoiceNumber"]], others

def parse_usf_dir(path):
    rows, others = [], 0
    for fp in sorted(glob.glob(os.path.join(path, "**", "*.csv"), recursive=True)):
        with open(fp, newline="", encoding="utf-8-sig") as fh:
            for o in csv.DictReader(fh):
                ship = (o.get("ShipToName") or "").upper()
                if SHIP_FILTER not in ship:
                    others += 1
                    continue
                rows.append({"vendor": "US Foods", "vendorSku": (o.get("ProductNumber") or "").strip(),
                             "description": (o.get("ProductDescription") or "").strip(),
                             "packDescription": (o.get("PackingSize") or "").strip(),
                             "qty": qty_or_fallback(o.get("QtyShip"), o.get("QtyOrder")),
                             "unit": map_unit(o.get("PricingUnit")), "unitCost": num(o.get("UnitPrice")),
                             "extendedCost": num(o.get("ExtendedPrice")),
                             "invoiceNumber": (o.get("DocumentNumber") or "").strip(),
                             "invoiceDate": to_iso(o.get("DocumentDate"))})
    return [r for r in rows if r["description"] and r["invoiceNumber"]], others

rows, other_lines = [], 0
if PFG_PATH != "-":
    r, n = parse_pfg(PFG_PATH); rows += r; other_lines += n
if USF_DIR != "-":
    r, n = parse_usf_dir(USF_DIR); rows += r; other_lines += n
print(f"parsed {len(rows)} invoice lines matching ship_filter={SHIP_FILTER!r} for {RID} ({other_lines} lines shipped to other locations — skipped)")

# ---------------- load catalog, build match indexes ----------------
items = list(db.items.find({"restaurantId": RID}, {"_id": 0}))
by_sku = {}
by_name = {}
for it in items:
    for s in it.get("vendorSkus", []):
        if s.get("vendorSku"):
            by_sku[(s["vendor"], str(s["vendorSku"]).strip())] = it
    by_name.setdefault(norm_name(it["name"]), it)

def match(row):
    hit = by_sku.get((row["vendor"], row["vendorSku"]))
    if hit:
        return hit, "sku"
    hit = by_name.get(norm_name(row["description"]))
    if hit:
        return hit, "name"
    inv_toks = tokens(row["description"])
    best, best_score, best_overlap = None, 0, 0
    for it in items:
        toks = tokens(it["name"])
        overlap = len(inv_toks & toks)
        score = overlap / len(inv_toks) if inv_toks else 0
        if score > best_score or (score == best_score and overlap > best_overlap):
            best, best_score, best_overlap = it, score, overlap
    if best and best_overlap >= 2 and best_score >= 0.5:
        return best, "fuzzy"
    return None, None

# ---------------- replace estimated lines ----------------
deleted = db.purchases.delete_many({"restaurantId": RID, "invoiceNumber": {"$regex": "^YTD-EST"}}).deleted_count
print(f"removed {deleted} estimated (YTD-EST) lines")

existing = {(p["vendor"], p["invoiceNumber"], p["invoiceDate"], p["controlNumber"], p["itemName"])
            for p in db.purchases.find({"restaurantId": RID}, {"_id": 0})}

# ---------------- match + insert ----------------
new_purchases, unmatched, matched_by = [], [], defaultdict(int)
item_updates = defaultdict(list)  # controlNumber -> rows
seen_in_file = set()
for r in rows:
    it, how = match(r)
    if not it:
        unmatched.append(r)
        continue
    key = (r["vendor"], r["invoiceNumber"], r["invoiceDate"], it["controlNumber"], it["name"])
    if key in existing or key in seen_in_file:
        continue
    seen_in_file.add(key)
    matched_by[how] += 1
    new_purchases.append({"id": "pl_" + uuid.uuid4().hex[:8], "invoiceId": "inv_" + r["vendor"].replace(" ", "") + "_" + r["invoiceNumber"],
                          "invoiceDate": r["invoiceDate"], "invoiceNumber": r["invoiceNumber"], "vendor": r["vendor"],
                          "controlNumber": it["controlNumber"], "itemName": it["name"], "qty": r["qty"],
                          "unit": r["unit"], "unitCost": r["unitCost"], "extendedCost": r["extendedCost"] or r["qty"] * r["unitCost"]})
    item_updates[it["controlNumber"]].append(r)

for it in items:
    hits = item_updates.get(it["controlNumber"])
    if not hits:
        continue
    skus = it.get("vendorSkus", [])
    for r in hits:
        idx = next((i for i, s in enumerate(skus) if s["vendor"] == r["vendor"]), None)
        if idx is not None:
            s = skus[idx]
            s["price"] = r["unitCost"]
            s["priceUpdatedAt"] = r["invoiceDate"]
            s["priceSource"] = "invoice_import"
            if not s.get("vendorSku") and r["vendorSku"]:
                s["vendorSku"] = r["vendorSku"]
            if not s.get("packDescription") and r["packDescription"]:
                s["packDescription"] = r["packDescription"]
        else:
            skus.append({"id": "vs_" + uuid.uuid4().hex[:8], "vendor": r["vendor"], "vendorSku": r["vendorSku"],
                         "packDescription": r["packDescription"], "purchaseUnit": r["unit"] or "case",
                         "packCount": 0, "unitQty": 0, "unitUOM": "each", "price": r["unitCost"],
                         "priceUpdatedAt": r["invoiceDate"], "priceSource": "invoice_import",
                         "available": True, "preferred": len(skus) == 0})
    db.items.update_one({"restaurantId": RID, "controlNumber": it["controlNumber"]}, {"$set": {"vendorSkus": skus}})

if new_purchases:
    db.purchases.insert_many([dict(p, restaurantId=RID) for p in new_purchases])

inv_count = len({(p["vendor"], p["invoiceNumber"]) for p in new_purchases})
spend = sum(p["extendedCost"] for p in new_purchases)
print(f"imported {len(new_purchases)} lines across {inv_count} invoices — ${spend:,.2f}")
print(f"matched by: {dict(matched_by)} | items updated with SKU/price data: {len(item_updates)}")
print(f"unmatched lines: {len(unmatched)}")
if unmatched:
    out = "/tmp/unmatched_invoice_lines.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(unmatched[0].keys()))
        w.writeheader()
        w.writerows(unmatched)
    print(f"unmatched written to {out}")
    for r in unmatched[:15]:
        print("  -", r["vendor"], r["vendorSku"], r["description"][:45], r["invoiceDate"], r["unitCost"])
print("done")
