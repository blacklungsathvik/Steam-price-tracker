import React from "react";
export default function Privacy() {
  return (
    <div className="static-page">
      <h1>Privacy &amp; Cookies</h1>
      <p>Last updated: November 2026</p>
      <h2>What data we collect</h2>
      <ul>
        <li>SteamTracker is self-hosted. No personal data is sent to any third party by this application.</li>
        <li>The server logs standard HTTP request data (IP address, path, timestamp) for debugging only.</li>
        <li>No accounts, no email addresses, no user profiles.</li>
      </ul>
      <h2>Local storage</h2>
      <p>We use the browser's localStorage (not traditional cookies) to remember:</p>
      <ul>
        <li><code>st_cc</code> — your selected Steam region (e.g. "us", "in").</li>
        <li><code>st_consent</code> — whether you accepted or declined this notice.</li>
      </ul>
      <p>No tracking pixels, no advertising, no analytics SDKs, no third-party scripts.</p>
      <h2>Third-party requests</h2>
      <ul>
        <li>Game cover images are loaded from Steam's CDN (steamstatic.com). Steam's privacy policy applies to those requests.</li>
        <li>No other third-party assets are loaded.</li>
      </ul>
      <h2>Your choices</h2>
      <ul>
        <li>If you clicked "Decline", your region preference is not saved between visits.</li>
        <li>To clear stored data: browser DevTools → Application → Local Storage → delete <code>st_cc</code> and <code>st_consent</code>.</li>
      </ul>
    </div>
  );
}
