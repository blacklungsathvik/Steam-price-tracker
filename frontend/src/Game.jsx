import React, { useEffect, useState } from "react";
import { api, money, date, iso, num, pct, daysFrom, CC_NAMES } from "./api.js";
import Chart from "./Chart.jsx";

const KIND = {
  first_seen:    ["First seen", ""],
  sale_start:    ["Sale started", "down"],
  sale_end:      ["Sale ended", "up"],
  deeper_sale:   ["Discount deepened", "down"],
  shallower_sale:["Discount reduced", "up"],
  base_hike:     ["Price increased", "up"],
  base_cut:      ["Price cut", "down"],
  price_change:  ["Price changed", ""],
};

function Stat({ label, value, sub }) {
  return (
    <div className="stat-tile">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function ProbBar({ p }) {
  return (
    <div className="prob-row">
      <div className="prob-track"><div className="prob-fill" style={{ width: `${p * 100}%` }} /></div>
      <span className="prob-pct">{pct(p)}</span>
    </div>
  );
}

function Verdict({ pr, M }) {
  if (!pr?.available) return <div className="panel muted-text">{pr?.reason || "No prediction available yet."}</div>;

  const cls = { wait: "verdict-wait", buy_now: "verdict-buy", consider: "verdict-consider" }[pr.recommendation.action] || "";
  const label = { wait: "WAIT", buy_now: "BUY NOW", consider: "YOUR CALL" }[pr.recommendation.action] || "YOUR CALL";
  const confCls = { high: "conf-high", medium: "conf-med", low: "conf-low" }[pr.confidence] || "";

  return (
    <div className={`panel verdict ${cls}`}>
      <div className="verdict-header">
        <span className="verdict-label">{label}</span>
        <span className={`conf-badge ${confCls}`}>{pr.confidence} confidence</span>
      </div>
      <p className="verdict-headline">{pr.recommendation.headline}</p>

      {pr.next_drop && (
        <div className="stat-grid">
          <Stat label="Next likely drop" value={iso(pr.next_drop.start)} sub={pr.next_drop.event} />
          <Stat label="Est. discount" value={`~${pr.next_drop.expected_discount}%`} sub={`${pct(pr.next_drop.probability)} probability`} />
          <Stat label="Est. price" value={M(pr.next_drop.expected_price)} sub={`${M(pr.next_drop.price_range[0])} – ${M(pr.next_drop.price_range[1])}`} />
          <Stat label="30 / 90 day chance" value={`${pct(pr.p_discount_30d)} / ${pct(pr.p_discount_90d)}`} />
          {pr.model.episodes_observed > 0 && (
            <Stat label="Past sales" value={pr.model.episodes_observed} sub={`over ${pr.model.observed_days} days`} />
          )}
          {pr.model.season_windows_observed > 0 && (
            <Stat label="Seasonal hit rate" value={`${pr.model.season_windows_discounted}/${pr.model.season_windows_observed}`} sub="windows with a discount" />
          )}
        </div>
      )}

      <ul className="verdict-reasons">
        {pr.recommendation.reasons.map(r => <li key={r}>{r}</li>)}
      </ul>
      <p className="disclaimer">{pr.disclaimer}</p>
    </div>
  );
}

function RegionTable({ appId }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let live = true;
    api(`/games/${appId}/regions`)
      .then(d => live && setData(d.cc_prices))
      .catch(() => live && setErr(true));
    return () => { live = false; };
  }, [appId]);

  return (
    <div className="panel">
      <h2>Regional Prices</h2>
      <p className="section-desc">Steam sets prices independently per region.</p>
      {!data && !err && <div className="loading-text">Loading…</div>}
      {err && <div className="muted-text">Could not load regional prices.</div>}
      {data && data.length === 0 && <div className="muted-text">No regional data yet — the collector will fill this in.</div>}
      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Region</th>
                <th>Currency</th>
                <th>Price</th>
                <th>Last changed</th>
              </tr>
            </thead>
            <tbody>
              {data.map(r => (
                <tr key={r.cc} className={r.discount > 0 ? "row-sale" : ""}>
                  <td>
                    <span className="cc-code">{r.cc.toUpperCase()}</span>
                    <span className="cc-name">{CC_NAMES[r.cc] || ""}</span>
                  </td>
                  <td className="muted-text">{r.currency}</td>
                  <td>
                    {r.final > 0 ? (
                      <>
                        {r.discount > 0 && <span className="disc-badge" style={{marginRight:6}}>-{r.discount}%</span>}
                        <strong>{money(r.final, r.currency, r.divisor)}</strong>
                        {r.discount > 0 && <span className="old-price" style={{marginLeft:6}}>{money(r.initial, r.currency, r.divisor)}</span>}
                      </>
                    ) : (
                      <span className="muted-text">Price on Steam</span>
                    )}
                  </td>
                  <td className="muted-text">{r.changed_at ? date(r.changed_at) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function Game({ id, cc }) {
  const [data, setData] = useState(null);
  const [hist, setHist] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let live = true;
    setData(null); setErr(null);
    Promise.all([api(`/games/${id}`, cc), api(`/games/${id}/history`, cc)])
      .then(([d, h]) => {
        if (live) { setData(d); setHist(h); document.title = `${d.game.name} — SteamTracker`; }
      })
      .catch(e => live && setErr(e));
    return () => { live = false; document.title = "SteamTracker"; };
  }, [id, cc]);

  if (err) return <div className="err-msg">{err.status === 404 ? "Game not found on Steam." : err.message}</div>;
  if (!data) return <div className="loading-page">Loading…</div>;

  const { game: g, price: p, stats: s, prediction: pr } = data;
  const M = v => money(v, data.currency, data.divisor);

  return (
    <div className="page-game">
      {/* Hero */}
      <div className="game-hero">
        <div className="hero-img-wrap">
          <img src={g.header_image || ""} alt={g.name} referrerPolicy="no-referrer" />
        </div>
        <div className="hero-info">
          <h1>{g.name}</h1>
          {g.short_description && <p className="hero-desc">{g.short_description}</p>}
          <div className="tag-row">
            {[...g.genres, ...g.platforms].map(t => <span key={t} className="tag">{t}</span>)}
          </div>
          {p && p.final > 0 ? (
            <div className="hero-price">
              {p.discount > 0 && <span className="disc-badge lg">-{p.discount}%</span>}
              {p.discount > 0 && <span className="old-price lg">{M(p.initial)}</span>}
              <span className="cur-price lg">{M(p.final)}</span>
              {s.is_at_all_time_low && s.sale_count > 0 && <span className="atl-badge">All-time low</span>}
            </div>
          ) : (
            <p className="hero-unpriced">{g.is_free ? "Free to Play" : "Price on Steam (Bundle / Edition)"}</p>
          )}
          <a
            className="steam-btn"
            href={`https://store.steampowered.com/app/${g.app_id}`}
            target="_blank" rel="noopener noreferrer"
          >
            View on Steam ↗
          </a>
        </div>
      </div>

      {/* Prediction */}
      <Verdict pr={pr} M={M} />

      {/* Price chart */}
      <div className="panel">
        <h2>Price History</h2>
        <Chart hist={hist} pred={pr} />
      </div>

      {/* Stats */}
      {s.all_time_low && (
        <div className="panel">
          <h2>Price Statistics</h2>
          <div className="stat-grid">
            <Stat label="All-time low" value={M(s.all_time_low.final)} sub={`${date(s.all_time_low.ts)} (−${s.all_time_low.discount}%)`} />
            <Stat label="Highest base price" value={M(s.highest_base)} />
            <Stat label="Avg price (time-weighted)" value={M(s.average_price)} />
            <Stat label="Time on sale" value={`${s.pct_time_on_sale}%`} sub={`${s.sale_count} sales tracked`} />
            <Stat label="Avg / max discount" value={`${s.avg_sale_depth}% / ${s.max_sale_depth}%`} />
            <Stat
              label="Last sale ended"
              value={s.last_sale_ended ? date(s.last_sale_ended) : "—"}
              sub={s.days_since_last_sale != null ? `${Math.round(s.days_since_last_sale)} days ago` : null}
            />
            <Stat label="Price hikes" value={s.base_hike_count ?? 0} />
            {data.external_low && <Stat label="All-time low (CheapShark, USD)" value={money(data.external_low.usd_cents, "USD")} />}
          </div>
        </div>
      )}

      {/* Regional prices */}
      <RegionTable appId={id} />

      {/* Sale outlook */}
      {pr?.available && pr.outlook.length > 0 && (
        <div className="panel">
          <h2>Sale Outlook</h2>
          <p className="section-desc">Estimated probability of a discount in each upcoming Steam sale event.</p>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Dates</th>
                  <th>Probability</th>
                  <th>Est. Discount</th>
                  <th>Est. Price</th>
                </tr>
              </thead>
              <tbody>
                {pr.outlook.map(o => (
                  <tr key={o.event + o.start}>
                    <td>
                      {o.event}
                      {o.ongoing && <span className="live-badge">LIVE</span>}
                      {!o.confirmed && o.type !== "cadence" && <span className="muted-text" style={{display:"block",fontSize:12}}>(dates estimated)</span>}
                    </td>
                    <td className="muted-text">{iso(o.start)} – {iso(o.end)}</td>
                    <td><ProbBar p={o.probability} /></td>
                    <td>~{o.expected_discount}%</td>
                    <td>
                      {M(o.expected_price)}
                      <span className="muted-text" style={{display:"block",fontSize:11.5}}>
                        {M(o.price_range[0])} – {M(o.price_range[1])}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Change log */}
      <div className="panel">
        <h2>Price Changes</h2>
        {data.changes.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr><th>Date</th><th>Event</th><th>Price</th><th>Change</th></tr>
              </thead>
              <tbody>
                {data.changes.slice(0, 60).map(c => {
                  const [label, cls] = KIND[c.kind] || ["Changed", ""];
                  const delta = c.from_final != null ? c.final - c.from_final : null;
                  return (
                    <tr key={c.ts}>
                      <td className="muted-text">{date(c.ts)}</td>
                      <td className={cls === "down" ? "text-green" : cls === "up" ? "text-red" : ""}>{label}</td>
                      <td>{M(c.final)}{c.discount ? ` (−${c.discount}%)` : ""}</td>
                      <td className={delta > 0 ? "text-red" : delta < 0 ? "text-green" : ""}>
                        {delta == null ? "" : (delta > 0 ? "▲ " : "▼ ") + M(Math.abs(delta))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : <div className="muted-text">No changes recorded yet.</div>}
        {s.first_seen && (
          <p className="note-text">Tracking since {date(s.first_seen)}.</p>
        )}
      </div>

      {/* Game info */}
      <div className="panel">
        <h2>Game Info</h2>
        <div className="stat-grid">
          <Stat label="Released" value={g.release_date || "—"} />
          <Stat label="Developer" value={g.developers.join(", ") || "—"} />
          <Stat label="Publisher" value={g.publishers.join(", ") || "—"} />
          <Stat label="Players online" value={num(g.current_players)} />
          <Stat
            label="Reviews"
            value={g.review_desc || "—"}
            sub={g.review_pct != null ? `${g.review_pct}% positive · ${num((g.reviews_positive || 0) + (g.reviews_negative || 0))}` : null}
          />
          <Stat label="Metacritic" value={g.metacritic ?? "—"} />
        </div>
        {g.categories.length > 0 && (
          <div className="tag-row" style={{ marginTop: 12 }}>
            {g.categories.map(t => <span key={t} className="tag">{t}</span>)}
          </div>
        )}
      </div>
    </div>
  );
}
