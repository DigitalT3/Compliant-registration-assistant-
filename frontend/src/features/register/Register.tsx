import { useEffect, useReducer, useState } from "react";
import { get, post, ApiError } from "../../api/client";
import { useI18n } from "../../i18n";
import CustomerData from "./CustomerData";

/** Best guess of what the employee typed, shown as a hint under the search box (the search itself tries every kind). */
const guessType = (q: string) => {
  const v = q.trim();
  if (/^ord-/i.test(v)) return "order";
  if (/^box-/i.test(v)) return "container";
  if (/^\d{6}$/.test(v)) return "customer_number";
  if (/^\d{4}\s?[a-z]{0,2}$/i.test(v)) return "postcode";
  return "name";
};

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
  analysedText: string;
  email: string;
  participant: string;
  scenarioTag: string;
  mode: "assistant" | "plain";
  emailNote: any | null;
  decisions: Record<string, { decision: "confirm" | "reject"; reason: string }>;
  cls: any | null;
  clsFailed: string | null;
  rootCause: string;
  causeOrigin: string;
  otherReason: string;
  repeat: any | null;
  sessionId: string | null;
  saved: any | null;
}

const init: State = {
  step: 0, q: "", search: null, customerId: null, ctx: null, fields: {}, text: "", textLang: "auto", summary: null,
  summaryFailed: null, analysedText: "", email: "", participant: "", scenarioTag: "", mode: "assistant", emailNote: null, decisions: {}, cls: null, clsFailed: null, rootCause: "", causeOrigin: "manual", otherReason: "", repeat: null, sessionId: null, saved: null,
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

export default function Register({ onViewHistory, onManageData, meName, config }: { onViewHistory: () => void; onManageData: () => void; meName?: string; config: any }) {
  const { t, lang } = useI18n();
  const [s, set] = useReducer(reducer, undefined, load);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");

  useEffect(() => { sessionStorage.setItem("cra.register", JSON.stringify(s)); }, [s]);

  // Coming back from the Customer data screen (or a reload): pick up sites, contracts, orders and containers added meanwhile.
  useEffect(() => {
    if (!s.customerId || s.saved) return;
    sessionStorage.setItem("cra.currentCustomer", s.customerId);
    get(`/api/customers/${s.customerId}/context`).then((ctx) => set({ ctx })).catch(() => undefined);
  }, []);

  const val = (k: string) => s.fields[k]?.value || "";
  const label = (o: any) => (o ? o[lang] || o.en : "");
  const causes: any[] = config?.root_causes || [];
  const cause = causes.find((c) => c.id === s.rootCause);
  // Two-level taxonomy: show "Category › sub-cause" (FR-11); "Other" stands alone.
  const causeLabel = (c: any) => {
    if (!c) return "";
    const cat = (config?.categories || []).find((x: any) => x.id === c.level1);
    return cat && c.id !== "other" ? `${label(cat)} › ${label(c)}` : label(c);
  };

  const run = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setErr(null);
    try { return await fn(); }
    catch (e) { setErr(e instanceof ApiError ? `${e.message}${e.requestId ? ` (${e.requestId.slice(0, 8)})` : ""}` : String(e)); }
    finally { setBusy(false); }
  };

  // Best-effort session/event logging: never blocks the user.
  const ev = (body: object) => { if (s.sessionId) post(`/api/sessions/${s.sessionId}/events`, body).catch(() => undefined); };
  const plain = s.mode === "plain";
  const next = async () => {
    if (plain && s.step === 2 && !s.summary) set({ summary: emptySummary });   // form only: no AI call
    if (!plain && s.step === 2 && s.text.trim() && s.analysedText !== s.text) {
      setBusy(true); setErr(null);
      try { await analyse(); }
      catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); setBusy(false); return; }
      setBusy(false);
    }
    goto(s.step + 1);
  };
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

  // FR-02: pasted email -> identifiers (checked against the customer data) + complaint text; then search.
  const extractEmail = () => run(async () => {
    const r = await post("/api/complaints/extract", { text: s.email });
    if (r.ai_status !== "ok") { set({ emailNote: { failed: r.error_category || "unavailable" } }); return; }
    const x = r.result, v = x.validation || {};
    const q = (v.customer_number && x.customer_number) || (v.order_reference && x.order_reference) || (v.container && x.container) || "";
    set({ text: x.description, textLang: x.language, emailNote: { x, q }, q: q || s.q, search: q ? await get("/api/customers/search", { q }) : null });
  });

  const selectCandidate = (c: any) => run(async () => {
    const sid = s.sessionId || (await post("/api/sessions", { scenario: s.scenarioTag || null, mode: s.mode, participant_id: s.participant || null })).session_id;
    const ctx = await get(`/api/customers/${c.customer_id}/context`);
    const pf = await post("/api/prefill", {
      customer_id: c.customer_id, site_id: c.matched_site_id, order_id: c.matched_order_id,
      complaint_type: s.fields.complaint_type?.value, session_id: sid,
    });
    sessionStorage.setItem("cra.currentCustomer", c.customer_id);
    set({ sessionId: sid, customerId: c.customer_id, ctx, fields: pf.fields, step: 1, search: null });
    post(`/api/sessions/${sid}/events`, { type: "step_entered", step: "review_details" }).catch(() => undefined);
  });

  // Fields the user typed or edited survive a re-prefill; everything system-filled is recomputed.
  const keepManual = (skip: string[] = []) => Object.fromEntries(
    Object.entries(s.fields).filter(([k, f]) => (f.provenance === "manual" || f.provenance === "edited") && !skip.includes(k)));

  // Choosing a type (by the user or accepting the AI suggestion) applies that type's defaults.
  const applyType = async (v: string, provenance: "manual" | "suggested") => {
    const pf = await post("/api/prefill", {
      customer_id: s.customerId, site_id: val("site_id") || null, order_id: val("order_id") || null, complaint_type: v,
      current_fields: keepManual(["complaint_type"]),
    });
    set({ fields: { ...pf.fields, complaint_type: { value: v, provenance } } });
  };
  const changeType = (v: string) => run(() => applyType(v, "manual"));

  // A newly chosen site pulls in its contract, most recent order and container.
  const changeSite = (v: string) => run(async () => {
    const prev = s.fields.site_id?.provenance;
    const pf = await post("/api/prefill", {
      customer_id: s.customerId, site_id: v || null, order_id: null, complaint_type: val("complaint_type") || null,
      current_fields: keepManual(["site_id", "contract_id", "order_id", "container"]),
    });
    const provenance = prev === "prefilled" || prev === "default" || prev === "edited" ? "edited" : "manual";
    set({ fields: { ...pf.fields, site_id: { value: v || null, provenance } } });
    ev({ type: "field", field: "site_id", origin: provenance, changed: true });
  });

  const changeOrder = (v: string) => {
    const order = s.ctx?.orders.find((o: any) => o.id === v);
    const prev = s.fields.order_id?.provenance;
    const provenance = prev === "prefilled" || prev === "default" || prev === "edited" ? "edited" : "manual";
    set({ fields: { ...s.fields, order_id: { value: v || null, provenance },
                    container: { value: order?.container || null, provenance: order ? "prefilled" : "blank" } } });
    ev({ type: "field", field: "order_id", origin: provenance, changed: true });
  };

  // A contract or order belongs to one site: picking one from another site switches the site too and re-prefills around it.
  const pickRelated = (rowSite: string, extra: { contract_id?: string; order_id?: string }) => run(async () => {
    const pf = await post("/api/prefill", {
      customer_id: s.customerId, site_id: rowSite, order_id: extra.order_id ?? null, complaint_type: val("complaint_type") || null,
      current_fields: keepManual(["site_id", "contract_id", "order_id", "container"]),
    });
    const prov = (k: string) => { const p = s.fields[k]?.provenance; return p === "prefilled" || p === "default" || p === "edited" ? "edited" : "manual"; };
    const fields: Record<string, any> = { ...pf.fields, site_id: { value: rowSite, provenance: prov("site_id") } };
    if (extra.contract_id) fields.contract_id = { value: extra.contract_id, provenance: prov("contract_id") };
    if (extra.order_id) fields.order_id = { value: extra.order_id, provenance: prov("order_id") };
    set({ fields });
    ev({ type: "field", field: "site_id", origin: prov("site_id"), changed: true });
  });
  const pickContract = (c: any) => (c.site_id === val("site_id") ? setField("contract_id", c.id) : pickRelated(c.site_id, { contract_id: c.id }));
  const pickOrder = (o: any) => (o.site_id === val("site_id") ? changeOrder(o.id) : pickRelated(o.site_id, { order_id: o.id }));

  const emptySummary = { what: "", where: "", when: "", impact: "", extras: {} };

  // One AI call when leaving Describe: structured summary + type + top-3 causes together.
  const analyse = async () => {
    const r = await post("/api/complaints/analyze", {
      text: s.text, language: s.textLang === "auto" ? null : s.textLang, site_id: val("site_id") || null,
      complaint_type: val("complaint_type") || null, session_id: s.sessionId,
    });
    if (r.ai_status === "ok") {
      const { summary, classification } = r.result;
      set({ summary: { ...summary, mock: r.mock }, summaryFailed: null, cls: { ...r, result: classification }, clsFailed: null,
            rootCause: r.preselect || "", causeOrigin: r.preselect ? "suggested" : "manual", analysedText: s.text });
      if (classification.complaint_type && !val("complaint_type")) await applyType(classification.complaint_type, "suggested");
    } else {
      const cat = r.error_category || "unavailable";
      set({ summary: s.summary || emptySummary, summaryFailed: cat, cls: null, clsFailed: cat, analysedText: s.text });
    }
  };

  // The user picked another type after the analysis: apply its defaults and refresh only the type-specific fields.
  const retype = (v: string) => run(async () => {
    await applyType(v, "manual");
    if (s.text.trim() && s.summary) {
      const r = await post("/api/complaints/summarise", { text: s.text, language: s.textLang === "auto" ? null : s.textLang,
        site_id: val("site_id") || null, complaint_type: v, session_id: s.sessionId });
      if (r.ai_status === "ok") set({ summary: { ...s.summary, extras: r.result.extras } });
    }
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
    ...Object.entries(s.decisions).filter(([, d]) => d.decision === "reject" && d.reason.trim().length < 3).map(([id]) => ["repeat_reason", ""]),
  ].filter(([, v]) => !String(v || "").trim()).map(([k]) => k);

  // Origin of each tracked field at save time; drives the prefill-rate metric (PRD: prefilled or defaulted).
  const finalProvenance = () => {
    const p: Record<string, string> = {};
    for (const k of ["customer_id", "site_id", "contract_id", "order_id", "container", "channel", "registration_date",
      "registering_user", "priority", "status", "owner_team", "complaint_type"]) p[k] = s.fields[k]?.provenance || "blank";
    p.root_cause = s.rootCause ? s.causeOrigin : "blank";
    p.description = s.text ? "manual" : "blank";
    p.summary = s.summary ? "suggested" : "blank";
    return p;
  };

  const save = () => run(async () => {
    const r = await post("/api/complaints", {
      customer_id: s.customerId, site_id: val("site_id") || null, contract_id: val("contract_id") || null,
      order_id: val("order_id") || null, channel: val("channel"), complaint_type: val("complaint_type"),
      root_cause: s.rootCause, other_reason: s.rootCause === "other" ? s.otherReason : null, description: s.text,
      language: s.textLang === "auto" ? s.summary?.language || null : s.textLang, summary: s.summary,
      summary_meta: s.summary ? { mock: !!s.summary.mock } : null, session_id: s.sessionId,
      priority: val("priority") || null, owner_team: val("owner_team") || null, field_provenance: finalProvenance(),
    });
    // FR-13: the rule outcome is stored as is; the user's confirm/dispute decisions are stored next to it.
    for (const [prior, d] of Object.entries(s.decisions)) {
      await post("/api/repeat-disputes", { complaint_id: r.id, prior_complaint_id: prior, decision: d.decision,
        reason: d.reason.trim() || t("repeat.confirmed_default") }).catch(() => undefined);
    }
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

  const filtered = (f: string) => causes.filter((c) => !f || `${causeLabel(c)} ${c.en} ${c.nl} ${c.id}`.toLowerCase().includes(f.toLowerCase()));
  const selectFields = (k: string, items: any[], text: (i: any) => string) => (
    <select id={k} value={val(k)} onChange={(e) => setField(k, e.target.value)}>
      <option value="">{t("choose")}</option>
      {items.map((i) => <option key={i.id} value={i.id}>{text(i)}</option>)}
    </select>
  );
  const optionSelect = (k: string, options: string[]) => (
    <select id={k} value={val(k)} onChange={(e) => setField(k, e.target.value)}>
      <option value="">{t("choose")}</option>
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
  const opts = config?.field_options || {};
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
            <input id="q" autoFocus value={s.q} onChange={(e) => set({ q: e.target.value, search: null })} maxLength={100} />
            <button disabled={busy || !s.q.trim()}>{busy ? t("search.searching") : t("search")}</button>
          </form>
          {s.q.trim() && !s.search && <p className="muted" aria-live="polite">{t("search.looks", { type: t(`search.type.${guessType(s.q)}`) })}</p>}
          <details className="card" open={!!s.participant || !!s.scenarioTag || plain}>
            <summary>{t("test.title")}</summary>
            <div className="inline">
              <label>{t("ut.participant")}<input value={s.participant} maxLength={40} disabled={!!s.sessionId} onChange={(e) => set({ participant: e.target.value })} /></label>
              <label>{t("ut.scenario")}<input value={s.scenarioTag} maxLength={20} disabled={!!s.sessionId} onChange={(e) => set({ scenarioTag: e.target.value })} /></label>
              <label>{t("test.mode")}
                <select value={s.mode} disabled={!!s.sessionId} onChange={(e) => set({ mode: e.target.value as "assistant" | "plain" })}>
                  <option value="assistant">{t("mode.assistant")}</option><option value="plain">{t("mode.plain")}</option>
                </select></label>
            </div>
            <p className="muted">{t("test.note")}</p>
          </details>
          <details className="card" open={!!s.email}>
            <summary>{t("email.title")}</summary>
            <textarea aria-label={t("email.paste")} rows={5} maxLength={8000} value={s.email} onChange={(e) => set({ email: e.target.value })} />
            <button className="secondary" disabled={busy || !s.email.trim()} onClick={extractEmail}>{t("email.extract")}</button>
            {s.emailNote?.failed && <p className="warn">{t("ai.failed", { cat: s.emailNote.failed })}</p>}
            {s.emailNote?.x && (
              <div className={s.emailNote.q ? "ok" : "warn"}>
                <p style={{ margin: 0 }}>{s.emailNote.q ? t("email.found", { q: s.emailNote.q }) : t("email.none")}</p>
                <p style={{ margin: ".3rem 0 0" }}>
                  {t("email.ids")}: {[["customer_number", s.emailNote.x.customer_number], ["order_reference", s.emailNote.x.order_reference], ["container", s.emailNote.x.container]]
                    .filter(([, v]) => v).map(([k, v]) => `${v} ${s.emailNote.x.validation?.[k as string] ? "✓" : "✗"}`).join(" · ") || "–"}
                  {" · "}{t("email.language", { lang: String(s.emailNote.x.language || "?").toUpperCase() })}
                  {" · "}{t("email.text_taken", { n: (s.emailNote.x.description || "").length })}
                </p>
              </div>
            )}
          </details>
          {s.search?.match_type === "none" && (
            <div className="card warn" role="status">
              <strong>{t("search.none2", { q: s.search.query })}</strong>
              <p>{t("search.tip.title")}</p>
              <ul>
                {["number", "order", "container", "name", "postcode", "email"].map((k) => <li key={k}>{t(`search.tip.${k}`)}</li>)}
              </ul>
              <button className="secondary" onClick={() => set({ q: "", search: null })}>{t("search.clear")}</button>
            </div>
          )}
          {s.search?.ambiguous && <p className="warn" role="status">{t("search.many", { n: s.search.count, q: s.search.query })}</p>}
          {s.search?.candidates?.map((c: any) => (
            <div className={`card${s.search.count === 1 ? " found" : ""}`} key={c.customer_id}>
              {s.search.count === 1 && <span className="badge status-active">{t("search.found")}</span>}
              <h3 style={{ margin: ".3rem 0" }}>{c.name}</h3>
              <div>{t("f.customer_number")} {c.number} · {c.postcode}</div>
              <div className="muted">
                {t("search.via", { type: t(`search.type.${s.search.match_type}`) })}
                {c.matched_order_reference && ` · ${t("search.via_order", { ref: c.matched_order_reference })}`}
                {c.matched_container && ` · ${t("search.via_container", { ref: c.matched_container })}`}
                {c.matched_site_name && ` · ${c.matched_site_name}`}
              </div>
              <div className="muted">
                {t("search.sites")}: {c.sites.map((x: any) => `${x.name} (${x.postcode})`).join(", ")}
                {c.last_order_date && ` · ${t("search.last_order", { date: c.last_order_date.slice(0, 10) })}`}
              </div>
              <button autoFocus={s.search.count === 1} disabled={busy} onClick={() => selectCandidate(c)}>
                {s.search.count === 1 ? t("search.use") : t("search.select")}
              </button>
            </div>
          ))}
        </div>
      )}

      {s.step === 1 && s.ctx && (
        <div>
          <div>
            {row("customer_name", <span>{val("customer_name")}</span>)}
            {row("customer_number", <span>{val("customer_number")}</span>)}
            {row("site_id", (
              <select id="site_id" value={val("site_id")} onChange={(e) => changeSite(e.target.value)}>
                <option value="">{t("choose")}</option>
                {s.ctx.sites.map((i: any) => <option key={i.id} value={i.id}>{`${i.name} (${i.reference})`}</option>)}
              </select>
            ))}
            {row("contract_id", selectFields("contract_id", s.ctx.contracts.filter((c: any) => !val("site_id") || c.site_id === val("site_id")), (i) => i.reference))}
            {row("order_id", (
              <select id="order_id" value={val("order_id")} onChange={(e) => changeOrder(e.target.value)}>
                <option value="">{t("choose")}</option>
                {s.ctx.orders.filter((o: any) => !val("site_id") || o.site_id === val("site_id")).map((i: any) => <option key={i.id} value={i.id}>{`${i.reference} · ${i.container}`}</option>)}
              </select>
            ))}
            {row("container", <span>{val("container") || "–"}</span>)}
            {row("channel", optionSelect("channel", opts.channel || []))}
            {row("complaint_type", (
              <select id="complaint_type" value={val("complaint_type")} onChange={(e) => changeType(e.target.value)}>
                <option value="">{t("choose")}</option>
                {(config?.types || []).map((x: any) => <option key={x.id} value={x.id}>{label(x)}</option>)}
              </select>
            ))}
            {row("priority", optionSelect("priority", opts.priority || []))}
            {row("owner_team", optionSelect("owner_team", opts.owner_team || []))}
            {row("status", <span>{val("status") || "–"}</span>)}
            {row("registering_user", <span>{meName || val("registering_user")}</span>)}
            {row("registration_date", <span>{val("registration_date")}</span>)}
          </div>
          <p><button className="secondary" onClick={onManageData}>{t("cd.manage")} →</button></p>
          <CustomerData ctx={s.ctx} siteId={val("site_id")} contractId={val("contract_id")} orderId={val("order_id")}
            onPickSite={changeSite} onPickContract={pickContract} onPickOrder={pickOrder} />
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
          </div>
          <p className="muted">{t("describe.hint")}</p>
        </div>
      )}

      {s.step === 3 && (
        <div>
          {(s.summaryFailed || s.clsFailed) && <p className="warn">{t("ai.failed", { cat: s.summaryFailed || s.clsFailed || "" })}</p>}
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
              {(config?.summary?.by_type?.[val("complaint_type")] || []).map((k: string) => (
                <div className="row" key={k}>
                  <label htmlFor={`x-${k}`}>{config.summary.extra_labels?.[k]?.[lang] || k}</label>
                  <input id={`x-${k}`} value={s.summary.extras?.[k] || ""} placeholder={t("summary.unknown")}
                    onChange={(e) => set({ summary: { ...s.summary, extras: { ...(s.summary.extras || {}), [k]: e.target.value || null } } })} />
                </div>
              ))}
            </div>
          )}
          <div className="row">
            <label htmlFor="type-cls">{t("f.complaint_type")}</label>
            <select id="type-cls" value={val("complaint_type")} onChange={(e) => retype(e.target.value)}>
              <option value="">{t("choose")}</option>
              {(config?.types || []).map((x: any) => <option key={x.id} value={x.id}>{label(x)}</option>)}
            </select>
            <Prov p={s.fields.complaint_type?.provenance || "blank"} />
          </div>
          {s.cls && (
            <div className="card">
              <h3>{t("classify.cands")} {s.cls.mock && <span className="badge mock">{t("ai.mock")}</span>}</h3>
              {s.cls.low_confidence && <p className="warn">{t("classify.low")}</p>}
              {s.cls.result.candidates.map((c: any) => (
                <label key={c.root_cause_id} className="radio">
                  <input type="radio" name="rc-top" checked={s.rootCause === c.root_cause_id} onChange={() => set({ rootCause: c.root_cause_id, causeOrigin: "suggested" })} />
                  {causeLabel(causes.find((x) => x.id === c.root_cause_id))} <span className="muted">({Math.round(c.confidence * 100)}% – {c.reason})</span>
                </label>
              ))}
              <p className="muted">{t("classify.note")}</p>
            </div>
          )}
          {plain ? <p className="muted">{t("mode.plain_note")}</p>
            : <button className="secondary" disabled={busy || !s.text.trim()} onClick={() => run(analyse)}>{t("classify")}</button>}
          <h3>{t("classify.all")}</h3>
          <label htmlFor="cf">{t("classify.search")}</label>
          <input id="cf" value={filter} onChange={(e) => setFilter(e.target.value)} />
          <div className="list">
            {filtered(filter).map((c) => (
              <label key={c.id} className="radio">
                <input type="radio" name="rc" checked={s.rootCause === c.id} onChange={() => set({ rootCause: c.id, causeOrigin: "manual" })} />
                {causeLabel(c)}
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
              <ul>{s.repeat.matches.map((m: any) => {
                const d = s.decisions[m.id];
                const setD = (patch: Partial<{ decision: "confirm" | "reject"; reason: string }>) =>
                  set({ decisions: { ...s.decisions, [m.id]: { ...(d || { decision: "confirm" as const, reason: "" }), ...patch } } });
                return (
                  <li key={m.id}>
                    {m.id} · {String(m.date || m.created || "").slice(0, 10)} · {m.cause || m.root_cause} · {m.status} {m.reason && <span className="muted">({m.reason})</span>}
                    <div className="inline">
                      <label><input type="radio" name={`d-${m.id}`} checked={d?.decision === "confirm"} onChange={() => setD({ decision: "confirm" })} /> {t("repeat.confirm")}</label>
                      <label><input type="radio" name={`d-${m.id}`} checked={d?.decision === "reject"} onChange={() => setD({ decision: "reject" })} /> {t("repeat.reject")}</label>
                      {d?.decision === "reject" && (
                        <input aria-label={t("repeat.reason")} placeholder={t("repeat.reason")} maxLength={500} value={d.reason} onChange={(e) => setD({ reason: e.target.value })} />
                      )}
                    </div>
                  </li>
                );
              })}</ul>
              <p className="muted">{t("repeat.decision_note")}</p>
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
            <dt>{t("col.cause")}</dt><dd>{causeLabel(cause) || "–"}{s.rootCause === "other" && `: ${s.otherReason}`}</dd>
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
          {s.step < 5 && <button onClick={next} disabled={busy}>{!plain && s.step === 2 && s.text.trim() && s.analysedText !== s.text ? t("next.analyse") : t("next")}</button>}
        </div>
      )}
    </section>
  );
}
