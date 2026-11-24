from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

CHEAPSHARK = "https://www.cheapshark.com/api/1.0"
ITAD = "https://api.isthereanydeal.com"
ITAD_STEAM_SHOP_ID = 61


def _iso_to_ts(s: str) -> int | None:
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp())
    except (ValueError, AttributeError):
        return None


def cheapshark_lowest(app_id: int, session: requests.Session | None = None, timeout: float = 10) -> dict | None:
    """Return {'price_usd_cents', 'ts'} for the all-time low CheapShark knows about, or None."""
    s = session or requests
    try:
        r = s.get(f"{CHEAPSHARK}/games", params={"steamAppID": app_id}, timeout=timeout)
        r.raise_for_status()
        games = r.json()
        if not games:
            return None
        r = s.get(f"{CHEAPSHARK}/games", params={"id": games[0]["gameID"]}, timeout=timeout)
        r.raise_for_status()
        low = (r.json() or {}).get("cheapestPriceEver") or {}
        if "price" not in low:
            return None
        return {"price_usd_cents": int(round(float(low["price"]) * 100)), "ts": int(low.get("date") or 0) or None}
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as e:
        log.info("cheapshark lookup failed for %s: %s", app_id, e)
        return None


def itad_history(app_id: int, cc: str, key: str, session: requests.Session | None = None,
                 timeout: float = 20) -> list[tuple[int, int, int, int, str]]:
    """Return [(ts, initial, final, discount, currency)] oldest-first for Steam in one country."""
    if not key:
        return []
    s = session or requests
    try:
        r = s.get(f"{ITAD}/games/lookup/v1", params={"key": key, "appid": app_id}, timeout=timeout)
        r.raise_for_status()
        body = r.json() or {}
        if not body.get("found"):
            return []
        gid = body["game"]["id"]
        r = s.get(
            f"{ITAD}/games/history/v2",
            params={"key": key, "id": gid, "country": cc.upper(), "shops": ITAD_STEAM_SHOP_ID,
                    "since": "2010-01-01T00:00:00Z"},
            timeout=timeout,
        )
        r.raise_for_status()
        rows = []
        for item in r.json() or []:
            ts = _iso_to_ts(item.get("timestamp"))
            deal = item.get("deal") or {}
            price, regular = deal.get("price") or {}, deal.get("regular") or {}
            if ts is None or "amount" not in price:
                continue
            final = price.get("amountInt", int(round(price["amount"] * 100)))
            initial = regular.get("amountInt", int(round(regular.get("amount", price["amount"]) * 100)))
            rows.append((ts, int(initial), int(final), int(deal.get("cut", 0)), price.get("currency", "")))
        rows.sort()
        return rows
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        log.info("ITAD history failed for %s: %s", app_id, e)
        return []
