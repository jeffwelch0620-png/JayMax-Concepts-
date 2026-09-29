from fastapi import FastAPI, APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict, BeforeValidator
from typing import Optional, List, Annotated, Any
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os, json, math, re, uuid, logging, ipaddress, io, base64, hashlib, hmac, secrets, time, asyncio
import httpx
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse
from pymongo import UpdateOne, ReturnDocument
from pymongo.errors import DuplicateKeyError
import asyncpg
import db_pg
try:
    from pywebpush import webpush, WebPushException
except ImportError:  # pragma: no cover - optional dependency, push notifications no-op without it
    webpush = None
    class WebPushException(Exception):
        pass

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
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:ops@jaymaxconcepts.example").strip()
PUSH_ENABLED = bool(webpush and VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)

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
    key = AUTH_SECRET
    if not key:
        raise HTTPException(503, "AUTH_SECRET is not configured")
    return f"{raw}.{_b64(hmac.new(key.encode(), raw.encode(), hashlib.sha256).digest())}"

def _decode_token(token):
    try:
        raw, sig = token.split(".", 1)
        key = AUTH_SECRET
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
    return next((PG_STORE_TO_RESTAURANT[p] for p in parts if p in PG_STORE_TO_RESTAURANT), None) or next((p for p in parts if p in RIDS), None)

def _is_pin_optional(path):
    # Staff-facing routes whose OWN handler falls back to checking a shared PIN when
    # there's no bearer token (staff_prepsheet, staff_complete, staff_counts,
    # staff_counts_save, staff_task_inbox, staff_task_complete, verify_pin, and the
    # push endpoints). Without this, the blanket 401 below would run first and that
    # PIN fallback would never be reachable — silently breaking the entire PIN-only
    # staff model (Prep Sheet, Enter Counts, task portal) whenever AUTH_REQUIRED=true.
    # /api/staff/{rid}/pin (view/set the PIN itself) is intentionally excluded — that
    # stays manager/owner-only, since it manages the secret the others fall back to.
    if path == "/api/staff/verify":
        return True
    if not path.startswith("/api/staff/"):
        return False
    tail = path[len("/api/staff/"):].split("/")
    return not (len(tail) >= 2 and tail[1] in ("pin", "members"))

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
    if AUTH_REQUIRED and not AUTH_SECRET:
        return JSONResponse({"detail": "AUTH_SECRET is not configured"}, status_code=503)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token) if token else None
    if AUTH_REQUIRED and not user and not _is_pin_optional(path):
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
    route_path = path.removeprefix("/api/pg").removeprefix("/api")
    rid = _path_rid(path)
    allowed = set(user.get("locations", []))
    if rid and user.get("role") != "owner" and rid not in allowed:
        return JSONResponse({"detail": "Location access denied"}, status_code=403)
    role = user.get("role")
    if route_path.startswith(OWNER_PATHS) and role != "owner":
        return JSONResponse({"detail": "Owner role required"}, status_code=403)
    if request.method != "GET":
        if role == "readonly":
            return JSONResponse({"detail": "Read-only access"}, status_code=403)
        if role == "staff" and not route_path.startswith(STAFF_WRITE_PATHS):
            return JSONResponse({"detail": "Staff access is limited to prep workflow"}, status_code=403)
        if route_path.startswith(STAFF_PATHS) and role not in ("owner", "manager", "staff"):
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
    query = {"restaurantId": rid}
    if raw and current:
        query["revision"] = revision
    try:
        updated = await db.state_versions.find_one_and_update(
            query, {"$inc": {"revision": 1}, "$set": {"updatedAt": _now_iso()}},
            upsert=not current, return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        updated = None
    if not updated:
        latest = await db.state_versions.find_one({"restaurantId": rid}, {"_id": 0, "revision": 1})
        latest_revision = (latest or {}).get("revision", 0)
        raise HTTPException(409, f"State changed by another collaborator; reload before saving (revision {latest_revision})")
    return updated["revision"]

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
async def set_pin(rid: str, body: dict, request: Request):
    check_rid(rid)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token)
    if not user or user.get("role") not in ("owner", "manager"):
        raise HTTPException(403, "Manager role required")
    pin = str(body.get("staffPin", "")).strip()
    if not (pin.isdigit() and 4 <= len(pin) <= 8):
        raise HTTPException(400, "PIN must be 4-8 digits")
    await db.settings.update_one({"restaurantId": rid, "key": "staff"},
        {"$set": {"restaurantId": rid, "key": "staff", "staffPin": pin}}, upsert=True)
    return {"ok": True}

# ---------------- Staff roster (named staff + role, for PIN-flow identification) ----------------
STAFF_ROLES = ("owner_admin", "cook")

class StaffMemberIn(BaseModel):
    name: str
    role: str = "cook"
    active: bool = True

def _clean_staff_member(doc):
    return {"id": doc["id"], "name": doc.get("name", ""), "role": doc.get("role", "cook"),
            "active": doc.get("active", True)}

def _validate_staff_member(body):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name is required")
    if body.role not in STAFF_ROLES:
        raise HTTPException(400, "Role must be owner_admin or cook")
    return name

@api_router.get("/staff/{rid}/members")
async def list_staff_members(rid: str, request: Request):
    check_rid(rid)
    _require_manager(request)
    docs = await db.staff_members.find({"restaurantId": rid}, {"_id": 0}).sort("name", 1).to_list(500)
    return [_clean_staff_member(d) for d in docs]

@api_router.post("/staff/{rid}/members")
async def create_staff_member(rid: str, body: StaffMemberIn, request: Request):
    check_rid(rid)
    _require_manager(request)
    name = _validate_staff_member(body)
    doc = {"id": "stf_" + uuid.uuid4().hex[:10], "restaurantId": rid, "name": name,
           "role": body.role, "active": True, "createdAt": _now_iso()}
    await db.staff_members.insert_one(dict(doc))
    return _clean_staff_member(doc)

@api_router.put("/staff/{rid}/members/{staff_id}")
async def update_staff_member(rid: str, staff_id: str, body: StaffMemberIn, request: Request):
    check_rid(rid)
    _require_manager(request)
    name = _validate_staff_member(body)
    res = await db.staff_members.update_one({"restaurantId": rid, "id": staff_id},
        {"$set": {"name": name, "role": body.role, "active": bool(body.active)}})
    if not res.matched_count:
        raise HTTPException(404, "Staff member not found")
    doc = await db.staff_members.find_one({"restaurantId": rid, "id": staff_id}, {"_id": 0})
    return _clean_staff_member(doc)

@api_router.delete("/staff/{rid}/members/{staff_id}")
async def delete_staff_member(rid: str, staff_id: str, request: Request):
    check_rid(rid)
    _require_manager(request)
    await db.staff_members.delete_one({"restaurantId": rid, "id": staff_id})
    return {"ok": True}

@api_router.post("/staff/verify")
async def verify_pin(body: dict, request: Request):
    rid = body.get("restaurantId", "")
    check_rid(rid)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token)
    ok = False
    if user and user.get("role") == "owner":
        ok = True
    elif user and rid in user.get("locations", []) and user.get("role") in ("manager", "staff"):
        ok = True
    else:
        ok = str(body.get("pin", "")) == await _get_pin(rid)
    if not ok:
        return {"ok": False}
    roster = await db.staff_members.find({"restaurantId": rid, "active": True}, {"_id": 0}).sort("name", 1).to_list(500)
    return {"ok": True, "staff": [_clean_staff_member(d) for d in roster]}

@api_router.post("/staff/{rid}/identify")
async def staff_identify(rid: str, body: dict, request: Request):
    check_rid(rid)
    if str(body.get("pin", "")) != await _get_pin(rid):
        raise HTTPException(403, "Invalid PIN")
    member = await db.staff_members.find_one(
        {"restaurantId": rid, "id": body.get("staffId", ""), "active": True}, {"_id": 0})
    if not member:
        raise HTTPException(404, "Staff member not found")
    if member.get("role") != "owner_admin":
        return {"ok": True, "name": member["name"], "role": "cook"}
    # Owner/Admin identified via the shared staff PIN: mint a real session token so this
    # device gets full app access, scoped to this one restaurant (manager-equivalent —
    # not a global "owner" token, which would also unlock the other restaurants).
    synth_user = {"id": member["id"], "email": f"staff:{member['id']}", "role": "manager", "locations": [rid]}
    return {"ok": True, "name": member["name"], "role": "owner_admin",
            "session": {"user": _clean_user(synth_user), "token": _token(synth_user)}}

@api_router.post("/staff/{rid}/prepsheet")
async def staff_prepsheet(rid: str, body: dict, request: Request):
    check_rid(rid)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token)
    if not user and str((body or {}).get("pin", "")) != await _get_pin(rid):
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
    pin: str = ""
    listId: str
    taskId: str
    batches: float
    doneBy: str = ""

@api_router.post("/staff/{rid}/prepsheet/complete")
async def staff_complete(rid: str, body: StaffCompleteIn, request: Request):
    check_rid(rid)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token)
    if not user and body.pin != await _get_pin(rid):
        raise HTTPException(403, "Invalid PIN")
    done_by = body.doneBy.strip() or (user or {}).get("email", "")
    if not done_by:
        raise HTTPException(400, "Enter your name so the task is attributed")
    res = await _complete_task_core(rid, body.listId, body.taskId, body.batches, done_by, [])
    return {"ok": True, "log": res.get("log")}

# ---------------- Staff counts (Enter Counts, PIN-gated employee portal) ----------------
def _is_count_active(item):
    if item.get("countActive") is not None:
        return bool(item.get("countActive"))
    return item.get("active") is not False

@api_router.post("/staff/{rid}/counts")
async def staff_counts(rid: str, body: dict, request: Request):
    check_rid(rid)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token)
    if not user and str((body or {}).get("pin", "")) != await _get_pin(rid):
        raise HTTPException(403, "Invalid PIN")
    items = await db.items.find({"restaurantId": rid}, {"_id": 0}).to_list(5000)
    counted = [it for it in items if _is_count_active(it)]
    return {"date": _today(), "items": [{
        "controlNumber": it.get("controlNumber", ""), "name": it.get("name", ""),
        "storageArea": it.get("storageArea", ""), "unitUOM": it.get("unitUOM", ""),
        "currentStock": f(it.get("currentStock")), "lastCounted": it.get("lastCounted", ""),
        "lastCountedBy": it.get("lastCountedBy", ""),
    } for it in counted]}

class StaffCountEntryIn(BaseModel):
    controlNumber: str
    onHand: float

class StaffCountsSaveIn(BaseModel):
    pin: str = ""
    doneBy: str = ""
    counts: List[StaffCountEntryIn] = []

async def _apply_and_record_counts(rid, submitted_by, counts, source):
    # Shared by both count-entry surfaces (the manager-facing Enter Counts tab and the
    # PIN-gated staff portal) so "Count History" is a single, complete audit trail no
    # matter which one a physical count came through — both write the same currentStock/
    # lastCounted* fields on items today, but neither used to leave a per-submission record.
    ts, today = _now_iso(), _today()
    entries = []
    for entry in counts:
        it = await db.items.find_one({"restaurantId": rid, "controlNumber": entry.controlNumber}, {"_id": 0})
        if not it:
            continue
        prev = f(it.get("currentStock"))
        await db.items.update_one({"restaurantId": rid, "controlNumber": entry.controlNumber},
            {"$set": {"currentStock": entry.onHand, "lastCounted": today, "lastCountedBy": submitted_by, "lastCountedAt": ts}})
        entries.append({"controlNumber": entry.controlNumber, "name": it.get("name", ""),
                         "storageArea": it.get("storageArea", ""), "purchaseUnit": it.get("purchaseUnit", ""),
                         "previousStock": prev, "newStock": f(entry.onHand)})
    if entries:
        await db.inventory_count_submissions.insert_one({
            "id": "cnt_" + uuid.uuid4().hex[:10], "restaurantId": rid, "submittedAt": ts,
            "submittedBy": submitted_by, "source": source, "itemCount": len(entries), "items": entries})
    return len(entries)

@api_router.post("/staff/{rid}/counts/save")
async def staff_counts_save(rid: str, body: StaffCountsSaveIn, request: Request):
    check_rid(rid)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token)
    if not user and body.pin != await _get_pin(rid):
        raise HTTPException(403, "Invalid PIN")
    done_by = body.doneBy.strip() or (user or {}).get("email", "")
    if not done_by:
        raise HTTPException(400, "Enter your name so the count is attributed")
    if not body.counts:
        raise HTTPException(400, "No counts submitted")
    saved = await _apply_and_record_counts(rid, done_by, body.counts, "staff_pwa")
    return {"ok": True, "saved": saved}

class CountSubmitIn(BaseModel):
    submittedBy: str = ""
    counts: List[StaffCountEntryIn] = []

@api_router.post("/counts/{rid}/submit")
async def submit_count(rid: str, body: CountSubmitIn, request: Request):
    check_rid(rid)
    submitted_by = body.submittedBy.strip()
    if not submitted_by:
        raise HTTPException(400, "Enter your name so the count is attributed")
    if not body.counts:
        raise HTTPException(400, "No counts submitted")
    saved = await _apply_and_record_counts(rid, submitted_by, body.counts, "manager")
    return {"ok": True, "saved": saved}

@api_router.get("/counts/{rid}/history")
async def count_history(rid: str, request: Request, date_from: str = Query(None, alias="from"), date_to: str = Query(None, alias="to")):
    check_rid(rid)
    _require_manager(request)
    q = {"restaurantId": rid}
    if date_from or date_to:
        q["submittedAt"] = {}
        if date_from:
            q["submittedAt"]["$gte"] = date_from
        if date_to:
            # +2 days, not +1: submittedAt is a UTC timestamp, but `date_to` is the browser's
            # LOCAL "today" — every restaurant here is US-based (behind UTC), so an evening
            # submission can already read as tomorrow's date in UTC. One extra day of slack
            # absorbs that skew without needing to convert timezones on either side.
            q["submittedAt"]["$lt"] = (datetime.fromisoformat(date_to) + timedelta(days=2)).date().isoformat()
    return await db.inventory_count_submissions.find(q, {"_id": 0}).sort("submittedAt", -1).to_list(500)

# ---------------- Employee task portal: scheduled/assigned tasks + web push ----------------
def _require_manager(request: Request):
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token)
    if not user or user.get("role") not in ("owner", "manager"):
        raise HTTPException(403, "Manager role required")
    return user

class StaffTaskIn(BaseModel):
    taskType: str  # "count" | "prep"
    title: str
    dueDate: str  # YYYY-MM-DD
    recurrence: str = "once"  # once | daily | weekly
    assignedTo: str = ""
    track: str = "daily"
    note: str = ""

@api_router.get("/staff-tasks/{rid}")
async def list_staff_tasks(rid: str, request: Request):
    check_rid(rid)
    _require_manager(request)
    return await db.staff_tasks.find({"restaurantId": rid}, {"_id": 0}).sort("dueDate", -1).to_list(500)

async def _notify_new_staff_task(rid, task):
    if not PUSH_ENABLED:
        return
    subs = await db.push_subscriptions.find({"restaurantId": rid}, {"_id": 0}).to_list(500)
    if not subs:
        return
    label = "Count" if task.get("taskType") == "count" else "Prep"
    payload = json.dumps({"title": f"New {label} task", "body": task.get("title", "A task is due"), "taskId": task.get("id")})
    stale = []
    for sub in subs:
        try:
            await asyncio.to_thread(webpush, subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]},
                                     data=payload, vapid_private_key=VAPID_PRIVATE_KEY,
                                     vapid_claims={"sub": VAPID_CLAIM_EMAIL})
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                stale.append(sub["endpoint"])
            else:
                logger.warning("web push delivery failed: %s", e)
        except Exception:
            logger.exception("web push delivery error")
    for endpoint in stale:
        await db.push_subscriptions.delete_one({"restaurantId": rid, "endpoint": endpoint})

@api_router.post("/staff-tasks/{rid}")
async def create_staff_task(rid: str, body: StaffTaskIn, request: Request):
    check_rid(rid)
    user = _require_manager(request)
    if body.taskType not in ("count", "prep"):
        raise HTTPException(400, "taskType must be count or prep")
    if body.recurrence not in ("once", "daily", "weekly"):
        raise HTTPException(400, "recurrence must be once, daily, or weekly")
    doc = body.model_dump()
    doc.update({"id": "stask_" + uuid.uuid4().hex[:8], "restaurantId": rid, "status": "pending",
                "completedBy": "", "completedAt": None, "createdBy": user.get("email", ""), "createdAt": _now_iso()})
    await db.staff_tasks.insert_one(dict(doc))
    doc.pop("restaurantId", None)
    await _notify_new_staff_task(rid, doc)
    return doc

@api_router.delete("/staff-tasks/{rid}/{task_id}")
async def delete_staff_task(rid: str, task_id: str, request: Request):
    check_rid(rid)
    _require_manager(request)
    await db.staff_tasks.delete_one({"restaurantId": rid, "id": task_id})
    return {"ok": True}

@api_router.post("/staff/{rid}/tasks")
async def staff_task_inbox(rid: str, body: dict, request: Request):
    check_rid(rid)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token)
    if not user and str((body or {}).get("pin", "")) != await _get_pin(rid):
        raise HTTPException(403, "Invalid PIN")
    today = _today()
    tasks = await db.staff_tasks.find({"restaurantId": rid, "status": "pending", "dueDate": {"$lte": today}},
                                       {"_id": 0}).sort("dueDate", 1).to_list(200)
    return {"date": today, "tasks": tasks}

class StaffTaskCompleteIn(BaseModel):
    pin: str = ""
    doneBy: str = ""

@api_router.post("/staff/{rid}/tasks/{task_id}/complete")
async def staff_task_complete(rid: str, task_id: str, body: StaffTaskCompleteIn, request: Request):
    check_rid(rid)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token)
    if not user and body.pin != await _get_pin(rid):
        raise HTTPException(403, "Invalid PIN")
    done_by = body.doneBy.strip() or (user or {}).get("email", "")
    if not done_by:
        raise HTTPException(400, "Enter your name so the task is attributed")
    task = await db.staff_tasks.find_one({"restaurantId": rid, "id": task_id})
    if not task:
        raise HTTPException(404, "task not found")
    now = _now_iso()
    next_due = None
    if task.get("recurrence") == "daily":
        next_due = (datetime.fromisoformat(_today()) + timedelta(days=1)).date().isoformat()
    elif task.get("recurrence") == "weekly":
        next_due = (datetime.fromisoformat(_today()) + timedelta(days=7)).date().isoformat()
    await db.staff_tasks.update_one({"_id": task["_id"]},
        {"$set": {"status": "done", "completedBy": done_by, "completedAt": now}})
    if next_due:
        new_doc = {k: v for k, v in task.items() if k != "_id"}
        new_doc.update({"id": "stask_" + uuid.uuid4().hex[:8], "status": "pending", "dueDate": next_due,
                        "completedBy": "", "completedAt": None, "createdAt": now})
        await db.staff_tasks.insert_one(new_doc)
    return {"ok": True}

# ---------------- Web push subscriptions (VAPID) ----------------
@api_router.get("/staff/{rid}/push/public-key")
async def push_public_key(rid: str):
    check_rid(rid)
    return {"publicKey": VAPID_PUBLIC_KEY, "enabled": PUSH_ENABLED}

class PushSubscriptionIn(BaseModel):
    pin: str = ""
    endpoint: str
    keys: dict

@api_router.post("/staff/{rid}/push/subscribe")
async def push_subscribe(rid: str, body: PushSubscriptionIn, request: Request):
    check_rid(rid)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token)
    if not user and body.pin != await _get_pin(rid):
        raise HTTPException(403, "Invalid PIN")
    if not body.endpoint or not body.keys.get("p256dh") or not body.keys.get("auth"):
        raise HTTPException(400, "Invalid push subscription")
    await db.push_subscriptions.update_one({"restaurantId": rid, "endpoint": body.endpoint},
        {"$set": {"restaurantId": rid, "endpoint": body.endpoint, "keys": body.keys, "updatedAt": _now_iso()}}, upsert=True)
    return {"ok": True}

class PushUnsubscribeIn(BaseModel):
    pin: str = ""
    endpoint: str

@api_router.post("/staff/{rid}/push/unsubscribe")
async def push_unsubscribe(rid: str, body: PushUnsubscribeIn, request: Request):
    check_rid(rid)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token)
    if not user and body.pin != await _get_pin(rid):
        raise HTTPException(403, "Invalid PIN")
    await db.push_subscriptions.delete_one({"restaurantId": rid, "endpoint": body.endpoint})
    return {"ok": True}

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
async def ai_chat(body: ChatIn, request: Request):
    check_rid(body.restaurantId)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    user = _decode_token(token)
    if user and user.get("role") != "owner" and body.restaurantId not in user.get("locations", []):
        raise HTTPException(403, "Location access denied")
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

# ==================== Postgres (Supabase) migration: Vendors / Items / Invoices ====================
# See docs/SUPABASE_MIGRATION_PLAN.md. Lives under /api/pg while the migration is in
# progress so the existing Mongo-backed /api/... endpoints keep working untouched;
# nothing on the frontend points here yet. Store ids come from the `stores` table
# (berts, rudds, papa, comm) -- note "papa", not "papa_leonis" like the Mongo side,
# and the commissary is its own store here rather than a track field.
pg_router = APIRouter(prefix="/api/pg")
PG_STORE_IDS = {"berts", "rudds", "papa", "comm"}
PG_STORE_TO_RESTAURANT = {"berts": "berts", "rudds": "rudds", "papa": "papa_leonis", "comm": "comm"}

def check_store_id(store_id):
    if store_id not in PG_STORE_IDS:
        raise HTTPException(404, f"Unknown store '{store_id}'")

# ---------------- Vendors (global, not store-scoped) ----------------
class VendorIn(BaseModel):
    id: str
    name: str
    order_email: Optional[str] = None
    rep_name: Optional[str] = None
    rep_phone: Optional[str] = None
    active: bool = True

@pg_router.get("/vendors")
async def pg_list_vendors():
    rows = await db_pg.pool().fetch("SELECT * FROM vendors ORDER BY name")
    return [dict(r) for r in rows]

@pg_router.post("/vendors")
async def pg_create_vendor(body: VendorIn):
    row = await db_pg.pool().fetchrow(
        """INSERT INTO vendors (id, name, order_email, rep_name, rep_phone, active)
           VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
        body.id, body.name, body.order_email, body.rep_name, body.rep_phone, body.active)
    return dict(row)

@pg_router.put("/vendors/{vendor_id}")
async def pg_update_vendor(vendor_id: str, body: VendorIn):
    row = await db_pg.pool().fetchrow(
        """UPDATE vendors SET name=$2, order_email=$3, rep_name=$4, rep_phone=$5,
           active=$6, updated_at=now() WHERE id=$1 RETURNING *""",
        vendor_id, body.name, body.order_email, body.rep_name, body.rep_phone, body.active)
    if not row:
        raise HTTPException(404, "Vendor not found")
    return dict(row)

# ---------------- Items (global catalog + per-store tracking + per-vendor SKUs) ----------------
class VendorSkuIn(BaseModel):
    vendor_id: str
    vendor_sku: str
    vendor_description: Optional[str] = None
    purchase_unit: str = "case"
    base_per_purchase_unit: Optional[float] = None
    pack_count: Optional[float] = None
    unit_qty: Optional[float] = None
    unit_uom: Optional[str] = None
    price: Optional[float] = None
    preferred: bool = False
    available: bool = True

class ItemIn(BaseModel):
    code: str
    name: str
    category: Optional[str] = None
    base_unit: str = "each"
    item_type: Optional[str] = None
    is_high_value: Optional[bool] = None
    notes: Optional[str] = None
    # costing fields (Chunk 3 addition -- mirrors the Mongo item's itemType/pack*/portion*,
    # which the frontend's itemDerived() needs to compute portionsPerUnit/costPerPortion the
    # same way it does today; see docs/SUPABASE_MIGRATION_PLAN.md)
    costing_type: str = "portion"  # "portion" | "usage" -- unrelated to item_type above
    pack_count: Optional[float] = None
    unit_qty: Optional[float] = None
    unit_uom: Optional[str] = None
    portion_size: Optional[float] = None
    portion_uom: Optional[str] = None
    # store_items fields
    count_unit: str = "case"
    base_per_count_unit: float = 1
    storage_area: Optional[str] = None
    counted_nightly: bool = False
    par: float = 0
    active: bool = True
    order_enabled: bool = True
    sales_tracked: bool = True
    needs_review: bool = False
    vendor_skus: List[VendorSkuIn] = []

async def _item_row_to_api(conn, store_id, item_row, store_item_row):
    skus = await conn.fetch(
        """SELECT vi.*, v.name AS vendor_name FROM vendor_items vi
           JOIN vendors v ON v.id = vi.vendor_id WHERE vi.item_code = $1""", item_row["code"])
    return {
        "code": item_row["code"], "name": item_row["name"], "category": item_row["category"],
        "baseUnit": item_row["base_unit"], "itemType": item_row["item_type"],
        "isHighValue": item_row["is_high_value"], "notes": item_row["notes"],
        "costingType": item_row["costing_type"],
        "packCount": float(item_row["pack_count"]) if item_row["pack_count"] is not None else None,
        "unitQty": float(item_row["unit_qty"]) if item_row["unit_qty"] is not None else None,
        "unitUOM": item_row["unit_uom"],
        "portionSize": float(item_row["portion_size"]) if item_row["portion_size"] is not None else None,
        "portionUOM": item_row["portion_uom"],
        "countUnit": store_item_row["count_unit"] if store_item_row else None,
        "basePerCountUnit": float(store_item_row["base_per_count_unit"]) if store_item_row else None,
        "storageArea": store_item_row["storage_area"] if store_item_row else None,
        "countedNightly": store_item_row["counted_nightly"] if store_item_row else False,
        "active": store_item_row["store_active"] if store_item_row else True,
        "countActive": store_item_row["store_active"] if store_item_row else True,
        "orderEnabled": store_item_row["order_enabled"] if store_item_row else True,
        "salesTracked": store_item_row["sales_tracked"] if store_item_row else True,
        "needsReview": store_item_row["needs_review"] if store_item_row else False,
        "currentStock": float(store_item_row["current_stock"]) if store_item_row else 0,
        "par": float(store_item_row["par"]) if store_item_row else 0,
        "lastCounted": store_item_row["last_counted"].isoformat() if store_item_row and store_item_row["last_counted"] else None,
        "lastCountedBy": store_item_row["last_counted_by"] if store_item_row else None,
        "vendorSkus": [{
            "id": str(s["id"]), "vendor": s["vendor_id"], "vendorName": s["vendor_name"],
            "vendorSku": s["vendor_sku"], "vendorDescription": s["vendor_description"],
            "purchaseUnit": s["purchase_unit"],
            "basePerPurchaseUnit": float(s["base_per_purchase_unit"]) if s["base_per_purchase_unit"] is not None else None,
            "packCount": float(s["pack_count"]) if s["pack_count"] is not None else None,
            "unitQty": float(s["unit_qty"]) if s["unit_qty"] is not None else None,
            "unitUOM": s["unit_uom"],
            "price": float(s["price"]) if s["price"] is not None else None,
            "priceUpdatedAt": s["price_updated_at"].isoformat() if s["price_updated_at"] else None,
            "priceSource": s["price_source"], "preferred": s["preferred"], "available": s["available"],
        } for s in skus],
    }

@pg_router.get("/items/{store_id}")
async def pg_list_items(store_id: str):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        rows = await conn.fetch(
            """SELECT i.*, si.count_unit, si.base_per_count_unit, si.storage_area, si.counted_nightly,
                      si.current_stock, si.par, si.last_counted, si.last_counted_by,
                      si.active AS store_active, si.order_enabled, si.sales_tracked, si.needs_review
               FROM items i JOIN store_items si ON si.item_code = i.code
               WHERE si.store_id = $1 ORDER BY i.name""", store_id)
        return [await _item_row_to_api(conn, store_id, r, r) for r in rows]
    finally:
        await db_pg.pool().release(conn)

async def _pg_save_item(conn, store_id, body):
    await conn.execute(
                """INSERT INTO items (code, name, category, base_unit, item_type, is_high_value, notes,
                       costing_type, pack_count, unit_qty, unit_uom, portion_size, portion_uom)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                   ON CONFLICT (code) DO UPDATE SET name=$2,
                       category=CASE WHEN $14 THEN $3 ELSE items.category END, base_unit=$4,
                       item_type=CASE WHEN $15 THEN $5 ELSE items.item_type END,
                       is_high_value=CASE WHEN $16 THEN $6 ELSE items.is_high_value END,
                       notes=CASE WHEN $17 THEN $7 ELSE items.notes END,
                       costing_type=$8, pack_count=$9, unit_qty=$10, unit_uom=$11,
                       portion_size=$12, portion_uom=$13, updated_at=now()""",
                body.code, body.name, body.category, body.base_unit, body.item_type or "raw",
                body.is_high_value if body.is_high_value is not None else False, body.notes,
                body.costing_type, body.pack_count, body.unit_qty, body.unit_uom, body.portion_size, body.portion_uom,
                "category" in body.model_fields_set, "item_type" in body.model_fields_set,
                "is_high_value" in body.model_fields_set, "notes" in body.model_fields_set)
    si = await conn.fetchrow(
                """INSERT INTO store_items (store_id, item_code, count_unit, base_per_count_unit,
                       storage_area, counted_nightly, par, active, order_enabled, sales_tracked, needs_review)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                   ON CONFLICT (store_id, item_code) DO UPDATE SET count_unit=$3,
                       base_per_count_unit=$4, storage_area=$5, counted_nightly=$6, par=$7,
                       active=$8, order_enabled=$9, sales_tracked=$10, needs_review=$11
                   RETURNING *, active AS store_active""",
                store_id, body.code, body.count_unit, body.base_per_count_unit, body.storage_area,
                body.counted_nightly, body.par, body.active, body.order_enabled, body.sales_tracked, body.needs_review)
    existing_skus = await conn.fetch(
                "SELECT id, vendor_id, vendor_sku FROM vendor_items WHERE item_code=$1 FOR UPDATE", body.code)
    desired_skus = set()
    for sk in body.vendor_skus:
        desired_skus.add((sk.vendor_id, sk.vendor_sku))
        existing = await conn.fetchrow(
                    "SELECT id, item_code FROM vendor_items WHERE vendor_id=$1 AND vendor_sku=$2 FOR UPDATE",
                    sk.vendor_id, sk.vendor_sku)
        if existing and existing["item_code"] != body.code:
            raise HTTPException(409, "Vendor SKU is already linked to another item")
        if existing:
            await conn.execute(
                        """UPDATE vendor_items SET vendor_description=$2, purchase_unit=$3,
                               base_per_purchase_unit=$4, pack_count=$5, unit_qty=$6, unit_uom=$7,
                               price=$8, price_updated_at=CASE WHEN $8 IS NOT NULL THEN now() ELSE price_updated_at END,
                               price_source=CASE WHEN $8 IS NOT NULL THEN 'manual' ELSE price_source END,
                               preferred=$9, available=$10 WHERE id=$1""",
                        existing["id"], sk.vendor_description, sk.purchase_unit, sk.base_per_purchase_unit,
                        sk.pack_count, sk.unit_qty, sk.unit_uom, sk.price, sk.preferred, sk.available)
        else:
            await conn.execute(
                        """INSERT INTO vendor_items (vendor_id, vendor_sku, vendor_description, item_code,
                               purchase_unit, base_per_purchase_unit, pack_count, unit_qty, unit_uom,
                               price, price_updated_at, price_source, preferred, available)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10, CASE WHEN $10 IS NOT NULL THEN now() END, 'manual', $11, $12)""",
                        sk.vendor_id, sk.vendor_sku, sk.vendor_description, body.code, sk.purchase_unit,
                        sk.base_per_purchase_unit, sk.pack_count, sk.unit_qty, sk.unit_uom, sk.price,
                        sk.preferred, sk.available)
    for sku in existing_skus:
        if (sku["vendor_id"], sku["vendor_sku"]) not in desired_skus:
            referenced = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM invoice_lines WHERE vendor_item_id=$1)", sku["id"])
            if not referenced:
                await conn.execute("DELETE FROM vendor_items WHERE id=$1", sku["id"])
    item_row = await conn.fetchrow("SELECT * FROM items WHERE code=$1", body.code)
    return await _item_row_to_api(conn, store_id, item_row, si)

@pg_router.post("/items/{store_id}")
async def pg_create_item(store_id: str, body: ItemIn):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        async with conn.transaction():
            return await _pg_save_item(conn, store_id, body)
    finally:
        await db_pg.pool().release(conn)

@pg_router.put("/items/{store_id}")
async def pg_replace_items(store_id: str, body: List[ItemIn], request: Request):
    check_store_id(store_id)
    revision_rid = {"papa": "papa_leonis"}.get(store_id, store_id)
    revision = await _check_and_bump_revision(revision_rid, request)
    conn = await db_pg.pool().acquire()
    try:
        async with conn.transaction():
            existing = await conn.fetch("SELECT item_code FROM store_items WHERE store_id=$1 FOR UPDATE", store_id)
            next_codes = {item.code for item in body}
            for item in body:
                await _pg_save_item(conn, store_id, item)
            for row in existing:
                if row["item_code"] not in next_codes:
                    await _pg_delete_item_in_conn(conn, store_id, row["item_code"])
        return {"ok": True, "revision": revision}
    finally:
        await db_pg.pool().release(conn)

async def _pg_delete_item_in_conn(conn, store_id, code):
    await conn.execute("DELETE FROM store_items WHERE store_id=$1 AND item_code=$2", store_id, code)
    other_stores = await conn.fetchval("SELECT count(*) FROM store_items WHERE item_code=$1", code)
    if other_stores == 0:
        await conn.execute("DELETE FROM vendor_items WHERE item_code=$1", code)
        await conn.execute("DELETE FROM items WHERE code=$1", code)

@pg_router.delete("/items/{store_id}/{code}")
async def pg_delete_item(store_id: str, code: str):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        async with conn.transaction():
            exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM store_items WHERE store_id=$1 AND item_code=$2)", store_id, code)
            await _pg_delete_item_in_conn(conn, store_id, code)
            return {"ok": True, "deleted": bool(exists)}
    finally:
        await db_pg.pool().release(conn)

# ---------------- Invoices ----------------
class InvoiceLineIn(BaseModel):
    vendor_item_id: Optional[str] = None
    description: Optional[str] = None
    qty: float
    purchase_unit: Optional[str] = None
    unit_price: Optional[float] = None

class InvoiceIn(BaseModel):
    vendor_id: str
    invoice_number: Optional[str] = None
    invoice_date: str
    delivered_to: Optional[str] = None
    source: Optional[str] = None
    created_by: Optional[str] = None
    lines: List[InvoiceLineIn] = []

@pg_router.get("/invoices/{store_id}")
async def pg_list_invoices(store_id: str, date_from: str = Query(None, alias="from"), date_to: str = Query(None, alias="to")):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        q = "SELECT * FROM invoices WHERE store_id = $1"
        params = [store_id]
        if date_from:
            params.append(date_from); q += f" AND invoice_date >= ${len(params)}"
        if date_to:
            params.append(date_to); q += f" AND invoice_date <= ${len(params)}"
        q += " ORDER BY invoice_date DESC"
        invoices = await conn.fetch(q, *params)
        out = []
        for inv in invoices:
            lines = await conn.fetch(
                """SELECT il.*, vi.vendor_sku, i.name AS item_name, i.code AS item_code
                   FROM invoice_lines il
                   LEFT JOIN vendor_items vi ON vi.id = il.vendor_item_id
                   LEFT JOIN items i ON i.code = vi.item_code
                   WHERE il.invoice_id = $1""", inv["id"])
            out.append({
                "id": str(inv["id"]), "vendorId": inv["vendor_id"], "invoiceNumber": inv["invoice_number"],
                "invoiceDate": inv["invoice_date"].isoformat(), "total": float(inv["total"]) if inv["total"] is not None else 0,
                "source": inv["source"], "lines": [{
                    "id": str(l["id"]), "itemCode": l["item_code"], "itemName": l["item_name"],
                    "description": l["description"], "qty": float(l["qty"]),
                    "unit": l["purchase_unit"], "unitPrice": float(l["unit_price"]) if l["unit_price"] is not None else 0,
                    "extended": float(l["extended"]) if l["extended"] is not None else 0,
                } for l in lines],
            })
        return out
    finally:
        await db_pg.pool().release(conn)

@pg_router.post("/invoices/{store_id}")
async def pg_create_invoice(store_id: str, body: InvoiceIn):
    check_store_id(store_id)
    if not body.lines:
        raise HTTPException(400, "Invoice needs at least one line")
    conn = await db_pg.pool().acquire()
    try:
        async with conn.transaction():
            total = sum((ln.qty or 0) * (ln.unit_price or 0) for ln in body.lines)
            inv = await conn.fetchrow(
                """INSERT INTO invoices (store_id, delivered_to, vendor_id, invoice_number, invoice_date, total, source, created_by)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *""",
                store_id, body.delivered_to or store_id, body.vendor_id, body.invoice_number,
                body.invoice_date, total, body.source or "manual", body.created_by)
            for ln in body.lines:
                extended = (ln.qty or 0) * (ln.unit_price or 0)
                await conn.execute(
                    """INSERT INTO invoice_lines (invoice_id, vendor_item_id, description, qty, purchase_unit, unit_price, extended)
                       VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                    inv["id"], ln.vendor_item_id, ln.description, ln.qty, ln.purchase_unit, ln.unit_price, extended)
                if ln.vendor_item_id and ln.unit_price:
                    await conn.execute(
                        """UPDATE vendor_items SET price=$2, price_updated_at=now(), price_source='invoice'
                           WHERE id=$1""", ln.vendor_item_id, ln.unit_price)
            return {"ok": True, "id": str(inv["id"]), "total": float(total)}
    finally:
        await db_pg.pool().release(conn)

# ---------------- Dishes (menu items + prep recipes) ----------------
# Dish ids here are real Postgres uuids -- unlike the Mongo side's client-generated
# "dish_xxx"/"prep_xxx" strings. Prep's own endpoints above (prep_recipe_stock,
# prep_logs, prep_overrides) already key everything by this same uuid, so once the
# frontend adapter is wired to /api/pg/dishes those stay consistent with each other.
# reportingPeriods.dishSales (still Mongo-only, not migrated) is keyed by the OLD
# Mongo dish id and is NOT remapped here -- see the Chunk 4 note in
# docs/SUPABASE_MIGRATION_PLAN.md.
class DishLineIn(BaseModel):
    source_type: str  # "item" | "prep"
    item_code: Optional[str] = None
    prep_dish_id: Optional[str] = None
    qty: float = 0

class DishIn(BaseModel):
    id: Optional[str] = None  # set -> update that dish; absent -> create
    client_id: Optional[str] = None
    name: str
    menu_code: Optional[str] = None
    recipe_type: str = "menu"
    price: Optional[float] = None
    target_pct: Optional[float] = None
    yield_qty: Optional[float] = None
    yield_uom: Optional[str] = None
    prep_par: Optional[float] = None
    procedure: Optional[str] = None
    equipment: Optional[str] = None
    shelf_life: Optional[str] = None
    menu_category: Optional[str] = None
    description: Optional[str] = None
    photo_url: Optional[str] = None
    portion_note: Optional[str] = None
    frequency: Optional[str] = None
    lines: List[DishLineIn] = []

def _dish_row_to_api(row, lines):
    return {
        "id": str(row["id"]), "name": row["name"], "menuCode": row["menu_code"], "recipeType": row["recipe_type"],
        "price": float(row["price"]) if row["price"] is not None else None,
        "targetPct": float(row["target_pct"]) if row["target_pct"] is not None else None,
        "yieldQty": float(row["yield_qty"]) if row["yield_qty"] is not None else None,
        "yieldUOM": row["yield_uom"], "prepPar": float(row["prep_par"]) if row["prep_par"] is not None else None,
        "procedure": row["procedure"], "equipment": row["equipment"], "shelfLife": row["shelf_life"],
        "menuCategory": row["menu_category"], "description": row["description"], "photoUrl": row["photo_url"],
        "portionNote": row["portion_note"], "frequency": row["frequency"],
        "lines": [{
            "sourceType": l["source_type"], "itemCode": l["item_code"],
            "prepDishId": str(l["prep_dish_id"]) if l["prep_dish_id"] else None, "qty": float(l["qty"] or 0),
        } for l in lines],
    }

@pg_router.get("/dishes/{store_id}")
async def pg_list_dishes(store_id: str):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        rows = await conn.fetch("SELECT * FROM dishes WHERE store_id=$1 ORDER BY name", store_id)
        out = []
        for r in rows:
            lines = await conn.fetch("SELECT * FROM dish_lines WHERE dish_id=$1", r["id"])
            out.append(_dish_row_to_api(r, lines))
        return out
    finally:
        await db_pg.pool().release(conn)

@pg_router.post("/dishes/{store_id}")
async def pg_create_dish(store_id: str, body: DishIn):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        async with conn.transaction():
            return await _pg_save_dish(conn, store_id, body, {})
    finally:
        await db_pg.pool().release(conn)

async def _pg_save_dish(conn, store_id, body, client_ids):
    if body.id:
        row = await conn.fetchrow(
            """UPDATE dishes SET name=$1, menu_code=$2, recipe_type=$3, price=$4, target_pct=$5,
                   yield_qty=$6, yield_uom=$7, prep_par=$8, procedure=$9, equipment=$10, shelf_life=$11,
                   menu_category=$12, description=$13, photo_url=$14, portion_note=$15, frequency=$16,
                   updated_at=now()
               WHERE id=$17 AND store_id=$18 RETURNING *""",
            body.name, body.menu_code, body.recipe_type, body.price, body.target_pct, body.yield_qty,
            body.yield_uom, body.prep_par, body.procedure, body.equipment, body.shelf_life,
            body.menu_category, body.description, body.photo_url, body.portion_note, body.frequency,
            body.id, store_id)
        if not row:
            raise HTTPException(404, "Dish not found")
    else:
        row = await conn.fetchrow(
            """INSERT INTO dishes (store_id, name, menu_code, recipe_type, price, target_pct, yield_qty,
                   yield_uom, prep_par, procedure, equipment, shelf_life, menu_category, description,
                   photo_url, portion_note, frequency)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17) RETURNING *""",
            store_id, body.name, body.menu_code, body.recipe_type, body.price, body.target_pct,
            body.yield_qty, body.yield_uom, body.prep_par, body.procedure, body.equipment, body.shelf_life,
            body.menu_category, body.description, body.photo_url, body.portion_note, body.frequency)
    await conn.execute("DELETE FROM dish_lines WHERE dish_id=$1", row["id"])
    for ln in body.lines:
        prep_id = client_ids.get(ln.prep_dish_id, ln.prep_dish_id)
        await conn.execute(
            """INSERT INTO dish_lines (dish_id, source_type, item_code, prep_dish_id, qty)
               VALUES ($1,$2,$3,$4,$5)""",
            row["id"], ln.source_type, ln.item_code, prep_id, ln.qty)
    lines = await conn.fetch("SELECT * FROM dish_lines WHERE dish_id=$1", row["id"])
    return _dish_row_to_api(row, lines)

@pg_router.put("/dishes/{store_id}")
async def pg_replace_dishes(store_id: str, body: List[DishIn], request: Request):
    check_store_id(store_id)
    revision_rid = {"papa": "papa_leonis"}.get(store_id, store_id)
    revision = await _check_and_bump_revision(revision_rid, request)
    conn = await db_pg.pool().acquire()
    try:
        async with conn.transaction():
            existing = await conn.fetch("SELECT id FROM dishes WHERE store_id=$1 FOR UPDATE", store_id)
            next_ids = {dish.id for dish in body if dish.id}
            client_ids, saved = {}, {}
            for index, dish in sorted(enumerate(body), key=lambda pair: pair[1].recipe_type != "prep"):
                lines = [line.model_copy(update={
                    "prep_dish_id": client_ids.get(line.prep_dish_id, line.prep_dish_id)
                }) for line in dish.lines]
                canonical_dish = dish.model_copy(update={"lines": lines})
                saved_dish = await _pg_save_dish(conn, store_id, canonical_dish, client_ids)
                if dish.client_id:
                    client_ids[dish.client_id] = saved_dish["id"]
                saved[index] = saved_dish
            for row in existing:
                if str(row["id"]) not in next_ids:
                    await conn.execute("DELETE FROM dishes WHERE id=$1 AND store_id=$2", row["id"], store_id)
        return {"ok": True, "revision": revision, "dishes": [saved[i] for i in range(len(body))]}
    finally:
        await db_pg.pool().release(conn)

@pg_router.delete("/dishes/{store_id}/{dish_id}")
async def pg_delete_dish(store_id: str, dish_id: str):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        async with conn.transaction():
            try:
                deleted = await conn.execute("DELETE FROM dishes WHERE id=$1 AND store_id=$2", dish_id, store_id)
            except asyncpg.exceptions.ForeignKeyViolationError:
                raise HTTPException(400, "This recipe is referenced elsewhere (another recipe's ingredients, prep history, "
                                          "or a count) -- remove those references first")
            return {"ok": True, "deleted": deleted != "DELETE 0"}
    finally:
        await db_pg.pool().release(conn)

# ==================== Postgres (Supabase) migration: Prep ====================
# See docs/SUPABASE_MIGRATION_PLAN.md (step 3). Same /api/pg prefix and
# fails-open-if-unreachable pattern as the Vendors/Items/Invoices section above.
# NOT live-verified end to end yet (needs the real DATABASE_URL password) -- built and
# reviewed against the real, already-migrated data's shape, same caveat as that
# earlier section.
#
# Track (daily/bulk) maps directly to count_sessions.count_type (nightly_prep/
# commissary) and to prep_lists.count_type (added specifically so a list is
# filterable without joining through from_count). prep_items has no track column at
# all -- it's derived from made_at vs store_id (made_at == store_id -> daily, made_at
# != store_id -> bulk/commissary), matching the "faithful port" decision in the plan:
# store_id is always the CONSUMING restaurant, made_at is where it's actually produced.
TRACK_TO_COUNT_TYPE = {"daily": "nightly_prep", "bulk": "commissary"}
COUNT_TYPE_TO_TRACK = {v: k for k, v in TRACK_TO_COUNT_TYPE.items()}

def _pg_now_iso():
    return datetime.now(timezone.utc).isoformat()

def _pg_today():
    return datetime.now(timezone.utc).date().isoformat()

def _pg_prep_items_track_where(track):
    return "made_at IS NOT NULL AND made_at != store_id" if track == "bulk" else "(made_at IS NULL OR made_at = store_id)"

async def _pg_item_derived(conn, item_code):
    # Mirrors item_derived(): cost/portions come from the item's PREFERRED vendor_item
    # (falling back to any vendor_item), not from store_items.base_per_count_unit --
    # purchase_unit and count_unit can differ even though they're equal for every item
    # in the currently-migrated data.
    sku = await conn.fetchrow(
        "SELECT price, base_per_purchase_unit FROM vendor_items WHERE item_code = $1 ORDER BY preferred DESC, price NULLS LAST LIMIT 1",
        item_code)
    if not sku or not sku["base_per_purchase_unit"]:
        return {"portionsPerUnit": 0.0, "costPerPortion": 0.0, "price": float(sku["price"]) if sku and sku["price"] else 0.0}
    ppu = float(sku["base_per_purchase_unit"])
    price = float(sku["price"] or 0)
    return {"portionsPerUnit": ppu, "costPerPortion": (price / ppu) if ppu > 0 else 0.0, "price": price}

async def _pg_raw_portions(conn, dish_id, target_item_code, stack=()):
    # Mirrors raw_portions(): recursively resolves how many portions of an item a
    # recipe consumes, walking prep-within-prep lines (e.g. a pizza's dough-batch
    # sub-recipe, which itself consumes flour).
    if not dish_id or dish_id in stack:
        return 0.0
    stack = stack + (dish_id,)
    lines = await conn.fetch("SELECT source_type, item_code, prep_dish_id, qty FROM dish_lines WHERE dish_id = $1", dish_id)
    total = 0.0
    for l in lines:
        qty = float(l["qty"] or 0)
        if l["source_type"] == "prep" and l["prep_dish_id"]:
            sub = await conn.fetchrow("SELECT yield_qty FROM dishes WHERE id = $1", l["prep_dish_id"])
            sy = float((sub["yield_qty"] if sub else None) or 1) or 1
            total += await _pg_raw_portions(conn, l["prep_dish_id"], target_item_code, stack) * (qty / sy)
        elif l["source_type"] == "item" and l["item_code"] == target_item_code:
            total += qty
    return total

def _pg_log_to_api(row):
    return {"id": str(row["id"]), "kind": row["kind"], "recipeId": str(row["dish_id"]) if row["dish_id"] else None,
            "prepItemId": str(row["prep_item_id"]) if row["prep_item_id"] else None,
            "name": row["name"], "batches": float(row["batches"] or 0), "produced": float(row["produced"] or 0),
            "yieldUOM": row["yield_uom"], "usage": row["usage"] or [], "containers": row["containers"] or [],
            "totalCost": float(row["total_cost"] or 0), "date": row["date"].isoformat() if row["date"] else None,
            "createdAt": row["created_at"].isoformat() if row["created_at"] else None}

async def _pg_prep_stock_list(conn, store_id):
    rows = await conn.fetch(
        """SELECT prs.dish_id, prs.prep_item_id, prs.on_hand, prs.containers,
                  COALESCE(d.name, pi.name) AS name, COALESCE(d.yield_uom, pi.container) AS yield_uom
           FROM prep_recipe_stock prs
           LEFT JOIN dishes d ON d.id = prs.dish_id
           LEFT JOIN prep_items pi ON pi.id = prs.prep_item_id
           WHERE prs.store_id = $1""", store_id)
    return [{"recipeId": str(r["dish_id"]) if r["dish_id"] else None,
             "prepItemId": str(r["prep_item_id"]) if r["prep_item_id"] else None,
             "name": r["name"], "onHand": float(r["on_hand"] or 0),
             "yieldUOM": r["yield_uom"], "containers": r["containers"] or []} for r in rows]

@pg_router.get("/prep/{store_id}/state")
async def pg_prep_state(store_id: str):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        logs = await conn.fetch(
            "SELECT * FROM prep_logs WHERE store_id=$1 ORDER BY created_at DESC LIMIT 20000", store_id)
        return {"prepStock": await _pg_prep_stock_list(conn, store_id),
               "prepLogs": [_pg_log_to_api(row) for row in logs]}
    finally:
        await db_pg.pool().release(conn)

async def _pg_deduct_and_stock(conn, store_id, recipe, batches, containers, kind, name):
    store_items = await conn.fetch(
        "SELECT item_code, current_stock, count_unit FROM store_items WHERE store_id=$1 ORDER BY item_code FOR UPDATE",
        store_id)
    yield_qty = float(recipe["yield_qty"] or 1) or 1
    usage = []
    for si in store_items:
        portions = await _pg_raw_portions(conn, recipe["id"], si["item_code"]) * batches
        if portions <= 0:
            continue
        item = await conn.fetchrow("SELECT name FROM items WHERE code = $1", si["item_code"])
        derived = await _pg_item_derived(conn, si["item_code"])
        ppu = derived["portionsPerUnit"]
        units = portions / ppu if ppu > 0 else 0
        new_stock = max(0, round(float(si["current_stock"] or 0) - units, 3))
        await conn.execute("UPDATE store_items SET current_stock=$1 WHERE store_id=$2 AND item_code=$3",
                            new_stock, store_id, si["item_code"])
        usage.append({"controlNumber": si["item_code"], "name": (item["name"] if item else ""), "portions": round(portions, 2),
                      "units": round(units, 3), "purchaseUnit": si["count_unit"], "cost": round(portions * derived["costPerPortion"], 2)})
    produced = yield_qty * batches
    new_containers = [dict(c, id="c_" + uuid.uuid4().hex[:8], createdAt=_pg_now_iso())
                       for c in containers if (c.get("count") or 0) > 0 and (c.get("size") or 0) > 0]
    await conn.fetchrow(
        "SELECT on_hand FROM prep_recipe_stock WHERE dish_id=$1 AND store_id=$2 FOR UPDATE", recipe["id"], store_id)
    await conn.execute(
        """INSERT INTO prep_recipe_stock (dish_id, store_id, on_hand, containers) VALUES ($1,$2,$3,$4)
           ON CONFLICT (store_id, dish_id) WHERE dish_id IS NOT NULL
           DO UPDATE SET on_hand=prep_recipe_stock.on_hand + EXCLUDED.on_hand,
                         containers=prep_recipe_stock.containers || EXCLUDED.containers""",
        recipe["id"], store_id, round(produced, 3), new_containers)
    total_cost = round(sum(u["cost"] for u in usage), 2)
    log_row = await conn.fetchrow(
        """INSERT INTO prep_logs (store_id, kind, dish_id, name, batches, produced, yield_uom, usage, containers, total_cost, date, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING *""",
        store_id, kind, recipe["id"], name, batches, round(produced, 2), recipe["yield_uom"],
        usage, new_containers, total_cost, _pg_today(), _pg_now_iso())
    return {"prepStock": await _pg_prep_stock_list(conn, store_id), "log": _pg_log_to_api(log_row)}

async def _pg_deduct_item_and_stock(conn, store_id, pitem, vessels):
    if not pitem["item_code"]:
        raise HTTPException(400, "prep item has no linked inventory item")
    si = await conn.fetchrow(
        "SELECT * FROM store_items WHERE store_id=$1 AND item_code=$2 FOR UPDATE", store_id, pitem["item_code"])
    if not si:
        raise HTTPException(404, f"inventory item {pitem['item_code']} not found")
    item = await conn.fetchrow("SELECT name FROM items WHERE code=$1", pitem["item_code"])
    derived = await _pg_item_derived(conn, pitem["item_code"])
    ppu = derived["portionsPerUnit"]
    portions = vessels * float(pitem["vessel_capacity"] or 0)
    units = portions / ppu if ppu > 0 else 0
    cost = portions * derived["costPerPortion"]
    new_stock = max(0, round(float(si["current_stock"] or 0) - units, 3))
    await conn.execute("UPDATE store_items SET current_stock=$1 WHERE store_id=$2 AND item_code=$3", new_stock, store_id, pitem["item_code"])
    await conn.fetchrow(
        "SELECT on_hand FROM prep_recipe_stock WHERE store_id=$1 AND prep_item_id=$2 FOR UPDATE", store_id, pitem["id"])
    await conn.execute(
        """INSERT INTO prep_recipe_stock (prep_item_id, store_id, on_hand, containers) VALUES ($1,$2,$3,'[]'::jsonb)
           ON CONFLICT (store_id, prep_item_id) WHERE prep_item_id IS NOT NULL
           DO UPDATE SET on_hand=prep_recipe_stock.on_hand + EXCLUDED.on_hand""",
        pitem["id"], store_id, round(vessels, 3))
    log_row = await conn.fetchrow(
        """INSERT INTO prep_logs (store_id, kind, prep_item_id, name, batches, produced, yield_uom, usage, containers, total_cost, date, created_at)
           VALUES ($1,'batch',$2,$3,$4,$5,$6,$7,'[]'::jsonb,$8,$9,$10) RETURNING *""",
        store_id, pitem["id"], pitem["name"], vessels, round(vessels, 2), pitem["container"] or "vessel",
        [{"controlNumber": pitem["item_code"], "name": (item["name"] if item else ""), "portions": round(portions, 2),
          "units": round(units, 3), "purchaseUnit": si["count_unit"], "cost": round(cost, 2)}],
        round(cost, 2), _pg_today(), _pg_now_iso())
    log = _pg_log_to_api(log_row)
    log["prepItemId"] = str(pitem["id"])
    return {"prepStock": await _pg_prep_stock_list(conn, store_id), "log": log}

class PgContainerIn(BaseModel):
    label: str = ""
    size: float = 0
    count: int = 0

class PgPrepCompleteIn(BaseModel):
    recipeId: str
    batches: float
    containers: List[PgContainerIn] = []

@pg_router.post("/prep/{store_id}/complete")
async def pg_complete_prep(store_id: str, body: PgPrepCompleteIn):
    check_store_id(store_id)
    if body.batches <= 0:
        raise HTTPException(400, "batches must be greater than zero")
    conn = await db_pg.pool().acquire()
    try:
        recipe = await conn.fetchrow("SELECT * FROM dishes WHERE id=$1 AND store_id=$2 AND recipe_type='prep'", body.recipeId, store_id)
        if not recipe:
            raise HTTPException(404, "prep recipe not found")
        return await _pg_deduct_and_stock(conn, store_id, recipe, body.batches, [c.model_dump() for c in body.containers], "batch", recipe["name"])
    finally:
        await db_pg.pool().release(conn)

class PgApplySalesIn(BaseModel):
    dishSales: dict = {}

@pg_router.post("/prep/{store_id}/apply-sales")
async def pg_apply_sales(store_id: str, body: PgApplySalesIn):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        dishes = await conn.fetch("SELECT * FROM dishes WHERE store_id=$1", store_id)
        by_id = {str(d["id"]): dict(d) for d in dishes}
        usage_by_recipe = {}
        for d in dishes:
            if d["recipe_type"] == "prep":
                continue
            sold = f(body.dishSales.get(str(d["id"])))
            if sold <= 0:
                continue
            lines = await conn.fetch("SELECT * FROM dish_lines WHERE dish_id=$1 AND source_type='prep'", d["id"])
            for l in lines:
                key = str(l["prep_dish_id"])
                usage_by_recipe[key] = usage_by_recipe.get(key, 0) + float(l["qty"] or 0) * sold
        if not usage_by_recipe:
            raise HTTPException(400, "no prep usage found in the saved sales figures")
        usage_rows = []
        for recipe_id, used in usage_by_recipe.items():
            stock = await conn.fetchrow("SELECT * FROM prep_recipe_stock WHERE store_id=$1 AND dish_id=$2", store_id, recipe_id)
            if not stock:
                continue
            new_on_hand = max(0, round(float(stock["on_hand"] or 0) - used, 3))
            await conn.execute("UPDATE prep_recipe_stock SET on_hand=$1 WHERE store_id=$2 AND dish_id=$3", new_on_hand, store_id, recipe_id)
            sub = by_id.get(recipe_id, {})
            usage_rows.append({"recipeId": recipe_id, "name": sub.get("name", ""), "used": round(used, 2),
                               "yieldUOM": sub.get("yield_uom", ""), "remaining": new_on_hand})
        log_row = await conn.fetchrow(
            """INSERT INTO prep_logs (store_id, kind, name, usage, date, created_at)
               VALUES ($1,'sales_usage','Menu sales prep usage',$2,$3,$4) RETURNING *""",
            store_id, usage_rows, _pg_today(), _pg_now_iso())
        return {"prepStock": await _pg_prep_stock_list(conn, store_id), "log": _pg_log_to_api(log_row)}
    finally:
        await db_pg.pool().release(conn)

class PgUseContainerIn(BaseModel):
    recipeId: str
    containerId: str

@pg_router.post("/prep/{store_id}/use-container")
async def pg_use_container(store_id: str, body: PgUseContainerIn):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        stock = await conn.fetchrow("SELECT * FROM prep_recipe_stock WHERE store_id=$1 AND dish_id=$2", store_id, body.recipeId)
        if not stock:
            raise HTTPException(404, "prep stock not found")
        conts = stock["containers"] or []
        target = next((c for c in conts if c.get("id") == body.containerId), None)
        if not target:
            raise HTTPException(404, "container not found")
        remaining = [c for c in conts if c.get("id") != body.containerId]
        new_on_hand = max(0, round(float(stock["on_hand"] or 0) - float(target.get("size") or 0), 3))
        await conn.execute("UPDATE prep_recipe_stock SET on_hand=$1, containers=$2 WHERE store_id=$3 AND dish_id=$4",
                            new_on_hand, remaining, store_id, body.recipeId)
        dish = await conn.fetchrow("SELECT name, yield_uom FROM dishes WHERE id=$1", body.recipeId)
        log_row = await conn.fetchrow(
            """INSERT INTO prep_logs (store_id, kind, dish_id, name, produced, yield_uom, date, created_at)
               VALUES ($1,'container_use',$2,$3,$4,$5,$6,$7) RETURNING *""",
            store_id, body.recipeId, f"{(dish['name'] if dish else '')} — {target.get('label', 'container')} to service",
            -float(target.get("size") or 0), (dish["yield_uom"] if dish else ""), _pg_today(), _pg_now_iso())
        return {"prepStock": await _pg_prep_stock_list(conn, store_id), "log": _pg_log_to_api(log_row)}
    finally:
        await db_pg.pool().release(conn)

# ---------------- Nightly prep count & task workflow (Postgres) ----------------
async def _pg_prep_universe_for_track(conn, store_id, track):
    all_recipes = await conn.fetch("SELECT * FROM dishes WHERE store_id=$1 AND recipe_type='prep'", store_id)
    prep_items = await conn.fetch(
        f"SELECT * FROM prep_items WHERE store_id=$1 AND active=TRUE AND ({_pg_prep_items_track_where(track)})", store_id)
    direct_recipes = [] if track == "bulk" else all_recipes
    all_recipes_by_id = {str(r["id"]): r for r in all_recipes}
    return direct_recipes, prep_items, all_recipes_by_id

async def _pg_get_or_create_session(conn, store_id, date, track):
    count_type = TRACK_TO_COUNT_TYPE.get(track, "nightly_prep")
    s = await conn.fetchrow("SELECT * FROM count_sessions WHERE store_id=$1 AND count_date=$2 AND count_type=$3",
                             store_id, date, count_type)
    if not s:
        s = await conn.fetchrow(
            "INSERT INTO count_sessions (store_id, count_date, count_type, status) VALUES ($1,$2,$3,'open') RETURNING *",
            store_id, date, count_type)
    recipes, prep_items, _ = await _pg_prep_universe_for_track(conn, store_id, track)
    existing_lines = await conn.fetch("SELECT dish_id, prep_item_id FROM count_lines WHERE session_id=$1", s["id"])
    known = {str(l["dish_id"] or l["prep_item_id"]) for l in existing_lines}
    for r in recipes:
        if str(r["id"]) not in known:
            await conn.execute("INSERT INTO count_lines (session_id, dish_id, status) VALUES ($1,$2,'not_counted')", s["id"], r["id"])
    for p in prep_items:
        if str(p["id"]) not in known:
            await conn.execute("INSERT INTO count_lines (session_id, prep_item_id, status) VALUES ($1,$2,'not_counted')", s["id"], p["id"])
    lines = await conn.fetch("SELECT * FROM count_lines WHERE session_id = $1", s["id"])
    entries = [{"recipeId": str(l["dish_id"]) if l["dish_id"] else None,
                "prepItemId": str(l["prep_item_id"]) if l["prep_item_id"] else None,
                "onHand": float(l["qty"]) if l["qty"] is not None else None,
                "note": l["note"] or "", "savedAt": l["updated_at"].isoformat() if l["updated_at"] else None,
                "savedBy": l["saved_by"] or ""} for l in lines]
    return {
        "id": str(s["id"]), "date": s["count_date"].isoformat(), "track": track, "status": s["status"],
        "countedBy": s["counted_by_name"] or "", "entries": entries,
        "submittedAt": s["submitted_at"].isoformat() if s["submitted_at"] else None,
        "recipes": [{"id": str(r["id"]), "name": r["name"], "yieldUOM": r["yield_uom"],
                     "yieldQty": float(r["yield_qty"] or 1), "shelfLife": r["shelf_life"] or "", "prepPar": float(r["prep_par"] or 0)}
                    for r in recipes],
        "prepItems": [{"id": str(p["id"]), "name": p["name"], "vesselName": p["container"] or "vessel",
                       "parVessels": float(p["par_vessels"] or 0), "schedule": p["schedule"]} for p in prep_items],
    }

@pg_router.get("/prepcount/{store_id}/session")
async def pg_get_count_session(store_id: str, date: str = Query(""), track: str = Query("daily")):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        return await _pg_get_or_create_session(conn, store_id, date or _pg_today(), track)
    finally:
        await db_pg.pool().release(conn)

class PgCountEntryIn(BaseModel):
    recipeId: Optional[str] = None
    prepItemId: Optional[str] = None
    onHand: Optional[float] = None
    note: str = ""
    countedBy: str = ""

@pg_router.post("/prepcount/{store_id}/session/{sid}/entry")
async def pg_save_count_entry(store_id: str, sid: str, body: PgCountEntryIn):
    check_store_id(store_id)
    if body.onHand is None:
        raise HTTPException(400, "Blank counts are not saved — enter a number")
    conn = await db_pg.pool().acquire()
    try:
        s = await conn.fetchrow("SELECT * FROM count_sessions WHERE id=$1 AND store_id=$2", sid, store_id)
        if not s:
            raise HTTPException(404, "session not found")
        key_col = "dish_id" if body.recipeId else "prep_item_id"
        key_val = body.recipeId or body.prepItemId
        line = await conn.fetchrow(f"SELECT * FROM count_lines WHERE session_id=$1 AND {key_col}=$2", sid, key_val)
        if not line:
            raise HTTPException(404, "item not in this count list")
        # Revision history (Mongo's archive-then-bump on re-save-after-submit) isn't
        # tracked in Postgres yet -- see docs/SUPABASE_MIGRATION_PLAN.md. Updates in
        # place regardless of session status.
        await conn.execute(
            "UPDATE count_lines SET status='counted', qty=$1, note=$2, saved_by=$3, updated_at=now() WHERE id=$4",
            body.onHand, body.note, body.countedBy, line["id"])
        if body.countedBy:
            await conn.execute("UPDATE count_sessions SET counted_by_name=$1 WHERE id=$2", body.countedBy, sid)
        return {"ok": True, "entry": {"recipeId": body.recipeId, "prepItemId": body.prepItemId, "onHand": body.onHand,
                                       "note": body.note, "savedAt": _pg_now_iso(), "savedBy": body.countedBy}}
    finally:
        await db_pg.pool().release(conn)

@pg_router.post("/prepcount/{store_id}/session/{sid}/submit")
async def pg_submit_count(store_id: str, sid: str, body: dict):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        s = await conn.fetchrow("SELECT * FROM count_sessions WHERE id=$1 AND store_id=$2", sid, store_id)
        if not s:
            raise HTTPException(404, "session not found")
        uncounted = await conn.fetchval("SELECT count(*) FROM count_lines WHERE session_id=$1 AND status='not_counted'", sid)
        if uncounted and not body.get("acknowledgeUncounted"):
            raise HTTPException(409, f"{uncounted} item(s) have no saved count")
        counted_by = body.get("countedBy") or s["counted_by_name"] or ""
        await conn.execute("UPDATE count_sessions SET status='submitted', submitted_at=now(), counted_by_name=$1 WHERE id=$2",
                            counted_by, sid)
        return {"ok": True, "uncounted": uncounted}
    finally:
        await db_pg.pool().release(conn)

@pg_router.get("/prepcount/{store_id}/history")
async def pg_count_history(store_id: str):
    check_store_id(store_id)
    rows = await db_pg.pool().fetch("SELECT * FROM count_sessions WHERE store_id=$1 ORDER BY count_date DESC LIMIT 60", store_id)
    return [{"id": str(r["id"]), "date": r["count_date"].isoformat(), "track": COUNT_TYPE_TO_TRACK.get(r["count_type"], "daily"),
             "status": r["status"], "countedBy": r["counted_by_name"] or "",
             "submittedAt": r["submitted_at"].isoformat() if r["submitted_at"] else None} for r in rows]

# ---------------- Prep lists (Postgres) ----------------
async def _pg_prep_list_to_api(conn, plist):
    lines = await conn.fetch(
        """SELECT pll.*, pi.vessel_capacity AS prep_vessel_capacity, pi.item_code AS prep_item_code
           FROM prep_list_lines pll LEFT JOIN prep_items pi ON pi.id=pll.prep_item_id
           WHERE pll.list_id=$1""", plist["id"])
    tasks = [{
        "id": str(l["id"]), "recipeId": str(l["recipe_id"]) if l["recipe_id"] else None,
        "prepItemId": str(l["prep_item_id"]) if l["prep_item_id"] else None, "taskType": l["task_type"],
        "name": l["name"], "yieldUOM": l["yield_uom"], "yieldQty": float(l["yield_qty"] or 0),
        "par": float(l["par"] or 0), "counted": float(l["on_hand"]) if l["on_hand"] is not None else None,
        "uncounted": l["uncounted"], "neededUnits": float(l["needed_units"] or 0),
        "batchesPlanned": float(l["batches_planned"] or 0), "batchesDone": float(l["batches_done"] or 0),
        "doneBy": l["done_by_name"] or "", "doneAt": l["done_at"].isoformat() if l["done_at"] else None,
        "note": l["note"] or "", "vesselName": l["vessel_name"] or "", "removed": l["removed"],
        "vesselCapacity": float(l["prep_vessel_capacity"] or 0),
        "controlNumber": l["prep_item_code"][len(PG_STORE_TO_RESTAURANT[plist["store_id"]]) + 1:]
        if l["prep_item_code"] and l["prep_item_code"].startswith(PG_STORE_TO_RESTAURANT[plist["store_id"]] + "_") else None,
    } for l in lines]
    return {
        "id": str(plist["id"]), "date": plist["prep_date"].isoformat(),
        "track": COUNT_TYPE_TO_TRACK.get(plist["count_type"], "daily"), "status": plist["status"], "tasks": tasks,
        "releasedAt": plist["released_at"].isoformat() if plist["released_at"] else None,
        "releasedBy": plist["released_by"] or "",
    }

@pg_router.get("/preplists/{store_id}")
async def pg_get_prep_list(store_id: str, date: str = Query(""), track: str = Query("daily")):
    check_store_id(store_id)
    count_type = TRACK_TO_COUNT_TYPE.get(track, "nightly_prep")
    conn = await db_pg.pool().acquire()
    try:
        plist = await conn.fetchrow("SELECT * FROM prep_lists WHERE store_id=$1 AND prep_date=$2 AND count_type=$3",
                                     store_id, date or _pg_today(), count_type)
        return {"list": await _pg_prep_list_to_api(conn, plist) if plist else None}
    finally:
        await db_pg.pool().release(conn)

@pg_router.post("/preplists/{store_id}/generate")
async def pg_generate_prep_list(store_id: str, body: dict):
    check_store_id(store_id)
    date = body.get("date") or _pg_today()
    track = body.get("track") or "daily"
    count_type = TRACK_TO_COUNT_TYPE.get(track, "nightly_prep")
    conn = await db_pg.pool().acquire()
    try:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
                               store_id, f"{date}:{count_type}")
            return await _pg_generate_prep_list_in_transaction(conn, store_id, date, track, count_type)
    finally:
        await db_pg.pool().release(conn)

async def _pg_generate_prep_list_in_transaction(conn, store_id, date, track, count_type):
    existing = await conn.fetchrow("SELECT * FROM prep_lists WHERE store_id=$1 AND prep_date=$2 AND count_type=$3",
                                    store_id, date, count_type)
    if existing:
        return {"list": await _pg_prep_list_to_api(conn, existing), "regenerated": False}
    session = await conn.fetchrow(
        """SELECT * FROM count_sessions WHERE store_id=$1 AND status='submitted' AND count_date<=$2 AND count_type=$3
           ORDER BY count_date DESC LIMIT 1""", store_id, date, count_type)
    if not session:
        raise HTTPException(400, "No submitted evening count yet — submit a prep count first.")
    recipes, prep_items, by_id = await _pg_prep_universe_for_track(conn, store_id, track)
    overrides = await conn.fetch("SELECT * FROM prep_overrides WHERE store_id=$1 AND date=$2", store_id, date)
    removed_ids = {str(o["recipe_id"] or o["prep_item_id"]) for o in overrides
                   if o["type"] == "remove" and (o["recipe_id"] or o["prep_item_id"])}
    par_over, par_note = {}, {}
    for o in overrides:
        if o["type"] == "par":
            k = str(o["recipe_id"] or o["prep_item_id"]) if (o["recipe_id"] or o["prep_item_id"]) else None
            if k:
                par_over[k] = float(o["par"] or 0)
                par_note[k] = o["note"] or ""
    count_lines = await conn.fetch("SELECT * FROM count_lines WHERE session_id=$1", session["id"])
    counted_map = {}
    for l in count_lines:
        k = str(l["dish_id"]) if l["dish_id"] else (str(l["prep_item_id"]) if l["prep_item_id"] else None)
        if k:
            counted_map[k] = l
    governed = {str(p["recipe_id"]) for p in prep_items if p["recipe_id"]}

    def note_for(key, counted):
        parts = []
        if counted is None:
            parts.append("Not counted — planned at full par")
        if key in par_over:
            parts.append(("Par override for this date: " + par_note[key]) if par_note[key] else "Par override for this date")
        return " ".join(parts)

    tasks = []
    for r in recipes:
        rid_s = str(r["id"])
        if rid_s in removed_ids or rid_s in governed:
            continue
        par = par_over.get(rid_s, float(r["prep_par"] or 0))
        line = counted_map.get(rid_s)
        counted = float(line["qty"]) if line and line["qty"] is not None else None
        yield_qty = float(r["yield_qty"] or 1) or 1
        needed = max(0, par - counted) if counted is not None else par
        batches = math.ceil(needed / yield_qty) if needed > 0 and yield_qty > 0 else 0
        tasks.append({"recipe_id": r["id"], "prep_item_id": None, "task_type": "batch", "name": r["name"],
                      "yield_uom": r["yield_uom"], "yield_qty": yield_qty, "par": par, "on_hand": counted,
                      "uncounted": counted is None, "needed_units": round(needed, 2), "batches_planned": batches,
                      "batches_done": 0, "vessel_name": None, "note": note_for(rid_s, counted), "removed": False})
    for p in prep_items:
        pid_s = str(p["id"])
        if pid_s in removed_ids or (p["schedule"] or "daily") != "daily":
            continue
        line = counted_map.get(pid_s)
        counted = float(line["qty"]) if line and line["qty"] is not None else None
        note = note_for(pid_s, counted)
        if p["recipe_id"]:
            r = by_id.get(str(p["recipe_id"]))
            if not r:
                continue
            item_par = float(p["par_weekday"] or 0)
            default_par = item_par if item_par > 0 else float(r["prep_par"] or 0)
            par = par_over.get(pid_s, default_par)
            yield_qty = float(r["yield_qty"] or 1) or 1
            needed = max(0, par - counted) if counted is not None else par
            batches = math.ceil(needed / yield_qty) if needed > 0 and yield_qty > 0 else 0
            vn = p["container"] or ""
            tasks.append({"recipe_id": r["id"], "prep_item_id": p["id"], "task_type": "batch",
                          "name": p["name"] or r["name"], "yield_uom": r["yield_uom"], "yield_qty": yield_qty,
                          "par": par, "on_hand": counted, "uncounted": counted is None, "needed_units": round(needed, 2),
                          "batches_planned": batches, "batches_done": 0, "vessel_name": vn,
                          "note": ((f"Portion into {vn}. " if vn else "") + note).strip(), "removed": False})
        else:
            par = par_over.get(pid_s, float(p["par_vessels"] or 0))
            needed = max(0, par - counted) if counted is not None else par
            vessels = math.ceil(needed * 2) / 2 if needed > 0 else 0
            tasks.append({"recipe_id": None, "prep_item_id": p["id"], "task_type": "vessel", "name": p["name"],
                          "yield_uom": p["container"] or "vessel", "yield_qty": 1, "par": par, "on_hand": counted,
                          "uncounted": counted is None, "needed_units": round(needed, 2), "batches_planned": vessels,
                          "batches_done": 0, "vessel_name": p["container"], "note": note, "removed": False})
    for o in overrides:
        if o["type"] != "add":
            continue
        r = by_id.get(str(o["recipe_id"])) if o["recipe_id"] else None
        if o["recipe_id"] and not r:
            continue
        tasks.append({"recipe_id": r["id"] if r else None, "prep_item_id": None, "task_type": "batch",
                      "name": (r["name"] + " (one-off)") if r else (o["custom_name"] or "One-off item"),
                      "yield_uom": (r["yield_uom"] if r else "batch"), "yield_qty": float((r["yield_qty"] if r else 1) or 1),
                      "par": 0, "on_hand": None, "uncounted": False, "needed_units": 0,
                      "batches_planned": float(o["batches"] or 1) or 1, "batches_done": 0, "vessel_name": None,
                      "note": ("One-off add: " + (o["note"] or "")).strip(), "removed": False})

    plist = await conn.fetchrow(
        """INSERT INTO prep_lists (store_id, prep_date, from_count, status, count_type, created_at)
           VALUES ($1,$2,$3,'draft',$4,$5) RETURNING *""",
        store_id, date, session["id"], count_type, _pg_now_iso())
    for t in tasks:
        await conn.execute(
            """INSERT INTO prep_list_lines (list_id, prep_item_id, recipe_id, task_type, name, yield_uom, yield_qty,
                   par, on_hand, uncounted, needed_units, batches_planned, batches_done, vessel_name, note, done, removed)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,FALSE,$16)""",
            plist["id"], t["prep_item_id"], t["recipe_id"], t["task_type"], t["name"], t["yield_uom"], t["yield_qty"],
            t["par"], t["on_hand"], t["uncounted"], t["needed_units"], t["batches_planned"], t["batches_done"],
            t["vessel_name"], t["note"], t["removed"])
    return {"list": await _pg_prep_list_to_api(conn, plist), "regenerated": True}

class PgPrepListUpdateIn(BaseModel):
    tasks: List[dict]

@pg_router.put("/preplists/{store_id}/{list_id}")
async def pg_update_prep_list(store_id: str, list_id: str, body: PgPrepListUpdateIn):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        plist = await conn.fetchrow("SELECT * FROM prep_lists WHERE id=$1 AND store_id=$2", list_id, store_id)
        if not plist:
            raise HTTPException(404, "prep list not found")
        if plist["status"] != "draft":
            raise HTTPException(400, "Only draft lists can be edited")
        async with conn.transaction():
            await conn.execute("DELETE FROM prep_list_lines WHERE list_id=$1", list_id)
            for t in body.tasks:
                batches_planned = f(t.get("batchesPlanned"))
                batches_done = f(t.get("batchesDone"))
                await conn.execute(
                    """INSERT INTO prep_list_lines (list_id, prep_item_id, recipe_id, task_type, name, yield_uom, yield_qty,
                           par, on_hand, uncounted, needed_units, batches_planned, batches_done, vessel_name, note, done,
                           done_by_name, done_at, removed)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)""",
                    list_id, t.get("prepItemId"), t.get("recipeId"), t.get("taskType", "batch"), t.get("name"),
                    t.get("yieldUOM"), t.get("yieldQty"), t.get("par"), t.get("counted"), bool(t.get("uncounted", False)),
                    t.get("neededUnits"), batches_planned, batches_done, t.get("vesselName"), t.get("note"),
                    bool(batches_planned > 0 and batches_done >= batches_planned), t.get("doneBy"), t.get("doneAt"),
                    bool(t.get("removed", False)))
        return {"ok": True}
    finally:
        await db_pg.pool().release(conn)

@pg_router.post("/preplists/{store_id}/{list_id}/release")
async def pg_release_prep_list(store_id: str, list_id: str, body: dict):
    check_store_id(store_id)
    row = await db_pg.pool().fetchrow(
        "UPDATE prep_lists SET status='released', released_at=now(), released_by=$3 WHERE id=$1 AND store_id=$2 RETURNING id",
        list_id, store_id, body.get("releasedBy", ""))
    if not row:
        raise HTTPException(404, "prep list not found")
    return {"ok": True}

async def _pg_complete_task_core(conn, store_id, list_id, task_id, batches, done_by, containers):
    plist = await conn.fetchrow("SELECT * FROM prep_lists WHERE id=$1 AND store_id=$2 FOR UPDATE", list_id, store_id)
    if not plist:
        raise HTTPException(404, "prep list not found")
    if plist["status"] != "released":
        raise HTTPException(400, "The list must be released before tasks can be completed")
    task = await conn.fetchrow("SELECT * FROM prep_list_lines WHERE id=$1 AND list_id=$2 FOR UPDATE", task_id, list_id)
    if not task:
        raise HTTPException(404, "task not found")
    remaining = float(task["batches_planned"] or 0) - float(task["batches_done"] or 0)
    if batches <= 0 or batches > remaining + 1e-9:
        raise HTTPException(400, f"batches must be between 0 and {remaining:g} remaining")
    result = {}
    if task["recipe_id"]:
        recipe = await conn.fetchrow("SELECT * FROM dishes WHERE id=$1", task["recipe_id"])
        if recipe:
            result = await _pg_deduct_and_stock(conn, store_id, recipe, batches, containers, "batch", f"{task['name']} — prep task")
    elif task["prep_item_id"]:
        pitem = await conn.fetchrow("SELECT * FROM prep_items WHERE id=$1", task["prep_item_id"])
        if pitem:
            result = await _pg_deduct_item_and_stock(conn, store_id, pitem, batches)
    new_done = round(float(task["batches_done"] or 0) + batches, 3)
    await conn.execute("UPDATE prep_list_lines SET batches_done=$1, done_by_name=$2, done_at=now() WHERE id=$3",
                        new_done, done_by, task_id)
    return {"list": await _pg_prep_list_to_api(conn, plist), **result}

class PgTaskCompleteIn(BaseModel):
    batches: float
    doneBy: str = ""
    containers: List[PgContainerIn] = []

@pg_router.post("/preplists/{store_id}/{list_id}/task/{task_id}/complete")
async def pg_complete_task(store_id: str, list_id: str, task_id: str, body: PgTaskCompleteIn):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        async with conn.transaction():
            return await _pg_complete_task_core(conn, store_id, list_id, task_id, body.batches, body.doneBy,
                                                 [c.model_dump() for c in body.containers])
    finally:
        await db_pg.pool().release(conn)

@pg_router.post("/preplists/{store_id}/{list_id}/add-item")
async def pg_add_item_to_list(store_id: str, list_id: str, body: dict):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        plist = await conn.fetchrow("SELECT * FROM prep_lists WHERE id=$1 AND store_id=$2", list_id, store_id)
        if not plist:
            raise HTTPException(404, "prep list not found")
        pitem = await conn.fetchrow("SELECT * FROM prep_items WHERE id=$1 AND store_id=$2", body.get("prepItemId"), store_id)
        if not pitem:
            raise HTTPException(404, "prep item not found")
        dup = await conn.fetchrow("SELECT 1 FROM prep_list_lines WHERE list_id=$1 AND prep_item_id=$2", list_id, pitem["id"])
        if dup:
            raise HTTPException(400, "That item is already on this day's list")
        qty = f(body.get("qty"), 0)
        note = ("One-off add: " + (body.get("note") or "")).strip()
        if pitem["recipe_id"]:
            r = await conn.fetchrow("SELECT * FROM dishes WHERE id=$1", pitem["recipe_id"])
            if not r:
                raise HTTPException(404, "linked prep recipe not found")
            await conn.execute(
                """INSERT INTO prep_list_lines (list_id, prep_item_id, recipe_id, task_type, name, yield_uom, yield_qty,
                       par, batches_planned, batches_done, vessel_name, note, done, removed)
                   VALUES ($1,$2,$3,'batch',$4,$5,$6,0,$7,0,$8,$9,FALSE,FALSE)""",
                list_id, pitem["id"], r["id"], pitem["name"] or r["name"], r["yield_uom"], float(r["yield_qty"] or 1) or 1,
                qty or 1, pitem["container"], note)
        else:
            await conn.execute(
                """INSERT INTO prep_list_lines (list_id, prep_item_id, recipe_id, task_type, name, yield_uom, yield_qty,
                       par, batches_planned, batches_done, vessel_name, note, done, removed)
                   VALUES ($1,$2,NULL,'vessel',$3,$4,1,0,$5,0,$6,$7,FALSE,FALSE)""",
                list_id, pitem["id"], pitem["name"], pitem["container"] or "vessel",
                qty or float(pitem["par_vessels"] or 1) or 1, pitem["container"], note)
        return {"list": await _pg_prep_list_to_api(conn, plist)}
    finally:
        await db_pg.pool().release(conn)

# ---------------- Standing prep items catalog (Postgres) ----------------
class PgPrepItemIn(BaseModel):
    name: str
    sourceType: str
    itemCode: Optional[str] = None
    recipeId: Optional[str] = None
    vesselName: str = "1/6 Pan"
    vesselCapacity: float = 0
    parVessels: float = 0
    schedule: str = "daily"
    note: str = ""
    track: str = "daily"
    par: float = 0

def _pg_prep_item_to_api(row, store_id):
    item_code = row["item_code"]
    code_prefix = PG_STORE_TO_RESTAURANT[store_id] + "_"
    return {"id": str(row["id"]), "name": row["name"], "sourceType": "item" if row["item_code"] else "prep",
            "controlNumber": item_code[len(code_prefix):] if item_code and item_code.startswith(code_prefix) else item_code,
            "recipeId": str(row["recipe_id"]) if row["recipe_id"] else None,
            "vesselName": row["container"] or "", "vesselCapacity": float(row["vessel_capacity"] or 0),
            "parVessels": float(row["par_vessels"] or 0), "schedule": row["schedule"],
            "track": "daily" if (row["made_at"] is None or row["made_at"] == row["store_id"]) else "bulk",
            "note": row["note"] or "", "par": float(row["par_weekday"] or 0), "active": row["active"]}

@pg_router.get("/prep-items/{store_id}")
async def pg_list_prep_items(store_id: str, track: Optional[str] = Query(None)):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        if track:
            rows = await conn.fetch(f"SELECT * FROM prep_items WHERE store_id=$1 AND ({_pg_prep_items_track_where(track)})", store_id)
        else:
            rows = await conn.fetch("SELECT * FROM prep_items WHERE store_id=$1", store_id)
        return [_pg_prep_item_to_api(r, store_id) for r in rows]
    finally:
        await db_pg.pool().release(conn)

async def _pg_validate_prep_item(conn, store_id, body):
    if body.sourceType not in ("item", "prep"):
        raise HTTPException(400, "sourceType must be item or prep")
    if body.schedule not in ("daily", "oneoff"):
        raise HTTPException(400, "schedule must be daily or oneoff")
    if body.track not in ("daily", "bulk"):
        raise HTTPException(400, "track must be daily or bulk")
    if body.sourceType == "item":
        if not await conn.fetchrow("SELECT 1 FROM store_items WHERE store_id=$1 AND item_code=$2", store_id, body.itemCode):
            raise HTTPException(404, "inventory item not found")
    elif not await conn.fetchrow(
            "SELECT 1 FROM dishes WHERE id=$1 AND store_id=$2 AND recipe_type='prep'", body.recipeId, store_id):
        raise HTTPException(404, "prep recipe not found")

@pg_router.post("/prep-items/{store_id}")
async def pg_create_prep_item(store_id: str, body: PgPrepItemIn):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        await _pg_validate_prep_item(conn, store_id, body)
        made_at = "comm" if body.track == "bulk" else store_id
        row = await conn.fetchrow(
            """INSERT INTO prep_items (store_id, name, item_code, recipe_id, container, vessel_capacity, par_vessels,
                   schedule, note, made_at, par_weekday, par_weekend, active)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$11,TRUE) RETURNING *""",
            store_id, body.name, body.itemCode if body.sourceType == "item" else None,
            body.recipeId if body.sourceType == "prep" else None, body.vesselName, body.vesselCapacity,
            body.parVessels, body.schedule, body.note, made_at, body.par)
        return _pg_prep_item_to_api(row, store_id)
    finally:
        await db_pg.pool().release(conn)

@pg_router.put("/prep-items/{store_id}/{pid}")
async def pg_update_prep_item(store_id: str, pid: str, body: PgPrepItemIn):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        await _pg_validate_prep_item(conn, store_id, body)
        made_at = "comm" if body.track == "bulk" else store_id
        row = await conn.fetchrow(
            """UPDATE prep_items SET name=$3, item_code=$4, recipe_id=$5, container=$6, vessel_capacity=$7,
                   par_vessels=$8, schedule=$9, note=$10, made_at=$11, par_weekday=$12, par_weekend=$12
               WHERE id=$1 AND store_id=$2 RETURNING *""",
            pid, store_id, body.name, body.itemCode if body.sourceType == "item" else None,
            body.recipeId if body.sourceType == "prep" else None, body.vesselName, body.vesselCapacity,
            body.parVessels, body.schedule, body.note, made_at, body.par)
        if not row:
            raise HTTPException(404, "prep item not found")
        return {"ok": True}
    finally:
        await db_pg.pool().release(conn)

@pg_router.delete("/prep-items/{store_id}/{pid}")
async def pg_delete_prep_item(store_id: str, pid: str):
    check_store_id(store_id)
    await db_pg.pool().execute("DELETE FROM prep_items WHERE id=$1 AND store_id=$2", pid, store_id)
    return {"ok": True}

# ---------------- Day overrides (Postgres) ----------------
class PgOverrideIn(BaseModel):
    date: str
    type: str
    recipeId: Optional[str] = None
    prepItemId: Optional[str] = None
    customName: str = ""
    par: Optional[float] = None
    batches: Optional[float] = None
    note: str = ""
    createdBy: str = ""

def _pg_override_to_api(row):
    return {"id": str(row["id"]), "date": row["date"].isoformat(), "type": row["type"],
            "recipeId": str(row["recipe_id"]) if row["recipe_id"] else None,
            "prepItemId": str(row["prep_item_id"]) if row["prep_item_id"] else None,
            "customName": row["custom_name"] or "", "par": float(row["par"]) if row["par"] is not None else None,
            "batches": float(row["batches"]) if row["batches"] is not None else None,
            "note": row["note"] or "", "createdBy": row["created_by"] or ""}

@pg_router.get("/prep-overrides/{store_id}")
async def pg_list_overrides(store_id: str, date: str = Query("")):
    check_store_id(store_id)
    conn = await db_pg.pool().acquire()
    try:
        if date:
            rows = await conn.fetch("SELECT * FROM prep_overrides WHERE store_id=$1 AND date=$2 ORDER BY date DESC", store_id, date)
        else:
            rows = await conn.fetch("SELECT * FROM prep_overrides WHERE store_id=$1 ORDER BY date DESC LIMIT 500", store_id)
        return [_pg_override_to_api(r) for r in rows]
    finally:
        await db_pg.pool().release(conn)

@pg_router.post("/prep-overrides/{store_id}")
async def pg_add_override(store_id: str, body: PgOverrideIn):
    check_store_id(store_id)
    if body.type not in ("add", "par", "remove"):
        raise HTTPException(400, "type must be add, par, or remove")
    row = await db_pg.pool().fetchrow(
        """INSERT INTO prep_overrides (store_id, date, type, recipe_id, prep_item_id, custom_name, par, batches, note, created_by)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *""",
        store_id, body.date, body.type, body.recipeId, body.prepItemId, body.customName, body.par, body.batches,
        body.note, body.createdBy)
    return _pg_override_to_api(row)

@pg_router.delete("/prep-overrides/{store_id}/{oid}")
async def pg_delete_override(store_id: str, oid: str):
    check_store_id(store_id)
    await db_pg.pool().execute("DELETE FROM prep_overrides WHERE id=$1 AND store_id=$2", oid, store_id)
    return {"ok": True}

app.include_router(api_router)
app.include_router(pg_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_pg_pool():
    await db.state_versions.create_index("restaurantId", unique=True)
    await db_pg.init_pool()

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
    await db_pg.close_pool()
