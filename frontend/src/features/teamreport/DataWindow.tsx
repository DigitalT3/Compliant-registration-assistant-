import { useEffect } from "react";
import { useI18n } from "../../i18n";

export type Since = { mode: "all" | "1h" | "today" | "7d" | "custom"; custom: string };
export const ALL: Since = { mode: "all", custom: "" };
const KEY = "cra.since";
const AUTO_MS = 30000;

/** The start of the window as an ISO time (computed when asked, so "last hour" keeps moving); undefined means everything. */
export function sinceIso(s: Since): string | undefined {
  const now = new Date();
  if (s.mode === "1h") return new Date(now.getTime() - 3600_000).toISOString();
  if (s.mode === "7d") return new Date(now.getTime() - 7 * 86400_000).toISOString();
  if (s.mode === "today") return new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
  if (s.mode === "custom" && s.custom) { const d = new Date(s.custom); return isNaN(d.getTime()) ? undefined : d.toISOString(); }
  return undefined;
}

export function loadSince(): Since {
  try { const v = JSON.parse(localStorage.getItem(KEY) || "null"); if (v && typeof v.mode === "string") return { mode: v.mode, custom: v.custom || "" }; } catch { /* no storage: start from everything */ }
  return ALL;
}
export function saveSince(s: Since) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* a per-viewer convenience only */ } }

/** Calls ``tick`` every 30 s while the page is visible and auto-refresh is on, so the figures follow new registrations. */
export function useAutoRefresh(on: boolean, tick: () => void) {
  useEffect(() => {
    if (!on) return;
    const id = window.setInterval(() => { if (document.visibilityState === "visible") tick(); }, AUTO_MS);
    return () => window.clearInterval(id);
  }, [on, tick]);
}

/** Which registrations the figures cover, and how fresh they are. */
export default function DataWindow({ since, onSince, onRefresh, auto, onAuto, updatedAt, busy }: {
  since: Since; onSince: (s: Since) => void; onRefresh: () => void; auto: boolean; onAuto: (v: boolean) => void; updatedAt: Date | null; busy: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="inline data-window" role="group" aria-label={t("win.title")}>
      <label>{t("win.since")} <select value={since.mode} onChange={(e) => onSince({ ...since, mode: e.target.value as Since["mode"] })}>
        <option value="all">{t("win.all")}</option>
        <option value="1h">{t("win.1h")}</option>
        <option value="today">{t("win.today")}</option>
        <option value="7d">{t("win.7d")}</option>
        <option value="custom">{t("win.custom")}</option>
      </select></label>
      {since.mode === "custom" && (
        <input type="datetime-local" aria-label={t("win.custom")} value={since.custom} onChange={(e) => onSince({ ...since, custom: e.target.value })} />
      )}
      <button className="secondary" onClick={onRefresh} disabled={busy}>{t("win.refresh")}</button>
      <label className="check"><input type="checkbox" checked={auto} onChange={(e) => onAuto(e.target.checked)} /> {t("win.auto")}</label>
      <span className="muted" role="status">{updatedAt ? t("win.updated", { time: updatedAt.toLocaleTimeString() }) : ""}</span>
    </div>
  );
}
