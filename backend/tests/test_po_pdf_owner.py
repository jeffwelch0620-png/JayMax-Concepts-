"""Pytest for the 3 latest PO features: PO PDF, Owner Discrepancies, Vendor Scorecard."""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as _f:
        for _l in _f:
            if _l.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = _l.split("=", 1)[1].strip().rstrip("/")

RID = "rudds"


# --- PO PDF endpoint ---
class TestPoPdf:
    def test_pdf_endpoint_returns_pdf(self):
        # Find any PO on rudds
        orders = requests.get(f"{BASE_URL}/api/orders/{RID}", timeout=30).json()
        assert isinstance(orders, list) and len(orders) > 0, "need at least one PO"
        oid = orders[0]["id"]
        r = requests.get(f"{BASE_URL}/api/orders/{RID}/{oid}/pdf", timeout=30)
        assert r.status_code == 200, r.text[:200]
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct, f"content-type={ct}"
        assert len(r.content) > 500
        assert r.content[:4] == b"%PDF", "body must start with %PDF magic"

    def test_pdf_unknown_order_404(self):
        r = requests.get(f"{BASE_URL}/api/orders/{RID}/NO_SUCH_ORDER_ZZZ/pdf", timeout=30)
        assert r.status_code == 404


# --- Owner discrepancies ---
class TestOwnerDiscrepancies:
    def test_returns_list(self):
        r = requests.get(f"{BASE_URL}/api/owner/discrepancies", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # From prior seed there should be flagged discrepancies on rudds
        assert len(data) >= 1, "expected at least one flagged discrepancy"
        row = data[0]
        # Structure assertions
        for k in ("orderId", "restaurantName", "vendor", "invoiceNumber", "flaggedCount", "lines"):
            assert k in row, f"missing {k} in {row}"
        assert row["flaggedCount"] >= 1
        assert isinstance(row["lines"], list) and len(row["lines"]) >= 1


# --- Vendor scorecard ---
class TestVendorScorecard:
    def test_returns_vendor_rows(self):
        r = requests.get(f"{BASE_URL}/api/owner/vendor-scorecard", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1, "expected at least one vendor row"
        row = data[0]
        for k in ("vendor", "locations", "receivedOrders", "avgLeadDays",
                  "priceAccuratePct", "avgPriceVariance", "totalSpend"):
            assert k in row, f"missing {k} in {row}"
        assert isinstance(row["vendor"], str)
        assert isinstance(row["locations"], list)
        assert isinstance(row["receivedOrders"], int)
        assert isinstance(row["totalSpend"], (int, float))
