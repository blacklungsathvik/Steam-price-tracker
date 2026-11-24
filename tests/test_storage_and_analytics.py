from app import analytics, service

DAY = 86400


def obs(initial, final, disc, cur="USD"):
    return {"currency": cur, "initial": initial, "final": final, "discount": disc, "formatted": None}


def test_record_price_is_change_only(conn):
    service.upsert_stub(conn, 1, "G")
    assert service.record_price(conn, 1, "us", obs(2000, 2000, 0), ts=1000) is True
    assert service.record_price(conn, 1, "us", obs(2000, 2000, 0), ts=2000) is False  # unchanged
    assert service.record_price(conn, 1, "us", obs(2000, 1000, 50), ts=3000) is True
    assert conn.execute("SELECT COUNT(*) c FROM prices").fetchone()["c"] == 2
    st = conn.execute("SELECT * FROM price_state").fetchone()
    assert st["checked_at"] == 3000 and st["changed_at"] == 3000 and st["discount"] == 50
    service.record_price(conn, 1, "us", obs(2000, 1000, 50), ts=4000)
    st = conn.execute("SELECT * FROM price_state").fetchone()
    assert st["checked_at"] == 4000 and st["changed_at"] == 3000  # only 'checked' moved


def test_episodes_and_changes():
    pts = [(0, 2000, 2000, 0), (10 * DAY, 2000, 1000, 50), (12 * DAY, 2000, 600, 70), (20 * DAY, 2000, 2000, 0),
           (40 * DAY, 2500, 2500, 0), (50 * DAY, 2500, 1750, 30)]
    eps = analytics.build_episodes(pts)
    assert len(eps) == 2
    assert eps[0]["depth"] == 70 and eps[0]["end"] == 20 * DAY and eps[1]["end"] is None
    kinds = [c["kind"] for c in analytics.price_changes(pts)]
    assert kinds == ["first_seen", "sale_start", "deeper_sale", "sale_end", "base_hike", "sale_start"]


def test_stats():
    pts = [(0, 2000, 2000, 0), (10 * DAY, 2000, 1000, 50), (20 * DAY, 2000, 2000, 0)]
    s = analytics.stats(pts, 30 * DAY)
    assert s["all_time_low"]["final"] == 1000 and s["sale_count"] == 1
    assert s["pct_time_on_sale"] == 33.3 and s["is_at_all_time_low"] is False
    assert s["highest_base"] == 2000
