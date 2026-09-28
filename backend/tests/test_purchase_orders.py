"""End-to-end pytest for Purchase Orders approval-chain module (rudds)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as _f:
        for _l in _f:
            if _l.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = _l.split("=", 1)[1].strip().rstrip("/")
RID = "rudds"


@pytest.fixture(scope="module")
def api(auth_headers):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", **auth_headers})
    # Ensure state seeded
    r = s.get(f"{BASE_URL}/api/state/{RID}", timeout=30)
    assert r.status_code == 200
    return s


@pytest.fixture(scope="module")
def sample_item(api):
    """Pick an existing item to receive against."""
    r = api.get(f"{BASE_URL}/api/state/{RID}", timeout=30)
    items = r.json().get("items", [])
    assert items, "no items in rudds"
    return items[0]


def _create_draft(api, sample_item, qty=2):
    payload = {
        "vendor": "TEST_Vendor",
        "createdBy": "TEST_manager",
        "note": "pytest po",
        "lines": [{
            "controlNumber": sample_item["controlNumber"],
            "name": sample_item.get("name", "x"),
            "vendorSku": "TESTSKU-1",
            "qty": qty,
            "purchaseUnit": sample_item.get("purchaseUnit", "case"),
            "unitCost": 12.5,
        }],
    }
    r = api.post(f"{BASE_URL}/api/orders/{RID}", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    po = r.json()
    assert po["status"] == "draft"
    assert po["total"] == round(qty * 12.5, 2)
    return po


class TestPOFlow:
    def test_create_and_list(self, api, sample_item):
        po = _create_draft(api, sample_item)
        r = api.get(f"{BASE_URL}/api/orders/{RID}", timeout=15)
        assert r.status_code == 200
        ids = [p["id"] for p in r.json()]
        assert po["id"] in ids
        # cleanup
        api.delete(f"{BASE_URL}/api/orders/{RID}/{po['id']}")

    def test_full_approval_and_receive_adds_stock(self, api, sample_item):
        # snapshot stock
        state0 = api.get(f"{BASE_URL}/api/state/{RID}").json()
        it0 = next(i for i in state0["items"] if i["controlNumber"] == sample_item["controlNumber"])
        stock_before = float(it0.get("currentStock") or 0)

        po = _create_draft(api, sample_item, qty=3)
        oid = po["id"]

        # submit
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/submit", json={"by": "TEST_mgr"})
        assert r.status_code == 200
        assert r.json()["status"] == "pending"

        # owner endpoint sees it
        r = api.get(f"{BASE_URL}/api/owner/orders")
        assert r.status_code == 200
        assert any(p["id"] == oid for p in r.json())

        # approve
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/approve", json={"by": "TEST_owner"})
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

        # send
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/send", json={"by": "TEST_mgr"})
        assert r.status_code == 200
        assert r.json()["status"] == "sent"

        # receive
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/receive", json={
            "by": "TEST_mgr",
            "lines": [{"controlNumber": sample_item["controlNumber"], "receivedQty": 3}],
        })
        assert r.status_code == 200
        assert r.json()["status"] == "received"

        # verify inventory increased by 3
        state1 = api.get(f"{BASE_URL}/api/state/{RID}").json()
        it1 = next(i for i in state1["items"] if i["controlNumber"] == sample_item["controlNumber"])
        stock_after = float(it1.get("currentStock") or 0)
        assert round(stock_after - stock_before, 3) == 3.0, f"expected +3, before={stock_before}, after={stock_after}"

    def test_reject_and_reopen(self, api, sample_item):
        po = _create_draft(api, sample_item)
        oid = po["id"]
        api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/submit", json={"by": "m"})
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/reject", json={"by": "o", "reason": "TEST_reason_over_budget"})
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "rejected"
        assert j["rejectedReason"] == "TEST_reason_over_budget"

        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/reopen", json={"by": "m"})
        assert r.status_code == 200
        assert r.json()["status"] == "draft"

        # cleanup
        api.delete(f"{BASE_URL}/api/orders/{RID}/{oid}")

    def test_illegal_transitions(self, api, sample_item):
        po = _create_draft(api, sample_item)
        oid = po["id"]
        # can't approve a draft
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/approve", json={"by": "o"})
        assert r.status_code == 400
        # can't receive a draft
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/receive", json={})
        assert r.status_code == 400
        # delete draft ok
        r = api.delete(f"{BASE_URL}/api/orders/{RID}/{oid}")
        assert r.status_code == 200

    def test_submit_empty_order_fails(self, api):
        r = api.post(f"{BASE_URL}/api/orders/{RID}", json={"vendor": "TEST_Empty", "lines": []})
        assert r.status_code == 200
        oid = r.json()["id"]
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/submit", json={})
        assert r.status_code == 400
        api.delete(f"{BASE_URL}/api/orders/{RID}/{oid}")
