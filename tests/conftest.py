import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import db  # noqa: E402
from app.config import Config  # noqa: E402


@pytest.fixture
def cfg(tmp_path):
    return Config(db_path=str(tmp_path / "t.db"), regions=("us", "in"), request_delay=0, live_rate_per_min=3,
                  admin_token="secret", events_file=os.path.join(os.path.dirname(__file__), "..", "data", "steam_events.json"))


@pytest.fixture
def conn(cfg):
    db.init_db(cfg.db_path)
    c = db.connect(cfg.db_path)
    yield c
    c.close()


class FakeSteam:
    """Stands in for SteamClient. Prices are mutable so tests can simulate a sale starting."""

    def __init__(self):
        self.price = {620: {"currency": "USD", "initial": 1999, "final": 1999, "discount": 0, "formatted": "$19.99"}}
        self.calls = []

    def details(self, app_id, cc):
        self.calls.append(("details", app_id, cc))
        if app_id not in self.price:
            return None
        return {"app_id": app_id, "name": "Portal 2", "type": "game", "is_free": False,
                "short_description": "co-op puzzler", "header_image": "https://cdn.akamai.steamstatic.com/x.jpg",
                "developers": ["Valve"], "publishers": ["Valve"], "genres": ["Action"], "categories": ["Single-player"],
                "platforms": ["windows"], "release_date": "19 Apr, 2011", "release_ts": 1303171200,
                "metacritic": 95, "price": self.price[app_id]}

    def prices(self, ids, cc):
        return {i: self.price.get(i) for i in ids}

    def search(self, term, cc):
        return [{"app_id": 620, "name": "Portal 2", "image": None}]

    def featured(self, cc):
        return {"specials": [{"app_id": 620, "name": "Portal 2", "type": 0}], "top_sellers": [], "new_releases": [],
                "coming_soon": []}

    def players(self, app_id):
        return 1234

    def reviews(self, app_id):
        return {"desc": "Overwhelmingly Positive", "positive": 900, "negative": 100}


@pytest.fixture
def fake_steam():
    return FakeSteam()
