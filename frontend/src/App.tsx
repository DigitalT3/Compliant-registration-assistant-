import { FormEvent, useEffect, useMemo, useState } from "react";
import { ApiError, clearSession, download, get, getDemoUser, hasToken, post, put, setDemoUser } from "./api/client";
import { I18nProvider, useI18n } from "./i18n";
import Register from "./features/register/Register";
import AuthScreen, { ChangePassword, Me } from "./features/auth/Auth";
import Users from "./features/users/Users";

type Page = "register" | "history" | "dashboard" | "rootcauses" | "evaluation" | "config" | "users" | "about";

/** Menu items and the permission each needs; items a role cannot use are not shown (the backend still enforces it). */
const NAV: [Page, string | null][] = [
  ["register", "register"], ["history", "read"], ["dashboard", "analytics"], ["rootcauses", "read"],
  ["evaluation", "evaluate"], ["config", "configure"], ["users", "users"], ["about", null],
];

/** The first screen each role needs. */
const LANDING: Record<string, Page> = {
  employee: "register", lead: "dashboard", evaluator: "evaluation", admin: "users", governance: "history", viewer: "history",
};

function ErrorMessage({ error }: { error: string | null }) {
  const { t } = useI18n();
  return error ? <p className="error" role="alert">{t("error")}: {error}</p> : null;
}

function AppShell() {
  const { lang, setLang, t } = useI18n();
  const [me, setMe] = useState<Me | null>(null);
  const [booted, setBooted] = useState(false);
  const [notice, setNotice] = useState<string | undefined>();
  const [page, setPage] = useState<Page>("register");
  const [config, setConfig] = useState<any>(null);
  const [fnLabels, setFnLabels] = useState<any[]>([]);
  const [changingPw, setChangingPw] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enter = (user: Me) => {
    setNotice(undefined);
    setMe(user);
    setPage(LANDING[user.role] || "history");
  };

  // Resume an existing session (token or demo user) or show the sign-in screen.
  useEffect(() => {
    const signedOut = (e: Event) => { setMe(null); setConfig(null); setNotice(t("auth.expired")); void e; };
    window.addEventListener("cra:signed-out", signedOut);
    if (hasToken() || getDemoUser()) get("/api/auth/me").then(enter).catch(() => undefined).finally(() => setBooted(true));
    else setBooted(true);
    return () => window.removeEventListener("cra:signed-out", signedOut);
  }, []);

  useEffect(() => {
    if (!me) return;
    Promise.all([get("/api/config"), get("/api/config/root-causes"), get("/api/auth/options")])
      .then(([appConfig, taxonomy, opts]) => { setConfig({ ...appConfig, ...taxonomy }); setFnLabels(opts.functions); })
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : String(cause)));
  }, [me?.id]);

  const signOut = async () => {
    try { await post("/api/auth/logout"); } catch { /* already signed out */ }
    clearSession();
    setMe(null); setConfig(null); setNotice(undefined);
  };
  const changeDemoUser = async (id: string) => {
    setDemoUser(id);
    enter(await get("/api/auth/me"));
  };

  if (!booted) return <main className="loading-page"><p>{t("loading")}</p></main>;
  if (!me) return <AuthScreen notice={notice} onSignedIn={enter} />;
  if (me.must_change_password) return <ChangePassword forced onDone={enter} />;   // temporary password: nothing else until it is replaced
  if (!config) {
    return <main className="loading-page"><ErrorMessage error={error} /><p>{t("loading")}</p></main>;
  }

  const demoSession = !hasToken();
  const visible = NAV.filter(([, need]) => !need || me.permissions.includes(need)).map(([p]) => p);
  const current: Page = visible.includes(page) ? page : visible[0];
  const fnName = fnLabels.find((x) => x.id === me.function)?.[lang];

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
          {demoSession ? (
            <label>
              {t("user")}
              <select value={me.id} onChange={(event) => changeDemoUser(event.target.value)}>
                {config.demo_users.map((demo: any) => (
                  <option key={demo.id} value={demo.id}>{demo.name} ({demo.role})</option>
                ))}
              </select>
            </label>
          ) : (
            <div className="user-chip" aria-label={t("auth.signed_in_as")}>
              <div><strong>{me.name}</strong><small>{[fnName, me.role].filter(Boolean).join(" · ")}</small></div>
            </div>
          )}
          <label>
            {t("language")}
            <select value={lang} onChange={(event) => setLang(event.target.value as "nl" | "en")}>
              <option value="nl">Nederlands</option>
              <option value="en">English</option>
            </select>
          </label>
          {!demoSession && <button className="secondary" onClick={() => setChangingPw(true)}>{t("pw.change")}</button>}
          <button className="secondary" onClick={signOut}>{demoSession ? t("auth.demo.exit") : t("auth.signout")}</button>
        </div>
      </header>
      <div className="app-body">
        <nav className="sidebar" aria-label="Main navigation">
          {visible.map((item) => (
            <button
              className={current === item ? "active" : ""}
              key={item}
              onClick={() => setPage(item)}
              aria-current={current === item ? "page" : undefined}
            >
              {t(`nav.${item}`)}
            </button>
          ))}
        </nav>
        <main className="content">
          {changingPw && (
            <div className="card">
              <ChangePassword forced={false} onCancel={() => setChangingPw(false)}
                onDone={(u) => { setMe(u); setChangingPw(false); setNotice(undefined); }} />
            </div>
          )}
          {current === "register" && <Register config={config} onViewHistory={() => setPage("history")} />}
          {current === "history" && <History config={config} />}
          {current === "dashboard" && <Dashboard />}
          {current === "rootcauses" && <RootCauses config={config} />}
          {current === "evaluation" && <Evaluation config={config} />}
          {current === "config" && <Configuration config={config} onUpdated={setConfig} />}
          {current === "users" && <Users config={config} meId={me.id} />}
          {current === "about" && <About />}
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
  const [groupBy, setGroupBy] = useState("group");
  const [mode, setMode] = useState("");

  useEffect(() => {
    get("/api/analytics/summary", { group_by: groupBy, mode })
      .then((r) => { setSummary(r); setError(null); })
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : String(cause)));
  }, [groupBy, mode]);

  const filters = (
    <div className="inline">
      <label>{t("dash.group_by")}
        <select value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
          {["group", "mode", "scenario", "participant"].map((g) => <option key={g} value={g}>{t(`dash.by.${g}`)}</option>)}
        </select></label>
      <label>{t("dash.mode")}
        <select value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="">{t("dash.all")}</option><option value="assistant">{t("mode.assistant")}</option><option value="plain">{t("mode.plain")}</option>
        </select></label>
      <button className="secondary" onClick={() => download("/api/export/sessions.csv", "sessions.csv", { mode }).catch((c) => setError(String(c.message || c)))}>{t("dash.export")}</button>
    </div>
  );

  if (error) return <section><h2>{t("dash.title")}</h2><p className="warn">{t("dash.forbidden")}</p><ErrorMessage error={error} /></section>;
  if (!summary) return <section><h2>{t("dash.title")}</h2><p>{t("loading")}</p></section>;
  if (summary.empty) return <section><h2>{t("dash.title")}</h2>{filters}<p className="empty">{t("dash.empty")}</p></section>;

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
  const d = summary.duration_seconds;
  const fmt = (id: string, v: number | null) => v === null ? "–" : ["time", "daily_use"].includes(id) ? String(Math.round(v * 10) / 10) : `${Math.round(v * 100)}%`;

  return (
    <section>
      <h2>{t("dash.title")}</h2>
      <p className="muted">{summary.definitions.synthetic}</p>
      {filters}
      <div className="metric-grid">
        <Metric label={t("dash.sessions")} value={summary.sessions.started} note={`${summary.sessions.saved} saved`} />
        <Metric label={t("dash.duration")} value={d.mean ?? "–"} note={t("dash.n", { n: d.n })} />
        <Metric label="Median" value={d.median ?? "–"} note={t("dash.n", { n: d.n })} />
        <Metric label={t("dash.baseline")} value={d.baseline_seconds ?? "–"}
          note={d.baseline_seconds ? `${t("dash.n", { n: d.baseline_n })} · ${d.faster_than_baseline === null ? "" : `${Math.round(d.faster_than_baseline * 100)}% ${t("dash.faster")}`}` : t("dash.no_baseline")} />
      </div>
      <article className="card">
        <h3>{t("dash.targets")}</h3>
        <table><thead><tr><th>{t("dash.target")}</th><th>{t("dash.value")}</th><th>n</th><th>{t("dash.status")}</th></tr></thead>
          <tbody>{summary.targets.map((x: any) => (
            <tr key={x.id}><td>{x.target}</td><td>{fmt(x.id, x.value)}</td><td>{x.n}</td>
              <td><span className={`badge ${x.status === "met" ? "prov-prefilled" : x.status === "not_met" ? "prov-default" : "prov-blank"}`}>{t(`status.${x.status}`)}</span>{x.indicative && <small className="muted"> {t("dash.indicative")}</small>}</td></tr>
          ))}</tbody></table>
      </article>
      {summary.groups && (
        <article className="card">
          <h3>{t("dash.groups", { by: t(`dash.by.${groupBy}`) })}</h3>
          <table><thead><tr><th>{t(`dash.by.${groupBy}`)}</th><th>{t("dash.sessions")}</th><th>{t("dash.duration")}</th><th>Other</th><th>Repeat</th></tr></thead>
            <tbody>{Object.entries(summary.groups).map(([k, g]: [string, any]) => (
              <tr key={k}><td>{k}</td><td>{g.sessions} ({g.saved} saved)</td><td>{g.mean_duration ?? "–"} ({t("dash.n", { n: g.n_duration })})</td><td>{formatRate(g.other_share)}</td><td>{formatRate(g.repeat_rate)}</td></tr>
            ))}</tbody></table>
        </article>
      )}
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
            <p className="muted">{(config.categories || []).find((x: any) => x.id === cause.level1)?.[lang] || cause.level1}{cause.level2 ? ` › ${cause.level2}` : ""}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function UserTestData({ config, onChanged }: { config: any; onChanged: () => void }) {
  const { t, lang } = useI18n();
  const [base, setBase] = useState({ user_group: "group_a", scenario: "", participant_id: "", seconds: "", note: "" });
  const [exit, setExit] = useState({ participant_id: "", would_use_daily: true, comment: "" });
  const [sample, setSample] = useState<any[]>([]);
  const [labels, setLabels] = useState<Record<string, { cause: string; usable: boolean }>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const fail = (c: unknown) => setErr(c instanceof ApiError ? c.message : String(c));
  const loadSample = () => get<any>("/api/evaluations/sample", { limit: 10 }).then((r) => setSample(r.items)).catch(fail);
  useEffect(() => { loadSample(); }, []);
  const groups = Array.from(new Set((config.demo_users || []).filter((u: any) => u.role === "employee").map((u: any) => u.group))) as string[];

  return (
    <article className="card">
      <h3>{t("ut.title")}</h3>
      <ErrorMessage error={err} />{msg && <p className="ok">{msg}</p>}
      <form className="form-grid" onSubmit={(e) => { e.preventDefault(); setErr(null);
        post("/api/baseline", { ...base, scenario: base.scenario || null, participant_id: base.participant_id || null, note: base.note || null, seconds: Number(base.seconds) })
          .then(() => { setMsg(t("ut.recorded")); setBase({ ...base, seconds: "", note: "" }); onChanged(); }).catch(fail); }}>
        <h4>{t("ut.baseline")}</h4>
        <label>{t("ut.group")}<select value={base.user_group} onChange={(e) => setBase({ ...base, user_group: e.target.value })}>{groups.map((g) => <option key={g}>{g}</option>)}</select></label>
        <label>{t("ut.scenario")}<input value={base.scenario} maxLength={20} onChange={(e) => setBase({ ...base, scenario: e.target.value })} /></label>
        <label>{t("ut.participant")}<input value={base.participant_id} maxLength={40} onChange={(e) => setBase({ ...base, participant_id: e.target.value })} /></label>
        <label>{t("ut.seconds")}<input required type="number" min="1" step="1" value={base.seconds} onChange={(e) => setBase({ ...base, seconds: e.target.value })} /></label>
        <button>{t("eval.submit")}</button>
      </form>
      <form className="form-grid" onSubmit={(e) => { e.preventDefault(); setErr(null);
        post("/api/exit-interviews", { ...exit, comment: exit.comment || null })
          .then(() => { setMsg(t("ut.recorded")); setExit({ participant_id: "", would_use_daily: true, comment: "" }); onChanged(); }).catch(fail); }}>
        <h4>{t("ut.exit")}</h4>
        <label>{t("ut.participant")}<input required value={exit.participant_id} maxLength={40} onChange={(e) => setExit({ ...exit, participant_id: e.target.value })} /></label>
        <label className="checkbox"><input type="checkbox" checked={exit.would_use_daily} onChange={(e) => setExit({ ...exit, would_use_daily: e.target.checked })} />{t("ut.daily")}</label>
        <label>{t("ut.comment")}<input value={exit.comment} maxLength={500} onChange={(e) => setExit({ ...exit, comment: e.target.value })} /></label>
        <button>{t("eval.submit")}</button>
      </form>
      <h4>{t("ut.blind")}</h4>
      <p className="muted">{t("ut.blind_note")}</p>
      <button className="secondary" onClick={() => download("/api/export/labels-sample.csv", "labels-sample.csv").catch(fail)}>{t("ut.export_labels")}</button>
      {sample.length === 0 && <p className="empty">{t("eval.none")}</p>}
      {sample.map((item) => {
        const l = labels[item.id] || { cause: "", usable: true };
        return (
          <div className="card" key={item.id}>
            <b>{item.id}</b> · {item.language}
            <p>{item.description}</p>
            {item.summary && <p className="muted">{["what", "where", "when", "impact"].map((k) => item.summary[k]).filter(Boolean).join(" · ")}</p>}
            <div className="inline">
              <select aria-label={t("eval.expert")} value={l.cause} onChange={(e) => setLabels({ ...labels, [item.id]: { ...l, cause: e.target.value } })}>
                <option value="">{t("choose")}</option>{config.root_causes.map((c: any) => <option key={c.id} value={c.id}>{c[lang] || c.en}</option>)}
              </select>
              <label className="checkbox"><input type="checkbox" checked={l.usable} onChange={(e) => setLabels({ ...labels, [item.id]: { ...l, usable: e.target.checked } })} />{t("eval.useful")}</label>
              <button disabled={!l.cause} onClick={() => post("/api/evaluations", { complaint_id: item.id, usable: l.usable, expert_cause: l.cause })
                .then(() => { setMsg(t("ut.recorded")); loadSample(); onChanged(); }).catch(fail)}>{t("ut.save_label")}</button>
            </div>
          </div>
        );
      })}
    </article>
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
      <UserTestData config={config} onChanged={load} />
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
