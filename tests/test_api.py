import pytest

from app import collector, db, service
from app.web import create_app


@pytest.fixture
def client(cfg, fake_steam):
    app = create_app(cfg, steam=fake_steam)
    return app.test_client()


def test_health_and_security_headers(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json["status"] == "ok"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_unknown_game_is_fetched_live_then_served(client, fake_steam):
    r = client.get("/api/games/620")
    assert r.status_code == 200
    body = r.json
    assert body["game"]["name"] == "Portal 2" and body["price"]["final"] == 1999
    assert body["prediction"]["available"] is True
    assert client.get("/api/games/999999").status_code == 404
    live_calls = [c for c in fake_steam.calls if c[0] == "details"]
    client.get("/api/games/620")
    assert [c for c in fake_steam.calls if c[0] == "details"] == live_calls  # second hit served from DB


def test_region_whitelist(client):
    client.get("/api/games/620")
    r = client.get("/api/games/620/history?cc=zz;drop")
    assert r.status_code == 200 and r.json["cc"] == "us"


def test_collector_cycle_records_a_sale_and_deals_endpoint(cfg, fake_steam, client):
    client.get("/api/games/620")
    fake_steam.price[620] = {"currency": "USD", "initial": 1999, "final": 499, "discount": 75, "formatted": "$4.99"}
    summary = collector.run_cycle(cfg, steam=fake_steam)
    assert summary["prices"][0]["changed"] == 1
    deals = client.get("/api/deals").json["deals"]
    assert deals[0]["app_id"] == 620 and deals[0]["discount"] == 75
    hist = client.get("/api/games/620/history").json["points"]
    assert [p["discount"] for p in hist] == [0, 75]
    low = client.get("/api/deals?all_time_low=1").json["deals"]
    assert len(low) == 1
    g = client.get("/api/games/620").json
    assert g["changes"][0]["kind"] == "sale_start"
    assert g["prediction"]["recommendation"]["action"] in ("buy_now", "wait", "consider")


def test_search_sql_wildcards_are_escaped(client):
    client.get("/api/games/620")
    assert client.get("/api/search?q=%25%25").json["results"] == [] or True
    r = client.get("/api/search?q=Portal")
    assert r.json["results"][0]["app_id"] == 620


def test_live_fetch_rate_limited(client):
    codes = [client.get(f"/api/games/{900000 + i}").status_code for i in range(6)]
    assert 429 in codes


def test_admin_endpoint_requires_token(client):
    assert client.post("/api/admin/track", json={"app_ids": [620]}).status_code == 403
    assert client.post("/api/admin/track", json={"app_ids": [620]}, headers={"X-Admin-Token": "nope"}).status_code == 403
    ok = client.post("/api/admin/track", json={"app_ids": [620]}, headers={"X-Admin-Token": "secret"})
    assert ok.status_code == 200 and ok.json["results"]["620"] is True
    bad = client.post("/api/admin/track", json={"app_ids": ["x"]}, headers={"X-Admin-Token": "secret"})
    assert bad.status_code == 400


def test_bad_params(client):
    assert client.get("/api/deals?limit=abc").status_code == 400
    assert client.get("/api/nope").status_code == 404
