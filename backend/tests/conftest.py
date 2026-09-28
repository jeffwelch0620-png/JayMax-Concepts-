"""Shared pytest fixtures: the collaboration-auth PR made every API route (except
/health, /auth/login, /auth/bootstrap) require a Bearer token. `auth_headers` provisions
one test owner account (bootstrapping it on a fresh DB, logging in if it already exists
from a prior run) so every test file can attach it to its own requests.Session.
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as _f:
        for _l in _f:
            if _l.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = _l.split("=", 1)[1].strip().rstrip("/")

TEST_OWNER_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "pytest-owner@jaymax.test")
TEST_OWNER_PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "PytestOwnerPassword123!")
BOOTSTRAP_TOKEN = os.environ.get("BOOTSTRAP_TOKEN", "")


@pytest.fixture(scope="session")
def auth_token():
    r = requests.post(f"{BASE_URL}/api/auth/bootstrap", json={
        "bootstrapToken": BOOTSTRAP_TOKEN, "email": TEST_OWNER_EMAIL,
        "password": TEST_OWNER_PASSWORD, "role": "owner",
    }, timeout=30)
    if r.status_code == 200:
        return r.json()["token"]
    # 409 = an owner already exists (this DB was bootstrapped by a prior run, or by
    # someone else); 403 = BOOTSTRAP_TOKEN doesn't match. Either way, fall back to
    # logging in as the same test identity — it only works if that identity is the
    # one that originally bootstrapped this DB.
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_OWNER_EMAIL, "password": TEST_OWNER_PASSWORD,
    }, timeout=30)
    if r.status_code == 200:
        return r.json()["token"]
    pytest.skip(f"Could not authenticate the test session ({r.status_code}): {r.text}. "
                f"Set TEST_OWNER_EMAIL/TEST_OWNER_PASSWORD to an existing owner account, "
                f"or drop the database so bootstrap can run fresh.")


@pytest.fixture(scope="session")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}
