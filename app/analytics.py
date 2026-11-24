from __future__ import annotations

from statistics import median

DAY = 86400

# A point is (ts, initial, final, discount) in the region's minor currency units, oldest first.
Point = tuple[int, int, int, int]


def build_episodes(points: list[Point]) -> list[dict]:
    """Contiguous runs of discount > 0. 'end' is None while the sale is still running."""
    episodes: list[dict] = []
    cur: dict | None = None
    for ts, initial, final, disc in points:
        if disc > 0:
            if cur is None:
                cur = {"start": ts, "end": None, "depth": disc, "min_final": final, "initial": initial}
            else:
                cur["depth"] = max(cur["depth"], disc)
                cur["min_final"] = min(cur["min_final"], final)
        elif cur is not None:
            cur["end"] = ts
            episodes.append(cur)
            cur = None
    if cur is not None:
        episodes.append(cur)
    return episodes


def price_changes(points: list[Point]) -> list[dict]:
    """Human-readable change log: sale starts/ends, deeper/shallower sales, and base-price hikes/cuts."""
    out = []
    prev: Point | None = None
    for p in points:
        ts, initial, final, disc = p
        if prev is None:
            out.append({"ts": ts, "kind": "first_seen", "initial": initial, "final": final, "discount": disc})
        else:
            _, p_init, p_final, p_disc = prev
            if initial > p_init:
                kind = "base_hike"
            elif initial < p_init:
                kind = "base_cut"
            elif p_disc == 0 and disc > 0:
                kind = "sale_start"
            elif p_disc > 0 and disc == 0:
                kind = "sale_end"
            elif disc > p_disc:
                kind = "deeper_sale"
            elif disc < p_disc:
                kind = "shallower_sale"
            else:
                kind = "price_change"
            out.append({"ts": ts, "kind": kind, "initial": initial, "final": final, "discount": disc,
                        "from_final": p_final, "from_initial": p_init, "from_discount": p_disc})
        prev = p
    return out


def stats(points: list[Point], now: int, external_low_usd_cents: int | None = None, currency: str = "") -> dict:
    if not points:
        return {}
    first_ts = points[0][0]
    finals = [p[2] for p in points]
    episodes = build_episodes(points)
    # time-weighted share of time on sale and time-weighted average price
    on_sale_secs = 0
    weighted = 0
    total = 0
    for i, (ts, _init, fin, disc) in enumerate(points):
        end = points[i + 1][0] if i + 1 < len(points) else now
        dur = max(end - ts, 0)
        total += dur
        weighted += fin * dur
        if disc > 0:
            on_sale_secs += dur
    low_idx = min(range(len(points)), key=lambda i: (points[i][2], -points[i][0]))
    cur_final = points[-1][2]
    done = [e for e in episodes if e["end"] is not None]
    last_sale_end = max((e["end"] for e in done), default=None)
    gaps = [b["start"] - a["start"] for a, b in zip(episodes, episodes[1:])]
    hikes = [c for c in price_changes(points) if c["kind"] == "base_hike"]
    return {
        "first_seen": first_ts,
        "observed_days": round((now - first_ts) / DAY, 1),
        "all_time_low": {"final": finals[low_idx], "discount": points[low_idx][3], "ts": points[low_idx][0]},
        "is_at_all_time_low": cur_final <= min(finals),
        "highest_base": max(p[1] for p in points),
        "lowest_base": min(p[1] for p in points),
        "average_price": round(weighted / total) if total else cur_final,
        "pct_time_on_sale": round(100 * on_sale_secs / total, 1) if total else 0.0,
        "sale_count": len(episodes),
        "avg_sale_depth": round(sum(e["depth"] for e in episodes) / len(episodes), 1) if episodes else 0,
        "max_sale_depth": max((e["depth"] for e in episodes), default=0),
        "median_days_between_sales": round(median(gaps) / DAY, 1) if gaps else None,
        "last_sale_ended": last_sale_end,
        "days_since_last_sale": round((now - last_sale_end) / DAY, 1) if last_sale_end else None,
        "base_hike_count": len(hikes),
        "currency": currency,
        "external_low_usd_cents": external_low_usd_cents,
    }
