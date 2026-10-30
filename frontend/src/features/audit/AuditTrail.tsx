import React, { FormEvent, Fragment, useEffect, useState } from "react";
import { ApiError, download, get } from "../../api/client";
import { useI18n } from "../../i18n";

/** Administrator screen: every saved record, and for the one you open, how it was made (FR-14, FR-15). */
export default function AuditTrail({ config }: { config: any }) {
  const { lang, t } = useI18n();
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [includeSeed, setIncludeSeed] = useState(true);
  const [open, setOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"saved" | "unsaved">("saved");
  const [unsaved, setUnsaved] = useState<any>(null);
  const size = 15;
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));

  useEffect(() => {
    get<any>("/api/audit/records", { q: term || undefined, include_seed: includeSeed, page, page_size: size })
      .then((r) => { setItems(r.items); setTotal(r.total); setError(null); }).catch(fail);
  }, [term, includeSeed, page]);

  useEffect(() => {
    if (view === "unsaved") get<any>("/api/audit/unsaved", { page, page_size: size }).then((r) => { setUnsaved(r); setError(null); }).catch(fail);
  }, [view, page]);

  const toggle = (id: string) => {
    if (open === id) { setOpen(null); setDetail(null); return; }
    setOpen(id); setDetail(null);
    get<any>(`/api/audit/records/${id}`).then(setDetail).catch(fail);
  };

  const name = (list: any[], id: string) => list?.find((x: any) => x.id === id)?.[lang] || id || "–";
  const LABELS: Record<string, string> = { customer_id: t("f.customer_name"), root_cause: t("col.cause"), description: t("description"), summary: t("summary") };
  const field = (k: string) => LABELS[k] || (t(`f.${k}`) === `f.${k}` ? k : t(`f.${k}`));
  const action = (a: string) => (t(`audit.action.${a}`) === `audit.action.${a}` ? a.replace(/_/g, " ") : t(`audit.action.${a}`));
  const pages = Math.max(1, Math.ceil((view === "unsaved" ? (unsaved?.total ?? 0) : total) / size));
  const cell = (v: any) => (v === null || v === undefined || v === "" ? "–" : typeof v === "object" ? JSON.stringify(v) : String(v));

  return (
    <section>
      <h2>{t("audit.title")}</h2>
      <p className="muted">{t("audit.intro")}</p>
      {error && <p className="error" role="alert">{t("error")}: {error}</p>}
      <div className="inline" role="tablist">
        <button role="tab" aria-selected={view === "saved"} className={view === "saved" ? "" : "secondary"} onClick={() => { setView("saved"); setPage(1); }}>{t("audit.view.saved")}</button>
        <button role="tab" aria-selected={view === "unsaved"} className={view === "unsaved" ? "" : "secondary"} onClick={() => { setView("unsaved"); setPage(1); }}>{t("audit.view.unsaved")}</button>
      </div>
      {view === "unsaved" && (
        <>
          <p className="muted">{t("audit.unsaved.note")}</p>
          <p className="muted" role="status">{t("audit.unsaved.count", { n: unsaved?.total ?? 0 })}</p>
          <div className="table-scroll"><table>
            <thead><tr><th>{t("ds.when")}</th><th>{t("ds.by")}</th><th>{t("audit.col.last")}</th>
              {["find_customer", "review_details", "describe_complaint", "classify", "repeat_save"].map((k) => <th key={k}>{t(`step.${k}`)} (s)</th>)}<th>{t("audit.col.total")}</th><th>{t("audit.col.status")}</th></tr></thead>
            <tbody>{(unsaved?.items || []).map((r: any) => (
              <tr key={r.id}>
                <td>{String(r.started).replace("T", " ").slice(0, 19)}<br /><small>{r.id.slice(0, 8)}</small></td>
                <td>{r.actor_name || r.actor}</td>
                <td>{r.last_step ? t(`step.${r.last_step}`) : "–"}</td>
                {r.steps.map((st: any) => <td key={st.step}>{st.seconds > 0 ? st.seconds : "–"}</td>)}
                <td>{r.total_seconds}</td>
                <td>{t(`audit.status.${r.status}`)}{r.failure_status && ` (${r.failure_status})`}</td>
              </tr>))}</tbody>
          </table></div>
          {(unsaved?.items || []).length === 0 && <p className="empty">{t("audit.unsaved.none")}</p>}
        </>
      )}
      {view === "saved" && <>
      <div className="filters">
        <form className="inline" onSubmit={(e: FormEvent) => { e.preventDefault(); setPage(1); setTerm(q.trim()); }}>
          <label>{t("audit.search")}<input value={q} maxLength={100} onChange={(e) => setQ(e.target.value)} /></label>
          <button className="secondary">{t("audit.find")}</button>
        </form>
        <label className="checkbox">
          <input type="checkbox" checked={includeSeed} onChange={(e) => { setPage(1); setIncludeSeed(e.target.checked); }} />
          {t("history.seed")}
        </label>
        <button className="secondary" onClick={() => download("/api/export/records.csv", "records.csv", { include_seed: includeSeed }).catch(fail)}>{t("audit.export")}</button>
      </div>
      <p className="muted" role="status">{t("audit.count", { n: total })}</p>
      <div className="table-scroll"><table>
        <thead><tr>
          <th>{t("audit.col.record")}</th><th>{t("f.registration_date")}</th><th>{t("f.customer_name")}</th><th>{t("f.site_id")}</th>
          <th>{t("f.complaint_type")}</th><th>{t("col.cause")}</th><th>{t("f.channel")}</th><th>{t("f.status")}</th><th>{t("col.repeat")}</th><th>{t("f.registering_user")}</th><th>{t("audit.col.log")}</th>
        </tr></thead>
        <tbody>
          {items.map((r) => (
            <Fragment key={r.id}>
              <tr className={open === r.id ? "selected" : undefined}>
                <td>
                  <button className="secondary" aria-expanded={open === r.id} onClick={() => toggle(r.id)}>{r.id}</button>{" "}
                  <span className={`badge ${r.is_seed ? "prov-blank" : "prov-prefilled"}`}>{r.is_seed ? t("audit.seeded") : t("audit.registered")}</span>
                </td>
                <td>{String(r.registration_date || r.created || "").slice(0, 10)}</td>
                <td>{r.customer_name}<br /><small>{r.customer_number}</small></td>
                <td>{cell(r.site_name)}</td>
                <td>{name(config.types, r.complaint_type)}</td>
                <td>{name(config.root_causes, r.root_cause)}</td>
                <td>{r.channel}</td>
                <td>{r.status}</td>
                <td>{r.repeat_detected === null ? "–" : r.repeat_detected ? t("yes") : t("no")}</td>
                <td>{cell(r.registered_by)}</td>
                <td>{r.log === "complete" ? <span className="badge prov-prefilled">{t("audit.log.complete")}</span> : r.log === "incomplete" ? <span className="badge prov-default">{t("audit.log.incomplete")}</span> : <span className="muted">–</span>}</td>
              </tr>
            </Fragment>
          ))}
        </tbody>
      </table></div>
      {items.length === 0 && <p className="empty">{t("audit.none")}</p>}
      {open && (
        <div className="audit-panel" aria-label={open}>
          <h3>{open} <button className="secondary" onClick={() => { setOpen(null); setDetail(null); }}>{t("audit.close")}</button></h3>
{!detail ? <p>{t("loading")}</p> : (
            <div className="audit-detail">
              <article className="card" aria-label={t("audit.log.title")}>
                <h3>{t("audit.log.title")} {detail.log.applicable && (detail.log.complete
                  ? <span className="badge prov-prefilled">{t("audit.log.complete")}</span> : <span className="badge prov-default">{t("audit.log.incomplete")}</span>)}</h3>
                {!detail.log.applicable ? <p className="empty">{t("audit.no_origins")}</p> : (<>
                  {detail.log.missing.length > 0 && <p className="warn">{t("audit.log.missing")}: {detail.log.missing.join(", ")}</p>}
                  <p className="muted">{String(detail.log.started || "").replace("T", " ").slice(0, 19)} → {String(detail.log.ended || "").replace("T", " ").slice(0, 19)} · {t("audit.log.total", { s: detail.log.total_seconds })}
                    {detail.log.time_check?.result === "capped" && ` · ${t("audit.log.capped")}`}</p>
                  <h4>{t("audit.log.steps")}</h4>
                  <table><thead><tr><th>{t("audit.col.step")}</th><th>{t("audit.log.seconds")}</th><th>{t("audit.log.visits")}</th></tr></thead>
                    <tbody>{detail.log.steps.map((st: any) => <tr key={st.step}><td>{t(`step.${st.step}`)}</td><td>{st.seconds}</td><td>{st.visits}</td></tr>)}</tbody></table>
                  <h4>{t("audit.log.prefilled")}</h4>
                  <p>{t("audit.log.prefilled_n", { p: detail.log.prefilled_at_start.prefilled, d: detail.log.prefilled_at_start.default })}</p>
                  <p className="origins">{Object.entries(detail.log.fields_at_save).map(([o, n]: [string, any]) => <span key={o}><span className={`badge prov-${o}`}>{t(`prov.${o}`)}</span> {n}</span>)}</p>
                  {detail.log.edits.length > 0 && <p>{t("audit.log.edits")}: {detail.log.edits.map((e: any) => `${field(e.field)} → ${t(`prov.${e.origin}`)}`).join(", ")}</p>}
                  <h4>{t("audit.log.suggestions")}</h4>
                  {detail.log.suggestions.causes.length === 0 ? <p className="empty">{t("audit.log.none")}</p> : (<>
                    <p>{t("f.complaint_type")}: <b>{name(config.types, detail.log.suggestions.complaint_type)}</b> — {detail.log.suggestions.type_result === "kept" ? t("audit.type.kept") : t("audit.type.changed", { to: name(config.types, detail.log.suggestions.saved_type) })}</p>
                    <table><thead><tr><th>{t("col.cause")}</th><th>%</th><th>{t("ds.reason")}</th></tr></thead>
                      <tbody>{detail.log.suggestions.causes.map((c: any) => (
                        <tr key={c.root_cause_id} className={c.root_cause_id === detail.log.suggestions.selected_cause ? "selected" : undefined}>
                          <td>{name(config.root_causes, c.root_cause_id)}</td><td>{Math.round(c.confidence * 100)}</td><td>{c.reason}</td></tr>))}</tbody></table>
                    <p>{t("audit.log.chosen")}: <b>{name(config.root_causes, detail.log.suggestions.selected_cause)}</b> — {t(`audit.cause.${detail.log.suggestions.cause_result}`)}</p>
                  </>)}
                  {detail.log.suggestions.summary_result && <p>{t("summary")}: {detail.log.suggestions.summary_result === "kept" ? t("audit.log.summary_kept")
                    : t("audit.log.summary_changed", { f: detail.log.suggestions.summary_changed_fields.join(", ") })}</p>}
                  {detail.log.suggestions.ai_calls.length > 0 && <p className="muted">{detail.log.suggestions.ai_calls.map((c: any) => `${c.operation} ${c.status} ${c.ms} ms`).join(" · ")}</p>}
                </>)}
              </article>
              <article className="card">
                <h3>{t("audit.record")}</h3>
                <p className="muted">{t("audit.record_note")}{detail.missing_required.length === 0 && ` ${t("audit.complete")}`}</p>
                <table><tbody>
                  {Object.entries(detail.record).map(([k, v]) => <tr key={k}><td><code>{k}</code></td><td>{cell(v)}{k === "PROVISIONAL_RegisteredBy" && items.find((x) => x.id === open)?.registered_by ? ` (${items.find((x) => x.id === open)?.registered_by})` : ""}</td></tr>)}
                </tbody></table>
              </article>
              <article className="card">
                <h3>{t("audit.origins")}</h3>
                {detail.origins.length === 0 ? <p className="empty">{t("audit.no_origins")}</p> : (
                  <ul className="origins">{detail.origins.map((o: any) => (
                    <li key={o.field}>{field(o.field)} <span className={`badge prov-${o.origin}`}>{t(`prov.${o.origin}`)}</span></li>
                  ))}</ul>
                )}
              </article>
              <article className="card">
                <h3>{t("audit.repeat")}</h3>
                {detail.repeat_checks.length === 0 ? <p className="empty">{t("audit.no_repeat")}</p> : detail.repeat_checks.map((c: any) => (
                  <p key={c.id}>{c.is_repeat ? t("audit.is_repeat", { n: (c.matching_ids || []).length }) : t("repeat.no")} · {c.rule_version}
                    {(c.matching_ids || []).length > 0 && <> · {(c.matching_ids || []).join(", ")}</>}</p>
                ))}
                {detail.repeat_disputes.map((d: any) => (
                  <p key={d.id}><b>{d.prior_complaint_id}</b>: {d.decision === "reject" ? t("repeat.reject") : t("repeat.confirm")} — {d.reason}</p>
                ))}
              </article>
              <article className="card">
                <h3>{t("audit.events")}</h3>
                {detail.events.length === 0 ? <p className="empty">{t("eval.none")}</p> : (
                  <table>
                    <thead><tr><th>{t("ds.when")}</th><th>{t("audit.col.event")}</th><th>{t("ds.by")}</th></tr></thead>
                    <tbody>{detail.events.map((e: any) => (
                      <tr key={e.id}><td>{String(e.at).replace("T", " ").slice(0, 19)}</td><td>{action(e.action)}</td><td>{e.actor_name || e.actor}</td></tr>
                    ))}</tbody>
                  </table>
                )}
              </article>
            </div>
          )}
        </div>
      )}
      </>}
      <div className="pager">
        <button className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label={t("audit.prev")}>←</button>
        <span>{t("page", { p: page, n: pages })}</span>
        <button className="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label={t("audit.next")}>→</button>
      </div>
    </section>
  );
}
