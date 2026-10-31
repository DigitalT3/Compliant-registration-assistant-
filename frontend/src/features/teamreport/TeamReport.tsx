import { useEffect, useMemo, useState } from "react";
import { ApiError, get } from "../../api/client";
import { useI18n } from "../../i18n";
import { Loading } from "../../ui";

const STEPS = ["find_customer", "review_details", "describe_complaint", "classify", "repeat_save"];
const OUTCOMES = ["accepted", "changed", "typed"];
const PAGE = 20;
const WINDOWS = ["1", "5", "10", "15", "all"];                        // how many of the latest registrations the step list and its average cover

type Table = { columns: string[]; rows: any[][] };
const asObjects = (t: Table) => t.rows.map((r) => Object.fromEntries(t.columns.map((c, i) => [c, r[i]])) as Record<string, any>);
const label = (s: string) => s.replace(/_/g, " ");
const seconds = (v: number | null | undefined) => (v === null || v === undefined ? "–" : String(Math.round(v * 10) / 10));

/** The team report (step 6 of the user flow): time per step and every suggestion accepted or changed, drawn from the same read-only
 * tables as the Power BI feed. A team lead gets their own team's rows only (the server scopes them); an administrator gets everyone's. */
export default function TeamReport({ targets = {} }: { targets?: Record<string, number> }) {
  const { t } = useI18n();
  const [sessions, setSessions] = useState<Record<string, any>[] | null>(null);
  const [suggestions, setSuggestions] = useState<Record<string, any>[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [field, setField] = useState("");
  const [outcome, setOutcome] = useState("");
  const [page, setPage] = useState(1);
  const [window, setWindow] = useState("15");

  useEffect(() => {
    Promise.all([get<Table>("/api/reporting/sessions", { format: "json" }), get<Table>("/api/reporting/suggestions", { format: "json" })])
      .then(([s, g]) => { setSessions(asObjects(s)); setSuggestions(asObjects(g)); setError(null); })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  const byField = useMemo(() => {
    const out: Record<string, Record<string, number>> = {};
    for (const s of suggestions || []) (out[s.field] ||= { accepted: 0, changed: 0, typed: 0 })[s.outcome] = ((out[s.field] || {})[s.outcome] || 0) + 1;
    return Object.entries(out).sort((a, b) => a[0].localeCompare(b[0]));
  }, [suggestions]);
  const totals = useMemo(() => {
    const n = { accepted: 0, changed: 0, typed: 0 } as Record<string, number>;
    for (const s of suggestions || []) if (s.outcome in n) n[s.outcome] += 1;
    return n;
  }, [suggestions]);

  if (error) return <article className="card"><h3>{t("tr.title")}</h3><p className="warn" role="alert">{error}</p></article>;
  if (!sessions || !suggestions) return <article className="card"><h3>{t("tr.title")}</h3><Loading label={t("loading")} lines={4} /></article>;
  if (!sessions.length) return <article className="card"><h3>{t("tr.title")}</h3><p className="empty">{t("tr.empty")}</p></article>;

  const timed = sessions.filter((s) => STEPS.some((k) => typeof s[`${k}_s`] === "number"));
  const latest = window === "all" ? timed : timed.slice(0, Number(window));              // the feed lists the newest registration first
  const mean = (v: any[]) => { const n = v.filter((x) => typeof x === "number"); return n.length ? n.reduce((a: number, b: number) => a + b, 0) / n.length : null; };
  const avg = Object.fromEntries(STEPS.map((k) => [k, mean(latest.map((s) => s[`${k}_s`]))]));
  const longest = Math.max(1, ...latest.map((s) => STEPS.reduce((a, k) => a + (s[`${k}_s`] || 0), 0)));
  const totalTarget = STEPS.reduce((a, k) => a + (targets[k] || 0), 0);
  const avgTotal = mean(latest.map((s) => s.duration_s));
  const decided = totals.accepted + totals.changed + totals.typed;
  const share = (n: number) => (decided ? `${Math.round((n / decided) * 100)}%` : "–");
  const fields = [...new Set(suggestions.map((s) => s.field))].sort();
  const shown = suggestions.filter((s) => (!field || s.field === field) && (!outcome || s.outcome === outcome));
  const pages = Math.max(1, Math.ceil(shown.length / PAGE));
  const rows = shown.slice((page - 1) * PAGE, page * PAGE);
  const manyTeams = new Set(suggestions.map((s) => s.team)).size > 1;

  return (
    <article className="card team-report" aria-label={t("tr.title")}>
      <h3>{t("tr.title")}</h3>
      <p className="muted">{t("tr.intro")}</p>

      <div className="metric-grid">
        <article className="metric card"><span>{t("tr.registrations")}</span><strong>{sessions.length}</strong><small>{t("tr.timed", { n: timed.length })}</small></article>
        {OUTCOMES.map((o) => (
          <article key={o} className="metric card"><span>{t(`tr.o.${o}`)}</span><strong>{share(totals[o])}</strong><small>{totals[o]} / {decided}</small></article>
        ))}
      </div>

      <h4>{t("tr.steps")}</h4>
      <p className="muted">{t("tr.steps_note")}</p>
      <div className="inline">
        <label>{t("tr.window")} <select value={window} onChange={(e) => setWindow(e.target.value)}>
          {WINDOWS.map((w) => <option key={w} value={w}>{w === "all" ? t("tr.all_regs", { n: timed.length }) : w === "1" ? t("tr.latest_one") : t("tr.latest_n", { n: w })}</option>)}
        </select></label>
        <span className="muted">{t("tr.window_note", { n: latest.length })}</span>
      </div>
      <ul className="legend" aria-hidden="true">{STEPS.map((k, i) => <li key={k}><i className={`swatch step-${i}`} />{t(`tr.step.${k}`)}</li>)}</ul>
      <div className="table-scroll">
        <table>
          <thead><tr><th>{t("tr.user")}</th><th>{t("tr.registration")}</th><th>{t("tr.chart")}</th>{STEPS.map((k) => <th key={k}>{t(`tr.step.${k}`)}</th>)}<th>{t("tr.total")}</th></tr></thead>
          <tbody>
            {latest.map((s) => (
              <tr key={s.session_id}>
                <td>{s.user}</td><td><code>{String(s.session_id).slice(0, 8)}</code></td>
                <td className="stack-cell">
                  <div className="stack" role="img" aria-label={STEPS.map((k) => `${t(`tr.step.${k}`)} ${seconds(s[`${k}_s`])}`).join(", ")}>
                    {STEPS.map((k, i) => s[`${k}_s`] ? <span key={k} className={`seg step-${i}`} style={{ width: `${(s[`${k}_s`] / longest) * 100}%` }} title={`${t(`tr.step.${k}`)}: ${seconds(s[`${k}_s`])} s`} /> : null)}
                  </div>
                </td>
                {STEPS.map((k) => <td key={k}>{seconds(s[`${k}_s`])}</td>)}
                <td><b>{seconds(s.duration_s)}</b></td>
              </tr>
            ))}
            <tr className="sum-row"><td colSpan={3}>{latest.length === 1 ? t("tr.this_one") : t("tr.average")}</td>
              {STEPS.map((k) => <td key={k} className={targets[k] && avg[k] !== null && avg[k] > targets[k] ? "over-target" : undefined}>{seconds(avg[k])}</td>)}
              <td className={totalTarget && avgTotal !== null && avgTotal > totalTarget ? "over-target" : undefined}>{seconds(avgTotal)}</td></tr>
            {totalTarget > 0 && <tr className="target-row"><td colSpan={3}>{t("tr.target")}</td>{STEPS.map((k) => <td key={k}>{targets[k] ?? "–"}</td>)}<td>{totalTarget}</td></tr>}
          </tbody>
        </table>
      </div>

      <h4>{t("tr.by_field")}</h4>
      <p className="muted">{t("tr.by_field_note")}</p>
      <ul className="legend" aria-hidden="true">{OUTCOMES.map((o) => <li key={o}><i className={`swatch out-${o}`} />{t(`tr.o.${o}`)}</li>)}</ul>
      <div className="field-bars">
        {byField.map(([f, c]) => {
          const n = c.accepted + c.changed + c.typed;
          return (
            <div className="field-row" key={f}>
              <span>{label(f)}</span>
              <div className="stack" role="img" aria-label={OUTCOMES.map((o) => `${t(`tr.o.${o}`)} ${c[o]}`).join(", ")}>
                {OUTCOMES.map((o) => c[o] ? <span key={o} className={`seg out-${o}`} style={{ width: `${(c[o] / n) * 100}%` }} title={`${t(`tr.o.${o}`)}: ${c[o]}`}>{c[o]}</span> : null)}
              </div>
              <b>{n}</b>
            </div>
          );
        })}
      </div>

      <h4>{t("tr.log")}</h4>
      <div className="inline">
        <label>{t("tr.field")} <select value={field} onChange={(e) => { setField(e.target.value); setPage(1); }}><option value="">{t("tr.all")}</option>{fields.map((f) => <option key={f} value={f}>{label(f)}</option>)}</select></label>
        <label>{t("tr.outcome")} <select value={outcome} onChange={(e) => { setOutcome(e.target.value); setPage(1); }}><option value="">{t("tr.all")}</option>{OUTCOMES.map((o) => <option key={o} value={o}>{t(`tr.o.${o}`)}</option>)}</select></label>
        <span className="muted">{t("tr.count", { n: shown.length })}</span>
      </div>
      <div className="table-scroll">
        <table>
          <thead><tr><th>{t("tr.complaint")}</th><th>{t("tr.field")}</th><th>{t("tr.outcome")}</th><th>{t("tr.origin")}</th><th>{t("tr.user")}</th>{manyTeams && <th>{t("tr.team")}</th>}</tr></thead>
          <tbody>{rows.map((s, i) => (
            <tr key={`${s.complaint_id}-${s.field}-${i}`}>
              <td>{s.complaint_id}</td><td>{label(s.field)}</td>
              <td><span className={`badge out-badge out-${s.outcome}`}>{t(`tr.o.${s.outcome}`)}</span></td>
              <td>{s.origin}</td><td>{s.user}</td>{manyTeams && <td>{label(String(s.team || ""))}</td>}
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="inline">
        <button className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>←</button>
        <span>{t("page", { p: page, n: pages })}</span>
        <button className="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>→</button>
      </div>
    </article>
  );
}
