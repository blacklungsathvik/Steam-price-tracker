from __future__ import annotations

import hmac
import os
import threading
import time
from collections import defaultdict, deque

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from . import db, service
from .config import Config, load_config
from .steam import SteamClient, SteamError
from .steam_calendar import load_events, upcoming

STATIC = os.path.join(os.path.dirname(__file__), "static")   # legacy no-build UI (fallback)
DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")  # React build


def ui_dir() -> str:
    return DIST if os.path.isfile(os.path.join(DIST, "index.html")) else STATIC


class RateLimiter:
    """Tiny in-process sliding-window limiter (per worker). Put a real limiter at your proxy too."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            if len(self.hits) > 10000:  # bound memory
                self.hits.clear()
            return True


def create_app(cfg: Config | None = None, steam: SteamClient | None = None) -> Flask:
    cfg = cfg or load_config()
    db.init_db(cfg.db_path)
    app = Flask(__name__, static_folder=None)
    app.config["JSON_SORT_KEYS"] = False
    if cfg.trust_proxy:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=cfg.trust_proxy, x_proto=cfg.trust_proxy, x_host=cfg.trust_proxy)
    steam_client = steam or SteamClient(cfg)
    limiter = RateLimiter(cfg.live_rate_per_min)
    app.extensions["cfg"] = cfg

    def conn():
        if "db" not in g:
            g.db = db.connect(cfg.db_path)
        return g.db

    @app.teardown_appcontext
    def _close(_exc):
        c = g.pop("db", None)
        if c is not None:
            c.close()

    @app.after_request
    def _headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' https://shared.akamai.steamstatic.com "
            "https://cdn.akamai.steamstatic.com https://cdn.cloudflare.steamstatic.com data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        return resp

    def region() -> str:
        cc = (request.args.get("cc") or cfg.default_cc).lower()
        return cc if cc in cfg.regions else cfg.default_cc

    def cacheable(resp, seconds=60):
        resp.headers["Cache-Control"] = f"public, max-age={seconds}"
        return resp

    def live_allowed() -> bool:
        return cfg.live_fetch and limiter.allow(request.remote_addr or "?")

    def card(r, currency_divisor_cfg=cfg) -> dict:
        cur = r["currency"] or "USD"
        players = None
        try:
            players = r["current_players"] if r["current_players"] else None
        except (KeyError, IndexError):
            pass
        is_free = bool(r["is_free"]) if "is_free" in r.keys() and r["is_free"] is not None else False
        raw_final = r["final"]
        raw_initial = r["initial"]

        if is_free:
            final = 0
            initial = 0
        elif raw_final is not None and raw_final > 0:
            final = raw_final
            initial = raw_initial if (raw_initial and raw_initial > 0) else raw_final
        else:
            final = None
            initial = None

        return {
            "app_id": r["app_id"], "name": r["name"], "image": r["header_image"],
            "currency": cur, "divisor": cfg.divisor(cur),
            "is_free": is_free,
            "initial": initial, "final": final, "discount": r["discount"] or 0,
            "changed_at": r["changed_at"],
            "players": players,
        }

    # ------------------------------------------------------------------ API
    @app.get("/api/health")
    def health():
        n = conn().execute("SELECT COUNT(*) c FROM games").fetchone()["c"]
        return jsonify(status="ok", games=n)

    @app.get("/api/meta")
    def meta():
        c = conn()
        row = c.execute("SELECT COUNT(*) games, (SELECT COUNT(*) FROM prices) points, "
                        "(SELECT MAX(checked_at) FROM price_state) last_check FROM games").fetchone()
        return jsonify(regions=list(cfg.regions), default_region=cfg.default_cc, games=row["games"],
                       price_points=row["points"], last_check=row["last_check"])

    @app.get("/api/calendar")
    def calendar():
        evs = upcoming(load_events(cfg.events_file), db.now(), 400)
        return cacheable(jsonify(events=[e.as_dict() for e in evs]), 600)

    @app.get("/api/deals")
    def deals():
        cc = region()
        c = conn()
        if live_allowed():
            count = c.execute("SELECT COUNT(*) cnt FROM price_state WHERE cc=? AND currency!=''", (cc,)).fetchone()["cnt"]
            if count < 20:
                top_ids = [r["app_id"] for r in c.execute(
                    "SELECT app_id FROM games ORDER BY COALESCE(current_players, 0) DESC, app_id DESC LIMIT 50"
                ).fetchall()]
                if top_ids:
                    try:
                        prices_map = steam_client.prices(top_ids, cc)
                        for aid, obs in prices_map.items():
                            if obs:
                                service.record_price(c, aid, cc, obs)
                            else:
                                service.mark_checked_no_price(c, aid, cc)
                        c.commit()
                    except Exception as e:
                        log.warning("live populate for %s failed: %s", cc, e)

        try:
            min_disc = max(0, min(100, int(request.args.get("min_discount", 0))))
            limit = max(1, min(100, int(request.args.get("limit", 24))))
            offset = max(0, int(request.args.get("offset", 0)))
        except ValueError:
            return jsonify(error="bad parameter"), 400
        sort = request.args.get("sort", "popular")
        order = {
            "popular": "COALESCE(g.current_players, 0) DESC, COALESCE(g.reviews_positive, 0) DESC, COALESCE(s.discount, 0) DESC, g.name ASC",
            "discount": "COALESCE(s.discount, 0) DESC, s.final ASC",
            "price": "(CASE WHEN s.final IS NULL OR s.final = 0 THEN 99999999 ELSE s.final END) ASC",
            "recent": "COALESCE(s.changed_at, g.created_at) DESC",
            "name": "g.name COLLATE NOCASE ASC"
        }.get(sort, "COALESCE(s.discount, 0) DESC")
        low_only = request.args.get("all_time_low") == "1"

        if min_disc > 0:
            sql = """SELECT g.app_id, g.name, g.header_image, g.is_free, s.currency, s.initial, s.final, s.discount, s.changed_at,
                            COALESCE(g.current_players, 0) current_players
                     FROM price_state s JOIN games g ON g.app_id=s.app_id
                     WHERE s.cc=? AND s.currency!='' AND s.final > 0 AND s.discount>=? AND g.name IS NOT NULL"""
            params: list = [cc, min_disc]
        else:
            sql = """SELECT g.app_id, g.name, g.header_image, g.is_free, s.currency, s.initial, s.final, COALESCE(s.discount, 0) discount,
                            s.changed_at, COALESCE(g.current_players, 0) current_players
                     FROM games g
                     LEFT JOIN price_state s ON g.app_id=s.app_id AND s.cc=?
                     WHERE g.name IS NOT NULL
                       AND ((s.currency!='' AND s.final > 0) OR g.is_free=1)"""
            params = [cc]

        if low_only:
            sql += """ AND s.final <= (SELECT MIN(final) FROM prices p WHERE p.app_id=s.app_id AND p.cc=s.cc)
                       AND (SELECT COUNT(*) FROM prices p WHERE p.app_id=s.app_id AND p.cc=s.cc) > 1"""
        sql += f" ORDER BY {order} LIMIT ? OFFSET ?"
        rows = conn().execute(sql, params + [limit, offset]).fetchall()
        has_more = len(rows) == limit
        return cacheable(jsonify(cc=cc, deals=[card(r) for r in rows], has_more=has_more, offset=offset, limit=limit), 30)

    @app.get("/api/search")
    def search():
        q = (request.args.get("q") or "").strip()[:80]
        if len(q) < 2:
            return jsonify(results=[])
        cc = region()
        results = []
        c = conn()

        if q.isdigit():
            aid = int(q)
            row_aid = c.execute(
                """SELECT g.app_id, g.name, g.header_image, s.currency, s.initial, s.final, s.discount
                   FROM games g LEFT JOIN price_state s ON s.app_id=g.app_id AND s.cc=?
                   WHERE g.app_id=?""", (cc, aid)).fetchone()
            if row_aid:
                results.append({
                    "app_id": row_aid["app_id"], "name": row_aid["name"], "image": row_aid["header_image"],
                    "currency": row_aid["currency"], "divisor": cfg.divisor(row_aid["currency"]) if row_aid["currency"] else 100,
                    "final": row_aid["final"], "discount": row_aid["discount"], "tracked": True
                })
            elif live_allowed():
                try:
                    d = steam_client.details(aid, cc)
                    if d:
                        service.ensure_game(c, steam_client, cfg, aid, cc)
                        results.append({
                            "app_id": aid, "name": d["name"], "image": d.get("header_image"),
                            "currency": (d.get("price") or {}).get("currency"),
                            "divisor": cfg.divisor((d.get("price") or {}).get("currency") or "USD"),
                            "final": (d.get("price") or {}).get("final"),
                            "discount": (d.get("price") or {}).get("discount", 0),
                            "tracked": True
                        })
                except Exception:
                    pass

        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = c.execute(
            """SELECT g.app_id, g.name, g.header_image, s.currency, s.initial, s.final, s.discount, s.changed_at
               FROM games g LEFT JOIN price_state s ON s.app_id=g.app_id AND s.cc=?
               WHERE g.name LIKE ? ESCAPE '\\' ORDER BY (g.name LIKE ? ESCAPE '\\') DESC, g.name LIMIT 12""",
            (cc, like, q.replace("%", "") + "%")).fetchall()
        seen = {r["app_id"] for r in results}
        for r in rows:
            if r["app_id"] not in seen:
                seen.add(r["app_id"])
                results.append({
                    "app_id": r["app_id"], "name": r["name"], "image": r["header_image"],
                    "currency": r["currency"], "divisor": cfg.divisor(r["currency"]) if r["currency"] else 100,
                    "final": r["final"], "discount": r["discount"], "tracked": True
                })

        if len(results) < 8 and live_allowed():
            try:
                for it in steam_client.search(q, cc)[:10]:
                    if it["app_id"] not in seen:
                        seen.add(it["app_id"])
                        results.append({
                            "app_id": it["app_id"], "name": it["name"], "image": it["image"],
                            "tracked": False
                        })
            except SteamError:
                pass
        return jsonify(results=results)

    @app.get("/api/games/<int:app_id>")
    def game(app_id: int):
        c = conn()
        cc = region()
        if not service.game_row(c, app_id) or not c.execute(
                "SELECT 1 FROM games WHERE app_id=? AND details_updated_at IS NOT NULL", (app_id,)).fetchone():
            if not live_allowed():
                return jsonify(error="Game not tracked yet. Try again shortly."), 429
            try:
                if not service.ensure_game(c, steam_client, cfg, app_id, cc):
                    return jsonify(error="Game not found on Steam"), 404
            except SteamError:
                return jsonify(error="Steam is not responding right now"), 502
        else:
            st = c.execute("SELECT 1 FROM price_state WHERE app_id=? AND cc=? AND currency!=''", (app_id, cc)).fetchone()
            if not st and live_allowed():
                try:
                    p = steam_client.prices([app_id], cc).get(app_id)
                    if p:
                        service.record_price(c, app_id, cc, p)
                        c.commit()
                except Exception:
                    pass

        payload = service.game_payload(c, cfg, app_id, cc)
        if not payload:
            return jsonify(error="Game not found"), 404
        return cacheable(jsonify(payload), 30)

    @app.get("/api/games/<int:app_id>/regions")
    def all_regions(app_id: int):
        """Return current price in every tracked region for the price comparison table."""
        rows = conn().execute(
            """SELECT s.cc, s.currency, s.initial, s.final, s.discount, s.changed_at,
                      s.checked_at, cfg.divisor
               FROM price_state s
               WHERE s.app_id=? AND s.currency!=''
               ORDER BY s.cc""",
            (app_id,)).fetchall()
        result = []
        for r in rows:
            result.append({
                "cc": r["cc"],
                "currency": r["currency"],
                "divisor": cfg.divisor(r["currency"]),
                "initial": r["initial"],
                "final": r["final"],
                "discount": r["discount"],
                "changed_at": r["changed_at"],
                "checked_at": r["checked_at"],
            })
        return cacheable(jsonify(cc_prices=result, regions=list(cfg.regions)), 60)

    @app.get("/api/games/<int:app_id>/history")
    def history(app_id: int):
        cc = region()
        pts = service.load_points(conn(), app_id, cc)
        cur = conn().execute("SELECT currency FROM price_state WHERE app_id=? AND cc=?", (app_id, cc)).fetchone()
        currency = cur["currency"] if cur else ""
        return cacheable(jsonify(cc=cc, currency=currency, divisor=cfg.divisor(currency) if currency else 100,
                                 points=[{"ts": t, "initial": i, "final": f, "discount": d} for t, i, f, d in pts],
                                 now=db.now()), 30)

    @app.post("/api/admin/track")
    def admin_track():
        token = request.headers.get("X-Admin-Token", "")
        if not cfg.admin_token or not hmac.compare_digest(token, cfg.admin_token):
            return jsonify(error="forbidden"), 403
        body = request.get_json(silent=True) or {}
        ids = body.get("app_ids")
        if not isinstance(ids, list) or not ids or len(ids) > 50 or not all(isinstance(i, int) and i > 0 for i in ids):
            return jsonify(error="app_ids must be 1-50 positive integers"), 400
        c = conn()
        out = {}
        for aid in ids:
            try:
                out[str(aid)] = service.ensure_game(c, steam_client, cfg, aid)
            except SteamError:
                out[str(aid)] = False
        return jsonify(results=out)

    @app.errorhandler(404)
    def nf(_e):
        if request.path.startswith("/api/"):
            return jsonify(error="not found"), 404
        return send_from_directory(ui_dir(), "index.html")  # SPA fallback

    # ------------------------------------------------------------------ frontend
    @app.get("/")
    def index():
        return send_from_directory(ui_dir(), "index.html")

    @app.get("/assets/<path:name>")
    def assets(name):
        resp = send_from_directory(os.path.join(DIST, "assets"), name)
        resp.headers["Cache-Control"] = "public, max-age=300"
        return resp

    @app.get("/static/<path:name>")
    def static_files(name):
        resp = send_from_directory(STATIC, name)
        resp.headers["Cache-Control"] = "public, max-age=300"
        return resp

    return app
