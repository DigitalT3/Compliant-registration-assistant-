import { useEffect, useReducer, useState } from "react";
import { get, post, ApiError } from "../../api/client";
import { useI18n } from "../../i18n";

const STEPS = ["find_customer", "review_details", "describe_complaint", "classify", "check_repeats", "review_save"] as const;
type Field = { value: string | null; provenance: string };

interface State {
  step: number;
  q: string;
  search: any | null;
  customerId: string | null;
  ctx: any | null;
  fields: Record<string, Field>;
  text: string;
  textLang: string;
  summary: any | null;
  summaryFailed: string | null;
  cls: any | null;
  clsFailed: string | null;
  rootCause: string;
  otherReason: string;
  repeat: any | null;
  sessionId: string | null;
  saved: any | null;
}

const init: State = {
  step: 0, q: "", search: null, customerId: null, ctx: null, fields: {}, text: "", textLang: "auto", summary: null,
  summaryFailed: null, cls: null, clsFailed: null, rootCause: "", otherReason: "", repeat: null, sessionId: null, saved: null,
};

// Stepper state is kept in sessionStorage so a page reload does not lose the registration in progress.
function load(): State {
  try {
    return { ...init, ...JSON.parse(sessionStorage.getItem("cra.register") || "{}") };
  } catch {
    return init;
  }
}

function reducer(s: State, a: Partial<State> | { reset: true }): State {
  if ("reset" in a) return init;
  return { ...s, ...a };
}

function Prov({ p }: { p: string }) {
  const { t } = useI18n();
  return <span className={`badge prov-${p}`} title={t("prov.tip")}>{t(`prov.${p}`)}</span>;
}

export default function Register({ onViewHistory, config }: { onViewHistory: () => void; config: any }) {
  const { t, lang } = useI18n();
  const [s, set] = useReducer(reducer, undefined, load);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");

  useEffect(() => { sessionStorage.setItem("cra.register", JSON.stringify(s)); }, [s]);

  const val = (k: string) => s.fields[k]?.value || "";
  const label = (o: any) => (o ? o[lang] || o.en : "");
  const causes: any[] = config?.root_causes || [];
  const cause = causes.find((c) => c.id === s.rootCause);

  const run = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setErr(null);
    try { return await fn(); }
    catch (e) { setErr(e instanceof ApiError ? `${e.message}${e.requestId ? ` (${e.requestId.slice(0, 8)})` : ""}` : String(e)); }
    finally { setBusy(false); }
  };

  // Best-effort session/event logging: never blocks the user.
  const ev = (body: object) => { if (s.sessionId) post(`/api/sessions/${s.sessionId}/events`, body).catch(() => undefined); };
  const goto = (n: number) => {
    ev({ type: "step_completed", step: STEPS[s.step] });
    ev({ type: "step_entered", step: STEPS[n] });
    set({ step: n });
  };

  const setField = (k: string, v: string) => {
    const prev = s.fields[k]?.provenance;
    const provenance = prev === "prefilled" || prev === "default" || prev === "edited" ? "edited" : "manual";
    set({ fields: { ...s.fields, [k]: { value: v || null, provenance } } });
    ev({ type: "field", field: k, origin: provenance, changed: true });
  };

  const doSearch = () => run(async () => {
    const r = await get("/api/customers/search", { q: s.q });
    set({ search: r });
  });

  const selectCandidate = (c: any) => run(async () => {
    const sid = s.sessionId || (await post("/api/sessions")).session_id;
    const ctx = await get(`/api/customers/${c.customer_id}/context`);
    const pf = await post("/api/prefill", {
      customer_id: c.customer_id, site_id: c.matched_site_id, order_id: c.matched_order_id,
      complaint_type: s.fields.complaint_type?.value, session_id: sid,
    });
    set({ sessionId: sid, customerId: c.customer_id, ctx, fields: pf.fields, step: 1, search: null });
    post(`/api/sessions/${sid}/events`, { type: "step_entered", step: "review_details" }).catch(() => undefined);
  });

  const changeType = (v: string) => run(async () => {
    const pf = await post("/api/prefill", {
      customer_id: s.customerId, site_id: val("site_id") || null, order_id: val("order_id") || null, complaint_type: v,
      current_fields: Object.fromEntries(Object.entries(s.fields).filter(([, f]) => f.provenance === "manual" || f.provenance === "edited")),
    });
    set({ fields: { ...pf.fields, complaint_type: { value: v, provenance: "manual" } } });
  });

  const summarise = () => run(async () => {
    const r = await post("/api/complaints/summarise", {
      text: s.text, language: s.textLang === "auto" ? null : s.textLang, site_id: val("site_id") || null, session_id: s.sessionId,
    });
    if (r.ai_status === "ok") set({ summary: { ...r.result, mock: r.mock }, summaryFailed: null });
    else set({ summaryFailed: r.error_category || "unavailable", summary: s.summary || { what: "", where: "", when: "", impact: "" } });
  });

  const classify = () => run(async () => {
    const r = await post("/api/complaints/classify", { text: s.text, summary: s.summary, session_id: s.sessionId });
    if (r.ai_status === "ok") {
      const patch: Partial<State> = { cls: r, clsFailed: null, rootCause: r.preselect || "" };
      if (r.result.complaint_type && !val("complaint_type")) patch.fields = { ...s.fields, complaint_type: { value: r.result.complaint_type, provenance: "prefilled" } };
      set(patch);
    } else set({ cls: null, clsFailed: r.error_category || "unavailable" });
  });

  const checkRepeat = () => run(async () => {
    const r = await post("/api/complaints/check-repeat", {
      customer_id: s.customerId, site_id: val("site_id") || null, root_cause: s.rootCause || null, session_id: s.sessionId,
    });
    set({ repeat: r });
  });

  // Repeat panel re-runs whenever its key inputs change while on step 5.
  useEffect(() => {
    if (s.step === 4 && s.customerId) checkRepeat();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.step, s.rootCause, s.fields.site_id?.value]);

  const missing = [
    ["description", s.text], ["complaint_type", val("complaint_type")], ["root_cause", s.rootCause], ["channel", val("channel")],
    ...(s.rootCause === "other" ? [["other_reason", s.otherReason]] : []),
  ].filter(([, v]) => !String(v || "").trim()).map(([k]) => k);

  const save = () => run(async () => {
    const r = await post("/api/complaints", {
      customer_id: s.customerId, site_id: val("site_id") || null, contract_id: val("contract_id") || null,
      order_id: val("order_id") || null, channel: val("channel"), complaint_type: val("complaint_type"),
      root_cause: s.rootCause, other_reason: s.rootCause === "other" ? s.otherReason : null, description: s.text,
      language: s.textLang === "auto" ? s.summary?.language || null : s.textLang, summary: s.summary,
      summary_meta: s.summary ? { mock: !!s.summary.mock } : null, session_id: s.sessionId,
    });
    set({ saved: r });
  });

  if (s.saved)
    return (
      <section>
        <div className="ok" role="status">{t("saved", { id: s.saved.id })}</div>
        {s.saved.repeat.is_repeat && <p className="warn">{t("repeat.yes", { n: s.saved.repeat.count })}</p>}
        <button onClick={onViewHistory}>{t("saved.view")}</button>{" "}
        <button className="secondary" onClick={() => set({ reset: true })}>{t("new")}</button>
      </section>
    );

  const filtered = (f: string) => causes.filter((c) => !f || `${c.en} ${c.nl} ${c.id}`.toLowerCase().includes(f.toLowerCase()));
  const selectFields = (k: string, items: any[], text: (i: any) => string) => (
    <select id={k} value={val(k)} onChange={(e) => setField(k, e.target.value)}>
      <option value="">{t("choose")}</option>
      {items.map((i) => <option key={i.id} value={i.id}>{text(i)}</option>)}
    </select>
  );
  const row = (k: string, input: JSX.Element) => (
    <div className="row"><label htmlFor={k}>{t(`f.${k}`)}</label>{input}<Prov p={s.fields[k]?.provenance || "blank"} /></div>
  );

  return (
    <section>
      <ol className="stepper" aria-label="steps">
        {STEPS.map((k, i) => <li key={k} className={i === s.step ? "current" : i < s.step ? "done" : ""} aria-current={i === s.step ? "step" : undefined}>{i + 1}. {t(`step.${k}`)}</li>)}
      </ol>
      {err && <div className="error" role="alert">{t("error")}: {err}</div>}

      {s.step === 0 && (
        <div>
          <form onSubmit={(e) => { e.preventDefault(); doSearch(); }} className="inline">
            <label htmlFor="q">{t("search.label")}</label>
            <input id="q" value={s.q} onChange={(e) => set({ q: e.target.value })} maxLength={100} />
            <button disabled={busy || !s.q.trim()}>{t("search")}</button>
          </form>
          {s.search?.match_type === "none" && <p className="warn">{t("search.none")}</p>}
          {s.search?.ambiguous && <p className="warn">{t("search.ambiguous", { n: s.search.count })}</p>}
          {s.search?.candidates?.map((c: any) => (
            <div className="card" key={c.customer_id}>
              <strong>{c.name}</strong> · {c.number} · {c.postcode}
              <div className="muted">{t("search.matched", { type: s.search.match_type })} · {c.sites.length} {t("ctx.sites").toLowerCase()}</div>
              <button disabled={busy} onClick={() => selectCandidate(c)}>{t("search.select")}</button>
            </div>
          ))}
        </div>
      )}

      {s.step === 1 && s.ctx && (
        <div className="cols">
          <div>
            {row("customer_name", <span>{val("customer_name")}</span>)}
            {row("customer_number", <span>{val("customer_number")}</span>)}
            {row("site_id", selectFields("site_id", s.ctx.sites, (i) => `${i.name} (${i.reference})`))}
            {row("contract_id", selectFields("contract_id", s.ctx.contracts.filter((c: any) => !val("site_id") || c.site_id === val("site_id")), (i) => i.reference))}
            {row("order_id", selectFields("order_id", s.ctx.orders.filter((o: any) => !val("site_id") || o.site_id === val("site_id")), (i) => `${i.reference} · ${i.container}`))}
            {row("channel", <input id="channel" value={val("channel")} onChange={(e) => setField("channel", e.target.value)} />)}
            {row("complaint_type", (
              <select id="complaint_type" value={val("complaint_type")} onChange={(e) => changeType(e.target.value)}>
                <option value="">{t("choose")}</option>
                {(config?.types || []).map((x: any) => <option key={x.id} value={x.id}>{label(x)}</option>)}
              </select>
            ))}
            {row("registering_user", <span>{val("registering_user")}</span>)}
            {row("registration_date", <span>{val("registration_date")}</span>)}
          </div>
          <aside className="card">
            <h3>{t("ctx.title")}</h3>
            <h4>{t("ctx.sites")}</h4><ul>{s.ctx.sites.map((x: any) => <li key={x.id}>{x.name} · {x.postcode}</li>)}</ul>
            <h4>{t("ctx.contracts")}</h4><ul>{s.ctx.contracts.map((x: any) => <li key={x.id}>{x.reference} ({x.valid_to})</li>)}</ul>
            <h4>{t("ctx.orders")}</h4><ul>{s.ctx.orders.map((x: any) => <li key={x.id}>{x.reference} · {x.container} · {x.date.slice(0, 10)}</li>)}</ul>
          </aside>
        </div>
      )}

      {s.step === 2 && (
        <div>
          <label htmlFor="desc">{t("description")}</label>
          <textarea id="desc" rows={6} maxLength={8000} value={s.text} onChange={(e) => set({ text: e.target.value })} />
          <div className="inline">
            <label htmlFor="tl">{t("description.lang")}</label>
            <select id="tl" value={s.textLang} onChange={(e) => set({ textLang: e.target.value })}>
              <option value="auto">{t("lang.auto")}</option><option value="nl">NL</option><option value="en">EN</option>
            </select>
            <button disabled={busy || !s.text.trim()} onClick={summarise}>{t("summarise")}</button>
          </div>
          {s.summaryFailed && <p className="warn">{t("ai.failed", { cat: s.summaryFailed })}</p>}
          {s.summary && (
            <div className="card">
              <h3>{t("summary")} {s.summary.mock && <span className="badge mock">{t("ai.mock")}</span>}</h3>
              {(["what", "where", "when", "impact"] as const).map((k) => (
                <div className="row" key={k}>
                  <label htmlFor={`s-${k}`}>{t(`summary.${k}`)}</label>
                  <input id={`s-${k}`} value={s.summary[k] || ""} placeholder={t("summary.unknown")}
                    onChange={(e) => set({ summary: { ...s.summary, [k]: e.target.value || null } })} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {s.step === 3 && (
        <div>
          <button disabled={busy || !s.text.trim()} onClick={classify}>{t("classify")}</button>
          {s.clsFailed && <p className="warn">{t("ai.failed", { cat: s.clsFailed })}</p>}
          {s.cls && (
            <div className="card">
              <h3>{t("classify.cands")} <span className="badge mock">{t("ai.mock")}</span></h3>
              {s.cls.low_confidence && <p className="warn">{t("classify.low")}</p>}
              {s.cls.result.candidates.map((c: any) => (
                <label key={c.root_cause_id} className="radio">
                  <input type="radio" name="rc" checked={s.rootCause === c.root_cause_id} onChange={() => set({ rootCause: c.root_cause_id })} />
                  {label(causes.find((x) => x.id === c.root_cause_id))} <span className="muted">({Math.round(c.confidence * 100)}% – {c.reason})</span>
                </label>
              ))}
              <p className="muted">{t("classify.note")}</p>
            </div>
          )}
          <h3>{t("classify.all")}</h3>
          <label htmlFor="cf">{t("classify.search")}</label>
          <input id="cf" value={filter} onChange={(e) => setFilter(e.target.value)} />
          <div className="list">
            {filtered(filter).map((c) => (
              <label key={c.id} className="radio">
                <input type="radio" name="rc" checked={s.rootCause === c.id} onChange={() => set({ rootCause: c.id })} />
                {label(c)}
              </label>
            ))}
          </div>
          {s.rootCause === "other" && (
            <div className="card">
              <label htmlFor="or">{t("classify.other_reason")}</label>
              <input id="or" value={s.otherReason} maxLength={500} onChange={(e) => set({ otherReason: e.target.value })} />
              {s.cls && <p className="muted">{t("classify.closest")}: {s.cls.result.candidates.map((c: any) => label(causes.find((x) => x.id === c.root_cause_id))).join(", ") || "–"}</p>}
            </div>
          )}
        </div>
      )}

      {s.step === 4 && (
        <div className="card">
          {s.repeat ? (
            <>
              {s.repeat.missing_fields?.length > 0 && <p className="warn">{t("repeat.missing", { f: s.repeat.missing_fields.join(", ") })}</p>}
              <p className={s.repeat.is_repeat ? "warn" : "ok"}>{s.repeat.is_repeat ? t("repeat.yes", { n: s.repeat.count }) : t("repeat.no")}</p>
              <ul>{s.repeat.matches.map((m: any) => <li key={m.id}>{m.id} · {String(m.date || m.created || "").slice(0, 10)} · {m.cause || m.root_cause} · {m.status} {m.reason && <span className="muted">({m.reason})</span>}</li>)}</ul>
              <p className="muted">{t("repeat.rule", { v: s.repeat.rule_version, d: s.repeat.lookback_days })} · {s.repeat.checked_at}</p>
            </>
          ) : t("loading")}
          <button className="secondary" disabled={busy} onClick={checkRepeat}>{t("repeat.run")}</button>
        </div>
      )}

      {s.step === 5 && (
        <div className="card">
          <h3>{t("review.title")}</h3>
          <dl>
            <dt>{t("f.customer_name")}</dt><dd>{val("customer_name")} ({val("customer_number")})</dd>
            <dt>{t("f.site_id")}</dt><dd>{s.ctx?.sites.find((x: any) => x.id === val("site_id"))?.name || "–"}</dd>
            <dt>{t("f.channel")}</dt><dd>{val("channel") || "–"}</dd>
            <dt>{t("f.complaint_type")}</dt><dd>{label((config?.types || []).find((x: any) => x.id === val("complaint_type"))) || "–"}</dd>
            <dt>{t("col.cause")}</dt><dd>{label(cause) || "–"}{s.rootCause === "other" && `: ${s.otherReason}`}</dd>
            <dt>{t("description")}</dt><dd>{s.text || "–"}</dd>
            {s.summary && <><dt>{t("summary")}</dt><dd>{["what", "where", "when", "impact"].map((k) => s.summary[k]).filter(Boolean).join(" · ")}</dd></>}
            <dt>{t("col.repeat")}</dt><dd>{s.repeat ? (s.repeat.is_repeat ? t("yes") : t("no")) : "–"}</dd>
          </dl>
          {missing.length > 0 && <p className="warn">{t("review.missing", { f: missing.map((m) => t(`f.${m}`) === `f.${m}` ? m : t(`f.${m}`)).join(", ") })}</p>}
          <button disabled={busy || missing.length > 0} onClick={save}>{t("save")}</button>
        </div>
      )}

      {s.step > 0 && (
        <div className="nav">
          <button className="secondary" onClick={() => goto(s.step - 1)}>{t("back")}</button>{" "}
          {s.step < 5 && <button onClick={() => goto(s.step + 1)} disabled={busy}>{t("next")}</button>}
        </div>
      )}
    </section>
  );
}
