from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean, median, pstdev

from .analytics import DAY, build_episodes
from .steam_calendar import DEPTH_MULT, SEASON_WINDOWS, TYPE_TO_SLOT, SEASONAL_TYPES, Event, season_slots, upcoming

TIERS = [5, 10, 15, 20, 25, 30, 33, 35, 40, 45, 50, 55, 60, 65, 66, 67, 70, 75, 80, 85, 90]
K_PRIOR = 3.0   # pseudo-observations of prior participation
P_CLAMP_LO = 0.05
P_CLAMP_HI = 0.95


def snap_tier(depth: float) -> int:
    return min(TIERS, key=lambda t: abs(t - depth))


def _clamp_p(p: float) -> float:
    """Keep all probabilities in [P_CLAMP_LO, P_CLAMP_HI]: never claim certainty."""
    return max(P_CLAMP_LO, min(P_CLAMP_HI, p))


def prior_participation(age_days: float | None) -> float:
    if age_days is None:
        return 0.55
    for limit, p in ((60, 0.08), (180, 0.25), (365, 0.45), (730, 0.65)):
        if age_days < limit:
            return p
    return 0.82


def prior_depth(age_days: float | None) -> float:
    if age_days is None:
        return 33.0
    for limit, d in ((90, 10.0), (365, 25.0), (730, 33.0), (1460, 50.0)):
        if age_days < limit:
            return d
    return 60.0


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def _overlaps(ep: dict, start: int, end: int, now: int) -> bool:
    return ep["start"] <= end and (ep["end"] if ep["end"] is not None else now) >= start


def _shrunk(hits: int, n: int, prior: float, k: float = K_PRIOR) -> float:
    return (hits + k * prior) / (n + k)


def predict(points: list, release_ts: int | None, now: int, events: list[Event],
            horizon_days: int = 180, external_low_usd_cents: int | None = None,
            currency: str = "") -> dict:
    if not points:
        return {"available": False, "reason": "No price history yet — this game has no price (free or unreleased)."}

    points = sorted(points)
    first_ts = points[0][0]
    obs_days = (now - first_ts) / DAY
    _, cur_init, cur_final, cur_disc = points[-1]
    episodes = build_episodes(points)
    age_days = (now - release_ts) / DAY if release_ts else None

    # ---- participation in past seasonal windows
    slots = season_slots(first_ts, now, only_complete=True)
    per_slot: dict[str, dict] = {}
    seasonal_depths: list[tuple[int, int]] = []
    hits = 0
    for slot, s, e in sorted(slots, key=lambda x: x[1]):
        d = max((ep["depth"] for ep in episodes if _overlaps(ep, s, e, now)), default=0)
        rec = per_slot.setdefault(slot, {"n": 0, "hits": 0, "depths": []})
        rec["n"] += 1
        if d > 0:
            rec["hits"] += 1
            rec["depths"].append(d)
            seasonal_depths.append((s, d))
            hits += 1
    n_slots = len(slots)

    p_prior = prior_participation(age_days)
    d_prior = prior_depth(age_days)
    p_all = _shrunk(hits, n_slots, p_prior)

    # recency-weighted observed depth (up to last 5 seasonal discounts)
    depths_recent_first = [d for _, d in sorted(seasonal_depths, reverse=True)][:5]
    if depths_recent_first:
        w = [0.7 ** i for i in range(len(depths_recent_first))]
        obs_depth = sum(a * b for a, b in zip(w, depths_recent_first)) / sum(w)
        trust = len(depths_recent_first) / (len(depths_recent_first) + 2)
        depth_all = trust * obs_depth + (1 - trust) * d_prior
    else:
        depth_all = d_prior

    # ---- off-season cadence detection
    all_windows = season_slots(first_ts, now, only_complete=False)
    off_season = [ep for ep in episodes
                  if not any(_overlaps(ep, s, e, now) for _, s, e in all_windows)]
    cadence = None
    if len(off_season) >= 3:
        starts = [ep["start"] for ep in off_season]
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        g, gm = median(gaps), mean(gaps)
        cv = pstdev(gaps) / gm if gm else 9
        if cv < 0.6 and g >= 7 * DAY:
            nxt = starts[-1] + g
            if nxt >= now - 3 * DAY and nxt <= now + horizon_days * DAY:
                cadence = {
                    "start": max(nxt, now), "half_window": max(3 * DAY, int(g * 0.15)),
                    "p": _clamp_p(0.6 * (1 - cv)),
                    "depth": median(ep["depth"] for ep in off_season),
                    "gap_days": round(g / DAY),
                }

    # ---- confidence — requires real observed history to be anything above "low"
    done_episodes = [e for e in episodes if e["end"] is not None]
    if len(done_episodes) >= 4 and n_slots >= 4 and obs_days >= 365:
        confidence = "high"
    elif len(done_episodes) >= 2 and obs_days >= 120:
        confidence = "medium"
    else:
        confidence = "low"
    spread = {"high": 5, "medium": 10, "low": 15}[confidence]

    def price_at(depth: float) -> int:
        return int(round(cur_init * (1 - depth / 100)))

    # ---- per-event outlook
    outlook = []
    for ev in upcoming(events, now, horizon_days):
        if ev.type not in SEASONAL_TYPES:
            continue
        slot = TYPE_TO_SLOT[ev.type]
        rec = per_slot.get(slot, {"n": 0, "hits": 0, "depths": []})
        p = _shrunk(rec["hits"], rec["n"], p_all, k=1.5)
        if rec["depths"]:
            depth = (sum(rec["depths"]) + 2 * depth_all) / (len(rec["depths"]) + 2)
        else:
            depth = depth_all * DEPTH_MULT[ev.type]
        if ev.type == "black_friday":
            p *= 0.8   # only the Specials-hub subset is discounted in Black Friday
        if cur_disc > 0 and ev.start_ts <= now:
            p = max(p, 0.88)   # event is live and the game is already on sale
        p = _clamp_p(p)
        depth = snap_tier(depth)
        outlook.append({
            "event": ev.name, "type": ev.type, "confirmed": ev.confirmed,
            "start": _iso(ev.start_ts), "end": _iso(ev.end_ts),
            "start_ts": ev.start_ts, "end_ts": ev.end_ts,
            "days_until": max(0, round((ev.start_ts - now) / DAY)),
            "ongoing": ev.start_ts <= now <= ev.end_ts,
            "probability": round(p, 2),
            "expected_discount": depth,
            "expected_price": price_at(depth),
            "price_range": [price_at(min(90, depth + spread)), price_at(max(5, depth - spread))],
        })
    if cadence:
        depth = snap_tier(cadence["depth"])
        cadence_p = _clamp_p(cadence["p"])
        outlook.append({
            "event": f"Off-season sale (discounts ~every {cadence['gap_days']} days)",
            "type": "cadence", "confirmed": False,
            "start": _iso(cadence["start"] - cadence["half_window"]),
            "end": _iso(cadence["start"] + cadence["half_window"]),
            "start_ts": cadence["start"] - cadence["half_window"],
            "end_ts":   cadence["start"] + cadence["half_window"],
            "days_until": max(0, round((cadence["start"] - now) / DAY)),
            "ongoing": False,
            "probability": round(cadence_p, 2),
            "expected_discount": depth,
            "expected_price": price_at(depth),
            "price_range": [price_at(min(90, depth + spread)), price_at(max(5, depth - spread))],
        })
    outlook.sort(key=lambda o: o["start_ts"])

    def p_within(days: int) -> float:
        """Probability of at least one discount event within `days` days (independent events)."""
        q = 1.0
        for o in outlook:
            if o["start_ts"] <= now + days * DAY:
                q *= 1 - o["probability"]
        return round(1 - q, 2)

    # ---- headline: next event we'd actually bet on
    likely = [o for o in outlook if o["probability"] >= 0.5 and o["end_ts"] >= now]
    next_drop = None
    if likely:
        next_drop = min(likely, key=lambda o: o["start_ts"])
    elif outlook:
        # still return the best guess, clearly labelled as uncertain via confidence
        next_drop = max(outlook, key=lambda o: o["probability"] - 0.0005 * o["days_until"])
    next_out = {k: v for k, v in next_drop.items() if k not in ("start_ts", "end_ts")} if next_drop else None

    # ---- reasons / recommendation
    lows = [p[2] for p in points]
    atl = min(lows)
    at_low = cur_final <= atl
    on_sale = cur_disc > 0
    reasons: list[str] = []
    if not done_episodes:
        reasons.append(
            "No completed sale has been recorded yet. Estimates rely on Steam-wide averages for a "
            "game of this age — treat them as rough priors, not forecasts.")
    else:
        reasons.append(f"{len(done_episodes)} completed sale(s) recorded over {round(obs_days)} days; "
                       f"deepest was {max(e['depth'] for e in done_episodes)}%.")
    if n_slots:
        reasons.append(f"Discounted in {hits} of {n_slots} past seasonal windows we watched.")
    if age_days is not None:
        reasons.append(f"Released ~{round(age_days / 365, 1)} year(s) ago.")
    if cadence:
        reasons.append(f"Shows a regular off-season rhythm (~every {cadence['gap_days']} days).")
    if confidence == "low":
        reasons.append("⚠ Confidence is LOW — we have limited history. Priors dominate; treat the forecast as a rough guide only.")

    action, headline = "consider", "No strong discount signal in the forecast window."
    if on_sale and at_low:
        action, headline = "buy_now", "It's at its lowest recorded price right now — good time to buy."
    elif on_sale and next_drop and next_drop["expected_discount"] <= cur_disc + 5:
        action = "buy_now"
        headline = (f"The current {cur_disc}% off is about as deep as we expect at the next sale "
                    f"(~{next_drop['expected_discount']}%). Buy now.")
    elif next_drop and next_drop["probability"] >= 0.5 and next_drop["expected_price"] < cur_final * 0.95:
        action = "wait"
        headline = (f"Likely to drop ~{next_drop['expected_discount']}% off around "
                    f"{next_drop['event']} (~{next_drop['days_until']} days away).")
    elif on_sale:
        action, headline = "buy_now", "On sale now and no clearly better price is predicted soon."
    elif next_drop and next_drop["probability"] < 0.5:
        headline = "Discounts for this game are irregular — buy if you want it, or wait and check back."

    return {
        "available": True,
        "method": "Steam sale calendar + Bayesian-shrinkage heuristic (explainable, not ML)",
        "confidence": confidence,
        "currency": currency,
        "current": {"final": cur_final, "initial": cur_init, "discount": cur_disc},
        "all_time_low_final": atl,
        "next_drop": next_out,
        "outlook": [{k: v for k, v in o.items() if k not in ("start_ts", "end_ts")} for o in outlook],
        "p_discount_30d": p_within(30),
        "p_discount_90d": p_within(90),
        "recommendation": {"action": action, "headline": headline, "reasons": reasons},
        "model": {
            "episodes_observed": len(done_episodes),
            "observed_days": round(obs_days),
            "season_windows_observed": n_slots,
            "season_windows_discounted": hits,
            "participation_prior": p_prior,
            "depth_prior": d_prior,
        },
        "disclaimer": (
            "Estimates, not guarantees. Valve sets sale dates; publishers choose discounts. "
            "History starts when you began tracking — predictions improve as more data accumulates."
        ),
    }
