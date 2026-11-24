from app import steam

DETAILS = {"620": {"success": True, "data": {
    "type": "game", "name": "Portal 2", "is_free": False,
    "short_description": "The <b>sequel</b>", "header_image": "https://x/y.jpg",
    "developers": ["Valve"], "publishers": ["Valve"],
    "platforms": {"windows": True, "mac": True, "linux": True},
    "metacritic": {"score": 95}, "genres": [{"id": "1", "description": "Action"}],
    "categories": [{"id": 2, "description": "Single-player"}],
    "release_date": {"coming_soon": False, "date": "19 Apr, 2011"},
    "price_overview": {"currency": "USD", "initial": 1999, "final": 499, "discount_percent": 75,
                       "final_formatted": "$4.99"}}}}


def test_parse_details():
    d = steam.parse_details(620, DETAILS)
    assert d["name"] == "Portal 2" and d["short_description"] == "The sequel"
    assert d["platforms"] == ["windows", "mac", "linux"]
    assert d["release_ts"] == 1303171200
    assert d["price"] == {"currency": "USD", "initial": 1999, "final": 499, "discount": 75, "formatted": "$4.99"}


def test_parse_details_failure_and_garbage():
    assert steam.parse_details(1, {"1": {"success": False}}) is None
    assert steam.parse_details(1, None) is None
    assert steam.parse_details(1, {"1": {"success": True, "data": []}}) is None


def test_free_game_has_no_price():
    p = {"7": {"success": True, "data": {"type": "game", "name": "F2P", "is_free": True}}}
    assert steam.parse_details(7, p)["price"] is None
    assert steam.parse_price_overview([]) is None


def test_release_date_formats():
    assert steam.parse_release_date({"date": "Mar 5, 2020"})[1] is not None
    assert steam.parse_release_date({"date": "2020"})[1] is not None
    assert steam.parse_release_date({"date": "Coming soon", "coming_soon": True}) == ("Coming soon", None)


def test_featured_and_search():
    f = steam.parse_featured({"specials": {"items": [{"id": 1, "name": "A", "type": 0}, {"id": 2, "type": 1}]}})
    assert [i["app_id"] for i in f["specials"]] == [1]
    s = steam.parse_search({"items": [{"id": 5, "name": "X", "type": "app", "tiny_image": "u"}, {"id": 6, "type": "sub"}]})
    assert [i["app_id"] for i in s] == [5]


class _Resp:
    def __init__(self, code, body=None, headers=None):
        self.status_code, self._b, self.headers = code, body, headers or {}

    def json(self):
        return self._b

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _Sess:
    def __init__(self, script):
        self.script, self.headers, self.calls = list(script), {}, []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        return self.script.pop(0)


def test_bulk_prices_bisect_on_null_payload(cfg, monkeypatch):
    monkeypatch.setattr(steam.time, "sleep", lambda *_: None)
    ok = lambda i: {str(i): {"success": True, "data": {"price_overview": {"currency": "USD", "initial": 100, "final": 50, "discount_percent": 50}}}}
    # first request (2 ids) returns null -> bisect -> two single-id requests
    sess = _Sess([_Resp(200, None), _Resp(200, ok(1)), _Resp(200, ok(2))])
    c = steam.SteamClient(cfg, session=sess)
    res = c.prices([1, 2], "us")
    assert res[1]["discount"] == 50 and res[2]["final"] == 50


def test_403_raises_blocked(cfg):
    c = steam.SteamClient(cfg, session=_Sess([_Resp(403)]))
    import pytest
    with pytest.raises(steam.SteamBlocked):
        c.details(1, "us")
