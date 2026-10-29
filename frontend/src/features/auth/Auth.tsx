import { FormEvent, useEffect, useState } from "react";
import { ApiError, get, post, setDemoUser, setToken } from "../../api/client";
import { useI18n } from "../../i18n";

export type Me = { id: string; name: string; email?: string | null; role: string; user_group: string; function?: string | null; permissions: string[] };

/** Sign-in and create-account screen shown before any complaint can be registered. */
export default function AuthScreen({ notice, onSignedIn }: { notice?: string; onSignedIn: (me: Me) => void }) {
  const { lang, setLang, t } = useI18n();
  const [tab, setTab] = useState<"in" | "up">("in");
  const [opts, setOpts] = useState<any>(null);
  const [demoUsers, setDemoUsers] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ name: "", email: "", password: "", password2: "", function: "", demo: "demo.emp.a1" });
  const set = (k: keyof typeof f, v: string) => setF((p) => ({ ...p, [k]: v }));

  useEffect(() => {
    get("/api/auth/options").then(setOpts).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
    get("/api/config").then((c) => setDemoUsers(c.demo_users || [])).catch(() => undefined);
  }, []);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); } finally { setBusy(false); }
  };

  const signIn = (e: FormEvent) => { e.preventDefault(); run(async () => {
    const r = await post("/api/auth/login", { email: f.email, password: f.password });
    setToken(r.token);
    onSignedIn(r.user);
  }); };

  const signUp = (e: FormEvent) => { e.preventDefault(); run(async () => {
    if (f.password !== f.password2) throw new ApiError(0, "mismatch", t("auth.mismatch"));
    if (!f.function) throw new ApiError(0, "function", t("auth.function.hint"));
    const r = await post("/api/auth/register", { name: f.name, email: f.email, password: f.password, function: f.function });
    setDone(r.status === "pending" ? t("auth.created_pending") : t("auth.created_active"));
    setTab("in"); setF((p) => ({ ...p, password: "", password2: "" }));
  }); };

  const demo = () => run(async () => {
    setToken(null);
    setDemoUser(f.demo);
    onSignedIn(await get("/api/auth/me"));
  });

  return (
    <main className="auth-page">
      <div className="auth-card">
        <select className="lang" aria-label={t("language")} value={lang} onChange={(e) => setLang(e.target.value as "nl" | "en")}>
          <option value="nl">Nederlands</option><option value="en">English</option>
        </select>
        <h1>{t("app.title")}</h1>
        <p className="poc-banner">{t("auth.intro")}</p>
        {notice && <p className="warn" role="status">{notice}</p>}
        {done && <p className="ok" role="status">{done}</p>}
        {error && <p className="error" role="alert">{error}</p>}

        <div className="auth-tabs" role="tablist">
          <button role="tab" aria-selected={tab === "in"} className={tab === "in" ? "active" : ""} onClick={() => { setTab("in"); setError(null); }}>{t("auth.tab.in")}</button>
          <button role="tab" aria-selected={tab === "up"} className={tab === "up" ? "active" : ""} onClick={() => { setTab("up"); setError(null); setDone(null); }}>{t("auth.tab.up")}</button>
        </div>

        {tab === "in" ? (
          <form onSubmit={signIn}>
            <label htmlFor="li-email">{t("auth.email")}</label>
            <input id="li-email" type="email" autoComplete="username" required value={f.email} onChange={(e) => set("email", e.target.value)} />
            <label htmlFor="li-pw">{t("auth.password")}</label>
            <input id="li-pw" type="password" autoComplete="current-password" required value={f.password} onChange={(e) => set("password", e.target.value)} />
            <button className="primary" disabled={busy || !f.email || !f.password}>{t("auth.in.btn")}</button>
            <p className="hint">{t("auth.forgot")}</p>
          </form>
        ) : (
          <form onSubmit={signUp}>
            <label htmlFor="su-name">{t("auth.name")}</label>
            <input id="su-name" autoComplete="name" required maxLength={80} value={f.name} onChange={(e) => set("name", e.target.value)} />
            <label htmlFor="su-email">{t("auth.email")}</label>
            <input id="su-email" type="email" autoComplete="email" required value={f.email} onChange={(e) => set("email", e.target.value)} />
            <fieldset style={{ border: 0, padding: 0, margin: ".65rem 0 0" }}>
              <legend style={{ fontWeight: 600, padding: 0 }}>{t("auth.function")}</legend>
              <div className="function-choice">
                {(opts?.functions || []).map((fn: any) => (
                  <label key={fn.id}><input type="radio" name="function" checked={f.function === fn.id} onChange={() => set("function", fn.id)} />{fn[lang]}</label>
                ))}
              </div>
              <p className="hint">{t("auth.function.hint")}</p>
            </fieldset>
            <label htmlFor="su-pw">{t("auth.password")}</label>
            <input id="su-pw" type="password" autoComplete="new-password" required minLength={opts?.min_password_length || 10} value={f.password} onChange={(e) => set("password", e.target.value)} />
            <p className="hint">{t("auth.pw_hint", { n: opts?.min_password_length || 10 })}</p>
            <label htmlFor="su-pw2">{t("auth.password2")}</label>
            <input id="su-pw2" type="password" autoComplete="new-password" required value={f.password2} onChange={(e) => set("password2", e.target.value)} />
            <button className="primary" disabled={busy}>{t("auth.up.btn")}</button>
          </form>
        )}

        {opts?.demo_mode && (
          <details className="card">
            <summary>{t("auth.demo.title")}</summary>
            <label htmlFor="demo-user">{t("user")}</label>
            <select id="demo-user" value={f.demo} onChange={(e) => set("demo", e.target.value)}>
              {demoUsers.map((d: any) => <option key={d.id} value={d.id}>{d.name} ({d.role})</option>)}
            </select>
            <button className="secondary primary" disabled={busy} onClick={demo}>{t("auth.demo.btn")}</button>
          </details>
        )}
      </div>
    </main>
  );
}
