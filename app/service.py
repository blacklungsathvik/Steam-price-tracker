from __future__ import annotations

import json
import sqlite3

from . import analytics, db, external
from .predict import predict
from .steam_calendar import load_events


def _j(v) -> str:
    return json.dumps(v or [])


def upsert_stub(conn: sqlite3.Connection, app_id: int, name: str | None = None) -> None:
    conn.execute(
        "INSERT INTO games(app_id, name, created_at) VALUES(?,?,?) "
        "ON CONFLICT(app_id) DO UPDATE SET name=COALESCE(games.name, excluded.name)",
        (app_id, name, db.now()),
    )


def upsert_details(conn: sqlite3.Connection, d: dict) -> None:
    upsert_stub(conn, d["app_id"], d.get("name"))
    conn.execute(
        """UPDATE games SET name=?, type=?, is_free=?, short_description=?, header_image=?,
           developers=?, publishers=?, genres=?, categories=?, platforms=?,
           release_date=?, release_ts=?, metacritic=?, details_updated_at=? WHERE app_id=?""",
        (d["name"], d["type"], int(d["is_free"]), d["short_description"], d["header_image"],
         _j(d["developers"]), _j(d["publishers"]), _j(d["genres"]), _j(d["categories"]), _j(d["platforms"]),
         d["release_date"], d["release_ts"], d["metacritic"], db.now(), d["app_id"]),
    )


def record_price(conn: sqlite3.Connection, app_id: int, cc: str, obs: dict, ts: int | None = None) -> bool:
    """Store an observation. Writes to the change log only when something changed. Returns True if changed."""
    ts = ts or db.now()
    st = conn.execute("SELECT initial, final, discount, changed_at FROM price_state WHERE app_id=? AND cc=?",
                      (app_id, cc)).fetchone()
    changed = st is None or (st["initial"], st["final"], st["discount"]) != (obs["initial"], obs["final"], obs["discount"])
    if changed:
        if st is not None and ts <= st["changed_at"]:
            ts = st["changed_at"] + 1  # never overwrite an earlier change recorded in the same second
        conn.execute(
            "INSERT OR REPLACE INTO prices(app_id, cc, ts, currency, initial, final, discount, source) "
            "VALUES(?,?,?,?,?,?,?, 'steam')",
            (app_id, cc, ts, obs["currency"], obs["initial"], obs["final"], obs["discount"]),
        )
    conn.execute(
        """INSERT INTO price_state(app_id, cc, currency, initial, final, discount, formatted, changed_at, checked_at)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(app_id, cc) DO UPDATE SET currency=excluded.currency, initial=excluded.initial,
             final=excluded.final, discount=excluded.discount, formatted=excluded.formatted,
             changed_at=CASE WHEN ? THEN excluded.changed_at ELSE price_state.changed_at END,
             checked_at=excluded.checked_at""",
        (app_id, cc, obs["currency"], obs["initial"], obs["final"], obs["discount"], obs.get("formatted"),
         ts, ts, int(changed)),
    )
    return changed


def mark_checked_no_price(conn: sqlite3.Connection, app_id: int, cc: str) -> None:
    """The app has no price in this region (free / unreleased / not sold). Remember we looked."""
    conn.execute("INSERT OR IGNORE INTO price_state(app_id, cc, currency, initial, final, discount, changed_at, checked_at) "
                 "VALUES(?,?, '', 0, 0, 0, ?, ?)", (app_id, cc, db.now(), db.now()))
    conn.execute("UPDATE price_state SET checked_at=? WHERE app_id=? AND cc=? AND currency=''",
                 (db.now(), app_id, cc))


def backfill_history(conn: sqlite3.Connection, app_id: int, cc: str, key: str) -> int:
    """Import older history (before our first observation) from ITAD. Safe to call repeatedly."""
    if not key:
        return 0
    if conn.execute("SELECT 1 FROM backfill WHERE app_id=? AND cc=? AND source='itad'", (app_id, cc)).fetchone():
        return 0
    first = conn.execute("SELECT MIN(ts) m FROM prices WHERE app_id=? AND cc=?", (app_id, cc)).fetchone()["m"]
    rows = external.itad_history(app_id, cc, key)
    added = 0
    for ts, initial, final, disc, currency in rows:
        if first is not None and ts >= first:
            continue
        conn.execute("INSERT OR IGNORE INTO prices(app_id, cc, ts, currency, initial, final, discount, source) "
                     "VALUES(?,?,?,?,?,?,?, 'itad')", (app_id, cc, ts, currency, initial, final, disc))
        added += 1
    conn.execute("INSERT OR REPLACE INTO backfill(app_id, cc, source, done_at) VALUES(?,?, 'itad', ?)",
                 (app_id, cc, db.now()))
    return added


def ensure_game(conn: sqlite3.Connection, steam, cfg, app_id: int) -> bool:
    """Make sure a game is in the DB with details and a price in every tracked region."""
    row = conn.execute("SELECT details_updated_at FROM games WHERE app_id=?", (app_id,)).fetchone()
    if row and row["details_updated_at"]:
        return True
    d = steam.details(app_id, cfg.default_cc)
    if not d or d["type"] not in ("game", "dlc", "demo", "software", "music", "advertising", "mod", "video"):
        return False
    upsert_details(conn, d)
    if d["price"]:
        record_price(conn, app_id, cfg.default_cc, d["price"])
    for cc in cfg.regions[1:]:
        p = steam.prices([app_id], cc).get(app_id)
        if p:
            record_price(conn, app_id, cc, p)
    conn.commit()
    return True


# ----------------------------------------------------------------------------- read side

def load_points(conn: sqlite3.Connection, app_id: int, cc: str) -> list[tuple[int, int, int, int]]:
    rows = conn.execute("SELECT ts, initial, final, discount FROM prices WHERE app_id=? AND cc=? ORDER BY ts",
                        (app_id, cc)).fetchall()
    return [(r["ts"], r["initial"], r["final"], r["discount"]) for r in rows]


def game_row(conn: sqlite3.Connection, app_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM games WHERE app_id=?", (app_id,)).fetchone()
    if not r:
        return None
    g = dict(r)
    for k in ("developers", "publishers", "genres", "categories", "platforms"):
        g[k] = json.loads(g[k]) if g.get(k) else []
    pos, neg = g.get("reviews_positive"), g.get("reviews_negative")
    g["review_pct"] = round(100 * pos / (pos + neg)) if pos is not None and neg is not None and (pos + neg) else None
    return g


def game_payload(conn: sqlite3.Connection, cfg, app_id: int, cc: str, now: int | None = None) -> dict | None:
    now = now or db.now()
    g = game_row(conn, app_id)
    if not g:
        return None
    pts = load_points(conn, app_id, cc)
    st = conn.execute("SELECT * FROM price_state WHERE app_id=? AND cc=?", (app_id, cc)).fetchone()
    currency = st["currency"] if st and st["currency"] else (conn.execute(
        "SELECT currency FROM prices WHERE app_id=? AND cc=? LIMIT 1", (app_id, cc)).fetchone() or {"currency": ""})["currency"]
    ext = conn.execute("SELECT price_usd_cents, low_ts FROM external_lows WHERE app_id=?", (app_id,)).fetchone()
    ext_cents = ext["price_usd_cents"] if ext and currency == "USD" else None
    events = load_events(cfg.events_file)
    return {
        "game": g,
        "cc": cc,
        "currency": currency,
        "divisor": cfg.divisor(currency) if currency else 100,
        "price": ({
            "initial": st["initial"], "final": st["final"], "discount": st["discount"],
            "formatted": st["formatted"], "changed_at": st["changed_at"], "checked_at": st["checked_at"],
        } if st and st["currency"] else None),
        "stats": analytics.stats(pts, now, ext_cents, currency),
        "changes": analytics.price_changes(pts)[::-1][:200],
        "external_low": ({"usd_cents": ext["price_usd_cents"], "ts": ext["low_ts"]} if ext and ext["price_usd_cents"] else None),
        "prediction": predict(pts, g.get("release_ts"), now, events, external_low_usd_cents=ext_cents,
                              currency=currency),
    }
