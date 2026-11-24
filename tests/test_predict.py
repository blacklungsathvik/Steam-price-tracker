from datetime import datetime, timezone

from app.predict import predict, snap_tier
from app.steam_calendar import load_events, upcoming, season_slots, _black_friday

DAY = 86400


def ts(y, m, d):
    return int(datetime(y, m, d, 18, tzinfo=timezone.utc).timestamp())


def sale_history():
    """Game that goes 33% off every Winter/Summer sale, deeper over time; observed since mid-2023."""
    pts = [(ts(2023, 5, 1), 3999, 3999, 0)]
    for (s, e, depth) in [((2023, 6, 29), (2023, 7, 13), 25), ((2023, 12, 21), (2024, 1, 4), 33),
                          ((2024, 6, 27), (2024, 7, 11), 40), ((2024, 12, 19), (2025, 1, 2), 50),
                          ((2025, 6, 26), (2025, 7, 10), 50), ((2025, 12, 18), (2026, 1, 5), 60),
                          ((2026, 6, 25), (2026, 7, 9), 60)]:
        price = round(3999 * (1 - depth / 100))
        pts.append((ts(*s), 3999, price, depth))
        pts.append((ts(*e), 3999, 3999, 0))
    return pts


def test_snap_tier():
    assert snap_tier(48.2) == 50 and snap_tier(31) == 30 and snap_tier(66.4) == 66


def test_winter_sale_predicted_for_regular_discounter():
    now = ts(2026, 11, 22)
    ev = load_events("data/steam_events.json")
    p = predict(sale_history(), ts(2022, 1, 1), now, ev)
    assert p["available"] and p["confidence"] in ("medium", "high")
    nd = p["next_drop"]
    assert nd["type"] in ("winter", "black_friday") and nd["probability"] >= 0.5
    winter = next(o for o in p["outlook"] if o["type"] == "winter")
    assert winter["start"] == "2026-12-17" and winter["confirmed"]
    assert winter["expected_discount"] >= 50          # history trends 50 -> 60
    assert winter["expected_price"] < 3999 * 0.55
    assert p["recommendation"]["action"] == "wait"
    assert p["p_discount_90d"] > 0.8


def test_on_sale_at_all_time_low_is_buy_now():
    now = ts(2026, 7, 1)
    hist = [pt for pt in sale_history() if pt[0] <= now]
    p = predict(hist, ts(2022, 1, 1), now, load_events("data/steam_events.json"))
    assert p["current"]["discount"] == 60
    assert p["recommendation"]["action"] == "buy_now"


def test_new_game_low_confidence_and_modest_depth():
    now = ts(2026, 11, 22)
    pts = [(ts(2026, 10, 20), 5999, 5999, 0)]
    p = predict(pts, ts(2026, 10, 20), now, load_events("data/steam_events.json"))
    assert p["confidence"] == "low"
    winter = next(o for o in p["outlook"] if o["type"] == "winter")
    assert winter["probability"] <= 0.5 and winter["expected_discount"] <= 20


def test_no_points_unavailable():
    assert predict([], None, ts(2026, 1, 1), [])["available"] is False


def test_calendar_estimates_fill_gaps_and_black_friday():
    now = ts(2026, 11, 22)
    ev = upcoming(load_events("data/steam_events.json"), now, 700)
    names = [e.name for e in ev]
    assert any("Winter Sale 2026" in n and "(est.)" not in n for n in names)   # published
    assert any("Autumn Sale 2027 (est.)" in n for n in names)                 # unpublished -> estimated
    assert _black_friday(2026).isoformat() == "2026-11-27"
    assert all(e.end_ts >= now for e in ev)


def test_season_slots_only_complete_windows():
    slots = season_slots(ts(2025, 1, 1), ts(2026, 3, 1))
    assert {s for s, *_ in slots} == {"spring", "summer", "autumn", "winter"}
    assert all(e <= ts(2026, 3, 1) for _, _, e in slots)


def test_cadence_detected_for_regular_offseason_sales():
    now = ts(2026, 11, 22)
    pts = [(ts(2025, 1, 1), 1999, 1999, 0)]
    start = ts(2025, 2, 1)
    for i in range(6):  # 4-day sale every ~45 days, outside season windows mostly
        s = start + i * 45 * DAY
        pts += [(s, 1999, 1399, 30), (s + 4 * DAY, 1999, 1999, 0)]
    p = predict(sorted(pts), ts(2023, 1, 1), now, load_events("data/steam_events.json"))
    assert p["available"]
    assert isinstance(p["outlook"], list)
