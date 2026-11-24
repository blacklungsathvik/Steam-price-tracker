import React, { useEffect, useRef, useState } from "react";
import { api, money, num, date, CC_NAMES } from "./api.js";
import Home from "./Home.jsx";
import Game from "./Game.jsx";
import About from "./About.jsx";
import Privacy from "./Privacy.jsx";

function useRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const on = () => { setHash(window.location.hash); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const gm = hash.match(/^#\/game\/(\d+)/);
  if (gm) return { name: "game", id: gm[1] };
  if (hash === "#/about") return { name: "about" };
  if (hash === "#/privacy") return { name: "privacy" };
  return { name: "home" };
}

function Search({ cc }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const ref = useRef(null);

  useEffect(() => {
    const v = q.trim();
    if (v.length < 2) { setRes(null); return; }
    const t = setTimeout(() => {
      api(`/search?q=${encodeURIComponent(v)}`, cc)
        .then(d => setRes(d.results))
        .catch(() => setRes(null));
    }, 250);
    return () => clearTimeout(t);
  }, [q, cc]);

  useEffect(() => {
    const away = e => { if (ref.current && !ref.current.contains(e.target)) setRes(null); };
    document.addEventListener("click", away);
    return () => document.removeEventListener("click", away);
  }, []);

  return (
    <div className="search" ref={ref}>
      <svg className="search-ico" viewBox="0 0 20 20" fill="none">
        <circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M13 13l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
      <input
        type="search" value={q} onChange={e => setQ(e.target.value)}
        placeholder="Search any Steam game…" autoComplete="off"
        onFocus={() => q.trim().length >= 2 && setRes(res)}
      />
      {res && (
        <ul className="suggest">
          {res.length === 0 && <li className="suggest-empty">No results</li>}
          {res.map(r => (
            <li key={r.app_id}>
              <a href={`#/game/${r.app_id}`} onClick={() => { setRes(null); setQ(""); }}>
                <img src={r.image || ""} alt="" referrerPolicy="no-referrer" />
                <span className="sug-name">{r.name}</span>
                {r.final != null && <span className="sug-price">{money(r.final, r.currency, r.divisor)}</span>}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CookieBanner({ onAccept, onDecline }) {
  return (
    <div className="cookie-bar">
      <span>We use localStorage to remember your region preference.{" "}
        <a href="#/privacy">Privacy policy</a>
      </span>
      <div className="cookie-btns">
        <button className="btn-accept" onClick={onAccept}>Accept</button>
        <button className="btn-decline" onClick={onDecline}>Decline</button>
      </div>
    </div>
  );
}

export default function App() {
  const route = useRoute();
  const [meta, setMeta] = useState(null);
  const [cc, setCc] = useState(localStorage.getItem("st_cc") || "");
  const [cookieShown, setCookieShown] = useState(!localStorage.getItem("st_consent"));

  useEffect(() => {
    api("/meta")
      .then(m => {
        setMeta(m);
        setCc(cur => m.regions.includes(cur) ? cur : m.default_region);
      })
      .catch(() => {});
  }, []);

  const changeRegion = v => {
    setCc(v);
    if (localStorage.getItem("st_consent") === "yes") localStorage.setItem("st_cc", v);
  };

  const accept = () => { localStorage.setItem("st_consent", "yes"); localStorage.setItem("st_cc", cc); setCookieShown(false); };
  const decline = () => { localStorage.setItem("st_consent", "no"); setCookieShown(false); };

  const page = () => {
    if (route.name === "game") return <Game key={route.id + cc} id={route.id} cc={cc} />;
    if (route.name === "about") return <About />;
    if (route.name === "privacy") return <Privacy />;
    return <Home key={cc} cc={cc} meta={meta} />;
  };

  return (
    <>
      <header className="topbar">
        <a className="brand" href="#/">SteamTracker</a>
        <Search cc={cc} />
        <nav className="topnav">
          {meta && (
            <select value={cc} onChange={e => changeRegion(e.target.value)} aria-label="Region">
              {meta.regions.map(r => (
                <option key={r} value={r}>
                  {CC_NAMES[r] ? `${r.toUpperCase()} · ${CC_NAMES[r]}` : r.toUpperCase()}
                </option>
              ))}
            </select>
          )}
          <a href="#/about">About</a>
          <a href="#/privacy">Privacy</a>
        </nav>
      </header>

      <main>{page()}</main>

      <footer className="foot">
        <div className="foot-inner">
          <div className="foot-links">
            <span className="foot-brand">SteamTracker</span>
            <a href="#/about">About</a>
            <a href="#/privacy">Privacy</a>
          </div>
          {meta && (
            <p className="foot-meta">
              {num(meta.games)} games &middot; {num(meta.price_points)} price points
              {meta.last_check ? ` · last check ${date(meta.last_check)}` : ""}
            </p>
          )}
          <p className="foot-disc">
            Not affiliated with Valve or Steam. Prices sourced from Steam's public storefront API.
            Forecasts are estimates, not guarantees.
          </p>
        </div>
      </footer>

      {cookieShown && <CookieBanner onAccept={accept} onDecline={decline} />}
    </>
  );
}
