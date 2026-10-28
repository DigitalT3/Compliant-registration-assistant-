import { FormEvent, useEffect, useMemo, useState } from "react";
import { ApiError, get, getDemoUser, post, put, setDemoUser } from "./api/client";
import { I18nProvider, useI18n } from "./i18n";
import Register from "./features/register/Register";

type Page = "register" | "history" | "dashboard" | "rootcauses" | "evaluation" | "config" | "about";

const NAV: Page[] = ["register", "history", "dashboard", "rootcauses", "evaluation", "config", "about"];

function ErrorMessage({ error }: { error: string | null }) {
  const { t } = useI18n();
  return error ? <p className="error" role="alert">{t("error")}: {error}</p> : null;
}

function AppShell() {
  const { lang, setLang, t } = useI18n();
  const [page, setPage] = useState<Page>("register");
  const [config, setConfig] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState(getDemoUser());

  useEffect(() => {
    Promise.all([get("/api/config"), get("/api/config/root-causes")])
      .then(([appConfig, taxonomy]) => setConfig({ ...appConfig, ...taxonomy }))
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : String(cause)));
  }, []);

  const changeUser = (id: string) => {
    setDemoUser(id);
    setUser(id);
    setPage("register");
  };

  if (!config) {
    return <main className="loading-page"><ErrorMessage error={error} /><p>{t("loading")}</p></main>;
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>{t("app.title")}</h1>
          <p className="poc-banner">
            {t("banner", { ai: config.ai?.mock ? t("banner.mock") : t("banner.live") })}
          </p>
        </div>
        <div className="header-controls">
          <label>
            {t("user")}
            <select value={user} onChange={(event) => changeUser(event.target.value)}>
              {config.demo_users.map((demo: any) => (
                <option key={demo.id} value={demo.id}>{demo.name} ({demo.role})</option>
              ))}
            </select>
          </label>
          <label>
            {t("language")}
            <select value={lang} onChange={(event) => setLang(event.target.value as "nl" | "en")}>
              <option value="nl">Nederlands</option>
              <option value="en">English</option>
            </select>
          </label>
        </div>
      </header>
      <div className="app-body">
        <nav className="sidebar" aria-label="Main navigation">
          {NAV.map((item) => (
            <button
              className={page === item ? "active" : ""}
              key={item}
              onClick={() => setPage(item)}
              aria-current={page === item ? "page" : undefined}
            >
              {t(`nav.${item}`)}
            </button>
          ))}
        </nav>
        <main className="content">
          {page === "register" && <Register config={config} onViewHistory={() => setPage("history")} />}
          {page === "history" && <History config={config} />}
          {page === "dashboard" && <Dashboard />}
          {page === "rootcauses" && <RootCauses config={config} />}
          {page === "evaluation" && <Evaluation config={config} />}
          {page === "config" && <Configuration config={config} onUpdated={setConfig} />}
          {page === "about" && <About />}
        </main>
      </div>
    </div>
  );
}

function History({ config }: { config: any }) {
  const { lang, t } = useI18n();
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [includeSeed, setIncludeSeed] = useState(true);
  const [filter, setFilter] = useState({ complaint_type: "", root_cause: "", repeat: "" });
  const [error, setError] = useState<string | null>(null);
  const size = 10;

  useEffect(() => {
    get<any>("/api/complaints", {
      page,
      page_size: size,
      include_seed: includeSeed,
      complaint_type: filter.complaint_type || undefined,
      root_cause: filter.root_cause || undefined,
      repeat: filter.repeat === "" ? undefined : filter.repeat === "true",
    })
      .then((result) => {
        setItems(result.items);
        setTotal(result.total);
        setError(null);
      })
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : String(cause)));
  }, [page, includeSeed, filter]);

  const label = (id: string, values: any[]) => values.find((item) => item.id === id)?.[lang] || id;
  const pages = Math.max(1, Math.ceil(total / size));

  return (
    <section>
      <h2>{t("history.title")}</h2>
      <div className="filters">
        <label>
          {t("f.complaint_type")}
          <select value={filter.complaint_type} onChange={(event) => { setPage(1); setFilter({ ...filter, complaint_type: event.target.value }); }}>
            <option value="">{t("choose")}</option>
            {config.types.map((type: any) => <option key={type.id} value={type.id}>{type[lang]}</option>)}
          </select>
        </label>
        <label>
          {t("col.cause")}
          <select value={filter.root_cause} onChange={(event) => { setPage(1); setFilter({ ...filter, root_cause: event.target.value }); }}>
            <option value="">{t("choose")}</option>
            {config.root_causes.map((cause: any) => <option key={cause.id} value={cause.id}>{cause[lang]}</option>)}
          </select>
        </label>
        <label>
          {t("col.repeat")}
          <select value={filter.repeat} onChange={(event) => { setPage(1); setFilter({ ...filter, repeat: event.target.value }); }}>
            <option value="">{t("choose")}</option>
            <option value="true">{t("yes")}</option>
            <option value="false">{t("no")}</option>
          </select>
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={includeSeed} onChange={(event) => { setPage(1); setIncludeSeed(event.target.checked); }} />
          {t("history.seed")}
        </label>
      </div>
      <ErrorMessage error={error} />
      {items.length === 0 ? <p className="empty">{t("history.empty")}</p> : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("col.id")}</th><th>{t("col.date")}</th><th>{t("col.type")}</th><th>{t("col.cause")}</th><th>{t("col.status")}</th><th>{t("col.repeat")}</th></tr></thead>
            <tbody>{items.map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>{String(item.created).slice(0, 10)}</td>
                <td>{label(item.complaint_type, config.types)}</td>
                <td>{label(item.root_cause, config.root_causes)}</td>
                <td>{item.status}</td>
                <td>{item.repeat_detected ? t("yes") : t("no")}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <div className="pager">
        <button className="secondary" disabled={page === 1} onClick={() => setPage(page - 1)}>←</button>
        <span>{t("page", { p: page, n: pages })}</span>
        <button className="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>→</button>
      </div>
    </section>
  );
}

function Dashboard() {
  const { t } = useI18n();
  const [summary, setSummary] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get("/api/analytics/summary")
      .then(setSummary)
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : String(cause)));
  }, []);

  if (error) return <section><h2>{t("dash.title")}</h2><p className="warn">{t("dash.forbidden")}</p><ErrorMessage error={error} /></section>;
  if (!summary) return <section><h2>{t("dash.title")}</h2><p>{t("loading")}</p></section>;
  if (summary.empty) return <section><h2>{t("dash.title")}</h2><p className="empty">{t("dash.empty")}</p></section>;

  const rates = [
    ["Save", summary.sessions.save_rate],
    ["Top 3", summary.classification.top_three_rate],
    ["Prefill", summary.fields.prefill_rate],
    ["Other", summary.classification.other_share],
    ["Repeat", summary.repeat.rate],
    ["AI", summary.ai.success_rate],
  ];
  const causes = Object.entries(summary.classification.by_root_cause || {}) as [string, number][];
  const maxCause = Math.max(1, ...causes.map(([, count]) => count));

  return (
    <section>
      <h2>{t("dash.title")}</h2>
      <p className="muted">{summary.definitions.synthetic}</p>
      <div className="metric-grid">
        <Metric label={t("dash.sessions")} value={summary.sessions.started} note={`${summary.sessions.saved} saved`} />
        <Metric label={t("dash.duration")} value={summary.duration_seconds.mean ?? "–"} note={t("dash.n", { n: summary.duration_seconds.n })} />
        <Metric label="Median" value={summary.duration_seconds.median ?? "–"} note={t("dash.n", { n: summary.duration_seconds.n })} />
        <Metric label="AI" value={formatRate(summary.ai.success_rate)} note={summary.ai.mock_note} />
      </div>
      <div className="dashboard-grid">
        <article className="card">
          <h3>{t("dash.rates")}</h3>
          {rates.map(([label, rate]) => <Bar key={label} label={label} rate={rate as any} />)}
        </article>
        <article className="card">
          <h3>{t("dash.causes")}</h3>
          {causes.length ? causes.map(([cause, count]) => (
            <div className="bar-row" key={cause}>
              <span>{cause}</span><div className="bar-track"><div className="bar-fill" style={{ width: `${(count / maxCause) * 100}%` }} /></div><b>{count}</b>
            </div>
          )) : <p className="empty">–</p>}
        </article>
        <article className="card">
          <h3>{t("dash.steps")}</h3>
          {Object.entries(summary.step_seconds || {}).map(([step, value]: [string, any]) => <p key={step}><b>{step}</b>: {value.mean}s ({t("dash.n", { n: value.n })})</p>)}
        </article>
        <article className="card">
          <h3>{t("dash.other")}</h3>
          {summary.classification.other_reasons?.length
            ? <ul>{summary.classification.other_reasons.map((reason: string, index: number) => <li key={`${reason}-${index}`}>{reason}</li>)}</ul>
            : <p className="empty">–</p>}
        </article>
      </div>
    </section>
  );
}

function Metric({ label, value, note }: { label: string; value: string | number; note: string }) {
  return <article className="metric card"><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

function Bar({ label, rate }: { label: string; rate: { value: number | null; n: number } }) {
  const percent = rate?.value === null || rate?.value === undefined ? 0 : rate.value * 100;
  return <div className="bar-row"><span>{label}</span><div className="bar-track"><div className="bar-fill" style={{ width: `${percent}%` }} /></div><b>{formatRate(rate)}</b></div>;
}

function formatRate(rate: { value: number | null; n: number } | undefined) {
  return rate?.value === null || rate?.value === undefined ? "–" : `${Math.round(rate.value * 100)}% (n=${rate.n})`;
}

function RootCauses({ config }: { config: any }) {
  const { lang, t } = useI18n();
  return (
    <section>
      <h2>{t("ref.title", { v: config.taxonomy_version })}</h2>
      <div className="reference-grid">
        {config.root_causes.map((cause: any) => (
          <article className="card" key={cause.id}>
            <h3>{cause[lang]} <span className="muted">({cause.id})</span></h3>
            <p><b>{t("ref.definition")}:</b> {cause.definition}</p>
            <p><b>{t("ref.examples")}:</b> {cause.examples || "–"}</p>
            <p className="muted">{cause.level1}{cause.level2 ? ` / ${cause.level2}` : ""}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function Evaluation({ config }: { config: any }) {
  const { t } = useI18n();
  const [evaluations, setEvaluations] = useState<any>(null);
  const [disputes, setDisputes] = useState<any[]>([]);
  const [form, setForm] = useState({ complaint_id: "", usable: true, expert_cause: "" });
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    Promise.all([get<any>("/api/evaluations"), get<any>("/api/repeat-disputes")])
      .then(([evals, disputeRows]) => { setEvaluations(evals); setDisputes(disputeRows.items); setError(null); })
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : String(cause)));
  };
  useEffect(load, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    post("/api/evaluations", { ...form, expert_cause: form.expert_cause || null })
      .then(() => { setMessage("Recorded"); setForm({ complaint_id: "", usable: true, expert_cause: "" }); load(); })
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : String(cause)));
  };

  return (
    <section>
      <h2>{t("eval.title")}</h2>
      <ErrorMessage error={error} />
      {evaluations && <div className="metric-grid">
        <Metric label={t("eval.usable")} value={formatRate(evaluations.usable)} note={t("dash.n", { n: evaluations.usable.n })} />
        <Metric label={t("eval.agreement")} value={formatRate(evaluations.expert_agreement)} note={t("dash.n", { n: evaluations.expert_agreement.n })} />
      </div>}
      <form className="card form-grid" onSubmit={submit}>
        <h3>{t("eval.rate")}</h3>
        <label>{t("eval.id")}<input required value={form.complaint_id} onChange={(event) => setForm({ ...form, complaint_id: event.target.value })} /></label>
        <label>{t("eval.expert")}<select value={form.expert_cause} onChange={(event) => setForm({ ...form, expert_cause: event.target.value })}><option value="">{t("choose")}</option>{config.root_causes.map((cause: any) => <option key={cause.id} value={cause.id}>{cause.en}</option>)}</select></label>
        <label className="checkbox"><input type="checkbox" checked={form.usable} onChange={(event) => setForm({ ...form, usable: event.target.checked })} />{t("eval.useful")}</label>
        <button>{t("eval.submit")}</button>{message && <span className="ok">{message}</span>}
      </form>
      <article className="card">
        <h3>{t("eval.disputes")}</h3>
        {disputes.length ? <ul>{disputes.map((item) => <li key={item.id}>{item.complaint_id}: {item.decision} — {item.reason}</li>)}</ul> : <p className="empty">{t("eval.none")}</p>}
      </article>
    </section>
  );
}

function Configuration({ config, onUpdated }: { config: any; onUpdated: (config: any) => void }) {
  const { t } = useI18n();
  const [rule, setRule] = useState(config.repeat_rule);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    put<any>("/api/config/repeat-rule", {
      ...rule,
      lookback_days: Number(rule.lookback_days),
      match_keys: typeof rule.match_keys === "string" ? rule.match_keys.split(",").map((value: string) => value.trim()).filter(Boolean) : rule.match_keys,
      eligible_statuses: typeof rule.eligible_statuses === "string" ? rule.eligible_statuses.split(",").map((value: string) => value.trim()).filter(Boolean) : rule.eligible_statuses,
    }).then(async (result) => {
      const refreshed = await get<any>("/api/config");
      onUpdated({ ...config, ...refreshed, repeat_rule: result.repeat_rule });
      setRule(result.repeat_rule);
      setMessage(t("config.updated"));
      setError(null);
    }).catch((cause) => setError(cause instanceof ApiError ? cause.message : String(cause)));
  };

  return (
    <section>
      <h2>{t("config.title")}</h2>
      <p className="muted">{t("config.readonly")}</p>
      <ErrorMessage error={error} />
      <form className="card form-grid" onSubmit={submit}>
        <label>{t("config.lookback")}<input type="number" min="0" max="3650" value={rule.lookback_days} onChange={(event) => setRule({ ...rule, lookback_days: event.target.value })} /></label>
        <label>{t("config.keys")}<input value={Array.isArray(rule.match_keys) ? rule.match_keys.join(", ") : rule.match_keys} onChange={(event) => setRule({ ...rule, match_keys: event.target.value })} /></label>
        <label>{t("config.statuses")}<input value={Array.isArray(rule.eligible_statuses) ? rule.eligible_statuses.join(", ") : rule.eligible_statuses} onChange={(event) => setRule({ ...rule, eligible_statuses: event.target.value })} /></label>
        <label>{t("config.cause_mode")}<select value={rule.cause_mode} onChange={(event) => setRule({ ...rule, cause_mode: event.target.value })}><option value="level1">level1</option><option value="level2">level2</option><option value="none">none</option></select></label>
        <button>{t("config.update")}</button>{message && <span className="ok">{message}</span>}
      </form>
    </section>
  );
}

function About() {
  const { t } = useI18n();
  return (
    <section>
      <h2>{t("about.title")}</h2>
      <article className="card"><h3>{t("about.impl")}</h3><p>{t("about.impl.l")}</p></article>
      <article className="card"><h3>{t("about.mock")}</h3><p>{t("about.mock.l")}</p></article>
      <article className="card"><h3>{t("about.prov")}</h3><p>{t("about.prov.l")}</p></article>
    </section>
  );
}

// PUBLIC_INTERFACE
export default function App() {
  /** Render the localised PoC application and its backend-backed navigation shell. */
  return <I18nProvider><AppShell /></I18nProvider>;
}
