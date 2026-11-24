import React from "react";
export default function About() {
  return (
    <div className="static-page">
      <h1>About SteamTracker</h1>
      <p>SteamTracker is a self-hosted, open-source Steam price tracker. It watches Steam's public storefront API, records every price change for every tracked game in every region, and builds a local history over time.</p>
      <h2>How it works</h2>
      <ul>
        <li>A background collector polls Steam's public storefront endpoints every few hours.</li>
        <li>Only price <em>changes</em> are stored — if nothing changed, nothing is written.</li>
        <li>Prices are collected for every configured region simultaneously (US, UK, EU, India, and more).</li>
        <li>A prediction model uses the official Steam sale calendar plus the game's own discount history to estimate the probability and depth of the next discount.</li>
      </ul>
      <h2>Data sources</h2>
      <ul>
        <li><strong>Steam storefront API</strong> — prices, game metadata, player counts, reviews.</li>
        <li><strong>IsThereAnyDeal</strong> (optional) — historical price backfill.</li>
        <li><strong>CheapShark</strong> — all-time-low cross-check in USD.</li>
        <li><strong>Steam sale calendar</strong> — manually updated from published Valve announcements.</li>
      </ul>
      <h2>Limitations</h2>
      <ul>
        <li>History starts when you start collecting (or if you configure ITAD backfill).</li>
        <li>Predictions are probabilistic estimates. Valve sets sale dates; publishers choose discounts.</li>
        <li>Not affiliated with Valve Corporation or Steam.</li>
      </ul>
    </div>
  );
}
