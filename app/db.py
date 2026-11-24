from __future__ import annotations

import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    app_id INTEGER PRIMARY KEY,
    name TEXT,
    type TEXT,
    is_free INTEGER DEFAULT 0,
    short_description TEXT,
    header_image TEXT,
    developers TEXT, publishers TEXT, genres TEXT, categories TEXT, platforms TEXT,
    release_date TEXT, release_ts INTEGER,
    metacritic INTEGER,
    review_desc TEXT, reviews_positive INTEGER, reviews_negative INTEGER,
    current_players INTEGER, players_checked_at INTEGER,
    details_updated_at INTEGER,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_games_name ON games(name COLLATE NOCASE);

-- Change-only price log: a row is written only when initial/final/discount differ from the last row.
CREATE TABLE IF NOT EXISTS prices (
    app_id INTEGER NOT NULL,
    cc TEXT NOT NULL,
    ts INTEGER NOT NULL,
    currency TEXT NOT NULL,
    initial INTEGER NOT NULL,
    final INTEGER NOT NULL,
    discount INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'steam',
    PRIMARY KEY (app_id, cc, ts)
);

-- Latest observation per (game, region) plus when we last looked.
CREATE TABLE IF NOT EXISTS price_state (
    app_id INTEGER NOT NULL,
    cc TEXT NOT NULL,
    currency TEXT NOT NULL,
    initial INTEGER NOT NULL,
    final INTEGER NOT NULL,
    discount INTEGER NOT NULL,
    formatted TEXT,
    changed_at INTEGER NOT NULL,
    checked_at INTEGER NOT NULL,
    PRIMARY KEY (app_id, cc)
);
CREATE INDEX IF NOT EXISTS idx_state_checked ON price_state(cc, checked_at);
CREATE INDEX IF NOT EXISTS idx_state_discount ON price_state(cc, discount);

CREATE TABLE IF NOT EXISTS external_lows (
    app_id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    price_usd_cents INTEGER,
    low_ts INTEGER,
    fetched_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS backfill (
    app_id INTEGER NOT NULL,
    cc TEXT NOT NULL,
    source TEXT NOT NULL,
    done_at INTEGER NOT NULL,
    PRIMARY KEY (app_id, cc, source)
);
"""


def now() -> int:
    return int(time.time())


def connect(path: str) -> sqlite3.Connection:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db(path: str) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
