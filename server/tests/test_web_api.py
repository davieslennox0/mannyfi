"""The browser API over HTTP: sessions gate everything, and orders are private."""

import pytest
from fastapi.testclient import TestClient

from sarf import auth
import sarf.main as m

client = TestClient(m.app)


def bearer(account):
    token, _ = auth.mint_session(m.db, account, client_name="test")
    return {"authorization": f"Bearer {token}"}


def test_health_and_challenge():
    assert client.get("/healthz").json()["baskets"] == 7
    r = client.get("/api/auth/challenge", params={"account": "alice.near"})
    assert r.status_code == 200 and r.json()["recipient"] == "mannyfi"
    assert client.get("/api/auth/challenge", params={"account": "Not Valid"}).status_code == 400


@pytest.mark.parametrize("path", ["/api/orders/ord_x", "/api/portfolio"])
def test_routes_need_a_session(path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"authorization": "Bearer nonsense"}).status_code == 401


def test_unknown_order_is_404_and_empty_submit_is_400():
    h = bearer("alice.near")
    assert client.get("/api/orders/ord_missing", headers=h).status_code == 404
    assert client.post("/api/orders/ord_missing/submit", json={"legs": []}, headers=h).status_code == 400
    assert client.post("/api/orders/ord_missing/submit", json={"legs": [{"index": 0}]}, headers=h).status_code == 404


def test_verify_rejects_an_unsigned_login():
    r = client.post("/api/auth/verify", json={"account": "alice.near", "signature": {"public_key": "ed25519:x", "signature": ""}})
    assert r.status_code in (400, 401)


def test_cors_only_for_listed_origins():
    ok = client.options("/api/portfolio", headers={"origin": "http://localhost:3000",
                        "access-control-request-method": "GET"})
    bad = client.options("/api/portfolio", headers={"origin": "https://evil.example",
                         "access-control-request-method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in bad.headers


def test_submit_needs_a_batch_signature_or_legs():
    h = bearer("alice.near")
    assert client.post("/api/orders/ord_x/submit", json={}, headers=h).status_code == 400
    assert client.post("/api/orders/ord_x/submit", json={"batch": "nope"}, headers=h).status_code == 400
    assert client.post("/api/orders/ord_missing/submit", json={"batch": {"public_key": "x", "signature": "y"}},
                       headers=h).status_code == 404
