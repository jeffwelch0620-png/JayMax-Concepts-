"""Pytest for new PO features: apply-prices + vendor-scorecard trend fields."""
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
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def state(api):
    r = api.get(f"{BASE_URL}/api/state/{RID}", timeout=30)
    assert r.status_code == 200
    return r.json()


# --- Vendor scorecard trend fields ---
class TestScorecardTrends:
    def test_scorecard_includes_trend_fields(self, api):
        r = api.get(f"{BASE_URL}/api/owner/vendor-scorecard", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0
        for row in rows:
            assert "leadTrend" in row, f"missing leadTrend in {row}"
            assert "priceVarTrend" in row, f"missing priceVarTrend in {row}"
            for f in ("leadTrend", "priceVarTrend"):
                assert row[f] in (None, "up", "down", "flat"), f"bad {f}={row[f]}"


# --- Apply prices endpoint ---
class TestApplyPrices:
    def test_apply_prices_updates_item_vendor_sku(self, api, state):
        # Find a received PO on rudds with flagged price discrepancy
        orders = api.get(f"{BASE_URL}/api/orders/{RID}", timeout=30).json()
        target = None
        for po in orders:
            if po.get("status") != "received":
                continue
            rm = po.get("receiptMatch") or {}
            if not rm.get("invoiceFound"):
                continue
            flagged = [l for l in rm.get("lines", []) if l.get("flagged") and l.get("invoiceUnitCost")]
            if flagged:
                target = (po, flagged[0])
                break
        assert target, "no received PO with flagged price discrepancy on rudds"
        po, line = target
        cn = line["controlNumber"]
        vendor = po["vendor"]
        invoice_cost = float(line["invoiceUnitCost"])

        # Capture current item vendorSku price
        st = api.get(f"{BASE_URL}/api/state/{RID}").json()
        item = next(i for i in st["items"] if i["controlNumber"] == cn)
        skus = item.get("vendorSkus") or []
        sku_before = next((sk for sk in skus if sk.get("vendor") == vendor), None) or skus[0]
        before_price = sku_before.get("price")

        # Call apply-prices
        r = api.post(
            f"{BASE_URL}/api/orders/{RID}/{po['id']}/apply-prices",
            json={"lines": [{"controlNumber": cn, "unitCost": invoice_cost}]},
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("updated") >= 1

        # Verify persistence: GET /api/state and check item vendorSku
        st2 = api.get(f"{BASE_URL}/api/state/{RID}").json()
        item2 = next(i for i in st2["items"] if i["controlNumber"] == cn)
        skus2 = item2.get("vendorSkus") or []
        sku_after = next((sk for sk in skus2 if sk.get("vendor") == vendor), None) or skus2[0]
        assert abs(float(sku_after["price"]) - round(invoice_cost, 4)) < 0.001, (
            f"price not updated: was {before_price}, now {sku_after.get('price')}, expected {invoice_cost}"
        )
        assert sku_after.get("priceSource") == "invoice"
        assert sku_after.get("priceUpdatedAt")

    def test_apply_prices_empty_lines_ok(self, api):
        orders = api.get(f"{BASE_URL}/api/orders/{RID}").json()
        po = next((p for p in orders if p.get("status") == "received"), None)
        assert po
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{po['id']}/apply-prices", json={"lines": []})
        assert r.status_code == 200
        assert r.json().get("updated") == 0

    def test_apply_prices_404_unknown_order(self, api):
        r = api.post(f"{BASE_URL}/api/orders/{RID}/does-not-exist-zz/apply-prices",
                     json={"lines": []})
        assert r.status_code == 404

    def test_apply_prices_skips_invalid_lines(self, api):
        orders = api.get(f"{BASE_URL}/api/orders/{RID}").json()
        po = next((p for p in orders if p.get("status") == "received"), None)
        assert po
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{po['id']}/apply-prices",
                     json={"lines": [{"controlNumber": "", "unitCost": 5},
                                     {"controlNumber": "FAKE-CN-ZZ", "unitCost": 0}]})
        assert r.status_code == 200
        assert r.json().get("updated") == 0
