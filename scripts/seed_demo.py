"""Fill a database with synthetic games + price history so you can see the UI without waiting for the
collector. Data is FAKE (clearly named 'Demo ...'). Usage: DB_PATH=data/demo.db python scripts/seed_demo.py"""
import os
import random
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import db, service  # noqa: E402
from app.config import load_config  # noqa: E402

random.seed(7)
cfg = load_config()
db.init_db(cfg.db_path)
conn = db.connect(cfg.db_path)
now = db.now()
T = lambda y, m, d: int(datetime(y, m, d, 18, tzinfo=timezone.utc).timestamp())

GAMES = [
    (9000001, "Demo Quest: Dawn of Ash", 5999, T(2022, 3, 3), [(25, 0), (33, 1), (40, 2), (50, 3)]),
    (9000002, "Demo Racer GT", 3999, T(2021, 8, 12), [(30, 0), (50, 1), (60, 2), (75, 3)]),
    (9000003, "Demo Puzzle Garden", 1499, T(2023, 5, 20), [(20, 0), (25, 1), (33, 2), (50, 3)]),
    (9000004, "Demo Space Tycoon", 4999, T(2025, 9, 9), [(15, 0), (20, 3)]),
    (9000005, "Demo Tactics Online", 2999, T(2019, 1, 15), [(50, 0), (66, 1), (75, 2), (80, 3)]),
]
SALES = [((2023, 6, 29), 14), ((2023, 12, 21), 14), ((2024, 3, 14), 7), ((2024, 6, 27), 14), ((2024, 12, 19), 14),
         ((2025, 3, 13), 7), ((2025, 6, 26), 14), ((2025, 12, 18), 15), ((2026, 3, 19), 7), ((2026, 6, 25), 14),
         ((2026, 10, 1), 7)]
for app_id, name, base, rel, depth_pairs in GAMES:
    depths = [d for d, _ in depth_pairs]
    service.upsert_stub(conn, app_id, name)
    conn.execute("UPDATE games SET type='game', is_free=0, details_updated_at=?, release_ts=?, release_date=?, "
                 "short_description=?, genres='[\"Action\",\"Indie\"]', platforms='[\"windows\"]', developers='[\"Demo Studio\"]', "
                 "publishers='[\"Demo Pub\"]', categories='[\"Single-player\"]', current_players=?, review_desc='Very Positive', "
                 "reviews_positive=8200, reviews_negative=900 WHERE app_id=?",
                 (now, rel, datetime.fromtimestamp(rel, timezone.utc).strftime("%d %b, %Y"),
                  "Synthetic demo data - not a real game.", random.randint(200, 20000), app_id))
    conn.execute("DELETE FROM prices WHERE app_id=?", (app_id,))
    conn.execute("DELETE FROM price_state WHERE app_id=?", (app_id,))
    start = max(T(2023, 5, 1), rel)
    rows = [(start, base, base, 0)]
    cur_base = base
    n = 0
    for (y, m, d), days in SALES:
        s = T(y, m, d)
        if s < start or s > now:
            continue
        depth = depths[min(n * len(depths) // 6, len(depths) - 1)]
        n += 1
        if (y, m) == (2025, 3) and app_id == 9000004:
            continue
        if (y, m) == (2024, 6) and app_id == 9000001:
            cur_base = int(base * 1.1) // 100 * 100 + 99  # a base price hike
        e = min(s + days * 86400, now)
        rows.append((s, cur_base, round(cur_base * (1 - depth / 100)), depth))
        if e < now:
            rows.append((e, cur_base, cur_base, 0))
    for ts, ini, fin, disc in rows:
        conn.execute("INSERT OR REPLACE INTO prices VALUES(?,?,?,?,?,?,?, 'demo')", (app_id, "us", ts, "USD", ini, fin, disc))
    ts, ini, fin, disc = rows[-1]
    conn.execute("INSERT OR REPLACE INTO price_state VALUES(?,?,?,?,?,?,?,?,?)",
                 (app_id, "us", "USD", ini, fin, disc, None, ts, now))
conn.commit()
print(f"seeded {len(GAMES)} demo games into {cfg.db_path}")
