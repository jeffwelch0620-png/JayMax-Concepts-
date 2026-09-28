"""Backend tests for restaurant inventory & food-costing app."""
import os
import copy
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to reading frontend .env
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s(auth_headers):
    sess = requests.Session()
    sess.headers.update(auth_headers)
    return sess


# ---------- Health ----------
def test_health(s):
    r = s.get(f"{API}/health", timeout=30)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------- Per-restaurant state ----------
@pytest.mark.parametrize("rid,expected_cn_or_name", [
    ("berts", "PR-001"),
    ("rudds", "Pie"),
    ("papa_leonis", "Pizza"),
])
def test_state_per_location(s, rid, expected_cn_or_name):
    r = s.get(f"{API}/state/{rid}", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data and "dishes" in data and "purchases" in data
    assert len(data["items"]) >= 1
    if rid == "berts":
        cns = [i["controlNumber"] for i in data["items"]]
        assert "PR-001" in cns
        assert len(data["items"]) >= 8
        names = [i["name"] for i in data["items"]]
        assert any("Ground Beef" in n for n in names)
    if rid == "rudds":
        names = " ".join(i["name"] for i in data["items"])
        assert "Pie" in names or "Potato" in names
    if rid == "papa_leonis":
        names = " ".join(i["name"] for i in data["items"])
        assert "Pizza" in names or "Pepperoni" in names or "Mozzarella" in names


def test_state_unknown_rid(s):
    r = s.get(f"{API}/state/unknown", timeout=30)
    assert r.status_code == 404


# ---------- Owner summary ----------
def test_owner_summary(s):
    r = s.get(f"{API}/owner/summary", timeout=60)
    assert r.status_code == 200
    data = r.json()
    assert "stores" in data and "totals" in data
    assert len(data["stores"]) == 3
    for st in data["stores"]:
        for k in ("inventoryValue", "orderAlerts", "spend30", "avgFoodCost", "topCostDishes"):
            assert k in st
    for k in ("inventoryValue", "orderAlerts", "spend30"):
        assert k in data["totals"]


# ---------- Persistence: read-modify-write items for berts ----------
def test_items_persistence_roundtrip(s):
    state = s.get(f"{API}/state/berts", timeout=30).json()
    items = copy.deepcopy(state["items"])
    assert items, "no items"
    # pick SB-001 to modify (not PR-001 to avoid interfering with prep smoke test note)
    target = next((i for i in items if i["controlNumber"] == "SB-001"), items[0])
    original = target["currentStock"]
    target["currentStock"] = 99.0

    r = s.put(f"{API}/state/berts/items", json=items, timeout=30)
    assert r.status_code == 200
    assert r.json().get("ok") is True

    # Verify
    after = s.get(f"{API}/state/berts", timeout=30).json()
    got = next(i for i in after["items"] if i["controlNumber"] == target["controlNumber"])
    assert float(got["currentStock"]) == 99.0

    # Restore
    for it in items:
        if it["controlNumber"] == target["controlNumber"]:
            it["currentStock"] = original
    r2 = s.put(f"{API}/state/berts/items", json=items, timeout=30)
    assert r2.status_code == 200


# ---------- Prep flow on rudds ----------
def test_prep_flow_rudds(s):
    state = s.get(f"{API}/state/rudds", timeout=30).json()
    prep_recipe = next((d for d in state["dishes"] if d.get("recipeType") == "prep"), None)
    assert prep_recipe, "no prep recipe seeded for rudds"
    recipe_id = prep_recipe["id"]

    # capture beef stock before
    item_wi002 = next(i for i in state["items"] if i["controlNumber"] == "WI-002")
    beef_before = float(item_wi002["currentStock"])

    # 1) complete
    body = {"recipeId": recipe_id, "batches": 1,
            "containers": [{"label": "Hotel pan", "size": 64, "count": 5}]}
    r = s.post(f"{API}/prep/rudds/complete", json=body, timeout=30)
    assert r.status_code == 200, r.text
    resp = r.json()
    assert "items" in resp and "prepStock" in resp and "log" in resp
    # verify beef reduced
    new_wi002 = next(i for i in resp["items"] if i["controlNumber"] == "WI-002")
    assert float(new_wi002["currentStock"]) < beef_before

    # locate prep stock and containers
    ps = next(p for p in resp["prepStock"] if p["recipeId"] == recipe_id)
    on_hand_after_complete = float(ps["onHand"])
    assert on_hand_after_complete > 0
    assert len(ps["containers"]) >= 1

    # 2) use-container: remove one
    cont_id = ps["containers"][0]["id"]
    cont_size = float(ps["containers"][0]["size"])
    r2 = s.post(f"{API}/prep/rudds/use-container",
                json={"recipeId": recipe_id, "containerId": cont_id}, timeout=30)
    assert r2.status_code == 200, r2.text
    ps2 = next(p for p in r2.json()["prepStock"] if p["recipeId"] == recipe_id)
    assert float(ps2["onHand"]) == max(0, round(on_hand_after_complete - cont_size, 3))
    assert all(c["id"] != cont_id for c in ps2["containers"])

    # 3) apply-sales
    menu_dish = next(d for d in state["dishes"] if d.get("recipeType") != "prep"
                     and any(l.get("sourceType") == "prep" and l.get("recipeId") == recipe_id
                             for l in d.get("lines", [])))
    before_on_hand = float(ps2["onHand"])
    r3 = s.post(f"{API}/prep/rudds/apply-sales",
                json={"dishSales": {menu_dish["id"]: 10}}, timeout=30)
    assert r3.status_code == 200, r3.text
    ps3 = next(p for p in r3.json()["prepStock"] if p["recipeId"] == recipe_id)
    assert float(ps3["onHand"]) < before_on_hand


def test_prep_complete_bad_recipe(s):
    r = s.post(f"{API}/prep/rudds/complete",
               json={"recipeId": "does_not_exist", "batches": 1, "containers": []}, timeout=30)
    assert r.status_code == 404
