from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

STORE = "https://store.steampowered.com"
API = "https://api.steampowered.com"
MAX_BATCH = 50  # appids per bulk price request


class SteamError(Exception):
    pass


class SteamBlocked(SteamError):
    """Steam refused us (403) - back off for a long time."""


# --------------------------------------------------------------------------- pure parsers

def parse_price_overview(po: dict | None) -> dict | None:
    if not isinstance(po, dict) or "final" not in po:
        return None
    final = int(po["final"])
    initial = int(po.get("initial", final))
    return {
        "currency": po.get("currency", ""),
        "initial": initial,
        "final": final,
        "discount": int(po.get("discount_percent", 0)),
        "formatted": po.get("final_formatted"),
    }


_DATE_FORMATS = ("%d %b, %Y", "%b %d, %Y", "%d %B, %Y", "%B %d, %Y", "%b %Y", "%B %Y", "%Y")


def parse_release_date(rd: dict | None) -> tuple[str | None, int | None]:
    if not isinstance(rd, dict):
        return None, None
    text = (rd.get("date") or "").strip()
    if rd.get("coming_soon") or not text:
        return text or None, None
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return text, int(dt.timestamp())
        except ValueError:
            continue
    return text, None


def _desc_list(items) -> list[str]:
    return [i.get("description", "") for i in items or [] if isinstance(i, dict) and i.get("description")]


def parse_details(app_id: int, payload: dict | None) -> dict | None:
    """Normalise an appdetails response. Returns None for unknown/removed/region-locked apps."""
    if not isinstance(payload, dict):
        return None
    entry = payload.get(str(app_id))
    if not isinstance(entry, dict) or not entry.get("success"):
        return None
    d = entry.get("data")
    if not isinstance(d, dict):
        return None
    release_text, release_ts = parse_release_date(d.get("release_date"))
    plat = d.get("platforms") or {}
    meta = d.get("metacritic") or {}
    return {
        "app_id": app_id,
        "name": d.get("name"),
        "type": d.get("type"),
        "is_free": bool(d.get("is_free")),
        "short_description": re.sub(r"<[^>]+>", "", d.get("short_description") or ""),
        "header_image": d.get("header_image"),
        "developers": d.get("developers") or [],
        "publishers": [p for p in (d.get("publishers") or []) if p],
        "genres": _desc_list(d.get("genres")),
        "categories": _desc_list(d.get("categories"))[:12],
        "platforms": [k for k in ("windows", "mac", "linux") if plat.get(k)],
        "release_date": release_text,
        "release_ts": release_ts,
        "metacritic": meta.get("score"),
        "price": parse_price_overview(d.get("price_overview")),
    }


def parse_featured(payload: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for key in ("specials", "top_sellers", "new_releases", "coming_soon"):
        cat = payload.get(key) if isinstance(payload, dict) else None
        items = (cat or {}).get("items") or []
        out[key] = [
            {"app_id": int(i["id"]), "name": i.get("name"), "type": i.get("type", 0)}
            for i in items
            if isinstance(i, dict) and i.get("id") and i.get("type", 0) == 0  # type 0 = app
        ]
    return out


def parse_search(payload: dict) -> list[dict]:
    res = []
    for i in (payload or {}).get("items", []) or []:
        if not isinstance(i, dict) or not i.get("id"):
            continue
        if i.get("type") not in (None, "app"):
            continue
        res.append({"app_id": int(i["id"]), "name": i.get("name"), "image": i.get("tiny_image")})
    return res


# --------------------------------------------------------------------------- HTTP client

class SteamClient:
    def __init__(self, cfg, session: requests.Session | None = None):
        self.cfg = cfg
        self.s = session or requests.Session()
        self.s.headers.update({"User-Agent": cfg.user_agent, "Accept": "application/json"})
        self._lock = threading.Lock()
        self._last = 0.0

    def _throttle(self) -> None:
        with self._lock:
            wait = self._last + self.cfg.request_delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def _get(self, url: str, params: dict, timeout: float = 12, retries: int = 3):
        last_exc: Exception | None = None
        for attempt in range(retries):
            self._throttle()
            try:
                r = self.s.get(url, params=params, timeout=timeout)
            except requests.RequestException as e:
                last_exc = e
                time.sleep(min(2 ** attempt * 2, 20))
                continue
            if r.status_code == 403:
                raise SteamBlocked("Steam returned 403")
            if r.status_code == 429 or r.status_code >= 500:
                retry_after = r.headers.get("Retry-After")
                delay = int(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt * 5
                log.warning("Steam %s on %s; sleeping %ss", r.status_code, url, delay)
                time.sleep(min(delay, 120))
                last_exc = SteamError(f"HTTP {r.status_code}")
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            try:
                return r.json()
            except ValueError as e:
                last_exc = e
                continue
        raise SteamError(f"giving up on {url}: {last_exc}")

    # ---- endpoints
    def prices(self, app_ids: list[int], cc: str) -> dict[int, dict | None]:
        """Bulk price lookup. Maps app_id -> price dict, or None when the app has no price
        (free, unreleased, or not sold in that region). Apps missing from the result were not answered."""
        result: dict[int, dict | None] = {}
        for i in range(0, len(app_ids), MAX_BATCH):
            chunk = app_ids[i:i + MAX_BATCH]
            result.update(self._prices_chunk(chunk, cc))
        return result

    def _prices_chunk(self, chunk: list[int], cc: str) -> dict[int, dict | None]:
        params = {"appids": ",".join(map(str, chunk)), "cc": cc, "filters": "price_overview"}
        try:
            payload = self._get(f"{STORE}/api/appdetails", params)
        except SteamBlocked:
            raise
        except SteamError:
            payload = None
        if not isinstance(payload, dict):
            if len(chunk) == 1:
                return {}
            mid = len(chunk) // 2  # Steam sometimes rejects big batches: bisect
            return {**self._prices_chunk(chunk[:mid], cc), **self._prices_chunk(chunk[mid:], cc)}
        out: dict[int, dict | None] = {}
        for aid in chunk:
            entry = payload.get(str(aid))
            if not isinstance(entry, dict):
                continue
            if not entry.get("success"):
                out[aid] = None
                continue
            data = entry.get("data")
            out[aid] = parse_price_overview(data.get("price_overview")) if isinstance(data, dict) else None
        return out

    def details(self, app_id: int, cc: str) -> dict | None:
        payload = self._get(f"{STORE}/api/appdetails", {"appids": app_id, "cc": cc, "l": "english"})
        return parse_details(app_id, payload)

    def search(self, term: str, cc: str) -> list[dict]:
        payload = self._get(f"{STORE}/api/storesearch/", {"term": term, "l": "english", "cc": cc})
        return parse_search(payload)

    def featured(self, cc: str) -> dict[str, list[dict]]:
        return parse_featured(self._get(f"{STORE}/api/featuredcategories", {"cc": cc, "l": "english"}))

    def reviews(self, app_id: int) -> dict | None:
        payload = self._get(
            f"{STORE}/appreviews/{app_id}",
            {"json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0},
        )
        qs = (payload or {}).get("query_summary")
        if not isinstance(qs, dict):
            return None
        return {
            "desc": qs.get("review_score_desc"),
            "positive": qs.get("total_positive"),
            "negative": qs.get("total_negative"),
        }

    def players(self, app_id: int) -> int | None:
        payload = self._get(f"{API}/ISteamUserStats/GetNumberOfCurrentPlayers/v1/", {"appid": app_id})
        resp = (payload or {}).get("response") or {}
        return resp.get("player_count") if resp.get("result") == 1 else None

    def app_list(self, api_key: str, max_results: int = 50000, last_appid: int = 0) -> tuple[list[dict], int, bool]:
        """Fetch Steam games catalog via official IStoreService/GetAppList/v1/."""
        if not api_key:
            return [], last_appid, False
        params = {
            "key": api_key,
            "max_results": min(max_results, 50000),
            "last_appid": last_appid,
            "include_games": 1,
            "include_dlc": 0,
            "include_software": 0,
        }
        try:
            payload = self._get(f"{API}/IStoreService/GetAppList/v1/", params)
        except SteamError as e:
            log.warning("GetAppList failed: %s", e)
            return [], last_appid, False
        resp = (payload or {}).get("response") or {}
        apps = resp.get("apps") or []
        have_more = bool(resp.get("have_more_results", False))
        last = int(resp.get("last_appid") or (apps[-1]["appid"] if apps else last_appid))
        return apps, last, have_more
