from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from . import db, external, service
from .config import Config, load_config
from .steam import SteamBlocked, SteamClient, SteamError

log = logging.getLogger("collector")
_stop = False

DETAILS_MAX_AGE = 7 * 86400
SOCIAL_MAX_AGE = 2 * 86400


def discover(conn, steam: SteamClient, cfg: Config) -> int:
    """Add games from Steam's featured lists (specials, top sellers, new releases) in every region."""
    new = 0
    for cc in cfg.regions:
        try:
            feats = steam.featured(cc)
        except SteamBlocked:
            raise
        except SteamError as e:
            log.warning("featured(%s) failed: %s", cc, e)
            continue
        for items in feats.values():
            for it in items:
                if not conn.execute("SELECT 1 FROM games WHERE app_id=?", (it["app_id"],)).fetchone():
                    new += 1
                service.upsert_stub(conn, it["app_id"], it["name"])
    conn.commit()
    return new


def refresh_prices(conn, steam: SteamClient, cfg: Config, cc: str, limit: int = 2000) -> dict:
    """Check the stalest games first. Priority: games currently on sale (their prices move at sale boundaries)."""
    ids = [r["app_id"] for r in conn.execute(
        """SELECT g.app_id FROM games g LEFT JOIN price_state s ON s.app_id=g.app_id AND s.cc=?
           WHERE g.is_free=0 AND (g.type IS NULL OR g.type IN ('game','dlc'))
           ORDER BY COALESCE(s.checked_at, 0) ASC LIMIT ?""", (cc, limit))]
    changed = checked = 0
    for i in range(0, len(ids), 50):
        if _stop:
            break
        chunk = ids[i:i + 50]
        res = steam.prices(chunk, cc)
        for aid, obs in res.items():
            if obs:
                changed += int(service.record_price(conn, aid, cc, obs))
            else:
                service.mark_checked_no_price(conn, aid, cc)
            checked += 1
        conn.commit()
    return {"cc": cc, "checked": checked, "changed": changed}


def refresh_details(conn, steam: SteamClient, cfg: Config) -> int:
    cutoff = db.now() - DETAILS_MAX_AGE
    rows = conn.execute(
        "SELECT app_id FROM games WHERE details_updated_at IS NULL OR details_updated_at < ? "
        "ORDER BY details_updated_at IS NOT NULL, details_updated_at LIMIT ?", (cutoff, cfg.details_per_cycle)).fetchall()
    n = 0
    for r in rows:
        if _stop:
            break
        try:
            d = steam.details(r["app_id"], cfg.default_cc)
        except SteamBlocked:
            raise
        except SteamError as e:
            log.warning("details(%s) failed: %s", r["app_id"], e)
            continue
        if d is None:
            # unknown / removed / region-locked: stamp it so we don't retry every cycle
            conn.execute("UPDATE games SET details_updated_at=?, type=COALESCE(type,'unknown') WHERE app_id=?",
                         (db.now(), r["app_id"]))
        else:
            service.upsert_details(conn, d)
            if d["price"]:
                service.record_price(conn, r["app_id"], cfg.default_cc, d["price"])
            if cfg.itad_key:
                for cc in cfg.regions:
                    service.backfill_history(conn, r["app_id"], cc, cfg.itad_key)
        conn.commit()
        n += 1
    return n


def refresh_social(conn, steam: SteamClient, cfg: Config, limit: int = 40) -> int:
    """Player counts + review summary for the most relevant games (on sale first)."""
    cutoff = db.now() - SOCIAL_MAX_AGE
    rows = conn.execute(
        """SELECT g.app_id FROM games g LEFT JOIN price_state s ON s.app_id=g.app_id AND s.cc=?
           WHERE g.details_updated_at IS NOT NULL AND g.type='game'
             AND (g.players_checked_at IS NULL OR g.players_checked_at < ?)
           ORDER BY COALESCE(s.discount,0) DESC, COALESCE(g.players_checked_at,0) LIMIT ?""",
        (cfg.default_cc, cutoff, limit)).fetchall()
    n = 0
    for r in rows:
        if _stop:
            break
        try:
            players = steam.players(r["app_id"])
            rev = steam.reviews(r["app_id"])
        except SteamBlocked:
            raise
        except SteamError:
            continue
        conn.execute(
            """UPDATE games SET current_players=?, players_checked_at=?,
               review_desc=COALESCE(?, review_desc), reviews_positive=COALESCE(?, reviews_positive),
               reviews_negative=COALESCE(?, reviews_negative) WHERE app_id=?""",
            (players, db.now(), (rev or {}).get("desc"), (rev or {}).get("positive"),
             (rev or {}).get("negative"), r["app_id"]))
        conn.commit()
        n += 1
    return n


def refresh_external_lows(conn, limit: int = 15) -> int:
    rows = conn.execute(
        "SELECT g.app_id FROM games g LEFT JOIN external_lows e ON e.app_id=g.app_id "
        "WHERE e.app_id IS NULL AND g.type='game' AND g.is_free=0 LIMIT ?", (limit,)).fetchall()
    for r in rows:
        low = external.cheapshark_lowest(r["app_id"])
        conn.execute("INSERT OR REPLACE INTO external_lows(app_id, source, price_usd_cents, low_ts, fetched_at) "
                     "VALUES(?, 'cheapshark', ?, ?, ?)",
                     (r["app_id"], (low or {}).get("price_usd_cents"), (low or {}).get("ts"), db.now()))
        conn.commit()
    return len(rows)


def run_cycle(cfg: Config, steam: SteamClient | None = None) -> dict:
    steam = steam or SteamClient(cfg)
    conn = db.connect(cfg.db_path)
    summary: dict = {}
    try:
        summary["discovered"] = discover(conn, steam, cfg)
        summary["details"] = refresh_details(conn, steam, cfg)
        summary["prices"] = [refresh_prices(conn, steam, cfg, cc) for cc in cfg.regions]
        summary["social"] = refresh_social(conn, steam, cfg)
        summary["external_lows"] = refresh_external_lows(conn)
    finally:
        conn.close()
    return summary


def main(argv=None) -> int:
    global _stop
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--once", action="store_true")
    g.add_argument("--loop", action="store_true")
    g.add_argument("--add", nargs="+", type=int, metavar="APPID")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    db.init_db(cfg.db_path)

    def _sig(*_):
        global _stop
        _stop = True
        log.info("stopping after current batch...")

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    if args.add:
        steam = SteamClient(cfg)
        conn = db.connect(cfg.db_path)
        for aid in args.add:
            ok = service.ensure_game(conn, steam, cfg, aid)
            log.info("add %s -> %s", aid, "ok" if ok else "not found")
        return 0

    while True:
        t0 = time.time()
        try:
            log.info("cycle done: %s", run_cycle(cfg))
        except SteamBlocked:
            log.error("Steam blocked us (403). Sleeping 1h.")
            time.sleep(3600)
        except Exception:  # keep the service alive no matter what
            log.exception("cycle failed")
        if args.once or _stop:
            return 0
        sleep = max(60, cfg.collector_interval - (time.time() - t0))
        for _ in range(int(sleep)):
            if _stop:
                return 0
            time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
