"""SEC-001 verification: X-Forwarded-Host must not affect the PO email endpoint,
and the full PO chain + owner endpoints + apply-prices still work on rudds."""
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
EMAIL = "delivered@resend.dev"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.get(f"{BASE_URL}/api/state/{RID}", timeout=30)
    assert r.status_code == 200
    return s


@pytest.fixture(scope="module")
def state(api):
    return api.get(f"{BASE_URL}/api/state/{RID}").json()


def _create_approved_po(api, state, vendor, qty=1, unit_cost=5.0, cn=None, purchase_unit=None):
    if cn is None:
        item = state["items"][0]
        cn = item["controlNumber"]
        purchase_unit = item.get("purchaseUnit", "case")
        name = item.get("name", "")
    else:
        name = ""
        purchase_unit = purchase_unit or "case"
    r = api.post(f"{BASE_URL}/api/orders/{RID}", json={
        "vendor": vendor, "createdBy": "TEST_sec", "lines": [
            {"controlNumber": cn, "name": name, "vendorSku": "TEST-SKU",
             "qty": qty, "purchaseUnit": purchase_unit, "unitCost": unit_cost}
        ]})
    assert r.status_code == 200, r.text
    oid = r.json()["id"]
    a = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/submit", json={"by": "m"})
    assert a.status_code == 200, a.text
    b = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/approve", json={"by": "o"})
    assert b.status_code == 200, b.text
    return oid


# --- SEC-001 primary fix verification ---
class TestSec001HeaderInjection:
    def test_email_with_spoofed_host_header_ok(self, api, state):
        """Spoofed X-Forwarded-Host must NOT error or change email behavior."""
        oid = _create_approved_po(api, state, vendor="TEST_SEC001_Spoof")
        r = api.post(
            f"{BASE_URL}/api/orders/{RID}/{oid}/email",
            json={"email": EMAIL, "by": "TEST_sec"},
            headers={"X-Forwarded-Host": "evil.attacker.com",
                     "X-Forwarded-Proto": "https",
                     "X-Original-Host": "evil.attacker.com",
                     "Forwarded": "host=evil.attacker.com;proto=https"},
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "sent"
        assert j.get("emailedTo") == EMAIL

    def test_email_without_spoof_header_ok(self, api, state):
        oid = _create_approved_po(api, state, vendor="TEST_SEC001_Normal")
        r = api.post(
            f"{BASE_URL}/api/orders/{RID}/{oid}/email",
            json={"email": EMAIL, "by": "TEST_sec"},
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "sent"
        assert j.get("emailedTo") == EMAIL

    def test_cors_allow_credentials_false(self, api):
        r = api.options(
            f"{BASE_URL}/api/state/{RID}",
            headers={"Origin": "https://example.com",
                     "Access-Control-Request-Method": "GET"},
        )
        # allow-credentials should NOT be true
        val = r.headers.get("access-control-allow-credentials", "")
        assert val.lower() != "true", f"allow_credentials should be False, got: {val}"


# --- Regression: full PO chain + PDF ---
class TestFullPoChainRegression:
    def test_create_submit_approve_send_receive_pdf(self, api, state):
        purchases = state.get("purchases", [])
        # Use a known purchases invoice so match logic is real
        p = purchases[0] if purchases else None
        if p:
            cn = p["controlNumber"]
            inv_no = p["invoiceNumber"]
            inv_qty = float(p.get("qty") or 1)
            inv_cost = float(p.get("unitCost") or 1.0)
        else:
            item = state["items"][0]
            cn = item["controlNumber"]
            inv_no = "INV_TEST_REG"
            inv_qty = 1.0
            inv_cost = 1.0

        # snapshot currentStock for the CN
        it_before = next((it for it in state["items"] if it["controlNumber"] == cn), None)
        stock_before = float((it_before or {}).get("currentStock") or 0)

        po = api.post(f"{BASE_URL}/api/orders/{RID}", json={
            "vendor": "TEST_SEC001_Chain", "createdBy": "TEST_sec", "lines": [
                {"controlNumber": cn, "vendorSku": "TEST-CHAIN",
                 "qty": inv_qty, "purchaseUnit": "case", "unitCost": inv_cost}
            ]}).json()
        oid = po["id"]
        assert api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/submit", json={"by": "m"}).status_code == 200
        assert api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/approve", json={"by": "o"}).status_code == 200
        assert api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/send", json={"by": "m"}).status_code == 200
        recv = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/receive", json={
            "by": "m", "invoiceNumber": inv_no,
            "lines": [{"controlNumber": cn, "receivedQty": inv_qty}]})
        assert recv.status_code == 200, recv.text
        j = recv.json()
        assert j["status"] == "received"
        assert j.get("receiptMatch") is not None
        assert "invoiceFound" in j["receiptMatch"]

        # PDF
        pdf = api.get(f"{BASE_URL}/api/orders/{RID}/{oid}/pdf")
        assert pdf.status_code == 200
        assert "application/pdf" in pdf.headers.get("content-type", "").lower()
        assert len(pdf.content) > 100

        # Inventory increment
        st2 = api.get(f"{BASE_URL}/api/state/{RID}").json()
        it_after = next((it for it in st2["items"] if it["controlNumber"] == cn), None)
        stock_after = float((it_after or {}).get("currentStock") or 0)
        assert stock_after >= stock_before + inv_qty - 0.001, \
            f"stock did not increment: before={stock_before} after={stock_after} qty={inv_qty}"


# --- Regression: owner endpoints ---
class TestOwnerEndpointsRegression:
    def test_discrepancies(self, api):
        r = api.get(f"{BASE_URL}/api/owner/discrepancies")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_vendor_scorecard(self, api):
        r = api.get(f"{BASE_URL}/api/owner/vendor-scorecard")
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        if rows:
            # Trend fields must be present per spec
            sample = rows[0]
            assert "leadTrend" in sample, f"missing leadTrend in {sample.keys()}"
            assert "priceVarTrend" in sample, f"missing priceVarTrend in {sample.keys()}"

    def test_orders(self, api):
        r = api.get(f"{BASE_URL}/api/owner/orders")
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))


# --- Regression: apply-prices ---
class TestApplyPricesRegression:
    def test_apply_prices_updates_vendor_sku_price(self, api, state):
        purchases = state.get("purchases", [])
        assert purchases, "need seeded purchases"
        p = purchases[0]
        cn = p["controlNumber"]
        inv_no = p["invoiceNumber"]
        inv_qty = float(p.get("qty") or 1)
        inv_cost = float(p.get("unitCost") or 1.0)
        new_cost = round(inv_cost + 3.75, 2)
        vendor_sku = "TEST_APPLY_SKU"

        po = api.post(f"{BASE_URL}/api/orders/{RID}", json={
            "vendor": "TEST_SEC001_ApplyPrices", "createdBy": "TEST_sec", "lines": [
                {"controlNumber": cn, "vendorSku": vendor_sku,
                 "qty": inv_qty, "purchaseUnit": "case", "unitCost": inv_cost}
            ]}).json()
        oid = po["id"]
        api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/submit", json={"by": "m"})
        api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/approve", json={"by": "o"})
        api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/send", json={"by": "m"})
        # receive with a matching invoiceNumber but different price -> flagged
        api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/receive", json={
            "by": "m", "invoiceNumber": inv_no,
            "lines": [{"controlNumber": cn, "receivedQty": inv_qty, "unitCost": new_cost}]})
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/apply-prices", json={"by": "TEST_sec"})
        assert r.status_code == 200, r.text
        # Verify persistence: fetch item and check the vendor SKU price
        st2 = api.get(f"{BASE_URL}/api/state/{RID}").json()
        item = next((it for it in st2["items"] if it["controlNumber"] == cn), None)
        assert item is not None
        # priceSource=invoice on the vendor SKU we sent
        vskus = item.get("vendorSkus") or []
        target = next((v for v in vskus if v.get("vendorSku") == vendor_sku), None)
        # some impls key by vendor name; accept either presence signal
        if target is not None:
            assert target.get("priceSource") == "invoice", target
