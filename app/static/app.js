(() => {
"use strict";
// =============================================================
//  SteamTracker — SPA
//  Features: multi-region prices, About, Privacy, Cookie banner
// =============================================================
const $ = (s, r = document) => r.querySelector(s);
const app = $("#app");
const state = { cc: localStorage.getItem("st_cc") || null, meta: null };
const DAY = 86400;

// ---- Cookie consent ---------------------------------------------------------
(function cookieConsent() {
  const banner = $("#cookie-banner");
  if (!banner) return;
  const consent = localStorage.getItem("st_cookie_consent");
  if (!consent) {
    banner.hidden = false;
  }
  $("#cookie-accept")?.addEventListener("click", () => {
    localStorage.setItem("st_cookie_consent", "accepted");
    banner.hidden = true;
  });
  $("#cookie-decline")?.addEventListener("click", () => {
    localStorage.setItem("st_cookie_consent", "declined");
    // If declined, clear the saved region too (it was set by a cookie)
    banner.hidden = true;
  });
})();

// ---- Safe DOM builder -------------------------------------------------------
const SVG_TAGS = new Set(["svg","g","path","line","rect","text","circle","polygon","defs","linearGradient","stop"]);
function el(tag, attrs, ...kids) {
  const n = SVG_TAGS.has(tag)
    ? document.createElementNS("http://www.w3.org/2000/svg", tag)
    : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") n.setAttribute("class", v);
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat())
    if (kid != null && kid !== false)
      n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return n;
}

// ---- API helper -------------------------------------------------------------
const api = async (path) => {
  const sep = path.includes("?") ? "&" : "?";
  const url = `/api${path}${state.cc ? sep + "cc=" + encodeURIComponent(state.cc) : ""}`;
  const r = await fetch(url);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(body.error || r.statusText), { status: r.status });
  return body;
};

// ---- Formatters -------------------------------------------------------------
const money  = (minor, cur, div = 100) => {
  if (minor == null) return "—";
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency: cur || "USD" }).format(minor / div); }
  catch { return (minor / div).toFixed(2) + " " + (cur || ""); }
};
const date   = (ts) => new Date(ts * 1000).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
const iso    = (s)  => new Date(s + "T12:00:00Z").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
const num    = (n)  => (n == null ? "—" : n.toLocaleString());
const pct    = (p)  => Math.round(p * 100) + "%";

// ---- Shared components ------------------------------------------------------
function priceBlock(r) {
  if (r.final == null) return el("div", { class: "muted price" }, "No price");
  return el("div", { class: "price" },
    r.discount > 0 && el("span", { class: "badge" }, `-${r.discount}%`),
    r.discount > 0 && el("span", { class: "old" }, money(r.initial, r.currency, r.divisor)),
    el("span", { class: "now" }, money(r.final, r.currency, r.divisor)));
}
function gameCard(r) {
  return el("a", { class: "card", href: `#/game/${r.app_id}` },
    el("img", { src: r.image || "", alt: "", loading: "lazy", referrerpolicy: "no-referrer" }),
    el("div", { class: "b" },
      el("div", { class: "t", title: r.name }, r.name),
      priceBlock(r)));
}
function tile(k, v, sub) {
  return el("div", { class: "tile" },
    el("div", { class: "k" }, k),
    el("div", { class: "v" }, v),
    sub && el("div", { class: "sub" }, sub));
}

// ---- Region Price Table (all regions) ----------------------------------------
function regionTable(appId, M) {
  const wrap = el("div", { class: "panel" });
  wrap.append(el("h2", null, "Regional Prices"), el("p", { class: "muted", style: "font-size:13px;margin:-8px 0 12px" }, "Current price in every tracked region. Steam sets prices independently per country."));

  const spinner = el("div", { class: "muted", style: "font-size:13px" }, "Loading regional prices…");
  wrap.append(spinner);

  api(`/games/${appId}/regions`).then(({ cc_prices }) => {
    if (!cc_prices || !cc_prices.length) {
      spinner.textContent = "No regional price data yet — the collector will populate this over time.";
      return;
    }
    // Country-code to full country name
    const CC_NAMES = {
      us:"United States",gb:"United Kingdom",eu:"European Union",in:"India",au:"Australia",
      ca:"Canada",br:"Brazil",ru:"Russia",de:"Germany",fr:"France",jp:"Japan",kr:"South Korea",
      sg:"Singapore",tr:"Turkey",ar:"Argentina",mx:"Mexico",nz:"New Zealand",pl:"Poland",
      se:"Sweden",no:"Norway",dk:"Denmark",ch:"Switzerland",hk:"Hong Kong",id:"Indonesia",
      th:"Thailand",ph:"Philippines",vn:"Vietnam",cn:"China",sa:"Saudi Arabia",ae:"UAE",
      ng:"Nigeria",za:"South Africa",cl:"Chile",co:"Colombia",pe:"Peru",ua:"Ukraine"
    };
    const tbody = el("tbody");
    cc_prices.forEach(r => {
      const isOnSale = r.discount > 0;
      const row = el("tr", { class: isOnSale ? "on-sale-row" : "" },
        el("td", null, el("span", { class: "cc" }, r.cc.toUpperCase()),
          el("span", { class: "muted", style: "font-size:12px;margin-left:6px" }, CC_NAMES[r.cc] || "")),
        el("td", { class: "curr" }, r.currency),
        el("td", null,
          isOnSale && el("span", { class: "badge", style: "margin-right:6px" }, `-${r.discount}%`),
          el("b", null, money(r.final, r.currency, r.divisor)),
          isOnSale && el("span", { class: "old", style: "margin-left:6px" }, money(r.initial, r.currency, r.divisor))),
        el("td", { class: "muted", style: "font-size:12px" }, r.changed_at ? date(r.changed_at) : "—"));
      tbody.append(row);
    });
    const tbl = el("table", { class: "region-table" },
      el("thead", null, el("tr", null,
        ...["Region", "Currency", "Current Price", "Last Change"].map(x => el("th", null, x)))),
      tbody);
    spinner.replaceWith(el("div", { class: "region-table-wrap" }, tbl));
  }).catch(() => {
    spinner.textContent = "Could not load regional prices.";
  });
  return wrap;
}

// ---- Home page --------------------------------------------------------------
async function home() {
  const f = { sort: "discount", min: 1, low: false };
  const grid = el("div", { class: "grid" },
    el("div", { class: "empty" }, "Loading deals…"));

  const calEl = el("div", { class: "panel" },
    el("h2", null, "Upcoming Steam Sales"),
    el("div", { class: "cal-row" },
      el("div", { class: "muted", style: "font-size:13px" }, "Loading…")));

  api("/calendar").then(({ events }) => {
    const list = events.filter(e => e.type !== "fest").slice(0, 5);
    calEl.replaceChildren(
      el("h2", null, "Upcoming Steam Sales"),
      el("div", { class: "cal-row" }, ...list.map(e =>
        el("div", { class: "cal-card" },
          el("div", { class: "cal-label " + (e.confirmed ? "cal-confirmed" : "cal-estimated") },
            e.confirmed ? "✓ Confirmed" : "~ Estimated"),
          el("div", { class: "cal-name" }, e.name.replace(" (est.)", "")),
          el("div", { class: "cal-dates" }, `${iso(e.start)} – ${iso(e.end)}`)))));
  }).catch(() => calEl.remove());

  async function load() {
    grid.replaceChildren(el("div", { class: "empty" }, "Loading…"));
    try {
      const d = await api(`/deals?sort=${f.sort}&min_discount=${f.min}&limit=48${f.low ? "&all_time_low=1" : ""}`);
      grid.replaceChildren(...(d.deals.length
        ? d.deals.map(gameCard)
        : [el("div", { class: "empty" }, "No deals tracked yet. Search for a game to start tracking it.")]));
    } catch (e) {
      grid.replaceChildren(el("div", { class: "empty" }, e.message));
    }
  }

  const chips = el("div", { class: "chips" });
  function drawChips() {
    const mk = (label, on, fn) =>
      el("button", { class: "chip" + (on ? " on" : ""), onclick: () => { fn(); drawChips(); load(); } }, label);
    chips.replaceChildren(
      mk("Biggest Discount", f.sort === "discount", () => f.sort = "discount"),
      mk("Lowest Price",     f.sort === "price",    () => f.sort = "price"),
      mk("Newest Deals",     f.sort === "recent",   () => f.sort = "recent"),
      mk("50%+ Off",         f.min === 50,          () => f.min = f.min === 50 ? 1 : 50),
      mk("All-Time Low",     f.low,                 () => f.low = !f.low));
  }
  drawChips();

  app.replaceChildren(
    el("div", { class: "home-intro" },
      el("h1", null, "Steam Deals & Price History"),
      el("p",  null, "Every price change we've seen — plus a forecast of when each game is next likely to drop.")),
    calEl,
    chips,
    grid);
  load();
}

// ---- Price chart ------------------------------------------------------------
function chart(hist, pred) {
  const W = 920, H = 300, m = { l: 68, r: 20, t: 14, b: 30 };
  const pts = hist.points;
  if (!pts.length)
    return el("div", { class: "empty" }, "No price history yet.");
  let range = "all";
  const wrap = el("div", { class: "chartwrap" });
  const tip  = el("div", { class: "tip", hidden: true });

  function draw() {
    const now = hist.now;
    let t0 = pts[0].ts;
    if (range === "1y") t0 = Math.max(t0, now - 365 * DAY);
    if (range === "3y") t0 = Math.max(t0, now - 1095 * DAY);
    const next = pred && pred.available && pred.next_drop;
    const fwd  = next ? Math.max(0, Math.round(new Date(next.end + "T12:00:00Z") / 1000) - now) + 14 * DAY : 0;
    const t1 = now + Math.min(fwd, 200 * DAY);
    const lastBefore = pts.filter(q => q.ts < t0).pop();
    const vis = pts.filter(p => p.ts >= t0 || p === lastBefore);
    const maxV = Math.max(...vis.map(p => p.initial), ...pts.slice(-1).map(p => p.initial)) * 1.08;
    const x  = t => m.l + (t - t0) / (t1 - t0 || 1) * (W - m.l - m.r);
    const y  = v => H - m.b - v / maxV * (H - m.t - m.b);
    const cx = t => Math.min(Math.max(x(t), m.l), W - m.r);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", "aria-label": "Price chart" });

    // y-grid
    for (let i = 0; i <= 4; i++) {
      const v = maxV / 1.08 * i / 4;
      svg.append(
        el("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), stroke: "var(--line)", "stroke-width": 1 }),
        el("text", { x: m.l - 7, y: y(v) + 4, "text-anchor": "end" },
          money(Math.round(v), hist.currency, hist.divisor)));
    }
    // x-ticks
    const span = t1 - t0, every = span > 3 * 365 * DAY ? 12 : span > 365 * DAY ? 6 : 2;
    const d0 = new Date(t0 * 1000);
    for (let mo = Math.floor((d0.getUTCFullYear() * 12 + d0.getUTCMonth()) / every) * every; ; mo += every) {
      const t = Date.UTC(Math.floor(mo / 12), mo % 12, 1) / 1000;
      if (t > t1) break;
      if (t < t0) continue;
      svg.append(el("text", { x: x(t), y: H - 8, "text-anchor": "middle" },
        new Date(t * 1000).toLocaleDateString(undefined, { month: "short", year: "2-digit", timeZone: "UTC" })));
    }
    // price area + lines
    const seq = vis.map((p, i) => ({
      ...p,
      ts:  Math.max(p.ts, t0),
      end: Math.min(i + 1 < vis.length ? vis[i + 1].ts : now, t1)
    }));
    let base = "", fin = "", area = "";
    seq.forEach((p, i) => {
      base += `${i ? "L" : "M"}${cx(p.ts)},${y(p.initial)}L${cx(p.end)},${y(p.initial)}`;
      fin  += `${i ? "L" : "M"}${cx(p.ts)},${y(p.final)}L${cx(p.end)},${y(p.final)}`;
      if (p.discount > 0) area += `M${cx(p.ts)},${y(p.initial)}L${cx(p.end)},${y(p.initial)}L${cx(p.end)},${y(p.final)}L${cx(p.ts)},${y(p.final)}Z`;
    });
    svg.append(
      el("path", { d: area, fill: "var(--good)", opacity: .18 }),
      el("path", { d: base, fill: "none", stroke: "var(--line)", "stroke-dasharray": "4 4", "stroke-width": 1.2 }),
      el("path", { d: fin, fill: "none", stroke: "var(--accent)", "stroke-width": 2.2 }));
    // hike markers
    seq.forEach((p, i) => {
      if (i && vis[i].initial > vis[i - 1].initial)
        svg.append(el("polygon", {
          points: `${cx(p.ts)},${y(p.initial) - 9} ${cx(p.ts) - 5},${y(p.initial) - 1} ${cx(p.ts) + 5},${y(p.initial) - 1}`,
          fill: "var(--bad)", opacity: .85 }));
    });
    // today line
    svg.append(
      el("line", { x1: x(now), x2: x(now), y1: m.t, y2: H - m.b, stroke: "var(--muted)", "stroke-dasharray": "3 5" }),
      el("text", { x: x(now) + 4, y: m.t + 11 }, "today"));
    // forecast band
    if (next) {
      const s = new Date(next.start + "T12:00:00Z") / 1000;
      const e = new Date(next.end   + "T12:00:00Z") / 1000;
      const xs = Math.max(x(Math.max(s, now)), x(now)), xe = Math.min(x(e), W - m.r);
      const [lo, hi] = next.price_range;
      svg.append(
        el("rect", { x: xs, y: y(hi), width: Math.max(xe - xs, 6), height: Math.max(y(lo) - y(hi), 4), fill: "var(--warn)", opacity: .22, rx: 3 }),
        el("line", { x1: xs, x2: Math.max(xe, xs + 6), y1: y(next.expected_price), y2: y(next.expected_price), stroke: "var(--warn)", "stroke-width": 2.2, "stroke-dasharray": "5 3" }),
        el("text", { x: Math.min(xs + 65, W - m.r), y: y(hi) - 6, "text-anchor": "end", fill: "var(--warn)" },
          `forecast ≈ ${money(next.expected_price, hist.currency, hist.divisor)}`));
    }
    // hover
    const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent", style: "cursor:crosshair" });
    hit.addEventListener("mousemove", ev => {
      const r = svg.getBoundingClientRect();
      const px = (ev.clientX - r.left) / r.width * W;
      const t  = t0 + (px - m.l) / (W - m.l - m.r) * (t1 - t0);
      if (t > now) { tip.hidden = true; return; }
      const p = [...pts].reverse().find(q => q.ts <= t) || pts[0];
      tip.replaceChildren(
        el("b", null, date(Math.round(t))), el("br"),
        money(p.final, hist.currency, hist.divisor),
        p.discount ? ` (−${p.discount}%)` : "");
      tip.hidden = false;
      tip.style.left = Math.min(ev.clientX - r.left + 12, r.width - 150) + "px";
      tip.style.top  = "10px";
    });
    hit.addEventListener("mouseleave", () => tip.hidden = true);
    svg.append(hit);

    const ctl = el("div", { class: "chart-controls" },
      ...[ ["1y","1 year"], ["3y","3 years"], ["all","All time"] ].map(([k, l]) =>
        el("button", { class: "chip" + (range === k ? " on" : ""), onclick: () => { range = k; draw(); } }, l)),
      el("span", { class: "chart-legend" }, "── price  ┄ base price  ▲ hike  ▬ forecast"));
    wrap.replaceChildren(ctl, svg, tip);
  }
  draw();
  return wrap;
}

// ---- Confidence badge -------------------------------------------------------
function confBadge(level) {
  const labels = { high: "✓ High confidence", medium: "~ Medium confidence", low: "⚠ Low confidence" };
  return el("span", { class: `conf ${level}` }, labels[level] || level);
}

// ---- Game page --------------------------------------------------------------
const KIND = {
  first_seen:    ["First seen",           ""],
  sale_start:    ["Sale started",         "down"],
  sale_end:      ["Sale ended",           "up"],
  deeper_sale:   ["Discount deepened",    "down"],
  shallower_sale:["Discount reduced",     "up"],
  base_hike:     ["Regular price ↑",      "up"],
  base_cut:      ["Regular price ↓",      "down"],
  price_change:  ["Price changed",        ""],
};

async function gamePage(id) {
  app.replaceChildren(el("div", { class: "empty" }, "Loading…"));
  let d, h;
  try { [d, h] = await Promise.all([api(`/games/${id}`), api(`/games/${id}/history`)]); }
  catch (e) {
    app.replaceChildren(el("div", { class: "empty" },
      e.status === 404 ? "Game not found on Steam." : e.message));
    return;
  }
  const g = d.game, p = d.price, s = d.stats, pr = d.prediction;
  document.title = `${g.name} — SteamTracker`;
  const M = v => money(v, d.currency, d.divisor);

  // hero
  const hero = el("div", { class: "hero" },
    el("img", { src: g.header_image || "", alt: g.name, referrerpolicy: "no-referrer" }),
    el("div", { class: "hero-info" },
      el("h1", null, g.name),
      el("div", { class: "hero-desc" }, g.short_description || ""),
      el("div", { class: "tags" }, ...[...g.genres, ...g.platforms].map(t => el("span", { class: "tag" }, t))),
      p
        ? el("div", { class: "price-hero" },
            p.discount > 0 && el("span", { class: "badge" }, `-${p.discount}%`),
            p.discount > 0 && el("span", { class: "old" }, M(p.initial)),
            el("span", { class: "now" }, M(p.final)),
            s.is_at_all_time_low && s.sale_count > 0 && el("span", { class: "badge low" }, "All-time low"))
        : el("p", null, g.is_free ? "Free to play" : "No price in this region"),
      el("a", {
        class: "btn-steam",
        href: `https://store.steampowered.com/app/${g.app_id}`,
        target: "_blank", rel: "noopener noreferrer"
      }, "View on Steam ↗")));

  // prediction verdict
  let verdict;
  if (pr && pr.available) {
    const actionLabel = {
      wait:    "WAIT — Better price coming",
      buy_now: "GOOD TIME TO BUY",
      consider:"YOUR CALL",
    }[pr.recommendation.action] || "YOUR CALL";
    verdict = el("div", { class: `panel verdict ${pr.recommendation.action}` },
      el("div", { class: "verdict-top" },
        el("span", { class: "verdict-action" }, actionLabel),
        confBadge(pr.confidence)),
      el("div", { class: "verdict-headline" }, pr.recommendation.headline),
      pr.next_drop && el("div", { class: "tiles" },
        tile("Next likely drop",        iso(pr.next_drop.start), pr.next_drop.event),
        tile("Est. discount",           `~${pr.next_drop.expected_discount}%`, `${pct(pr.next_drop.probability)} probability`),
        tile("Est. price",              M(pr.next_drop.expected_price), `${M(pr.next_drop.price_range[0])} – ${M(pr.next_drop.price_range[1])}`),
        tile("30-day / 90-day chance",  `${pct(pr.p_discount_30d)} / ${pct(pr.p_discount_90d)}`),
        pr.model.episodes_observed > 0 && tile("Past sales",  pr.model.episodes_observed, `over ${pr.model.observed_days} days`),
        pr.model.season_windows_observed > 0 && tile("Seasonal hits", `${pr.model.season_windows_discounted} / ${pr.model.season_windows_observed}`, "windows with discount")),
      el("ul", null, ...pr.recommendation.reasons.map(r => el("li", null, r))),
      el("div", { class: "disclaimer" }, pr.disclaimer));
  } else {
    verdict = el("div", { class: "panel muted" },
      pr?.reason || "No prediction available yet.");
  }

  // stats panel
  const statPanel = el("div", { class: "panel" },
    el("h2", null, "Price Statistics"),
    el("div", { class: "tiles" },
      tile("All-time low", M(s.all_time_low?.final), s.all_time_low && `${date(s.all_time_low.ts)} (−${s.all_time_low.discount}%)`),
      tile("Highest base price", M(s.highest_base)),
      tile("Avg price (time-weighted)", M(s.average_price)),
      tile("Time on sale", (s.pct_time_on_sale ?? 0) + "%", `${s.sale_count ?? 0} sales tracked`),
      tile("Avg / max discount", `${s.avg_sale_depth ?? 0}% / ${s.max_sale_depth ?? 0}%`),
      tile("Last sale ended", s.last_sale_ended ? date(s.last_sale_ended) : "—",
        s.days_since_last_sale != null && `${Math.round(s.days_since_last_sale)} days ago`),
      tile("Price hikes", s.base_hike_count ?? 0),
      d.external_low && tile("All-time low (CheapShark, USD)", money(d.external_low.usd_cents, "USD"))));

  // outlook table
  const outlookPanel = (pr && pr.available && pr.outlook.length)
    ? el("div", { class: "panel" },
        el("h2", null, "Sale Outlook"),
        el("p", { class: "muted", style: "font-size:13px;margin:-8px 0 12px" },
          "Estimated probability of a discount in each upcoming Steam sale event, based on this game's historical pattern."),
        el("table", null,
          el("thead", null, el("tr", null,
            ...["Event", "Dates", "Probability", "Est. Discount", "Est. Price"].map(x => el("th", null, x)))),
          el("tbody", null, ...pr.outlook.map(o =>
            el("tr", null,
              el("td", null,
                o.event,
                !o.confirmed && o.type !== "cadence" && el("span", { class: "muted", style: "display:block;font-size:11.5px" }, "(dates estimated)"),
                o.ongoing && el("span", { class: "badge", style: "margin-left:6px;font-size:11px" }, "LIVE")),
              el("td", { class: "muted", style: "font-size:12.5px" }, `${iso(o.start)} – ${iso(o.end)}`),
              el("td", null,
                el("div", { class: "prob-cell" },
                  el("span", { class: "bar" }, el("i", { style: `width:${o.probability * 100}%` })),
                  el("b", null, pct(o.probability)))),
              el("td", null, `~${o.expected_discount}%`),
              el("td", null, M(o.expected_price),
                el("span", { class: "muted", style: "display:block;font-size:11.5px" },
                  `${M(o.price_range[0])} – ${M(o.price_range[1])}`)))))))
    : null;

  // change log
  const changeLog = el("div", { class: "panel" },
    el("h2", null, "Price Change History"),
    d.changes.length
      ? el("table", null,
          el("thead", null, el("tr", null,
            ...["Date", "Event", "Price", "Change"].map(x => el("th", null, x)))),
          el("tbody", null, ...d.changes.slice(0, 60).map(c => {
            const [label, cls] = KIND[c.kind] || ["Changed", ""];
            const delta = c.from_final != null ? c.final - c.from_final : null;
            return el("tr", null,
              el("td", { class: "muted", style: "font-size:13px" }, date(c.ts)),
              el("td", { class: cls }, label),
              el("td", null, M(c.final) + (c.discount ? ` (−${c.discount}%)` : "")),
              el("td", { class: delta > 0 ? "up" : "down" },
                delta == null ? "" : (delta > 0 ? "▲ " : "▼ ") + M(Math.abs(delta))));
          })))
      : el("div", { class: "muted" }, "No price changes recorded yet."),
    d.changes.length >= 1 && el("p", { class: "muted", style: "font-size:12px;margin-top:10px" },
      `Tracking since ${date(s.first_seen)}. Earlier history requires a backfill source (ITAD).`));

  // game info
  const infoPanel = el("div", { class: "panel" },
    el("h2", null, "Game Details"),
    el("div", { class: "tiles" },
      tile("Released", g.release_date || "—"),
      tile("Developer", g.developers.join(", ") || "—"),
      tile("Publisher", g.publishers.join(", ") || "—"),
      tile("Players online", num(g.current_players)),
      tile("Review score", g.review_desc || "—",
        g.review_pct != null && `${g.review_pct}% positive · ${num((g.reviews_positive || 0) + (g.reviews_negative || 0))}`),
      tile("Metacritic", g.metacritic ?? "—")),
    el("div", { class: "tags", style: "margin-top:10px" }, ...g.categories.map(t => el("span", { class: "tag" }, t))));

  // regional prices table
  const regionPricePanel = regionTable(id, M);

  app.replaceChildren(
    hero,
    el("div", { style: "height:14px" }),
    verdict,
    el("div", { class: "panel" },
      el("h2", null, "Price History"),
      chart(h, pr)),
    statPanel,
    regionPricePanel,
    ...(outlookPanel ? [outlookPanel] : []),
    changeLog,
    infoPanel);
}

// ---- About page -------------------------------------------------------------
function aboutPage() {
  document.title = "About — SteamTracker";
  app.replaceChildren(el("div", { class: "panel static-page" },
    el("h1", null, "About SteamTracker"),
    el("p", null, "SteamTracker is a self-hosted, open-source Steam price tracker. It watches Steam's public storefront API, records every price change for every tracked game in every region, and builds a local database of price history over time."),
    el("h2", null, "How it works"),
    el("ul", null,
      el("li", null, "A background collector polls Steam's public storefront endpoints every few hours (never scraping SteamDB)."),
      el("li", null, "Only changes are stored — if the price didn't change, no row is written."),
      el("li", null, "Prices are collected for every configured region simultaneously (US, UK, EU, India, and more)."),
      el("li", null, "A sale-prediction model uses the official Steam sale calendar plus the game's own discount history to estimate the probability and depth of the next discount.")),
    el("h2", null, "Data sources"),
    el("ul", null,
      el("li", null, "Steam public storefront API (store.steampowered.com) — prices, game metadata, player counts, reviews."),
      el("li", null, "IsThereAnyDeal (optional) — historical price backfill."),
      el("li", null, "CheapShark — all-time-low cross-check in USD."),
      el("li", null, "Steam sale calendar (data/steam_events.json) — manually updated from published Valve announcements.")),
    el("h2", null, "Accuracy & limitations"),
    el("ul", null,
      el("li", null, "History starts when you start collecting (or if you configure ITAD backfill)."),
      el("li", null, "Predictions are probabilistic estimates, not guarantees. Valve sets sale dates; publishers choose discounts."),
      el("li", null, "New installs give low-confidence prior-based estimates until real data accumulates."),
      el("li", null, "Not affiliated with Valve Corporation or Steam.")),
    el("h2", null, "Open source"),
    el("p", null, "SteamTracker is a self-hosted project. You run it on your own machine or server.")));
}

// ---- Privacy & Cookie page --------------------------------------------------
function privacyPage() {
  document.title = "Privacy & Cookies — SteamTracker";
  app.replaceChildren(el("div", { class: "panel static-page" },
    el("h1", null, "Privacy & Cookie Policy"),
    el("p", null, "Last updated: November 2026"),

    el("h2", null, "What data we collect"),
    el("ul", null,
      el("li", null, "SteamTracker is self-hosted. No personal data is sent to any third party by this application."),
      el("li", null, "The server logs HTTP requests (IP address, path, timestamp) in standard web server access logs. These are not shared and are used only for debugging."),
      el("li", null, "No account system. No email addresses. No user profiles.")),

    el("h2", null, "Cookies & local storage"),
    el("p", null, "We use the browser's localStorage (not traditional cookies) to remember:"),
    el("ul", null,
      el("li", null, el("b", null, "st_cc"), " — your selected Steam region (e.g. 'us', 'in'). This avoids you having to re-select it every visit."),
      el("li", null, el("b", null, "st_cookie_consent"), " — whether you accepted or declined this notice.")),
    el("p", null, "No tracking pixels, no advertising cookies, no analytics SDKs, no third-party scripts."),

    el("h2", null, "Third-party requests"),
    el("ul", null,
      el("li", null, "Game cover images are loaded directly from Steam's CDN (akamai.steamstatic.com / cloudflare.steamstatic.com). Steam's privacy policy applies to those requests."),
      el("li", null, "No other third-party assets are loaded.")),

    el("h2", null, "Your choices"),
    el("ul", null,
      el("li", null, 'If you clicked "Decline" on the cookie banner, your region preference is not saved between visits.'),
      el("li", null, "To clear stored preferences, open your browser's developer tools → Application → Local Storage → delete st_cc and st_cookie_consent.")),

    el("h2", null, "Contact"),
    el("p", null, "Because SteamTracker is self-hosted, the operator of this instance is the person or organisation who runs the server. Contact them directly for data requests.")));
}

// ---- Search -----------------------------------------------------------------
let searchTimer;
const qEl = $("#q"), sugEl = $("#suggest");
qEl?.addEventListener("input", () => {
  clearTimeout(searchTimer);
  const v = qEl.value.trim();
  if (v.length < 2) { sugEl.hidden = true; return; }
  searchTimer = setTimeout(async () => {
    try {
      const { results } = await api(`/search?q=${encodeURIComponent(v)}`);
      sugEl.replaceChildren(...results.map(r =>
        el("li", null,
          el("a", { href: `#/game/${r.app_id}`, role: "option" },
            el("img", { src: r.image || "", alt: "", referrerpolicy: "no-referrer" }),
            el("span", { class: "s-name" }, r.name),
            r.final != null && el("span", { class: "s-price" }, money(r.final, r.currency, r.divisor))))));
      if (!results.length)
        sugEl.replaceChildren(el("li", { class: "muted", style: "padding:9px 12px" }, "No matches."));
      sugEl.hidden = false;
    } catch { sugEl.hidden = true; }
  }, 260);
});
document.addEventListener("click", e => {
  if (!e.target.closest(".search")) sugEl.hidden = true;
  else if (e.target.closest("a")) { sugEl.hidden = true; qEl.value = ""; }
});

// ---- Router -----------------------------------------------------------------
function route() {
  const h = location.hash;
  document.title = "SteamTracker — Steam Price History & Sale Forecasts";
  window.scrollTo(0, 0);
  const gameM = h.match(/^#\/game\/(\d+)/);
  if (gameM)        return gamePage(gameM[1]);
  if (h === "#/about")   return aboutPage();
  if (h === "#/privacy") return privacyPage();
  home();
}

// ---- Init -------------------------------------------------------------------
(async function init() {
  try {
    state.meta = await api("/meta");
    state.cc = state.cc && state.meta.regions.includes(state.cc) ? state.cc : state.meta.default_region;
    const sel = $("#region");
    if (sel) {
      sel.replaceChildren(...state.meta.regions.map(r =>
        el("option", { value: r, selected: r === state.cc }, r.toUpperCase())));
      sel.addEventListener("change", () => {
        state.cc = sel.value;
        // only persist if cookies accepted
        if (localStorage.getItem("st_cookie_consent") === "accepted")
          localStorage.setItem("st_cc", state.cc);
        route();
      });
    }
    const metaEl = $("#meta");
    if (metaEl)
      metaEl.textContent = `${num(state.meta.games)} games tracked · ${num(state.meta.price_points)} price points`
        + (state.meta.last_check ? ` · last check ${date(state.meta.last_check)}` : "");
  } catch { /* API not ready yet */ }
  window.addEventListener("hashchange", route);
  route();
})();
})();
