"""Pytest for the three new PO features: reorder-last, vendor-contacts, email, receipt-match."""
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
    r = s.get(f"{BASE_URL}/api/state/{RID}", timeout=30)
    assert r.status_code == 200
    return s


@pytest.fixture(scope="module")
def state(api):
    return api.get(f"{BASE_URL}/api/state/{RID}").json()


# --- Vendor contacts registry ---
class TestVendorContacts:
    def test_put_and_get_vendor_contact(self, api):
        r = api.put(f"{BASE_URL}/api/vendor-contacts/{RID}",
                    json={"vendor": "TEST_VendorX", "orderEmail": "delivered@resend.dev"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["vendor"] == "TEST_VendorX"
        assert j["orderEmail"] == "delivered@resend.dev"

        r2 = api.get(f"{BASE_URL}/api/vendor-contacts/{RID}")
        assert r2.status_code == 200
        rows = r2.json()
        assert any(v.get("vendor") == "TEST_VendorX" and v.get("orderEmail") == "delivered@resend.dev" for v in rows)

    def test_invalid_email_rejected(self, api):
        r = api.put(f"{BASE_URL}/api/vendor-contacts/{RID}",
                    json={"vendor": "TEST_VendorX", "orderEmail": "not-an-email"})
        assert r.status_code == 400

    def test_missing_vendor_rejected(self, api):
        r = api.put(f"{BASE_URL}/api/vendor-contacts/{RID}",
                    json={"vendor": "", "orderEmail": "a@b.co"})
        assert r.status_code == 400


# --- Reorder from history ---
class TestReorderLast:
    def test_404_when_no_prior(self, api):
        r = api.post(f"{BASE_URL}/api/orders/{RID}/reorder-last",
                     json={"vendor": "TEST_NoSuchVendor_zzz", "createdBy": "TEST_m"})
        assert r.status_code == 404

    def test_clones_last_po_as_draft(self, api, state):
        item = state["items"][0]
        # create an initial PO for a unique vendor
        vendor = "TEST_ReorderVendor"
        create = api.post(f"{BASE_URL}/api/orders/{RID}", json={
            "vendor": vendor, "createdBy": "TEST_m", "lines": [
                {"controlNumber": item["controlNumber"], "name": item.get("name", ""),
                 "vendorSku": "SKU-R", "qty": 4, "purchaseUnit": item.get("purchaseUnit", "case"), "unitCost": 9.99}
            ]})
        assert create.status_code == 200
        orig = create.json()

        r = api.post(f"{BASE_URL}/api/orders/{RID}/reorder-last",
                     json={"vendor": vendor, "createdBy": "TEST_m"})
        assert r.status_code == 200, r.text
        clone = r.json()
        assert clone["status"] == "draft"
        assert clone["id"] != orig["id"]
        assert clone["vendor"] == vendor
        assert len(clone["lines"]) == len(orig["lines"])
        assert clone["lines"][0]["controlNumber"] == item["controlNumber"]
        assert clone["lines"][0]["qty"] == 4
        assert clone["total"] == round(4 * 9.99, 2)

        # cleanup drafts
        api.delete(f"{BASE_URL}/api/orders/{RID}/{clone['id']}")
        api.delete(f"{BASE_URL}/api/orders/{RID}/{orig['id']}")


# --- Email order ---
def _mk_approved_po(api, state, vendor="TEST_EmailVendor"):
    item = state["items"][0]
    r = api.post(f"{BASE_URL}/api/orders/{RID}", json={
        "vendor": vendor, "createdBy": "TEST_m", "lines": [
            {"controlNumber": item["controlNumber"], "name": item.get("name", ""),
             "vendorSku": "SKU-E", "qty": 1, "purchaseUnit": item.get("purchaseUnit", "case"), "unitCost": 5.0}
        ]})
    oid = r.json()["id"]
    api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/submit", json={"by": "m"})
    api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/approve", json={"by": "o"})
    return oid, item


class TestEmailOrder:
    def test_email_approved_moves_to_sent(self, api, state):
        oid, _ = _mk_approved_po(api, state, vendor="TEST_EmailVendor1")
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/email",
                     json={"email": "delivered@resend.dev", "by": "TEST_m"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "sent"
        assert j.get("emailedTo") == "delivered@resend.dev"
        # cascades vendor-contact save
        rows = api.get(f"{BASE_URL}/api/vendor-contacts/{RID}").json()
        assert any(v.get("vendor") == "TEST_EmailVendor1" and v.get("orderEmail") == "delivered@resend.dev" for v in rows)

    def test_email_uses_saved_contact_when_no_override(self, api, state):
        vendor = "TEST_EmailVendor2"
        api.put(f"{BASE_URL}/api/vendor-contacts/{RID}", json={"vendor": vendor, "orderEmail": "delivered@resend.dev"})
        oid, _ = _mk_approved_po(api, state, vendor=vendor)
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/email", json={"by": "m"})
        assert r.status_code == 200, r.text
        assert r.json().get("emailedTo") == "delivered@resend.dev"

    def test_email_without_address_400(self, api, state):
        vendor = "TEST_EmailVendor3_noaddr"
        oid, _ = _mk_approved_po(api, state, vendor=vendor)
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/email", json={"by": "m"})
        assert r.status_code == 400

    def test_email_on_draft_400(self, api, state):
        item = state["items"][0]
        r = api.post(f"{BASE_URL}/api/orders/{RID}", json={
            "vendor": "TEST_EmailDraft", "lines": [
                {"controlNumber": item["controlNumber"], "qty": 1, "unitCost": 1.0}]})
        oid = r.json()["id"]
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/email",
                     json={"email": "delivered@resend.dev"})
        assert r.status_code == 400
        api.delete(f"{BASE_URL}/api/orders/{RID}/{oid}")


# --- Receive with invoice match ---
class TestReceiveInvoiceMatch:
    def test_match_flags_discrepancy(self, api, state):
        purchases = state.get("purchases", [])
        assert purchases, "need purchases seeded in rudds"
        p = purchases[0]
        inv_no = p["invoiceNumber"]
        cn = p["controlNumber"]
        inv_qty = float(p.get("qty") or 0)
        inv_cost = float(p.get("unitCost") or 0)

        # Create a PO for the same CN with a different unit cost (force price flag)
        po = api.post(f"{BASE_URL}/api/orders/{RID}", json={
            "vendor": "TEST_MatchVendor", "createdBy": "m", "lines": [
                {"controlNumber": cn, "name": p.get("itemName", ""), "vendorSku": "SKU-M",
                 "qty": inv_qty, "purchaseUnit": "case", "unitCost": inv_cost + 50.0}
            ]}).json()
        oid = po["id"]
        api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/submit", json={"by": "m"})
        api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/approve", json={"by": "o"})
        api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/send", json={"by": "m"})
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/receive", json={
            "by": "m", "invoiceNumber": inv_no,
            "lines": [{"controlNumber": cn, "receivedQty": inv_qty}]})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "received"
        rm = j.get("receiptMatch")
        assert rm and rm["invoiceFound"] is True
        assert rm["flaggedCount"] >= 1
        line = next(l for l in rm["lines"] if l["controlNumber"] == cn)
        assert line["flagged"] is True
        assert abs((line["priceDiff"] or 0) - 50.0) < 0.001
        # qty should match
        assert abs(line.get("qtyDiff") or 0) < 0.001

    def test_unknown_invoice_number(self, api, state):
        item = state["items"][0]
        po = api.post(f"{BASE_URL}/api/orders/{RID}", json={
            "vendor": "TEST_MatchVendor2", "createdBy": "m", "lines": [
                {"controlNumber": item["controlNumber"], "qty": 1, "unitCost": 1.0}]}).json()
        oid = po["id"]
        api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/submit", json={"by": "m"})
        api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/approve", json={"by": "o"})
        api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/send", json={"by": "m"})
        r = api.post(f"{BASE_URL}/api/orders/{RID}/{oid}/receive", json={
            "invoiceNumber": "INV_TEST_DOES_NOT_EXIST_ZZ",
            "lines": [{"controlNumber": item["controlNumber"], "receivedQty": 1}]})
        assert r.status_code == 200
        rm = r.json().get("receiptMatch")
        assert rm and rm["invoiceFound"] is False
