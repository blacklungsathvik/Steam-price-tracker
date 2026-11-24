export async function api(path, cc) {
  const sep = path.includes("?") ? "&" : "?";
  const r = await fetch(`/api${path}${cc ? `${sep}cc=${encodeURIComponent(cc)}` : ""}`);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(body.error || r.statusText), { status: r.status });
  return body;
}

export const DAY = 86400;

export function money(minor, cur, div = 100) {
  if (minor == null) return "—";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: cur || "USD" }).format(minor / div);
  } catch {
    return (minor / div).toFixed(2) + " " + (cur || "");
  }
}

export const date = (ts) =>
  new Date(ts * 1000).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
export const iso = (s) =>
  new Date(s + "T12:00:00Z").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
export const num = (n) => (n == null ? "—" : n.toLocaleString());
export const pct = (p) => Math.round(p * 100) + "%";
export const daysFrom = (isoStr) =>
  Math.max(0, Math.round((new Date(isoStr + "T12:00:00Z") - Date.now()) / (DAY * 1000)));
