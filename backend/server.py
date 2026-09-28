from fastapi import FastAPI, APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict, BeforeValidator
from typing import Optional, List, Annotated, Any
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os, json, math, re, uuid, logging, ipaddress, io, base64, hashlib, hmac, secrets, time
import httpx
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse
from pymongo import UpdateOne

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AUTH_SECRET = os.environ.get("AUTH_SECRET", "").strip()
AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "true").lower() not in ("0", "false", "no")
BOOTSTRAP_TOKEN = os.environ.get("BOOTSTRAP_TOKEN", "").strip()
SESSION_TTL = int(os.environ.get("SESSION_TTL_SECONDS", "28800"))
READ_ONLY_PATHS = ("/owner/summary", "/owner/prep-summary", "/owner/orders",
                   "/owner/discrepancies", "/owner/vendor-scorecard", "/reports/")
STAFF_PATHS = ("/prepcount/", "/preplists/", "/prep/", "/staff/", "/prep-items/")
OWNER_PATHS = ("/owner/",)
STAFF_WRITE_PATHS = ("/prepcount/", "/preplists/", "/prep/")
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))
_rate_buckets = {}

def _b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

def _unb64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

def _password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    return f"pbkdf2${_b64(salt)}${hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 240000).hex()}"

def _password_ok(password, stored):
    try:
        _, salt, digest = stored.split("$", 2)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt), 240000).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False

def _token(user):
    payload = {"sub": user["id"], "email": user["email"], "role": user["role"],
               "locations": user.get("locations", []),
               "exp": int(datetime.now(timezone.utc).timestamp()) + SESSION_TTL}
    raw = _b64(json.dumps(payload, separators=(",", ":")).encode())
    key = AUTH_SECRET or BOOTSTRAP_TOKEN
    if not key:
        raise HTTPException(503, "AUTH_SECRET is not configured")
    return f"{raw}.{_b64(hmac.new(key.encode(), raw.encode(), hashlib.sha256).digest())}"

def _decode_token(token):
    try:
        raw, sig = token.split(".", 1)
        key = AUTH_SECRET or BOOTSTRAP_TOKEN
        expected = _b64(hmac.new(key.encode(), raw.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_unb64(raw))
        if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None

def _path_rid(path):
    parts = path.split("/")
    return next((p for p in parts if p in RIDS), None)

async def _record_activity(request, user, status):
    if user and request.url.path not in ("/api/health",):
        await db.activity_log.insert_one({"id": "act_" + uuid.uuid4().hex[:12],
            "userId": user.get("sub"), "email": user.get("email"), "role": user.get("role"),
            "method": request.method, "path": request.url.path, "status": status,
            "restaurantId": _path_rid(request.url.path), "createdAt": _now_iso()})

@app.middleware("http")
async def collaboration_security(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api") or path in ("/api/health", "/api/auth/login", "/api/auth/bootstrap"):
        return await call_next(request)
    if AUTH_REQUIRED and not (AUTH_SECRET or BOOTSTRAP_TOKEN):
        return JSONResponse({"detail": "AUTH_SECRET is not configured"}, status_code=503)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token) if token else None
    if AUTH_REQUIRED and not user:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    if not user:
        return await call_next(request)
    if path.startswith(("/api/ai/chat", "/api/orders/")):
        now = time.monotonic()
        key = (request.client.host if request.client else "unknown", path.split("/")[3] if path.startswith("/api/") else path)
        bucket = [stamp for stamp in _rate_buckets.get(key, []) if now - stamp < 60]
        if len(bucket) >= RATE_LIMIT:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        bucket.append(now)
        _rate_buckets[key] = bucket
    rid = _path_rid(path)
    allowed = set(user.get("locations", []))
    if rid and user.get("role") != "owner" and rid not in allowed:
        return JSONResponse({"detail": "Location access denied"}, status_code=403)
    role = user.get("role")
    if path.startswith(OWNER_PATHS) and role != "owner":
        return JSONResponse({"detail": "Owner role required"}, status_code=403)
    if request.method != "GET":
        if role == "readonly":
            return JSONResponse({"detail": "Read-only access"}, status_code=403)
        if role == "staff" and not path.startswith(STAFF_WRITE_PATHS):
            return JSONResponse({"detail": "Staff access is limited to prep workflow"}, status_code=403)
        if path.startswith(STAFF_PATHS) and role not in ("owner", "manager", "staff"):
            return JSONResponse({"detail": "Insufficient role"}, status_code=403)
    response = await call_next(request)
    try:
        await _record_activity(request, user, response.status_code)
    except Exception:
        logger.exception("Unable to write activity log")
    return response

PyObjectId = Annotated[str, BeforeValidator(str)]

class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    def to_mongo(self):
        return self.model_dump(exclude={"id"})
    @classmethod
    def from_mongo(cls, doc):
        if not doc:
            return None
        doc = dict(doc)
        doc["_id"] = str(doc["_id"])
        return cls(**doc)

class PrepLog(BaseDocument):
    restaurantId: str
    kind: str
    recipeId: Optional[str] = None
    prepItemId: Optional[str] = None
    name: str = ""
    batches: float = 0
    produced: float = 0
    yieldUOM: str = ""
    usage: list = []
    containers: list = []
    totalCost: float = 0
    date: str = ""
    createdAt: str = ""

class ChatMessage(BaseDocument):
    restaurantId: str
    role: str
    content: str
    ts: str = ""

# ---------------- Restaurant registry ----------------
RESTAURANTS = [
    {"id": "berts", "name": "Bert's Hometown Grill & Pizzeria", "short": "Bert's", "location": "Madisonville, TN", "accent": "#F97316"},
    {"id": "rudds", "name": "Rudd's Pies and Fries", "short": "Rudd's", "location": "", "accent": "#EAB308"},
    {"id": "papa_leonis", "name": "Papa Leoni's Pizza", "short": "Papa Leoni's", "location": "", "accent": "#E11D48"},
]
RIDS = {r["id"] for r in RESTAURANTS}

DEFAULT_AREAS = [
    {"name": "Salad Bar Room", "prefix": "SB"}, {"name": "Shed", "prefix": "SH"},
    {"name": "Office", "prefix": "OF"}, {"name": "Prep Room", "prefix": "PR"},
    {"name": "Walk-in", "prefix": "WI"}, {"name": "Counter", "prefix": "CT"},
]

# ---------------- UOM / costing math (ported from the audited JSX) ----------------
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

def preferred_sku(item):
    skus = item.get("vendorSkus") or []
    return next((s for s in skus if s.get("preferred")), skus[0] if skus else None)

def item_derived(item):
    pref = preferred_sku(item) or {}
    pack_count = f(pref.get("packCount", item.get("packCount")))
    unit_qty = f(pref.get("unitQty", item.get("unitQty")))
    unit_uom = pref.get("unitUOM") or item.get("unitUOM") or "each"
    ppu = calc_ppu(pack_count * unit_qty, unit_uom, item.get("portionSize"), item.get("portionUOM"))
    price = f(pref.get("price"))
    return {"portionsPerUnit": ppu, "costPerPortion": price / ppu if ppu > 0 else 0.0, "price": price}

def raw_portions(recipe, target_cn, by_id, stack=()):
    if not recipe or recipe.get("id") in stack:
        return 0.0
    stack = stack + (recipe.get("id"),)
    total = 0.0
    for l in recipe.get("lines", []):
        qty = f(l.get("qty", l.get("qtyPortions")))
        if l.get("sourceType") == "prep":
            sub = by_id.get(l.get("recipeId"))
            if not sub:
                continue
            sy = f(sub.get("yieldQty"), 1) or 1
            total += raw_portions(sub, target_cn, by_id, stack) * (qty / sy)
        elif l.get("controlNumber") == target_cn:
            total += qty
    return total

def recipe_cost(recipe, items_by_cn, by_id, stack=()):
    if not recipe or recipe.get("id") in stack:
        return 0.0
    stack = stack + (recipe.get("id"),)
    total = 0.0
    for l in recipe.get("lines", []):
        qty = f(l.get("qty", l.get("qtyPortions")))
        if l.get("sourceType") == "prep":
            sub = by_id.get(l.get("recipeId"))
            sub_cost = recipe_cost(sub, items_by_cn, by_id, stack)
            sy = f((sub or {}).get("yieldQty"), 1) or 1
            total += (sub_cost / sy) * qty
        else:
            it = items_by_cn.get(l.get("controlNumber"))
            if it:
                total += item_derived(it)["costPerPortion"] * qty
    return total

ADJ_DIRECTIONS = {"waste": "remove", "spoilage": "remove", "employee_meal": "remove", "comp": "remove",
                  "prep_loss": "remove", "transfer_out": "remove", "transfer_in": "add",
                  "count_correction_remove": "remove", "count_correction_add": "add",
                  "other_remove": "remove", "other_add": "add"}
def adj_value(adj, item):
    qty = f(adj.get("qty"))
    portions = qty if adj.get("qtyBasis") == "portion" else qty * item_derived(item)["portionsPerUnit"]
    return abs(portions) * item_derived(item)["costPerPortion"]

# ---------------- Seed data ----------------
def _vs(vendor, sku, pack, price, purchaseUnit="case", packCount=0, unitQty=0, unitUOM="each", preferred=True):
    return {"id": "vs_" + uuid.uuid4().hex[:8], "vendor": vendor, "vendorSku": sku, "packDescription": pack,
            "purchaseUnit": purchaseUnit, "packCount": packCount, "unitQty": unitQty, "unitUOM": unitUOM,
            "price": price, "priceUpdatedAt": "", "priceSource": "manual", "available": True, "preferred": preferred}

def _item(cn, name, area, unit, pc, uq, uuom, psize, puom, par, stock, skus, tracked=True, itype="portion"):
    return {"controlNumber": cn, "name": name, "storageArea": area, "active": True, "countActive": True,
            "orderEnabled": True, "salesTracked": tracked, "itemType": itype, "purchaseUnit": unit,
            "packCount": pc, "unitQty": uq, "unitUOM": uuom, "portionSize": psize, "portionUOM": puom,
            "par": par, "currentStock": stock, "lastCounted": "2026-06-01", "vendorSkus": skus}

def _pur(rid, inv, date, vendor, cn, name, qty, unit, cost):
    return {"id": "pl_" + uuid.uuid4().hex[:8], "invoiceId": "inv_" + inv, "invoiceDate": date,
            "invoiceNumber": inv, "vendor": vendor, "controlNumber": cn, "itemName": name,
            "qty": qty, "unit": unit, "unitCost": cost, "extendedCost": round(qty * cost, 2)}

def _prep(rid_, name, yq, yuom, lines, par, freq, shelf=""):
    return {"id": "prep_" + uuid.uuid4().hex[:8], "recipeType": "prep", "name": name, "menuCategory": "",
            "menuCode": "", "description": "", "photoUrl": "", "price": 0, "targetPct": 30,
            "yieldQty": yq, "yieldUOM": yuom, "procedure": "", "equipment": "", "shelfLife": shelf,
            "portionNote": "", "lines": lines, "prepPar": par, "frequency": freq}

def _il(cn, qty):
    return {"sourceType": "item", "controlNumber": cn, "qty": qty}

def _pl(rid__, qty):
    return {"sourceType": "prep", "recipeId": rid__, "qty": qty}

def build_seeds():
    berts_items = [
        _item("SB-001", "Shredded Lettuce", "Salad Bar Room", "case", 4, 5, "lb", 2, "oz", 3, 1, [_vs("US Foods", "1002341", "4/5lb", 18.5, packCount=4, unitQty=5, unitUOM="lb")]),
        _item("SH-001", "French Fries", "Shed", "case", 6, 5, "lb", 6, "oz", 4, 4, [_vs("PFG", "8821004", "6/5lb", 24.0, packCount=6, unitQty=5, unitUOM="lb")]),
        _item("PR-001", "Ground Beef 80/20", "Prep Room", "case", 1, 40, "lb", 8, "oz", 2, 0.5, [_vs("US Foods", "5501277", "40lb case", 142.0, packCount=1, unitQty=40, unitUOM="lb"), _vs("PFG", "7712450", "40lb case", 138.5, packCount=1, unitQty=40, unitUOM="lb", preferred=False)]),
        _item("WI-001", "Mozzarella Cheese", "Walk-in", "case", 4, 5, "lb", 4, "oz", 3, 2, [_vs("US Foods", "2208953", "4/5lb", 58.0, packCount=4, unitQty=5, unitUOM="lb")]),
        _item("WI-002", "Pizza Dough", "Walk-in", "bag", 1, 50, "lb", 16, "oz", 2, 1, [_vs("PFG", "6650091", "50lb bag", 32.0, "bag", 1, 50, "lb")]),
        _item("CT-001", "Burger Buns", "Counter", "case", 8, 8, "each", 1, "each", 2, 2, [_vs("US Foods", "3304112", "8/8ct", 21.0, packCount=8, unitQty=8, unitUOM="each")], tracked=False),
        _item("OF-001", "Paper Napkins", "Office", "case", 1, 1, "each", 1, "each", 2, 3, [_vs("Webstaurant", "WEB-8811", "Case", 29.99)], tracked=False, itype="usage"),
        _item("SH-002", "Chicken Breast", "Shed", "case", 2, 10, "lb", 6, "oz", 2, 2, [_vs("PFG", "9001234", "2/10lb", 48.0, packCount=2, unitQty=10, unitUOM="lb")]),
    ]
    berts_purchases = [
        _pur("berts", "INV-100234", "2026-06-02", "US Foods", "SB-001", "Shredded Lettuce", 4, "case", 18.5),
        _pur("berts", "INV-100234", "2026-06-02", "US Foods", "PR-001", "Ground Beef 80/20", 1, "case", 140.0),
        _pur("berts", "INV-100511", "2026-06-09", "US Foods", "WI-001", "Mozzarella Cheese", 4, "case", 57.0),
        _pur("berts", "INV-100511", "2026-06-09", "US Foods", "CT-001", "Burger Buns", 3, "case", 21.0),
        _pur("berts", "INV-88217", "2026-06-11", "PFG", "SH-001", "French Fries", 6, "case", 23.5),
        _pur("berts", "INV-88217", "2026-06-11", "PFG", "PR-001", "Ground Beef 80/20", 1, "case", 138.5),
        _pur("berts", "INV-88902", "2026-06-15", "PFG", "WI-002", "Pizza Dough", 4, "bag", 32.0),
        _pur("berts", "INV-100902", "2026-06-16", "US Foods", "OF-001", "Paper Napkins", 2, "case", 29.99),
    ]
    prep_crumble = _prep("berts", "Seasoned Beef Crumble", 240, "oz", [_il("PR-001", 40)], 480, "daily", "4 days refrigerated")
    prep_dough = _prep("berts", "Par-Portioned Dough Balls", 20, "each", [_il("WI-002", 20)], 40, "weekly", "2 days refrigerated")
    berts_dishes = [
        {"id": "dish_" + uuid.uuid4().hex[:8], "recipeType": "menu", "name": "Classic Cheeseburger", "menuCategory": "Sandwich", "menuCode": "SA-001", "description": "8 oz patty, mozzarella, shredded lettuce, toasted bun.", "photoUrl": "", "price": 12.99, "targetPct": 30, "yieldQty": 1, "yieldUOM": "each", "procedure": "", "equipment": "Flat top", "shelfLife": "", "portionNote": "8 oz beef, 4 oz cheese", "lines": [_pl(prep_crumble["id"], 8), _il("CT-001", 1), _il("WI-001", 1), _il("SB-001", 1)]},
        {"id": "dish_" + uuid.uuid4().hex[:8], "recipeType": "menu", "name": "Cheese Pizza 14\"", "menuCategory": "Pizza", "menuCode": "PZ-001", "description": "House dough, mozzarella blend.", "photoUrl": "", "price": 11.99, "targetPct": 30, "yieldQty": 1, "yieldUOM": "each", "procedure": "", "equipment": "Deck oven", "shelfLife": "", "portionNote": "", "lines": [_pl(prep_dough["id"], 1), _il("WI-001", 2)]},
        {"id": "dish_" + uuid.uuid4().hex[:8], "recipeType": "menu", "name": "Side Salad", "menuCategory": "Salads", "menuCode": "SL-001", "description": "", "photoUrl": "", "price": 5.99, "targetPct": 30, "yieldQty": 1, "yieldUOM": "each", "procedure": "", "equipment": "", "shelfLife": "", "portionNote": "", "lines": [_il("SB-001", 2)]},
        {"id": "dish_" + uuid.uuid4().hex[:8], "recipeType": "menu", "name": "Fries Side", "menuCategory": "Fryer/Appetizers", "menuCode": "FR-001", "description": "", "photoUrl": "", "price": 3.99, "targetPct": 30, "yieldQty": 1, "yieldUOM": "each", "procedure": "", "equipment": "Fryer", "shelfLife": "", "portionNote": "6 oz", "lines": [_il("SH-001", 1)]},
        prep_crumble, prep_dough,
    ]

    rudds_items = [
        _item("WI-001", "Russet Potatoes", "Walk-in", "bag", 1, 50, "lb", 10, "oz", 3, 2, [_vs("PFG", "1102033", "50lb bag", 28.0, "bag", 1, 50, "lb")]),
        _item("WI-002", "Beef Mince (Pie Grade)", "Walk-in", "case", 1, 40, "lb", 8, "oz", 2, 1, [_vs("US Foods", "5508100", "40lb case", 136.0, packCount=1, unitQty=40, unitUOM="lb")]),
        _item("PR-001", "Pie Dough", "Prep Room", "case", 2, 10, "lb", 6, "oz", 2, 1.5, [_vs("PFG", "6655010", "2/10lb", 26.5, packCount=2, unitQty=10, unitUOM="lb")]),
        _item("SH-001", "Fryer Oil", "Shed", "bucket", 1, 35, "lb", 1, "lb", 2, 1, [_vs("Webstaurant", "WEB-5520", "35lb jug", 42.0, "bucket", 1, 35, "lb")], tracked=False, itype="usage"),
        _item("CT-001", "Pie Foil Tins", "Counter", "case", 500, 1, "each", 1, "each", 1, 1, [_vs("Webstaurant", "WEB-7712", "500ct", 38.0, packCount=500, unitQty=1, unitUOM="each")], tracked=False),
        _item("WI-003", "Gravy Mix", "Walk-in", "case", 6, 1.5, "lb", 1, "oz", 1, 1, [_vs("US Foods", "7700321", "6/1.5lb", 31.0, packCount=6, unitQty=1.5, unitUOM="lb")]),
        _item("WI-004", "Cheese Curds", "Walk-in", "case", 4, 5, "lb", 2, "oz", 2, 1, [_vs("PFG", "3310890", "4/5lb", 62.0, packCount=4, unitQty=5, unitUOM="lb")]),
    ]
    rudds_purchases = [
        _pur("rudds", "INV-77001", "2026-06-03", "PFG", "WI-001", "Russet Potatoes", 3, "bag", 27.5),
        _pur("rudds", "INV-77001", "2026-06-03", "PFG", "PR-001", "Pie Dough", 2, "case", 26.5),
        _pur("rudds", "INV-20115", "2026-06-10", "US Foods", "WI-002", "Beef Mince (Pie Grade)", 1, "case", 136.0),
        _pur("rudds", "INV-20115", "2026-06-10", "US Foods", "WI-003", "Gravy Mix", 1, "case", 31.0),
    ]
    prep_filling = _prep("rudds", "Beef Pie Filling Batch", 320, "oz", [_il("WI-002", 40), _il("WI-003", 8)], 640, "daily", "3 days refrigerated")
    rudds_dishes = [
        {"id": "dish_" + uuid.uuid4().hex[:8], "recipeType": "menu", "name": "Classic Beef Pie", "menuCategory": "Grill", "menuCode": "GR-001", "description": "Flaky pie with seasoned beef filling and gravy.", "photoUrl": "", "price": 8.99, "targetPct": 30, "yieldQty": 1, "yieldUOM": "each", "procedure": "", "equipment": "Pie oven", "shelfLife": "", "portionNote": "", "lines": [_pl(prep_filling["id"], 8), _il("PR-001", 1), _il("CT-001", 1)]},
        {"id": "dish_" + uuid.uuid4().hex[:8], "recipeType": "menu", "name": "Loaded Curd Fries", "menuCategory": "Fryer/Appetizers", "menuCode": "FR-001", "description": "Hand-cut fries, cheese curds, gravy.", "photoUrl": "", "price": 6.99, "targetPct": 28, "yieldQty": 1, "yieldUOM": "each", "procedure": "", "equipment": "Fryer", "shelfLife": "", "portionNote": "", "lines": [_il("WI-001", 1.5), _il("WI-004", 1.5), _il("WI-003", 0.5)]},
        prep_filling,
    ]

    papa_items = [
        _item("WI-001", "00 Flour", "Walk-in", "bag", 1, 50, "lb", 10, "oz", 2, 1.5, [_vs("US Foods", "1109987", "50lb bag", 38.0, "bag", 1, 50, "lb")]),
        _item("WI-002", "San Marzano Tomatoes", "Walk-in", "case", 6, 100, "fl oz", 4, "fl oz", 2, 1, [_vs("PFG", "4401267", "6/#10", 42.0, packCount=6, unitQty=100, unitUOM="fl oz")]),
        _item("WI-003", "Fior di Latte Mozzarella", "Walk-in", "case", 6, 3, "lb", 4, "oz", 2, 2, [_vs("US Foods", "2208811", "6/3lb", 66.0, packCount=6, unitQty=3, unitUOM="lb")]),
        _item("WI-004", "Pepperoni", "Walk-in", "case", 2, 5, "lb", 2, "oz", 1, 1, [_vs("PFG", "5503412", "2/5lb", 44.0, packCount=2, unitQty=5, unitUOM="lb")]),
        _item("CT-001", "Pizza Boxes 14\"", "Counter", "case", 100, 1, "each", 1, "each", 1, 0.5, [_vs("Webstaurant", "WEB-3301", "100ct", 32.0, packCount=100, unitQty=1, unitUOM="each")], tracked=False),
    ]
    papa_purchases = [
        _pur("papa_leonis", "INV-55012", "2026-06-05", "US Foods", "WI-001", "00 Flour", 2, "bag", 37.5),
        _pur("papa_leonis", "INV-55012", "2026-06-05", "US Foods", "WI-003", "Fior di Latte Mozzarella", 2, "case", 65.0),
        _pur("papa_leonis", "INV-91044", "2026-06-12", "PFG", "WI-002", "San Marzano Tomatoes", 2, "case", 42.0),
        _pur("papa_leonis", "INV-91044", "2026-06-12", "PFG", "WI-004", "Pepperoni", 1, "case", 44.0),
    ]
    prep_pdough = _prep("papa_leonis", "Neapolitan Dough Batch", 50, "each", [_il("WI-001", 50)], 100, "daily", "48 hr cold ferment")
    prep_psauce = _prep("papa_leonis", "San Marzano Pizza Sauce", 3, "qt", [_il("WI-002", 24)], 6, "biweekly", "5 days refrigerated")
    papa_dishes = [
        {"id": "dish_" + uuid.uuid4().hex[:8], "recipeType": "menu", "name": "Margherita 14\"", "menuCategory": "Pizza", "menuCode": "PZ-001", "description": "San Marzano sauce, fior di latte, basil.", "photoUrl": "", "price": 14.99, "targetPct": 30, "yieldQty": 1, "yieldUOM": "each", "procedure": "", "equipment": "Wood-fired oven", "shelfLife": "", "portionNote": "", "lines": [_pl(prep_pdough["id"], 1), _pl(prep_psauce["id"], 0.125), _il("WI-003", 1.5), _il("CT-001", 1)]},
        {"id": "dish_" + uuid.uuid4().hex[:8], "recipeType": "menu", "name": "Pepperoni 14\"", "menuCategory": "Pizza", "menuCode": "PZ-002", "description": "Cup-and-char pepperoni, mozzarella.", "photoUrl": "", "price": 16.99, "targetPct": 30, "yieldQty": 1, "yieldUOM": "each", "procedure": "", "equipment": "Wood-fired oven", "shelfLife": "", "portionNote": "", "lines": [_pl(prep_pdough["id"], 1), _pl(prep_psauce["id"], 0.125), _il("WI-003", 1.5), _il("WI-004", 1.5), _il("CT-001", 1)]},
        prep_pdough, prep_psauce,
    ]

    return {
        "berts": {"items": berts_items, "purchases": berts_purchases, "dishes": berts_dishes},
        "rudds": {"items": rudds_items, "purchases": rudds_purchases, "dishes": rudds_dishes},
        "papa_leonis": {"items": papa_items, "purchases": papa_purchases, "dishes": papa_dishes},
    }

SEEDS = build_seeds()

# ---------------- Persistence helpers ----------------
COLL_MAP = {"items": "items", "purchases": "purchases", "dishes": "dishes", "adjustments": "adjustments",
            "reportingPeriods": "reporting_periods", "prepStock": "prep_stock", "prepLogs": "prep_logs"}
WRITABLE = {"items", "purchases", "dishes", "adjustments", "reportingPeriods", "prepStock"}

def check_rid(rid):
    if rid not in RIDS:
        raise HTTPException(404, "unknown restaurant")

def _workweek():
    today = datetime.now(timezone.utc).date()
    diff = (today.weekday() - 2) % 7  # workweek starts Wednesday (Mon=0)
    start = today - timedelta(days=diff)
    return start.isoformat(), (start + timedelta(days=6)).isoformat()

async def ensure_seed(rid):
    if await db.items.count_documents({"restaurantId": rid}) > 0:
        return
    seed = SEEDS[rid]
    for coll in ("items", "purchases", "dishes"):
        docs = [dict(d, restaurantId=rid) for d in seed[coll]]
        if docs:
            await db[COLL_MAP[coll]].insert_many(docs)
    ws, we = _workweek()
    await db.sales_periods.update_one({"restaurantId": rid},
        {"$setOnInsert": {"restaurantId": rid, "periodStart": ws, "periodEnd": we, "dishSales": {}, "itemCounts": {}}}, upsert=True)
    await db.areas.update_one({"restaurantId": rid}, {"$setOnInsert": {"restaurantId": rid, "list": DEFAULT_AREAS}}, upsert=True)

async def _check_and_bump_revision(rid, request: Request):
    raw = request.headers.get("if-match")
    current = await db.state_versions.find_one({"restaurantId": rid}, {"_id": 0, "revision": 1})
    revision = (current or {}).get("revision", 0)
    if raw and raw.strip('"') != str(revision):
        raise HTTPException(409, f"State changed by another collaborator; reload before saving (revision {revision})")
    new_revision = revision + 1
    await db.state_versions.update_one({"restaurantId": rid},
        {"$set": {"revision": new_revision, "updatedAt": _now_iso()}}, upsert=True)
    return new_revision

# ---------------- Routes ----------------
@api_router.get("/health")
async def health():
    return {"status": "ok"}

class LoginIn(BaseModel):
    email: str
    password: str

class BootstrapIn(BaseModel):
    bootstrapToken: str
    email: str
    password: str
    role: str = "owner"
    locations: List[str] = []

class UserIn(BaseModel):
    email: str
    password: str
    role: str = "staff"
    locations: List[str] = []

def _clean_user(doc):
    return {"id": doc["id"], "email": doc["email"], "role": doc["role"],
            "locations": doc.get("locations", [])}

@api_router.post("/auth/bootstrap")
async def auth_bootstrap(body: BootstrapIn):
    if not BOOTSTRAP_TOKEN or not hmac.compare_digest(body.bootstrapToken, BOOTSTRAP_TOKEN):
        raise HTTPException(403, "Invalid bootstrap token")
    if await db.users.count_documents({}):
        raise HTTPException(409, "Bootstrap has already been completed")
    if body.role != "owner" or not body.email.strip() or len(body.password) < 12:
        raise HTTPException(400, "The first account must be an owner with a 12-character password")
    user = {"id": "usr_" + uuid.uuid4().hex[:12], "email": body.email.strip().lower(),
            "passwordHash": _password_hash(body.password), "role": "owner",
            "locations": sorted(RIDS), "createdAt": _now_iso()}
    await db.users.insert_one(user)
    return {"user": _clean_user(user), "token": _token(user)}

@api_router.post("/auth/login")
async def auth_login(body: LoginIn):
    user = await db.users.find_one({"email": body.email.strip().lower()})
    if not user or not _password_ok(body.password, user.get("passwordHash", "")):
        raise HTTPException(401, "Invalid email or password")
    return {"user": _clean_user(user), "token": _token(user)}

@api_router.get("/auth/me")
async def auth_me(request: Request):
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token)
    if not user:
        raise HTTPException(401, "Authentication required")
    return user

@api_router.post("/auth/users")
async def auth_create_user(body: UserIn, request: Request):
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    actor = _decode_token(token)
    if not actor or actor.get("role") != "owner":
        raise HTTPException(403, "Owner role required")
    if body.role not in ("owner", "manager", "staff", "readonly") or len(body.password) < 12:
        raise HTTPException(400, "Invalid role or password")
    locations = sorted(set(body.locations) & RIDS)
    if body.role == "owner":
        locations = sorted(RIDS)
    user = {"id": "usr_" + uuid.uuid4().hex[:12], "email": body.email.strip().lower(),
            "passwordHash": _password_hash(body.password), "role": body.role,
            "locations": locations, "createdAt": _now_iso()}
    try:
        await db.users.insert_one(user)
    except Exception:
        raise HTTPException(409, "A user with that email already exists")
    return _clean_user(user)

@api_router.get("/restaurants")
async def restaurants():
    return RESTAURANTS

@api_router.get("/state/{rid}")
async def get_state(rid: str):
    check_rid(rid)
    await ensure_seed(rid)
    state = {}
    for name, coll in COLL_MAP.items():
        state[name] = await db[coll].find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    sp = await db.sales_periods.find_one({"restaurantId": rid}, {"_id": 0})
    ws, we = _workweek()
    state["salesPeriod"] = sp or {"periodStart": ws, "periodEnd": we, "dishSales": {}, "itemCounts": {}}
    state["salesPeriod"].pop("restaurantId", None)
    areas = await db.areas.find_one({"restaurantId": rid}, {"_id": 0})
    state["areas"] = (areas or {}).get("list", DEFAULT_AREAS)
    version = await db.state_versions.find_one({"restaurantId": rid}, {"_id": 0, "revision": 1})
    state["revision"] = (version or {}).get("revision", 0)
    return state

@api_router.put("/state/{rid}/salesPeriod")
async def put_sales_period(rid: str, payload: dict, request: Request):
    check_rid(rid)
    revision = await _check_and_bump_revision(rid, request)
    payload = dict(payload)
    payload["restaurantId"] = rid
    await db.sales_periods.replace_one({"restaurantId": rid}, payload, upsert=True)
    return {"ok": True, "revision": revision}

@api_router.put("/state/{rid}/areas")
async def put_areas(rid: str, payload: List[Any], request: Request):
    check_rid(rid)
    revision = await _check_and_bump_revision(rid, request)
    await db.areas.update_one({"restaurantId": rid}, {"$set": {"restaurantId": rid, "list": payload}}, upsert=True)
    return {"ok": True, "revision": revision}

@api_router.put("/state/{rid}/{collection}")
async def put_collection(rid: str, collection: str, payload: List[Any], request: Request):
    check_rid(rid)
    if collection not in WRITABLE:
        raise HTTPException(400, "collection not writable")
    revision = await _check_and_bump_revision(rid, request)
    coll = COLL_MAP[collection]
    # Insert the new snapshot FIRST (tagged with a one-off batch marker), then delete
    # only the old docs that aren't part of this batch. A delete-then-insert here would
    # leave the collection empty with no rollback if insert_many failed partway through;
    # this ordering means a failed write leaves the previous data intact instead.
    batch = uuid.uuid4().hex
    docs = [dict(d, restaurantId=rid, _batch=batch) for d in payload if isinstance(d, dict)]
    if docs:
        await db[coll].insert_many(docs)
    await db[coll].delete_many({"restaurantId": rid, "_batch": {"$ne": batch}})
    if docs:
        await db[coll].update_many({"restaurantId": rid, "_batch": batch}, {"$unset": {"_batch": ""}})
    return {"ok": True, "count": len(docs), "revision": revision}

# ---------------- Prep module ----------------
class ContainerIn(BaseModel):
    label: str = ""
    size: float = 0
    count: int = 0

class PrepCompleteIn(BaseModel):
    recipeId: str
    batches: float
    containers: List[ContainerIn] = []

async def _prep_stock_list(rid):
    return await db.prep_stock.find({"restaurantId": rid}, {"_id": 0}).to_list(5000)

async def _deduct_and_stock(rid, recipe, batches, containers, kind, name):
    items = await db.items.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    dishes = await db.dishes.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    by_id = {d["id"]: d for d in dishes}
    yield_qty = f(recipe.get("yieldQty"), 1) or 1
    usage = []
    for it in items:
        portions = raw_portions(recipe, it["controlNumber"], by_id) * batches
        if portions <= 0:
            continue
        d = item_derived(it)
        units = portions / d["portionsPerUnit"] if d["portionsPerUnit"] > 0 else 0
        it["currentStock"] = max(0, round(f(it.get("currentStock")) - units, 3))
        usage.append({"controlNumber": it["controlNumber"], "name": it.get("name", ""), "portions": round(portions, 2),
                      "units": round(units, 3), "purchaseUnit": it.get("purchaseUnit", "case"),
                      "cost": round(portions * d["costPerPortion"], 2)})
    await db.items.bulk_write([
        UpdateOne({"restaurantId": rid, "controlNumber": it["controlNumber"]},
                  {"$set": {"currentStock": it["currentStock"]}})
        for it in items
    ])
    produced = yield_qty * batches
    now = datetime.now(timezone.utc)
    new_conts = [dict(c, id="c_" + uuid.uuid4().hex[:8], createdAt=now.isoformat())
                 for c in containers if c.get("count", 0) > 0 and c.get("size", 0) > 0]
    existing = await db.prep_stock.find_one({"restaurantId": rid, "recipeId": recipe["id"]}, {"_id": 0})
    on_hand = f((existing or {}).get("onHand")) + produced
    conts = (existing or {}).get("containers", []) + new_conts
    await db.prep_stock.update_one({"restaurantId": rid, "recipeId": recipe["id"]},
        {"$set": {"restaurantId": rid, "recipeId": recipe["id"], "name": recipe.get("name", ""),
                  "onHand": round(on_hand, 3), "yieldUOM": recipe.get("yieldUOM", "each"), "containers": conts}}, upsert=True)
    log = PrepLog(restaurantId=rid, kind=kind, recipeId=recipe["id"], name=name,
                  batches=batches, produced=round(produced, 2), yieldUOM=recipe.get("yieldUOM", "each"),
                  usage=usage, containers=new_conts, totalCost=round(sum(u["cost"] for u in usage), 2),
                  date=now.date().isoformat(), createdAt=now.isoformat())
    await db.prep_logs.insert_one(log.to_mongo())
    items = await db.items.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    return {"items": items, "prepStock": await _prep_stock_list(rid), "log": log.model_dump()}

async def _deduct_item_and_stock(rid, pitem, vessels):
    items = await db.items.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    item = next((i for i in items if i["controlNumber"] == pitem.get("controlNumber")), None)
    if not item:
        raise HTTPException(404, f"inventory item {pitem.get('controlNumber')} not found")
    d = item_derived(item)
    portions = vessels * f(pitem.get("vesselCapacity"))
    units = portions / d["portionsPerUnit"] if d["portionsPerUnit"] > 0 else 0
    cost = portions * d["costPerPortion"]
    new_stock = max(0, round(f(item.get("currentStock")) - units, 3))
    await db.items.update_one({"restaurantId": rid, "controlNumber": item["controlNumber"]},
                              {"$set": {"currentStock": new_stock}})
    item["currentStock"] = new_stock
    now = datetime.now(timezone.utc)
    existing = await db.prep_stock.find_one({"restaurantId": rid, "prepItemId": pitem["id"]}, {"_id": 0})
    on_hand = f((existing or {}).get("onHand")) + vessels
    await db.prep_stock.update_one({"restaurantId": rid, "prepItemId": pitem["id"]},
        {"$set": {"restaurantId": rid, "prepItemId": pitem["id"], "recipeId": None, "name": pitem.get("name", ""),
                  "onHand": round(on_hand, 3), "yieldUOM": pitem.get("vesselName", "vessel"),
                  "containers": (existing or {}).get("containers", [])}}, upsert=True)
    log = PrepLog(restaurantId=rid, kind="batch", prepItemId=pitem["id"], name=pitem.get("name", ""),
                  batches=vessels, produced=round(vessels, 2), yieldUOM=pitem.get("vesselName", "vessel"),
                  usage=[{"controlNumber": item["controlNumber"], "name": item.get("name", ""), "portions": round(portions, 2),
                          "units": round(units, 3), "purchaseUnit": item.get("purchaseUnit", "case"), "cost": round(cost, 2)}],
                  containers=[], totalCost=round(cost, 2), date=now.date().isoformat(), createdAt=now.isoformat())
    await db.prep_logs.insert_one(log.to_mongo())
    items = await db.items.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    return {"items": items, "prepStock": await _prep_stock_list(rid), "log": log.model_dump()}

@api_router.post("/prep/{rid}/complete")
async def complete_prep(rid: str, body: PrepCompleteIn):
    check_rid(rid)
    if body.batches <= 0:
        raise HTTPException(400, "batches must be greater than zero")
    dishes = await db.dishes.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    recipe = next((d for d in dishes if d.get("id") == body.recipeId and d.get("recipeType") == "prep"), None)
    if not recipe:
        raise HTTPException(404, "prep recipe not found")
    return await _deduct_and_stock(rid, recipe, body.batches, [c.model_dump() for c in body.containers], "batch", recipe.get("name", ""))

class ApplySalesIn(BaseModel):
    dishSales: dict = {}

@api_router.post("/prep/{rid}/apply-sales")
async def apply_sales(rid: str, body: ApplySalesIn):
    check_rid(rid)
    dishes = await db.dishes.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    by_id = {d["id"]: d for d in dishes}
    usage_by_recipe = {}
    for d in dishes:
        if d.get("recipeType") == "prep":
            continue
        sold = f(body.dishSales.get(d.get("id")))
        if sold <= 0:
            continue
        for l in d.get("lines", []):
            if l.get("sourceType") == "prep":
                usage_by_recipe[l["recipeId"]] = usage_by_recipe.get(l["recipeId"], 0) + f(l.get("qty")) * sold
    if not usage_by_recipe:
        raise HTTPException(400, "no prep usage found in the saved sales figures")
    now = datetime.now(timezone.utc)
    usage_rows = []
    for recipe_id, used in usage_by_recipe.items():
        stock = await db.prep_stock.find_one({"restaurantId": rid, "recipeId": recipe_id}, {"_id": 0})
        if not stock:
            continue
        new_on_hand = max(0, round(f(stock.get("onHand")) - used, 3))
        await db.prep_stock.update_one({"restaurantId": rid, "recipeId": recipe_id}, {"$set": {"onHand": new_on_hand}})
        sub = by_id.get(recipe_id, {})
        usage_rows.append({"recipeId": recipe_id, "name": stock.get("name") or sub.get("name", ""),
                           "used": round(used, 2), "yieldUOM": stock.get("yieldUOM", ""), "remaining": new_on_hand})
    log = PrepLog(restaurantId=rid, kind="sales_usage", name="Menu sales prep usage", usage=usage_rows,
                  date=now.date().isoformat(), createdAt=now.isoformat())
    await db.prep_logs.insert_one(log.to_mongo())
    return {"prepStock": await _prep_stock_list(rid), "log": log.model_dump()}

class UseContainerIn(BaseModel):
    recipeId: str
    containerId: str

@api_router.post("/prep/{rid}/use-container")
async def use_container(rid: str, body: UseContainerIn):
    check_rid(rid)
    stock = await db.prep_stock.find_one({"restaurantId": rid, "recipeId": body.recipeId}, {"_id": 0})
    if not stock:
        raise HTTPException(404, "prep stock not found")
    conts = stock.get("containers", [])
    target = next((c for c in conts if c.get("id") == body.containerId), None)
    if not target:
        raise HTTPException(404, "container not found")
    remaining = [c for c in conts if c.get("id") != body.containerId]
    new_on_hand = max(0, round(f(stock.get("onHand")) - f(target.get("size")), 3))
    await db.prep_stock.update_one({"restaurantId": rid, "recipeId": body.recipeId},
                                   {"$set": {"onHand": new_on_hand, "containers": remaining}})
    now = datetime.now(timezone.utc)
    log = PrepLog(restaurantId=rid, kind="container_use", recipeId=body.recipeId,
                  name=f"{stock.get('name', '')} — {target.get('label', 'container')} to service",
                  produced=-f(target.get("size")), yieldUOM=stock.get("yieldUOM", ""),
                  date=now.date().isoformat(), createdAt=now.isoformat())
    await db.prep_logs.insert_one(log.to_mongo())
    return {"prepStock": await _prep_stock_list(rid), "log": log.model_dump()}

# ---------------- Nightly prep count & task workflow ----------------
def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _today():
    return datetime.now(timezone.utc).date().isoformat()

async def _prep_recipes(rid):
    dishes = await db.dishes.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    return [d for d in dishes if d.get("recipeType") == "prep"]

async def _prep_universe_for_track(rid, track):
    # Prep recipes are track-agnostic (shared) — track lives on the governing Prep Item.
    # "daily" keeps today's behavior: every recipe listed/seeded directly (governance
    # exclusion happens later, at task-building time, same as before this feature) plus
    # daily-track prep items. "bulk" has no direct-recipe path — a recipe only appears in
    # Bulk if a bulk-track Prep Item governs it, since recipes carry no track marker of
    # their own. `all_recipes_by_id` is always the FULL unfiltered set — needed to look up
    # name/yieldUOM/yieldQty/prepPar for recipe-governed items regardless of track.
    all_recipes = await _prep_recipes(rid)
    prep_items = await db.prep_items.find({"restaurantId": rid, **_track_filter(track)}, {"_id": 0}).to_list(1000)
    direct_recipes = [] if track == "bulk" else all_recipes
    all_recipes_by_id = {r["id"]: r for r in all_recipes}
    return direct_recipes, prep_items, all_recipes_by_id

async def _get_or_create_session(rid, date, track="daily"):
    s = await db.prep_count_sessions.find_one({"restaurantId": rid, "date": date, **_track_filter(track)}, {"_id": 0})
    if not s:
        s = {"id": "pcs_" + uuid.uuid4().hex[:10], "restaurantId": rid, "date": date, "track": track, "status": "open",
             "countedBy": "", "entries": [], "submittedAt": None, "revision": 1, "revisions": [],
             "createdAt": _now_iso()}
        await db.prep_count_sessions.insert_one(dict(s))
    recipes, prep_items, _ = await _prep_universe_for_track(rid, track)
    known = {(e.get("recipeId") or e.get("prepItemId")) for e in s["entries"]}
    added = False
    for r in recipes:
        if r["id"] not in known:
            s["entries"].append({"recipeId": r["id"], "prepItemId": None, "onHand": None, "note": "", "savedAt": None, "savedBy": ""})
            added = True
    for p in prep_items:
        if p["id"] not in known:
            s["entries"].append({"recipeId": None, "prepItemId": p["id"], "onHand": None, "note": "", "savedAt": None, "savedBy": ""})
            added = True
    if added and s.get("status") == "open":
        await db.prep_count_sessions.update_one({"restaurantId": rid, "id": s["id"]}, {"$set": {"entries": s["entries"]}})
    s["recipes"] = [{"id": r["id"], "name": r.get("name", ""), "yieldUOM": r.get("yieldUOM", "each"),
                     "yieldQty": f(r.get("yieldQty"), 1), "shelfLife": r.get("shelfLife", ""), "prepPar": f(r.get("prepPar"))} for r in recipes]
    s["prepItems"] = [{"id": p["id"], "name": p.get("name", ""), "vesselName": p.get("vesselName", "vessel"),
                       "parVessels": f(p.get("parVessels")), "schedule": p.get("schedule", "daily")} for p in prep_items]
    return s

@api_router.get("/prepcount/{rid}/session")
async def get_count_session(rid: str, date: str = "", track: str = "daily"):
    check_rid(rid)
    return await _get_or_create_session(rid, date or _today(), track)

class CountEntryIn(BaseModel):
    recipeId: Optional[str] = None
    prepItemId: Optional[str] = None
    onHand: Optional[float] = None
    note: str = ""
    countedBy: str = ""

@api_router.post("/prepcount/{rid}/session/{sid}/entry")
async def save_count_entry(rid: str, sid: str, body: CountEntryIn):
    check_rid(rid)
    if body.onHand is None:
        raise HTTPException(400, "Blank counts are not saved — enter a number")
    s = await db.prep_count_sessions.find_one({"restaurantId": rid, "id": sid})
    if not s:
        raise HTTPException(404, "session not found")
    entries = s.get("entries", [])
    key = body.recipeId or body.prepItemId
    idx = next((i for i, e in enumerate(entries) if (e.get("recipeId") or e.get("prepItemId")) == key), None)
    if idx is None:
        raise HTTPException(404, "item not in this count list")
    update = {"$set": {}}
    new_revision = s.get("revision", 1)
    if s.get("status") == "submitted":
        update["$push"] = {"revisions": {"revision": s.get("revision", 1), "entries": s.get("entries", []),
                                         "archivedAt": _now_iso(), "archivedBy": body.countedBy}}
        new_revision = s.get("revision", 1) + 1
        update["$set"]["revision"] = new_revision
    entries[idx] = {"recipeId": body.recipeId, "prepItemId": body.prepItemId, "onHand": body.onHand, "note": body.note,
                    "savedAt": _now_iso(), "savedBy": body.countedBy}
    update["$set"]["entries"] = entries
    if body.countedBy:
        update["$set"]["countedBy"] = body.countedBy
    await db.prep_count_sessions.update_one({"_id": s["_id"]}, update)
    return {"ok": True, "entry": entries[idx], "revision": new_revision}

@api_router.post("/prepcount/{rid}/session/{sid}/submit")
async def submit_count(rid: str, sid: str, body: dict):
    check_rid(rid)
    s = await db.prep_count_sessions.find_one({"restaurantId": rid, "id": sid})
    if not s:
        raise HTTPException(404, "session not found")
    uncounted = sum(1 for e in s.get("entries", []) if e.get("onHand") is None)
    if uncounted and not body.get("acknowledgeUncounted"):
        raise HTTPException(409, f"{uncounted} item(s) have no saved count")
    await db.prep_count_sessions.update_one({"_id": s["_id"]},
        {"$set": {"status": "submitted", "submittedAt": _now_iso(),
                  "countedBy": body.get("countedBy", s.get("countedBy", ""))}})
    return {"ok": True, "uncounted": uncounted}

@api_router.get("/prepcount/{rid}/history")
async def count_history(rid: str):
    check_rid(rid)
    return await db.prep_count_sessions.find({"restaurantId": rid}, {"_id": 0, "entries": 0}).sort("date", -1).limit(60).to_list(60)

# ---------------- Prep lists ----------------
@api_router.get("/preplists/{rid}")
async def get_prep_list(rid: str, date: str = "", track: str = "daily"):
    check_rid(rid)
    plist = await db.prep_lists.find_one({"restaurantId": rid, "date": date or _today(), **_track_filter(track)}, {"_id": 0})
    return {"list": plist}

@api_router.post("/preplists/{rid}/generate")
async def generate_prep_list(rid: str, body: dict):
    check_rid(rid)
    date = body.get("date") or _today()
    track = body.get("track") or "daily"
    existing = await db.prep_lists.find_one({"restaurantId": rid, "date": date, **_track_filter(track)}, {"_id": 0})
    if existing:
        return {"list": existing, "regenerated": False}
    session = await db.prep_count_sessions.find_one(
        {"restaurantId": rid, "status": "submitted", "date": {"$lte": date}, **_track_filter(track)}, {"_id": 0}, sort=[("date", -1)])
    if not session:
        raise HTTPException(400, "No submitted evening count yet — submit a prep count first.")
    recipes, prep_items, by_id = await _prep_universe_for_track(rid, track)
    overrides = await db.prep_overrides.find({"restaurantId": rid, "date": date}, {"_id": 0}).to_list(500)
    removed_ids = {(o.get("recipeId") or o.get("prepItemId")) for o in overrides if o["type"] == "remove"}
    par_over, par_note = {}, {}
    for o in overrides:
        if o["type"] == "par":
            k = o.get("recipeId") or o.get("prepItemId")
            if k:
                par_over[k] = f(o.get("par"))
                par_note[k] = o.get("note", "")
    counted_map = {}
    for e in session.get("entries", []):
        k = e.get("recipeId") or e.get("prepItemId")
        if k:
            counted_map[k] = e
    governed = {p["recipeId"] for p in prep_items if p.get("sourceType") == "prep" and p.get("recipeId")}

    def note_for(key, counted):
        parts = []
        if counted is None:
            parts.append("Not counted — planned at full par")
        if key in par_over:
            parts.append(("Par override for this date: " + par_note[key]) if par_note[key] else "Par override for this date")
        return " ".join(parts)

    tasks = []
    for r in recipes:
        if r["id"] in removed_ids or r["id"] in governed:
            continue
        par = par_over.get(r["id"], f(r.get("prepPar")))
        entry = counted_map.get(r["id"])
        counted = entry.get("onHand") if entry else None
        yield_qty = f(r.get("yieldQty"), 1) or 1
        needed = max(0, par - counted) if counted is not None else par
        batches = int(math.ceil(needed / yield_qty)) if needed > 0 and yield_qty > 0 else 0
        tasks.append({"id": "task_" + uuid.uuid4().hex[:8], "recipeId": r["id"], "prepItemId": None, "taskType": "batch",
                      "name": r.get("name", ""), "yieldUOM": r.get("yieldUOM", "each"), "yieldQty": yield_qty, "par": par,
                      "counted": counted, "uncounted": counted is None, "neededUnits": round(needed, 2),
                      "batchesPlanned": batches, "batchesDone": 0, "doneBy": "", "doneAt": None,
                      "note": note_for(r["id"], counted), "vesselName": "", "removed": False})
    for p in prep_items:
        if p["id"] in removed_ids or p.get("schedule", "daily") != "daily":
            continue
        entry = counted_map.get(p["id"])
        counted = entry.get("onHand") if entry else None
        note = note_for(p["id"], counted)
        if p.get("sourceType") == "prep" and p.get("recipeId"):
            r = by_id.get(p["recipeId"])
            if not r:
                continue
            item_par = f(p.get("par"))
            default_par = item_par if item_par > 0 else f(r.get("prepPar"))
            par = par_over.get(p["id"], default_par)
            yield_qty = f(r.get("yieldQty"), 1) or 1
            needed = max(0, par - counted) if counted is not None else par
            batches = int(math.ceil(needed / yield_qty)) if needed > 0 and yield_qty > 0 else 0
            vn = p.get("vesselName", "")
            tasks.append({"id": "task_" + uuid.uuid4().hex[:8], "recipeId": r["id"], "prepItemId": p["id"], "taskType": "batch",
                          "name": p.get("name") or r.get("name", ""), "yieldUOM": r.get("yieldUOM", "each"), "yieldQty": yield_qty,
                          "par": par, "counted": counted, "uncounted": counted is None, "neededUnits": round(needed, 2),
                          "batchesPlanned": batches, "batchesDone": 0, "doneBy": "", "doneAt": None,
                          "note": ((f"Portion into {vn}. " if vn else "") + note).strip(), "vesselName": vn, "removed": False})
        else:
            par = par_over.get(p["id"], f(p.get("parVessels")))
            needed = max(0, par - counted) if counted is not None else par
            vessels = math.ceil(needed * 2) / 2 if needed > 0 else 0
            tasks.append({"id": "task_" + uuid.uuid4().hex[:8], "recipeId": None, "prepItemId": p["id"], "taskType": "vessel",
                          "name": p.get("name", ""), "yieldUOM": p.get("vesselName", "vessel"), "yieldQty": 1,
                          "par": par, "counted": counted, "uncounted": counted is None, "neededUnits": round(needed, 2),
                          "batchesPlanned": vessels, "batchesDone": 0, "doneBy": "", "doneAt": None,
                          "note": note, "vesselName": p.get("vesselName", ""), "vesselCapacity": f(p.get("vesselCapacity")),
                          "controlNumber": p.get("controlNumber", ""), "removed": False})
    for o in overrides:
        if o["type"] != "add":
            continue
        r = by_id.get(o.get("recipeId")) if o.get("recipeId") else None
        if o.get("recipeId") and not r:
            continue
        tasks.append({"id": "task_" + uuid.uuid4().hex[:8], "recipeId": r["id"] if r else None, "prepItemId": None,
                      "taskType": "batch",
                      "name": (r.get("name", "") + " (one-off)") if r else (o.get("customName") or "One-off item"),
                      "yieldUOM": (r or {}).get("yieldUOM", "batch"), "yieldQty": f((r or {}).get("yieldQty"), 1) or 1,
                      "par": 0, "counted": None, "uncounted": False, "neededUnits": 0,
                      "batchesPlanned": f(o.get("batches"), 1) or 1, "batchesDone": 0, "doneBy": "", "doneAt": None,
                      "note": ("One-off add: " + o.get("note", "")).strip(), "vesselName": "", "removed": False})
    doc = {"id": "pl_" + uuid.uuid4().hex[:10], "restaurantId": rid, "date": date, "track": track, "status": "draft",
           "tasks": tasks, "generatedFrom": session["id"], "generatedFromDate": session["date"],
           "generatedAt": _now_iso(), "releasedAt": None, "releasedBy": ""}
    await db.prep_lists.insert_one(dict(doc))
    return {"list": doc, "regenerated": True}

class PrepListUpdateIn(BaseModel):
    tasks: List[dict]

@api_router.put("/preplists/{rid}/{list_id}")
async def update_prep_list(rid: str, list_id: str, body: PrepListUpdateIn):
    check_rid(rid)
    plist = await db.prep_lists.find_one({"restaurantId": rid, "id": list_id})
    if not plist:
        raise HTTPException(404, "prep list not found")
    if plist.get("status") != "draft":
        raise HTTPException(400, "Only draft lists can be edited")
    await db.prep_lists.update_one({"_id": plist["_id"]}, {"$set": {"tasks": body.tasks}})
    return {"ok": True}

@api_router.post("/preplists/{rid}/{list_id}/release")
async def release_prep_list(rid: str, list_id: str, body: dict):
    check_rid(rid)
    res = await db.prep_lists.update_one({"restaurantId": rid, "id": list_id},
        {"$set": {"status": "released", "releasedAt": _now_iso(), "releasedBy": body.get("releasedBy", "")}})
    if res.matched_count == 0:
        raise HTTPException(404, "prep list not found")
    return {"ok": True}

async def _complete_task_core(rid, list_id, task_id, batches, done_by, containers):
    plist = await db.prep_lists.find_one({"restaurantId": rid, "id": list_id}, {"_id": 0})
    if not plist:
        raise HTTPException(404, "prep list not found")
    if plist.get("status") != "released":
        raise HTTPException(400, "The list must be released before tasks can be completed")
    task = next((t for t in plist.get("tasks", []) if t["id"] == task_id), None)
    if not task:
        raise HTTPException(404, "task not found")
    remaining = f(task.get("batchesPlanned")) - f(task.get("batchesDone"))
    if batches <= 0 or batches > remaining + 1e-9:
        raise HTTPException(400, f"batches must be between 0 and {remaining:g} remaining")
    result = {}
    if task.get("recipeId"):
        dishes = await db.dishes.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
        recipe = next((d for d in dishes if d.get("id") == task["recipeId"]), None)
        if recipe:
            result = await _deduct_and_stock(rid, recipe, batches, containers, "batch", f"{task.get('name', '')} — prep task")
    elif task.get("prepItemId"):
        pitem = await db.prep_items.find_one({"restaurantId": rid, "id": task["prepItemId"]}, {"_id": 0})
        if pitem:
            result = await _deduct_item_and_stock(rid, pitem, batches)
    for t in plist["tasks"]:
        if t["id"] == task_id:
            t["batchesDone"] = round(f(t.get("batchesDone")) + batches, 3)
            t["doneBy"] = done_by
            t["doneAt"] = _now_iso()
    await db.prep_lists.update_one({"restaurantId": rid, "id": list_id}, {"$set": {"tasks": plist["tasks"]}})
    return {"list": plist, **result}

class TaskCompleteIn(BaseModel):
    batches: float
    doneBy: str = ""
    containers: List[ContainerIn] = []

@api_router.post("/preplists/{rid}/{list_id}/task/{task_id}/complete")
async def complete_task(rid: str, list_id: str, task_id: str, body: TaskCompleteIn):
    check_rid(rid)
    return await _complete_task_core(rid, list_id, task_id, body.batches, body.doneBy, [c.model_dump() for c in body.containers])

# ---------------- Standing prep items (inventory item or prep recipe → standard vessel) ----------------
class PrepItemIn(BaseModel):
    name: str
    sourceType: str
    controlNumber: Optional[str] = None
    recipeId: Optional[str] = None
    vesselName: str = "1/6 Pan"
    vesselCapacity: float = 0
    parVessels: float = 0
    schedule: str = "daily"
    note: str = ""
    track: str = "daily"  # "daily" (on-site) or "bulk" (commissary kitchen)
    par: float = 0  # par for sourceType=="prep" items, independent of the recipe's own prepPar

def _track_filter(track):
    # Missing `track` on legacy documents means "daily" — no migration needed.
    return {"track": "bulk"} if track == "bulk" else {"track": {"$ne": "bulk"}}

@api_router.get("/prep-items/{rid}")
async def list_prep_items(rid: str, track: Optional[str] = None):
    check_rid(rid)
    q = {"restaurantId": rid}
    if track:
        q.update(_track_filter(track))
    return await db.prep_items.find(q, {"_id": 0}).to_list(1000)

@api_router.post("/prep-items/{rid}")
async def create_prep_item(rid: str, body: PrepItemIn):
    check_rid(rid)
    if body.sourceType not in ("item", "prep"):
        raise HTTPException(400, "sourceType must be item or prep")
    if body.schedule not in ("daily", "oneoff"):
        raise HTTPException(400, "schedule must be daily or oneoff")
    if body.track not in ("daily", "bulk"):
        raise HTTPException(400, "track must be daily or bulk")
    if body.sourceType == "item":
        if not await db.items.find_one({"restaurantId": rid, "controlNumber": body.controlNumber}):
            raise HTTPException(404, "inventory item not found")
    else:
        if not await db.dishes.find_one({"restaurantId": rid, "id": body.recipeId, "recipeType": "prep"}):
            raise HTTPException(404, "prep recipe not found")
    doc = body.model_dump()
    doc.update({"id": "pitem_" + uuid.uuid4().hex[:8], "restaurantId": rid, "createdAt": _now_iso()})
    await db.prep_items.insert_one(dict(doc))
    doc.pop("restaurantId", None)
    return doc

@api_router.put("/prep-items/{rid}/{pid}")
async def update_prep_item(rid: str, pid: str, body: PrepItemIn):
    check_rid(rid)
    res = await db.prep_items.update_one({"restaurantId": rid, "id": pid}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(404, "prep item not found")
    return {"ok": True}

@api_router.delete("/prep-items/{rid}/{pid}")
async def delete_prep_item(rid: str, pid: str):
    check_rid(rid)
    await db.prep_items.delete_one({"restaurantId": rid, "id": pid})
    return {"ok": True}

@api_router.post("/preplists/{rid}/{list_id}/add-item")
async def add_item_to_list(rid: str, list_id: str, body: dict):
    check_rid(rid)
    plist = await db.prep_lists.find_one({"restaurantId": rid, "id": list_id}, {"_id": 0})
    if not plist:
        raise HTTPException(404, "prep list not found")
    pitem = await db.prep_items.find_one({"restaurantId": rid, "id": body.get("prepItemId")}, {"_id": 0})
    if not pitem:
        raise HTTPException(404, "prep item not found")
    if any(t.get("prepItemId") == pitem["id"] for t in plist.get("tasks", [])):
        raise HTTPException(400, "That item is already on this day's list")
    qty = f(body.get("qty"), 0)
    note = ("One-off add: " + body.get("note", "")).strip()
    if pitem.get("sourceType") == "prep" and pitem.get("recipeId"):
        r = await db.dishes.find_one({"restaurantId": rid, "id": pitem["recipeId"]}, {"_id": 0})
        if not r:
            raise HTTPException(404, "linked prep recipe not found")
        task = {"id": "task_" + uuid.uuid4().hex[:8], "recipeId": r["id"], "prepItemId": pitem["id"], "taskType": "batch",
                "name": pitem.get("name") or r.get("name", ""), "yieldUOM": r.get("yieldUOM", "each"),
                "yieldQty": f(r.get("yieldQty"), 1) or 1, "par": 0, "counted": None, "uncounted": False, "neededUnits": 0,
                "batchesPlanned": qty or 1, "batchesDone": 0, "doneBy": "", "doneAt": None,
                "note": note, "vesselName": pitem.get("vesselName", ""), "removed": False}
    else:
        task = {"id": "task_" + uuid.uuid4().hex[:8], "recipeId": None, "prepItemId": pitem["id"], "taskType": "vessel",
                "name": pitem.get("name", ""), "yieldUOM": pitem.get("vesselName", "vessel"), "yieldQty": 1,
                "par": 0, "counted": None, "uncounted": False, "neededUnits": 0,
                "batchesPlanned": qty or f(pitem.get("parVessels"), 1) or 1, "batchesDone": 0, "doneBy": "", "doneAt": None,
                "note": note, "vesselName": pitem.get("vesselName", ""), "vesselCapacity": f(pitem.get("vesselCapacity")),
                "controlNumber": pitem.get("controlNumber", ""), "removed": False}
    await db.prep_lists.update_one({"restaurantId": rid, "id": list_id}, {"$push": {"tasks": task}})
    plist["tasks"].append(task)
    return {"list": plist}

# ---------------- Day overrides ----------------
class OverrideIn(BaseModel):
    date: str
    type: str
    recipeId: Optional[str] = None
    prepItemId: Optional[str] = None
    customName: str = ""
    par: Optional[float] = None
    batches: Optional[float] = None
    note: str = ""
    createdBy: str = ""

@api_router.get("/prep-overrides/{rid}")
async def list_overrides(rid: str, date: str = ""):
    check_rid(rid)
    q = {"restaurantId": rid}
    if date:
        q["date"] = date
    return await db.prep_overrides.find(q, {"_id": 0}).sort("date", -1).to_list(500)

@api_router.post("/prep-overrides/{rid}")
async def add_override(rid: str, body: OverrideIn):
    check_rid(rid)
    if body.type not in ("add", "par", "remove"):
        raise HTTPException(400, "type must be add, par, or remove")
    doc = body.model_dump()
    doc["id"] = "ovr_" + uuid.uuid4().hex[:8]
    doc["restaurantId"] = rid
    doc["createdAt"] = _now_iso()
    await db.prep_overrides.insert_one(dict(doc))
    doc.pop("restaurantId", None)
    return doc

@api_router.delete("/prep-overrides/{rid}/{oid}")
async def delete_override(rid: str, oid: str):
    check_rid(rid)
    await db.prep_overrides.delete_one({"restaurantId": rid, "id": oid})
    return {"ok": True}

# ---------------- Projected sales ----------------
class ProjectionIn(BaseModel):
    date: str
    amount: float = 0
    note: str = ""
    enteredBy: str = ""

@api_router.get("/projections/{rid}")
async def get_projections(rid: str):
    check_rid(rid)
    return await db.projected_sales.find({"restaurantId": rid}, {"_id": 0}).sort("date", -1).limit(60).to_list(60)

@api_router.put("/projections/{rid}")
async def put_projection(rid: str, body: ProjectionIn):
    check_rid(rid)
    await db.projected_sales.update_one({"restaurantId": rid, "date": body.date},
        {"$set": {**body.model_dump(), "restaurantId": rid, "updatedAt": _now_iso()}}, upsert=True)
    return {"ok": True}

# ---------------- Staff PIN & prep sheet ----------------
DEFAULT_STAFF_PIN = "1234"

async def _get_pin(rid):
    cfg = await db.settings.find_one({"restaurantId": rid, "key": "staff"}, {"_id": 0})
    return (cfg or {}).get("staffPin") or DEFAULT_STAFF_PIN

@api_router.get("/staff/{rid}/pin")
async def get_pin(rid: str):
    check_rid(rid)
    cfg = await db.settings.find_one({"restaurantId": rid, "key": "staff"}, {"_id": 0})
    return {"staffPin": (cfg or {}).get("staffPin") or DEFAULT_STAFF_PIN, "custom": bool((cfg or {}).get("staffPin"))}

@api_router.post("/staff/{rid}/pin")
async def set_pin(rid: str, body: dict):
    check_rid(rid)
    pin = str(body.get("staffPin", "")).strip()
    if not (pin.isdigit() and 4 <= len(pin) <= 8):
        raise HTTPException(400, "PIN must be 4-8 digits")
    await db.settings.update_one({"restaurantId": rid, "key": "staff"},
        {"$set": {"restaurantId": rid, "key": "staff", "staffPin": pin}}, upsert=True)
    return {"ok": True}

@api_router.post("/staff/verify")
async def verify_pin(body: dict):
    rid = body.get("restaurantId", "")
    check_rid(rid)
    return {"ok": str(body.get("pin", "")) == await _get_pin(rid)}

@api_router.post("/staff/{rid}/prepsheet")
async def staff_prepsheet(rid: str, body: dict):
    check_rid(rid)
    # PIN travels in the POST body, not a GET query string — query strings land in
    # server/proxy access logs and browser history.
    if str((body or {}).get("pin", "")) != await _get_pin(rid):
        raise HTTPException(403, "Invalid PIN")
    track = body.get("track") or "daily"
    plist = await db.prep_lists.find_one({"restaurantId": rid, "date": _today(), "status": "released", **_track_filter(track)}, {"_id": 0})
    if not plist:
        plist = await db.prep_lists.find_one({"restaurantId": rid, "status": "released", **_track_filter(track)}, {"_id": 0}, sort=[("date", -1)])
    if not plist:
        return {"listId": None, "date": _today(), "tasks": []}
    dishes = await db.dishes.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    by_id = {d["id"]: d for d in dishes}
    tasks = []
    for t in plist.get("tasks", []):
        if t.get("removed"):
            continue
        r = by_id.get(t.get("recipeId") or "")
        tasks.append({"id": t["id"], "name": t.get("name", ""), "yieldUOM": t.get("yieldUOM", ""),
                      "batchesPlanned": t.get("batchesPlanned", 0), "batchesDone": t.get("batchesDone", 0),
                      "remaining": max(0, f(t.get("batchesPlanned")) - f(t.get("batchesDone"))),
                      "note": t.get("note", ""), "doneBy": t.get("doneBy", ""),
                      "card": {"procedure": (r or {}).get("procedure", ""), "equipment": (r or {}).get("equipment", ""),
                               "shelfLife": (r or {}).get("shelfLife", ""), "yieldQty": f((r or {}).get("yieldQty"), 1),
                               "yieldUOM": (r or {}).get("yieldUOM", t.get("yieldUOM", ""))}})
    return {"listId": plist["id"], "date": plist["date"], "tasks": tasks}

class StaffCompleteIn(BaseModel):
    pin: str
    listId: str
    taskId: str
    batches: float
    doneBy: str = ""

@api_router.post("/staff/{rid}/prepsheet/complete")
async def staff_complete(rid: str, body: StaffCompleteIn):
    check_rid(rid)
    if body.pin != await _get_pin(rid):
        raise HTTPException(403, "Invalid PIN")
    if not body.doneBy.strip():
        raise HTTPException(400, "Enter your name so the task is attributed")
    res = await _complete_task_core(rid, body.listId, body.taskId, body.batches, body.doneBy.strip(), [])
    return {"ok": True, "log": res.get("log")}

# ---------------- Prep reporting ----------------
@api_router.get("/reports/{rid}/prep")
async def prep_report(rid: str, frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = Query(None)):
    check_rid(rid)
    frm = frm or (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    to = to or _today()
    sessions = await db.prep_count_sessions.find({"restaurantId": rid, "date": {"$gte": frm, "$lte": to}}, {"_id": 0}).sort("date", 1).to_list(500)
    logs = await db.prep_logs.find({"restaurantId": rid, "date": {"$gte": frm, "$lte": to}}, {"_id": 0}).sort("date", 1).to_list(1000)
    recipes = await _prep_recipes(rid)
    out = []
    for r in recipes:
        counts = [{"date": s["date"], "onHand": e["onHand"], "by": e.get("savedBy") or s.get("countedBy", "")}
                  for s in sessions for e in s.get("entries", []) if e["recipeId"] == r["id"] and e.get("onHand") is not None]
        produced = sum(f(l.get("produced")) for l in logs if l.get("kind") == "batch" and l.get("recipeId") == r["id"])
        produced_cost = sum(f(l.get("totalCost")) for l in logs if l.get("kind") == "batch" and l.get("recipeId") == r["id"])
        used = sum(f(u.get("used")) for l in logs if l.get("kind") == "sales_usage" for u in l.get("usage", []) if u.get("recipeId") == r["id"])
        to_service = sum(abs(f(l.get("produced"))) for l in logs if l.get("kind") == "container_use" and l.get("recipeId") == r["id"])
        out.append({"recipeId": r["id"], "name": r.get("name", ""), "yieldUOM": r.get("yieldUOM", ""),
                    "counts": counts, "produced": round(produced, 2), "producedCost": round(produced_cost, 2),
                    "usedBySales": round(used, 2), "sentToService": round(to_service, 2)})
    pitems = await db.prep_items.find({"restaurantId": rid}, {"_id": 0}).to_list(1000)
    pout = []
    for p in pitems:
        counts = [{"date": s["date"], "onHand": e["onHand"], "by": e.get("savedBy") or s.get("countedBy", "")}
                  for s in sessions for e in s.get("entries", []) if e.get("prepItemId") == p["id"] and e.get("onHand") is not None]
        produced = sum(f(l.get("produced")) for l in logs if l.get("kind") == "batch" and l.get("prepItemId") == p["id"])
        produced_cost = sum(f(l.get("totalCost")) for l in logs if l.get("kind") == "batch" and l.get("prepItemId") == p["id"])
        pout.append({"prepItemId": p["id"], "name": p.get("name", ""), "yieldUOM": p.get("vesselName", "vessel"),
                     "counts": counts, "produced": round(produced, 2), "producedCost": round(produced_cost, 2)})
    return {"from": frm, "to": to, "recipes": out, "prepItems": pout,
            "sessions": [{"id": s["id"], "date": s["date"], "status": s["status"], "countedBy": s.get("countedBy", ""),
                          "revision": s.get("revision", 1)} for s in sessions],
            "totals": {"producedCost": round(sum(x["producedCost"] for x in out) + sum(x["producedCost"] for x in pout), 2)}}

@api_router.get("/owner/prep-summary")
async def owner_prep_summary():
    today = _today()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    stores = []
    for r in RESTAURANTS:
        rid = r["id"]
        session = await db.prep_count_sessions.find_one({"restaurantId": rid, "date": today}, {"_id": 0})
        plist = await db.prep_lists.find_one({"restaurantId": rid, "date": today}, {"_id": 0})
        logs = await db.prep_logs.find({"restaurantId": rid, "kind": "batch", "date": {"$gte": week_ago}}, {"_id": 0}).to_list(500)
        tasks = [t for t in (plist or {}).get("tasks", []) if not t.get("removed")]
        stores.append({"id": rid, "short": r["short"], "accent": r["accent"],
                       "countStatus": (session or {}).get("status", "none"),
                       "tasksTotal": len(tasks),
                       "tasksDone": len([t for t in tasks if f(t.get("batchesPlanned")) > 0 and f(t.get("batchesDone")) >= f(t.get("batchesPlanned"))]),
                       "prepCost7d": round(sum(f(l.get("totalCost")) for l in logs), 2)})
    return {"stores": stores}

# ---------------- AI par advisor (advisory only — never writes without manager apply) ----------------
@api_router.post("/ai/par-advisor/{rid}")
async def run_par_advisor(rid: str):
    check_rid(rid)
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(500, "AI key not configured")
    from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
    recipes = await _prep_recipes(rid)
    if not recipes:
        raise HTTPException(400, "No prep recipes yet")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=45)).date().isoformat()
    sessions = await db.prep_count_sessions.find({"restaurantId": rid, "date": {"$gte": cutoff}}, {"_id": 0}).to_list(200)
    logs = await db.prep_logs.find({"restaurantId": rid, "date": {"$gte": cutoff}}, {"_id": 0}).to_list(500)
    projections = await db.projected_sales.find({"restaurantId": rid}, {"_id": 0}).to_list(200)
    stats_lines = []
    total_counts = 0
    for r in recipes:
        counts = [[s["date"], e["onHand"]] for s in sessions for e in s.get("entries", [])
                  if e["recipeId"] == r["id"] and e.get("onHand") is not None]
        total_counts += len(counts)
        produced = sum(f(l.get("produced")) for l in logs if l.get("kind") == "batch" and l.get("recipeId") == r["id"])
        used = sum(f(u.get("used")) for l in logs if l.get("kind") == "sales_usage" for u in l.get("usage", []) if u.get("recipeId") == r["id"])
        stats_lines.append(json.dumps({"recipeId": r["id"], "name": r.get("name", ""), "unit": r.get("yieldUOM", ""),
                                       "currentPar": f(r.get("prepPar")), "batchYield": f(r.get("yieldQty"), 1),
                                       "eveningCounts": counts, "produced45d": round(produced, 1), "usedBySales45d": round(used, 1)}))
    proj_lines = [f"{p['date']}: ${f(p.get('amount')):,.0f}" for p in sorted(projections, key=lambda x: x.get("date", ""))]
    sparse = total_counts < 5 and not logs
    prompt = ("You are an F&B prep-planning analyst for a restaurant. Analyze this prep data and respond with STRICT JSON only, no markdown: "
              '{"recommendations": [{"recipeId": "...", "recipeName": "...", "currentPar": 0, "recommendedPar": 0, "reasoning": "..."}], "trends": "short paragraph"}. '
              "Rules: recommend new pars only where data supports it (repeated zero/low counts = stockouts, or large leftover counts = over-prepping). Round pars to whole units. "
              + ("History is very sparse, so return an EMPTY recommendations array and describe only early trends. " if sparse else "")
              + "PREP STATS:\n" + "\n".join(stats_lines)
              + (("\nPROJECTED SALES (upcoming): " + "; ".join(proj_lines)) if proj_lines else ""))
    chat = (LlmChat(api_key=api_key, session_id=f"par-{rid}", system_message="You output strict JSON only.")
            .with_model("openai", "gpt-5.4"))
    full = ""
    try:
        async for ev in chat.stream_message(UserMessage(text=prompt)):
            if isinstance(ev, TextDelta):
                full += ev.content
            elif isinstance(ev, StreamDone):
                break
    except Exception as e:
        logger.error(f"par advisor LLM error for {rid}: {e}")
        full = ""
    recs, trends = [], ""
    try:
        m = re.search(r"\{.*\}", full, re.S)
        parsed = json.loads(m.group(0)) if m else {}
        trends = parsed.get("trends", "")
        valid_ids = {r["id"] for r in recipes}
        for rec in (parsed.get("recommendations") or [])[:10]:
            if rec.get("recipeId") not in valid_ids or rec.get("recommendedPar") is None:
                continue
            recs.append({"id": "rec_" + uuid.uuid4().hex[:8], "restaurantId": rid, "recipeId": rec["recipeId"],
                         "recipeName": rec.get("recipeName", ""), "currentPar": f(rec.get("currentPar")),
                         "recommendedPar": f(rec.get("recommendedPar")), "reasoning": str(rec.get("reasoning", "")),
                         "status": "pending", "createdAt": _now_iso()})
    except Exception:
        trends = full[:800]
    if recs:
        await db.par_recommendations.insert_many([dict(r) for r in recs])
    return {"recommendations": recs, "trends": trends, "sparse": sparse}

@api_router.get("/ai/par-advisor/{rid}")
async def get_par_recs(rid: str):
    check_rid(rid)
    return await db.par_recommendations.find({"restaurantId": rid, "status": "pending"}, {"_id": 0}).sort("createdAt", -1).to_list(50)

@api_router.post("/ai/par-advisor/{rid}/{rec_id}/apply")
async def apply_par_rec(rid: str, rec_id: str):
    check_rid(rid)
    rec = await db.par_recommendations.find_one({"restaurantId": rid, "id": rec_id})
    if not rec:
        raise HTTPException(404, "recommendation not found")
    await db.dishes.update_one({"restaurantId": rid, "id": rec["recipeId"]}, {"$set": {"prepPar": rec["recommendedPar"]}})
    await db.par_recommendations.update_one({"_id": rec["_id"]}, {"$set": {"status": "applied", "appliedAt": _now_iso()}})
    return {"ok": True}

@api_router.post("/ai/par-advisor/{rid}/{rec_id}/dismiss")
async def dismiss_par_rec(rid: str, rec_id: str):
    check_rid(rid)
    await db.par_recommendations.update_one({"restaurantId": rid, "id": rec_id}, {"$set": {"status": "dismissed"}})
    return {"ok": True}

# ---------------- Ownership rollup ----------------
async def store_summary(r):
    rid = r["id"]
    await ensure_seed(rid)
    items = await db.items.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    purchases = await db.purchases.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    dishes = await db.dishes.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    adjustments = await db.adjustments.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    prep_stock = await _prep_stock_list(rid)
    items_by_cn = {i["controlNumber"]: i for i in items}
    by_id = {d["id"]: d for d in dishes}
    inv_value = sum(f(i.get("currentStock")) * item_derived(i)["price"] for i in items)
    alerts = sum(1 for i in items if i.get("orderEnabled", True) and f(i.get("currentStock")) < f(i.get("par")))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    spend30 = sum(f(p.get("extendedCost")) for p in purchases if (p.get("invoiceDate") or "") >= cutoff)
    waste30 = sum(adj_value(a, items_by_cn[a["controlNumber"]]) for a in adjustments
                  if (a.get("date") or "") >= cutoff and a.get("controlNumber") in items_by_cn
                  and ADJ_DIRECTIONS.get(a.get("reason"), "remove") == "remove")
    dish_rows = []
    for d in dishes:
        if d.get("recipeType", "menu") == "prep":
            continue
        cost = recipe_cost(d, items_by_cn, by_id)
        price = f(d.get("price"))
        pct = (cost / price * 100) if price > 0 else None
        dish_rows.append({"name": d.get("name", ""), "code": d.get("menuCode", ""), "cost": round(cost, 2),
                          "price": price, "pct": round(pct, 1) if pct is not None else None,
                          "target": f(d.get("targetPct"), 30)})
    pcts = [x["pct"] for x in dish_rows if x["pct"] is not None]
    stock_by_recipe = {s["recipeId"]: s for s in prep_stock}
    prep_low = sum(1 for d in dishes if d.get("recipeType") == "prep" and f(d.get("prepPar")) > 0
                   and f((stock_by_recipe.get(d["id"]) or {}).get("onHand")) < f(d.get("prepPar")))
    return {**r, "inventoryValue": round(inv_value, 2), "orderAlerts": alerts, "spend30": round(spend30, 2),
            "waste30": round(waste30, 2), "avgFoodCost": round(sum(pcts) / len(pcts), 1) if pcts else None,
            "dishCount": len(dish_rows), "itemCount": len(items), "prepLow": prep_low,
            "topCostDishes": sorted(dish_rows, key=lambda x: -(x["pct"] or 0))[:3]}

@api_router.get("/owner/summary")
async def owner_summary():
    stores = [await store_summary(r) for r in RESTAURANTS]
    totals = {"inventoryValue": round(sum(s["inventoryValue"] for s in stores), 2),
              "orderAlerts": sum(s["orderAlerts"] for s in stores),
              "spend30": round(sum(s["spend30"] for s in stores), 2),
              "waste30": round(sum(s["waste30"] for s in stores), 2)}
    return {"stores": stores, "totals": totals}

# ---------------- AI assistant (OpenAI via Emergent universal key) ----------------
def build_ai_context(rid, items, purchases, dishes, adjustments, prep_stock):
    rname = next((r["name"] for r in RESTAURANTS if r["id"] == rid), rid)
    items_by_cn = {i["controlNumber"]: i for i in items}
    by_id = {d["id"]: d for d in dishes}
    lines = [f"RESTAURANT: {rname}"]
    inv_value = sum(f(i.get("currentStock")) * item_derived(i)["price"] for i in items)
    lines.append(f"Live inventory value: ${inv_value:,.2f} across {len(items)} items")
    low = [i for i in items if i.get("orderEnabled", True) and f(i.get("currentStock")) < f(i.get("par"))]
    if low:
        lines.append("BELOW PAR: " + "; ".join(f"{i['controlNumber']} {i.get('name','')} stock {f(i.get('currentStock')):g}/{f(i.get('par')):g} {i.get('purchaseUnit','')}" for i in low[:25]))
    lines.append("ITEMS (cost per portion): " + "; ".join(
        f"{i['controlNumber']} {i.get('name','')} ${item_derived(i)['costPerPortion']:.3f}/portion" for i in items[:60]))
    menu_lines = []
    for d in dishes:
        if d.get("recipeType", "menu") == "prep":
            continue
        cost = recipe_cost(d, items_by_cn, by_id)
        price = f(d.get("price"))
        pct = f"{cost / price * 100:.1f}%" if price > 0 else "n/a"
        menu_lines.append(f"{d.get('menuCode','')} {d.get('name','')}: price ${price:.2f}, plate cost ${cost:.2f}, FC {pct} (target {f(d.get('targetPct'), 30):g}%)")
    if menu_lines:
        lines.append("MENU COSTING: " + " | ".join(menu_lines[:40]))
    preps = [d for d in dishes if d.get("recipeType") == "prep"]
    if preps:
        stock_map = {s["recipeId"]: s for s in prep_stock}
        lines.append("PREP INVENTORY: " + "; ".join(
            f"{p.get('name','')} on-hand {f((stock_map.get(p['id']) or {}).get('onHand')):g} {p.get('yieldUOM','')} (par {f(p.get('prepPar')):g}, {p.get('frequency','daily')}, yield {f(p.get('yieldQty')):g} {p.get('yieldUOM','')}/batch, shelf life {p.get('shelfLife','n/a')})"
            for p in preps))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    spend30 = sum(f(p.get("extendedCost")) for p in purchases if (p.get("invoiceDate") or "") >= cutoff)
    lines.append(f"Purchases last 30 days: ${spend30:,.2f} ({len(purchases)} invoice lines total on file)")
    waste30 = sum(adj_value(a, items_by_cn[a["controlNumber"]]) for a in adjustments
                  if (a.get("date") or "") >= cutoff and a.get("controlNumber") in items_by_cn
                  and ADJ_DIRECTIONS.get(a.get("reason"), "remove") == "remove")
    lines.append(f"Waste/removals last 30 days: ${waste30:,.2f}")
    return "\n".join(lines)

class ChatIn(BaseModel):
    restaurantId: str
    message: str

@api_router.post("/ai/chat")
async def ai_chat(body: ChatIn):
    check_rid(body.restaurantId)
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(500, "AI key not configured")
    from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
    rid = body.restaurantId
    await ensure_seed(rid)
    items = await db.items.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    purchases = await db.purchases.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    dishes = await db.dishes.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    adjustments = await db.adjustments.find({"restaurantId": rid}, {"_id": 0}).to_list(20000)
    prep_stock = await _prep_stock_list(rid)
    context = build_ai_context(rid, items, purchases, dishes, adjustments, prep_stock)
    history = await db.chat_messages.find({"restaurantId": rid}, {"_id": 0}).sort("ts", -1).limit(10).to_list(10)
    history.reverse()
    system = ("You are Sous, an expert restaurant operations copilot for a multi-unit restaurant group. "
              "You answer questions about inventory, food costing, recipes, prep planning, waste, and margins. "
              "Be concise, practical, and specific — cite actual numbers from the live data when relevant. "
              "You are READ-ONLY: you cannot add, change, or delete inventory, orders, counts, prep, or settings, "
              "and you must never claim or imply that a change was saved. If asked to change something, explain "
              "that you can't make changes yourself and point the person to the right screen "
              "(Item Setup, Enter Counts, Prep, Invoice Master, or Order Generator). "
              "All figures come from the restaurant's live database snapshot below.\n\n" + context)
    if history:
        system += "\n\nRecent conversation:\n" + "\n".join(f"{h['role'].upper()}: {h['content'][:600]}" for h in history)
    chat = (LlmChat(api_key=api_key, session_id=f"sous-{rid}", system_message=system)
            .with_model("openai", "gpt-5.4"))
    now = datetime.now(timezone.utc).isoformat()
    await db.chat_messages.insert_one(ChatMessage(restaurantId=rid, role="user", content=body.message, ts=now).to_mongo())

    async def gen():
        full = ""
        try:
            async for ev in chat.stream_message(UserMessage(text=body.message)):
                if isinstance(ev, TextDelta):
                    full += ev.content
                    yield f"data: {json.dumps({'t': ev.content})}\n\n"
                elif isinstance(ev, StreamDone):
                    break
        except Exception as e:
            logger.error(f"AI stream error: {e}")
            yield f"data: {json.dumps({'error': 'The assistant hit an error. Please try again.'})}\n\n"
        if full:
            await db.chat_messages.insert_one(ChatMessage(restaurantId=rid, role="assistant", content=full,
                                                          ts=datetime.now(timezone.utc).isoformat()).to_mongo())
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@api_router.get("/ai/history/{rid}")
async def ai_history(rid: str):
    check_rid(rid)
    msgs = await db.chat_messages.find({"restaurantId": rid}, {"_id": 0}).sort("ts", 1).limit(100).to_list(100)
    return msgs

@api_router.delete("/ai/history/{rid}")
async def ai_clear(rid: str):
    check_rid(rid)
    await db.chat_messages.delete_many({"restaurantId": rid})
    return {"ok": True}

# ---------------- Purchase Orders / Approval chain ----------------
PO_FLOW = {
    "draft": {"submit": "pending", "delete": True},
    "pending": {"approve": "approved", "reject": "rejected"},
    "approved": {"send": "sent"},
    "rejected": {"reopen": "draft", "delete": True},
    "sent": {"receive": "received"},
    "received": {},
}

class POLineIn(BaseModel):
    controlNumber: str
    name: str = ""
    vendorSku: str = ""
    qty: float = 0
    purchaseUnit: str = "case"
    unitCost: float = 0

class POCreateIn(BaseModel):
    vendor: str = "Unassigned"
    createdBy: str = ""
    note: str = ""
    lines: List[POLineIn] = []

def _po_public(po):
    po = dict(po)
    po.pop("_id", None)
    po.pop("restaurantId", None)
    return po

def _po_total(lines):
    return round(sum(f(l.get("qty")) * f(l.get("unitCost")) for l in lines), 2)

def _po_event(status, by, note=""):
    return {"status": status, "at": datetime.now(timezone.utc).isoformat(), "by": by or "", "note": note or ""}

async def _get_po(rid, oid):
    po = await db.purchase_orders.find_one({"restaurantId": rid, "id": oid})
    if not po:
        raise HTTPException(404, "purchase order not found")
    return po

@api_router.get("/orders/{rid}")
async def list_orders(rid: str, status: Optional[str] = None):
    check_rid(rid)
    q = {"restaurantId": rid}
    if status:
        q["status"] = status
    pos = await db.purchase_orders.find(q).sort("createdAt", -1).to_list(2000)
    return [_po_public(p) for p in pos]

@api_router.post("/orders/{rid}")
async def create_order(rid: str, body: POCreateIn):
    check_rid(rid)
    lines = [l.model_dump() for l in body.lines]
    for l in lines:
        l["receivedQty"] = 0
        l["lineTotal"] = round(f(l.get("qty")) * f(l.get("unitCost")), 2)
    now = datetime.now(timezone.utc)
    po = {
        "id": "po_" + uuid.uuid4().hex[:10], "restaurantId": rid, "vendor": body.vendor or "Unassigned",
        "status": "draft", "createdBy": body.createdBy or "", "note": body.note or "",
        "lines": lines, "total": _po_total(lines), "createdAt": now.isoformat(),
        "submittedAt": None, "approvedBy": None, "approvedAt": None, "rejectedReason": None,
        "sentAt": None, "receivedAt": None,
        "history": [_po_event("draft", body.createdBy)],
    }
    await db.purchase_orders.insert_one(dict(po))
    return _po_public(po)

@api_router.put("/orders/{rid}/{oid}")
async def update_order(rid: str, oid: str, body: POCreateIn):
    check_rid(rid)
    po = await _get_po(rid, oid)
    if po["status"] != "draft":
        raise HTTPException(400, "only draft orders can be edited")
    lines = [l.model_dump() for l in body.lines]
    for l in lines:
        l["receivedQty"] = 0
        l["lineTotal"] = round(f(l.get("qty")) * f(l.get("unitCost")), 2)
    await db.purchase_orders.update_one({"restaurantId": rid, "id": oid},
        {"$set": {"vendor": body.vendor or po.get("vendor"), "note": body.note, "lines": lines, "total": _po_total(lines)}})
    return _po_public(await _get_po(rid, oid))

@api_router.post("/orders/{rid}/{oid}/submit")
async def submit_order(rid: str, oid: str, payload: dict = None):
    check_rid(rid)
    po = await _get_po(rid, oid)
    if po["status"] != "draft":
        raise HTTPException(400, "only draft orders can be submitted")
    if not po.get("lines"):
        raise HTTPException(400, "cannot submit an empty order")
    by = (payload or {}).get("by", "")
    now = datetime.now(timezone.utc).isoformat()
    await db.purchase_orders.update_one({"restaurantId": rid, "id": oid},
        {"$set": {"status": "pending", "submittedAt": now}, "$push": {"history": _po_event("pending", by)}})
    return _po_public(await _get_po(rid, oid))

@api_router.post("/orders/{rid}/{oid}/approve")
async def approve_order(rid: str, oid: str, payload: dict = None):
    check_rid(rid)
    po = await _get_po(rid, oid)
    if po["status"] != "pending":
        raise HTTPException(400, "only pending orders can be approved")
    by = (payload or {}).get("by", "").strip()
    if not by:
        raise HTTPException(400, "Enter your name so the approval is attributed")
    creator = (po.get("createdBy") or "").strip()
    if creator and by.lower() == creator.lower():
        raise HTTPException(403, "This order's creator cannot approve their own order — a different person must approve it")
    now = datetime.now(timezone.utc).isoformat()
    await db.purchase_orders.update_one({"restaurantId": rid, "id": oid},
        {"$set": {"status": "approved", "approvedBy": by, "approvedAt": now}, "$push": {"history": _po_event("approved", by)}})
    return _po_public(await _get_po(rid, oid))

@api_router.post("/orders/{rid}/{oid}/reject")
async def reject_order(rid: str, oid: str, payload: dict = None):
    check_rid(rid)
    po = await _get_po(rid, oid)
    if po["status"] != "pending":
        raise HTTPException(400, "only pending orders can be rejected")
    by = (payload or {}).get("by", "")
    reason = (payload or {}).get("reason", "")
    await db.purchase_orders.update_one({"restaurantId": rid, "id": oid},
        {"$set": {"status": "rejected", "rejectedReason": reason}, "$push": {"history": _po_event("rejected", by, reason)}})
    return _po_public(await _get_po(rid, oid))

@api_router.post("/orders/{rid}/{oid}/reopen")
async def reopen_order(rid: str, oid: str, payload: dict = None):
    check_rid(rid)
    po = await _get_po(rid, oid)
    if po["status"] != "rejected":
        raise HTTPException(400, "only rejected orders can be reopened")
    by = (payload or {}).get("by", "")
    await db.purchase_orders.update_one({"restaurantId": rid, "id": oid},
        {"$set": {"status": "draft", "rejectedReason": None}, "$push": {"history": _po_event("draft", by, "reopened")}})
    return _po_public(await _get_po(rid, oid))

@api_router.post("/orders/{rid}/{oid}/send")
async def send_order(rid: str, oid: str, payload: dict = None):
    check_rid(rid)
    po = await _get_po(rid, oid)
    if po["status"] != "approved":
        raise HTTPException(400, "only approved orders can be sent to the supplier")
    by = (payload or {}).get("by", "")
    now = datetime.now(timezone.utc).isoformat()
    await db.purchase_orders.update_one({"restaurantId": rid, "id": oid},
        {"$set": {"status": "sent", "sentAt": now}, "$push": {"history": _po_event("sent", by)}})
    return _po_public(await _get_po(rid, oid))

@api_router.post("/orders/{rid}/{oid}/receive")
async def receive_order(rid: str, oid: str, payload: dict = None):
    check_rid(rid)
    po = await _get_po(rid, oid)
    if po["status"] != "sent":
        raise HTTPException(400, "only orders sent to the supplier can be received")
    by = (payload or {}).get("by", "")
    invoice_number = str((payload or {}).get("invoiceNumber", "")).strip()
    received = {r.get("controlNumber"): f(r.get("receivedQty")) for r in (payload or {}).get("lines", [])}
    lines = po.get("lines", [])
    updates = []
    for l in lines:
        cn = l.get("controlNumber")
        rq = received.get(cn, 0.0)  # a line the caller didn't mention was NOT received — never assume full receipt
        l["receivedQty"] = rq
        if rq > 0:
            updates.append((cn, rq))
    # add received quantities to inventory on-hand (single bulk write)
    if updates:
        items = await db.items.find({"restaurantId": rid, "controlNumber": {"$in": [cn for cn, _ in updates]}}, {"_id": 0}).to_list(20000)
        stock = {it["controlNumber"]: f(it.get("currentStock")) for it in items}
        ops = [UpdateOne({"restaurantId": rid, "controlNumber": cn},
                         {"$set": {"currentStock": round(stock.get(cn, 0) + rq, 3)}}) for cn, rq in updates if cn in stock]
        if ops:
            await db.items.bulk_write(ops)
    receipt_match = await _match_invoice(rid, invoice_number, lines) if invoice_number else None
    now = datetime.now(timezone.utc).isoformat()
    set_fields = {"status": "received", "receivedAt": now, "lines": lines, "invoiceNumber": invoice_number or None, "receiptMatch": receipt_match}
    note = ""
    if receipt_match:
        note = f"invoice {invoice_number}: {receipt_match['flaggedCount']} discrepanc{'y' if receipt_match['flaggedCount'] == 1 else 'ies'}" if receipt_match["invoiceFound"] else f"invoice {invoice_number} not found in Invoice Master"
    await db.purchase_orders.update_one({"restaurantId": rid, "id": oid},
        {"$set": set_fields, "$push": {"history": _po_event("received", by, note)}})
    return _po_public(await _get_po(rid, oid))

@api_router.delete("/orders/{rid}/{oid}")
async def delete_order(rid: str, oid: str):
    check_rid(rid)
    po = await _get_po(rid, oid)
    if po["status"] not in ("draft", "rejected"):
        raise HTTPException(400, "only draft or rejected orders can be deleted")
    await db.purchase_orders.delete_one({"restaurantId": rid, "id": oid})
    return {"ok": True}

@api_router.get("/owner/orders")
async def owner_orders():
    pos = await db.purchase_orders.find({"status": "pending"}).sort("submittedAt", 1).to_list(2000)
    name_by_rid = {r["id"]: r["short"] for r in RESTAURANTS}
    out = []
    for p in pos:
        d = _po_public(p)
        d["restaurantId"] = p.get("restaurantId")
        d["restaurantName"] = name_by_rid.get(p.get("restaurantId"), p.get("restaurantId"))
        out.append(d)
    return out

# ---------------- Supplier email (Emergent-managed Resend) ----------------
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Bert's Restaurant Group")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)

def _host_ok(host):
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)

def _same_site(shown, real):
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)

class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []
    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []
    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)
    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []

def _assert_safe_email(subject, html):
    scan = _EmailScan(); scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError("Email links/assets must be absolute https")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError("Shortened, numeric-host or credential-bearing URL")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError("Anchor text does not match real link host")

async def send_email(*, to, subject, html, from_name=None, reply_to=None):
    _assert_safe_email(subject, html)
    if not EMAIL_KEY:
        raise HTTPException(500, "Email is not configured")
    payload = {"to": [to], "subject": subject, "html": html, "from_name": from_name or EMAIL_FROM_NAME}
    if reply_to:
        payload["contact_email"] = reply_to
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{EMAIL_BASE_URL}/api/v1/email/send",
                                     headers={"X-Email-Key": EMAIL_KEY}, json=payload)
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as e:
        logger.error(f"Email send failed: {e.response.status_code} {e.response.text}")
        raise HTTPException(502, "Failed to send the supplier email")
    except Exception as e:
        logger.error(f"Email send error: {e}")
        raise HTTPException(500, "Failed to send the supplier email")

def _po_email_html(rname, po, pdf_url=None):
    rows = "".join(
        f'<tr><td style="padding:6px 10px;border-bottom:1px solid #eee">{escape(str(l.get("controlNumber","")))} &nbsp; {escape(str(l.get("name","")))}</td>'
        f'<td style="padding:6px 10px;border-bottom:1px solid #eee">{escape(str(l.get("vendorSku","") or "—"))}</td>'
        f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right">{f(l.get("qty")):g} {escape(str(l.get("purchaseUnit","")))}</td></tr>'
        for l in po.get("lines", []))
    pdf_row = (f'<tr><td style="padding:12px 0"><a href="{escape(pdf_url)}" style="display:inline-block;background:#111;'
               f'color:#fff;text-decoration:none;padding:10px 18px;border-radius:6px;font-size:14px">Download Purchase Order (PDF)</a></td></tr>') if pdf_url else ""
    return (f'<table role="presentation" width="100%" style="max-width:600px;font-family:Arial,sans-serif;color:#111">'
            f'<tr><td style="padding:20px 0"><h2 style="margin:0">{escape(rname)} — Purchase Order</h2>'
            f'<p style="color:#555;margin:6px 0 0">Vendor: <strong>{escape(str(po.get("vendor","")))}</strong> · '
            f'Order total (est.): <strong>${f(po.get("total")):,.2f}</strong></p></td></tr>'
            f'<tr><td><table role="presentation" width="100%" style="border-collapse:collapse;font-size:14px">'
            f'<tr style="background:#f6f6f6"><th style="text-align:left;padding:6px 10px">Item</th>'
            f'<th style="text-align:left;padding:6px 10px">SKU</th>'
            f'<th style="text-align:right;padding:6px 10px">Qty</th></tr>{rows}</table></td></tr>'
            f'{pdf_row}'
            f'<tr><td style="padding:16px 0;color:#555;font-size:13px">Please confirm receipt and expected delivery date by replying to this email.</td></tr>'
            f'<tr><td style="font-size:12px;color:#999;border-top:1px solid #eee;padding-top:12px">'
            f'Sent by {escape(rname)} via {escape(EMAIL_FROM_NAME)}. We never ask for passwords or payment details by email.</td></tr></table>')

def _po_pdf_bytes(rname, po):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    small = styles["Normal"].clone("small"); small.fontSize = 9
    elems = [Paragraph(f"{escape(rname)} — Purchase Order", styles["Title"]),
             Paragraph(f"Vendor: <b>{escape(str(po.get('vendor','')))}</b>", styles["Normal"]),
             Paragraph(f"Date: {escape((po.get('createdAt','') or '')[:10])}", styles["Normal"]),
             Spacer(1, 14)]
    data = [["Control #", "Item", "SKU", "Qty", "Unit Cost", "Line Total"]]
    for l in po.get("lines", []):
        data.append([l.get("controlNumber", ""), Paragraph(escape(str(l.get("name", ""))), small),
                     l.get("vendorSku", "") or "-", f"{f(l.get('qty')):g} {l.get('purchaseUnit','')}",
                     f"${f(l.get('unitCost')):,.2f}", f"${f(l.get('lineTotal')):,.2f}"])
    data.append(["", "", "", "", "Total", f"${f(po.get('total')):,.2f}"])
    t = Table(data, colWidths=[0.8 * inch, 2.6 * inch, 1.1 * inch, 1.0 * inch, 0.95 * inch, 1.05 * inch], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
        ("FONTNAME", (4, -1), (-1, -1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F9FAFB")]),
    ]))
    elems.append(t)
    doc.build(elems)
    return buf.getvalue()

def _days_between(a, b):
    try:
        da = datetime.fromisoformat(a.replace("Z", "+00:00"))
        db_ = datetime.fromisoformat(b.replace("Z", "+00:00"))
        return round((db_ - da).total_seconds() / 86400, 1)
    except (AttributeError, ValueError, TypeError):
        return None

async def _match_invoice(rid, invoice_number, po_lines):
    plines = await db.purchases.find({"restaurantId": rid, "invoiceNumber": str(invoice_number)}, {"_id": 0}).to_list(5000)
    inv_by_cn = {}
    for p in plines:
        cn = p.get("controlNumber")
        agg = inv_by_cn.setdefault(cn, {"qty": 0.0, "unitCost": f(p.get("unitCost")), "itemName": p.get("itemName", "")})
        agg["qty"] += f(p.get("qty"))
        agg["unitCost"] = f(p.get("unitCost"))
    result_lines, flagged = [], 0
    for l in po_lines:
        cn = l.get("controlNumber")
        inv = inv_by_cn.get(cn)
        rq = f(l.get("receivedQty"))
        po_cost = f(l.get("unitCost"))
        if inv:
            qty_diff = round(rq - inv["qty"], 3)
            price_diff = round(po_cost - inv["unitCost"], 4)
            fl = abs(qty_diff) > 0.001 or abs(price_diff) > 0.001
        else:
            qty_diff, price_diff, fl = None, None, True
        if fl:
            flagged += 1
        result_lines.append({"controlNumber": cn, "name": l.get("name", ""), "receivedQty": rq, "poUnitCost": po_cost,
                             "invoiceQty": inv["qty"] if inv else None, "invoiceUnitCost": inv["unitCost"] if inv else None,
                             "qtyDiff": qty_diff, "priceDiff": price_diff, "flagged": fl, "onInvoice": inv is not None})
    return {"invoiceNumber": str(invoice_number), "invoiceFound": len(plines) > 0,
            "matchedAt": datetime.now(timezone.utc).isoformat(), "flaggedCount": flagged, "lines": result_lines}

@api_router.get("/vendor-contacts/{rid}")
async def list_vendor_contacts(rid: str):
    check_rid(rid)
    vcs = await db.vendor_contacts.find({"restaurantId": rid}, {"_id": 0, "restaurantId": 0}).to_list(200)
    return vcs

@api_router.put("/vendor-contacts/{rid}")
async def put_vendor_contact(rid: str, payload: dict):
    check_rid(rid)
    vendor = str(payload.get("vendor", "")).strip()
    email = str(payload.get("orderEmail", "")).strip()
    if not vendor:
        raise HTTPException(400, "vendor is required")
    if email and not EMAIL_RE.match(email):
        raise HTTPException(400, "that doesn't look like a valid email")
    await db.vendor_contacts.update_one({"restaurantId": rid, "vendor": vendor},
        {"$set": {"restaurantId": rid, "vendor": vendor, "orderEmail": email}}, upsert=True)
    return {"ok": True, "vendor": vendor, "orderEmail": email}

class OrderEmailIn(BaseModel):
    email: Optional[str] = None
    by: str = ""

def _pdf_link(rid, oid):
    # Build the PO PDF link ONLY from a server-configured public URL — never from
    # request headers (X-Forwarded-Host) which a caller can spoof to inject an
    # attacker-controlled link into a trusted-brand email (SEC-001).
    base = os.environ.get("PUBLIC_APP_URL", "").strip().rstrip("/")
    if not base.startswith("https://"):
        return None
    host = urlparse(base).hostname or ""
    if not host or "." not in host or not _host_ok(host):
        return None
    return f"{base}/api/orders/{rid}/{oid}/pdf"

@api_router.post("/orders/{rid}/{oid}/email")
async def email_order(rid: str, oid: str, body: OrderEmailIn):
    check_rid(rid)
    po = await _get_po(rid, oid)
    if po["status"] not in ("approved", "sent"):
        raise HTTPException(400, "only approved or sent orders can be emailed to a supplier")
    vendor = po.get("vendor", "")
    override = (body.email or "").strip()
    if override and not EMAIL_RE.match(override):
        raise HTTPException(400, "that doesn't look like a valid email")
    if override:
        to = override
    else:
        vc = await db.vendor_contacts.find_one({"restaurantId": rid, "vendor": vendor}, {"_id": 0})
        to = (vc or {}).get("orderEmail", "")
    if not to:
        raise HTTPException(400, "no supplier email on file for this vendor — add one first")
    rname = next((r["name"] for r in RESTAURANTS if r["id"] == rid), rid)
    subject = f"Purchase Order from {rname} — {vendor}"
    pdf_url = _pdf_link(rid, oid)
    html = _po_email_html(rname, po, pdf_url)
    await send_email(to=to, subject=subject, html=html, from_name=rname)
    # only persist the recipient after a successful send
    if override:
        await db.vendor_contacts.update_one({"restaurantId": rid, "vendor": vendor},
            {"$set": {"restaurantId": rid, "vendor": vendor, "orderEmail": override}}, upsert=True)
    now = datetime.now(timezone.utc).isoformat()
    set_fields = {"emailedTo": to, "emailedAt": now}
    events = [_po_event("emailed", body.by, f"emailed to {to}")]
    if po["status"] == "approved":
        set_fields["status"] = "sent"
        set_fields["sentAt"] = now
        events.append(_po_event("sent", body.by, "sent via email"))
    await db.purchase_orders.update_one({"restaurantId": rid, "id": oid},
        {"$set": set_fields, "$push": {"history": {"$each": events}}})
    return _po_public(await _get_po(rid, oid))

class ReorderIn(BaseModel):
    vendor: str
    createdBy: str = ""

@api_router.post("/orders/{rid}/reorder-last")
async def reorder_last(rid: str, body: ReorderIn):
    check_rid(rid)
    last = await db.purchase_orders.find_one({"restaurantId": rid, "vendor": body.vendor, "status": {"$ne": "rejected"}}, sort=[("createdAt", -1)])
    if not last:
        raise HTTPException(404, "no previous order for this vendor to reorder")
    lines = [{"controlNumber": l.get("controlNumber"), "name": l.get("name", ""), "vendorSku": l.get("vendorSku", ""),
              "qty": f(l.get("qty")), "purchaseUnit": l.get("purchaseUnit", "case"), "unitCost": f(l.get("unitCost")),
              "receivedQty": 0, "lineTotal": round(f(l.get("qty")) * f(l.get("unitCost")), 2)} for l in last.get("lines", [])]
    now = datetime.now(timezone.utc)
    po = {"id": "po_" + uuid.uuid4().hex[:10], "restaurantId": rid, "vendor": body.vendor, "status": "draft",
          "createdBy": body.createdBy or "", "note": f"Reordered from PO on {(last.get('createdAt','') or '')[:10]}",
          "lines": lines, "total": _po_total(lines), "createdAt": now.isoformat(),
          "submittedAt": None, "approvedBy": None, "approvedAt": None, "rejectedReason": None,
          "sentAt": None, "receivedAt": None, "history": [_po_event("draft", body.createdBy, "reorder from history")]}
    await db.purchase_orders.insert_one(dict(po))
    return _po_public(po)

@api_router.get("/orders/{rid}/{oid}/pdf")
async def order_pdf(rid: str, oid: str):
    check_rid(rid)
    po = _po_public(await _get_po(rid, oid))
    rname = next((r["name"] for r in RESTAURANTS if r["id"] == rid), rid)
    pdf = _po_pdf_bytes(rname, po)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="PO_{oid}.pdf"'})

@api_router.get("/owner/discrepancies")
async def owner_discrepancies():
    name_by_rid = {r["id"]: r["short"] for r in RESTAURANTS}
    out = []
    for r in RESTAURANTS:
        pos = await db.purchase_orders.find({"restaurantId": r["id"], "status": "received"}).sort("receivedAt", -1).to_list(5000)
        for po in pos:
            rm = po.get("receiptMatch")
            if rm and rm.get("invoiceFound") and rm.get("flaggedCount", 0) > 0:
                flagged = [l for l in rm.get("lines", []) if l.get("flagged")]
                out.append({"restaurantId": r["id"], "restaurantName": name_by_rid[r["id"]], "orderId": po.get("id"),
                            "vendor": po.get("vendor"), "invoiceNumber": rm.get("invoiceNumber"),
                            "receivedAt": po.get("receivedAt"), "flaggedCount": rm.get("flaggedCount"), "lines": flagged})
    out.sort(key=lambda x: x.get("receivedAt") or "", reverse=True)
    return out

@api_router.get("/owner/vendor-scorecard")
async def owner_vendor_scorecard():
    now = datetime.now(timezone.utc)
    d45 = (now - timedelta(days=45)).isoformat()
    d90 = (now - timedelta(days=90)).isoformat()

    def _bucket(ra):
        if not ra:
            return None
        return "rec" if ra >= d45 else ("pri" if ra >= d90 else None)

    def _trend(rec, pri, eps):
        if not rec or not pri:
            return None
        ar, ap = sum(rec) / len(rec), sum(pri) / len(pri)
        if ar > ap + eps:
            return "up"
        if ar < ap - eps:
            return "down"
        return "flat"

    agg = {}
    for r in RESTAURANTS:
        pos = await db.purchase_orders.find({"restaurantId": r["id"], "status": "received"}).to_list(5000)
        for po in pos:
            v = po.get("vendor", "")
            s = agg.setdefault(v, {"receivedOrders": 0, "leadDays": [], "matchedLines": 0, "priceAccurate": 0,
                                   "priceVarSum": 0.0, "totalSpend": 0.0, "locations": set(), "flaggedLines": 0,
                                   "leadRec": [], "leadPri": [], "pvRec": [], "pvPri": []})
            s["receivedOrders"] += 1
            s["locations"].add(r["short"])
            s["totalSpend"] += f(po.get("total"))
            ra = po.get("receivedAt") or ""
            b = _bucket(ra)
            ld = _days_between(po.get("sentAt"), po.get("receivedAt"))
            if ld is not None and ld >= 0:
                s["leadDays"].append(ld)
                if b == "rec":
                    s["leadRec"].append(ld)
                elif b == "pri":
                    s["leadPri"].append(ld)
            rm = po.get("receiptMatch")
            if rm and rm.get("invoiceFound"):
                for l in rm.get("lines", []):
                    if l.get("onInvoice"):
                        s["matchedLines"] += 1
                        pv = abs(f(l.get("priceDiff")))
                        s["priceVarSum"] += pv
                        if b == "rec":
                            s["pvRec"].append(pv)
                        elif b == "pri":
                            s["pvPri"].append(pv)
                        if l.get("flagged"):
                            s["flaggedLines"] += 1
                        else:
                            s["priceAccurate"] += 1
    out = []
    for v, s in agg.items():
        ml = s["matchedLines"]
        out.append({"vendor": v, "locations": sorted(s["locations"]), "receivedOrders": s["receivedOrders"],
                    "avgLeadDays": round(sum(s["leadDays"]) / len(s["leadDays"]), 1) if s["leadDays"] else None,
                    "matchedLines": ml, "flaggedLines": s["flaggedLines"],
                    "priceAccuratePct": round(s["priceAccurate"] / ml * 100) if ml else None,
                    "avgPriceVariance": round(s["priceVarSum"] / ml, 2) if ml else None,
                    "leadTrend": _trend(s["leadRec"], s["leadPri"], 0.5),
                    "priceVarTrend": _trend(s["pvRec"], s["pvPri"], 0.01),
                    "totalSpend": round(s["totalSpend"], 2)})
    out.sort(key=lambda x: -x["totalSpend"])
    return out

class ApplyPricesIn(BaseModel):
    lines: List[dict] = []  # [{controlNumber, unitCost}]

@api_router.post("/orders/{rid}/{oid}/apply-prices")
async def apply_prices(rid: str, oid: str, body: ApplyPricesIn):
    check_rid(rid)
    po = await _get_po(rid, oid)
    vendor = po.get("vendor", "")
    today = datetime.now(timezone.utc).date().isoformat()
    updated = 0
    for ln in body.lines:
        cn = ln.get("controlNumber")
        cost = f(ln.get("unitCost"))
        if not cn or cost <= 0:
            continue
        item = await db.items.find_one({"restaurantId": rid, "controlNumber": cn}, {"_id": 0})
        if not item:
            continue
        skus = item.get("vendorSkus") or []
        target = next((sk for sk in skus if sk.get("vendor") == vendor), None) or next((sk for sk in skus if sk.get("preferred")), None) or (skus[0] if skus else None)
        if not target:
            continue
        target["price"] = round(cost, 4)
        target["priceUpdatedAt"] = today
        target["priceSource"] = "invoice"
        await db.items.update_one({"restaurantId": rid, "controlNumber": cn}, {"$set": {"vendorSkus": skus}})
        updated += 1
    return {"ok": True, "updated": updated}

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
