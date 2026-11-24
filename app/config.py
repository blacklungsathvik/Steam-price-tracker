from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    db_path: str = "data/tracker.db"
    regions: tuple = ("us",)
    request_delay: float = 1.6
    user_agent: str = "SteamPriceTracker/1.0 (+self-hosted; polite client)"
    itad_key: str = ""
    trust_proxy: int = 0
    live_fetch: bool = True
    live_rate_per_min: int = 20
    admin_token: str = ""
    collector_interval: int = 10800
    details_per_cycle: int = 60
    divisors: dict | None = None
    events_file: str = os.path.join(os.path.dirname(__file__), "..", "data", "steam_events.json")

    @property
    def default_cc(self) -> str:
        return self.regions[0]

    def divisor(self, currency: str) -> int:
        """Minor-unit divisor for a currency (Steam reports prices in minor units)."""
        return int((self.divisors or {}).get(currency, 100))


def load_config(**overrides) -> Config:
    env = os.environ
    try:
        divisors = json.loads(env.get("CURRENCY_DIVISORS") or "{}")
    except json.JSONDecodeError:
        divisors = {}
    regions = tuple(r.strip().lower() for r in env.get("TRACK_REGIONS", "us").split(",") if r.strip())
    cfg = Config(
        db_path=env.get("DB_PATH", "data/tracker.db"),
        regions=regions or ("us",),
        request_delay=float(env.get("STEAM_REQUEST_DELAY", "1.6")),
        itad_key=env.get("ITAD_API_KEY", ""),
        trust_proxy=int(env.get("TRUST_PROXY", "0")),
        live_fetch=_bool(env.get("LIVE_FETCH"), True),
        live_rate_per_min=int(env.get("LIVE_RATE_PER_MIN", "20")),
        admin_token=env.get("ADMIN_TOKEN", ""),
        collector_interval=int(env.get("COLLECTOR_INTERVAL_SECONDS", "10800")),
        details_per_cycle=int(env.get("DETAILS_PER_CYCLE", "60")),
        divisors=divisors,
    )
    return replace(cfg, **overrides) if overrides else cfg
