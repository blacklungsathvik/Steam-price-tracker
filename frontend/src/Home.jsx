import React, { useEffect, useState, useRef, useCallback } from "react";
import { api, money, iso, num } from "./api.js";

function PriceTag({ initial, final, discount, currency, divisor, is_free }) {
  const M = v => money(v, currency, divisor);
  if (is_free) return <span className="free-price">Free to Play</span>;
  if (final == null || final === 0) return <span className="no-price">Price on Steam</span>;
  return (
    <div className="price-tag">
      {discount > 0 && <span className="disc-badge">-{discount}%</span>}
      {discount > 0 && <span className="old-price">{M(initial)}</span>}
      <span className="cur-price">{M(final)}</span>
    </div>
  );
}

function GameCard({ r }) {
  return (
    <a className="game-card" href={`#/game/${r.app_id}`}>
      <div className="card-img">
        <img src={r.image || ""} alt="" loading="lazy" referrerPolicy="no-referrer" />
        {r.discount > 0 && <span className="card-disc">-{r.discount}%</span>}
      </div>
      <div className="card-body">
        <div className="card-name" title={r.name}>{r.name}</div>
        {r.players != null && r.players > 0 && (
          <div className="card-sub">{num(r.players)} online</div>
        )}
        <PriceTag {...r} is_free={r.is_free} />
      </div>
    </a>
  );
}

function CalCard({ event: e }) {
  return (
    <div className="cal-card">
      <div className={`cal-status ${e.confirmed ? "confirmed" : "estimated"}`}>
        {e.confirmed ? "Confirmed" : "Estimated"}
      </div>
      <div className="cal-name">{e.name.replace(" (est.)", "")}</div>
      <div className="cal-dates">{iso(e.start)} – {iso(e.end)}</div>
    </div>
  );
}

const PAGE_SIZE = 24;

export default function Home({ cc, meta }) {
  const [f, setF] = useState({ sort: "popular", min: 0, low: false });
  const [deals, setDeals] = useState([]);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [err, setErr] = useState("");
  const [events, setEvents] = useState([]);

  const sentinelRef = useRef(null);

  useEffect(() => {
    api("/calendar")
      .then(d => setEvents(d.events.filter(e => e.type !== "fest").slice(0, 5)))
      .catch(() => { });
  }, []);

  useEffect(() => {
    if (!cc) return;
    let live = true;
    setLoading(true);
    setErr("");
    setDeals([]);
    setHasMore(true);

    const url = `/deals?sort=${f.sort}&min_discount=${f.min}&limit=${PAGE_SIZE}&offset=0${f.low ? "&all_time_low=1" : ""}`;
    api(url, cc)
      .then(d => {
        if (!live) return;
        const list = d.deals || [];
        setDeals(list);
        setHasMore(d.has_more ?? list.length >= PAGE_SIZE);
        setLoading(false);
      })
      .catch(e => {
        if (!live) return;
        setErr(e.message || "Failed to load games");
        setLoading(false);
      });

    return () => { live = false; };
  }, [cc, f]);

  const loadMore = useCallback(() => {
    if (loading || loadingMore || !hasMore || !cc) return;
    setLoadingMore(true);

    const currentOffset = deals.length;
    const url = `/deals?sort=${f.sort}&min_discount=${f.min}&limit=${PAGE_SIZE}&offset=${currentOffset}${f.low ? "&all_time_low=1" : ""}`;

    api(url, cc)
      .then(d => {
        const nextList = d.deals || [];
        if (nextList.length === 0) {
          setHasMore(false);
        } else {
          setDeals(prev => {
            const seen = new Set(prev.map(g => g.app_id));
            const fresh = nextList.filter(g => !seen.has(g.app_id));
            return [...prev, ...fresh];
          });
          setHasMore(d.has_more ?? nextList.length >= PAGE_SIZE);
        }
        setLoadingMore(false);
      })
      .catch(() => {
        setLoadingMore(false);
      });
  }, [loading, loadingMore, hasMore, cc, deals.length, f]);

  useEffect(() => {
    if (!sentinelRef.current || !hasMore || loading || loadingMore) return;
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting) {
          loadMore();
        }
      },
      { rootMargin: "350px" }
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasMore, loading, loadingMore, loadMore]);

  const chip = (label, active, patch) => (
    <button
      className={`filter-chip${active ? " active" : ""}`}
      onClick={() => setF(prev => ({ ...prev, ...patch }))}
    >
      {label}
    </button>
  );

  return (
    <div className="page-home">
      <div className="home-hero">
        <div className="hero-badge">Engineering Portfolio · Live Distributed Data Engine</div>
        <h1 className="hero-title">SteamTracker</h1>
        <p className="hero-tagline">
          Real-time global Steam price intelligence, multi-region currency analytics, and empirical sale probability forecasting.
        </p>
        <div className="hero-stats-row">
          <div className="hstat">
            <span className="hstat-val">{meta ? meta.games : "100+"}</span>
            <span className="hstat-lbl">Tracked Games</span>
          </div>
          <div className="hstat">
            <span className="hstat-val">{meta && meta.regions ? meta.regions.length : "14"}</span>
            <span className="hstat-lbl">Currencies</span>
          </div>
          <div className="hstat">
            <span className="hstat-val">{meta && meta.price_points ? meta.price_points.toLocaleString() : "1,000+"}</span>
            <span className="hstat-lbl">Price Snapshots</span>
          </div>
          <div className="hstat">
            <span className="hstat-val">Official</span>
            <span className="hstat-lbl">Steam API</span>
          </div>
        </div>
      </div>

      {events.length > 0 && (
        <section className="section">
          <h2 className="section-title">Upcoming Steam Sales</h2>
          <div className="cal-row">
            {events.map(e => <CalCard key={e.name} event={e} />)}
          </div>
        </section>
      )}

      <section className="section">
        <div className="filter-bar">
          {chip("All Games", f.min === 0 && f.sort === "popular" && !f.low, { min: 0, sort: "popular", low: false })}
          {chip("Top Deals", f.min === 1 && f.sort === "discount" && !f.low, { min: 1, sort: "discount", low: false })}
          {chip("50%+ Off", f.min === 50 && f.sort === "discount", { min: 50, sort: "discount", low: false })}
          {chip("All-Time Low", f.low, { min: 1, sort: "discount", low: !f.low })}
          {chip("Lowest Price", f.sort === "price", { sort: "price", min: 0, low: false })}
          {chip("Recently Updated", f.sort === "recent", { sort: "recent", min: 0, low: false })}
        </div>

        {err && <div className="err-msg">{err}</div>}

        {loading && (
          <div className="deals-grid">
            {Array.from({ length: 16 }).map((_, i) => (
              <div key={i} className="game-card skeleton" />
            ))}
          </div>
        )}

        {!loading && deals.length === 0 && !err && (
          <div className="empty-state">
            {meta && meta.games === 0
              ? "Connecting to Steam API — initial prices will populate shortly."
              : "No matching games found. Try a different filter or search above."}
          </div>
        )}

        {deals.length > 0 && (
          <div className="deals-grid">
            {deals.map(r => <GameCard key={r.app_id} r={r} />)}
          </div>
        )}

        {loadingMore && (
          <div className="deals-grid deals-loading-more">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={`more-${i}`} className="game-card skeleton" />
            ))}
          </div>
        )}

        <div ref={sentinelRef} className="feed-sentinel" />

        {!loading && deals.length > 0 && (
          <div className="feed-footer">
            {hasMore ? (
              <button className="load-more-btn" onClick={loadMore} disabled={loadingMore}>
                {loadingMore ? "Loading more games…" : "Load More Games"}
              </button>
            ) : (
              <p className="feed-end">
                Browsed {deals.length} games. More are tracked automatically!
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
