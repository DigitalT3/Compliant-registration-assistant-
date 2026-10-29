import React, { useEffect, useState } from "react";
import { ApiError, get } from "../../api/client";
import { api } from "../../api/client";
import { useI18n } from "../../i18n";

/** Administrator screen: approve new employees, change role/group, disable or re-enable accounts. */
export default function Users({ config, meId }: { config: any; meId: string }) {
  const { lang, t } = useI18n();
  const [items, setItems] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [opts, setOpts] = useState<any>(null);
  const roles = Object.keys(config.roles || {});
  const [temp, setTemp] = useState<{ name: string; password: string } | null>(null);
  const [form, setForm] = useState({ name: "", email: "", function: "", role: "employee" });

  const load = () => get("/api/users").then((r) => setItems(r.items)).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  useEffect(() => { load(); get("/api/auth/options").then(setOpts).catch(() => undefined); }, []);

  const patch = async (id: string, body: Record<string, string>) => {
    setError(null);
    try { await api("PATCH", `/api/users/${id}`, body); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
  };
  const addPerson = async (e: React.FormEvent) => {
    e.preventDefault(); setError(null);
    try {
      const r = await api("POST", "/api/users", { name: form.name, email: form.email, function: form.function || null, role: form.role });
      setTemp({ name: r.user.name, password: r.temporary_password });
      setForm({ name: "", email: "", function: "", role: "employee" });
      await load();
    } catch (e2) { setError(e2 instanceof ApiError ? e2.message : String(e2)); }
  };
  const resetPw = async (u: any) => {
    setError(null);
    try { const r = await api("POST", `/api/users/${u.id}/reset-password`); setTemp({ name: u.name, password: r.temporary_password }); await load(); }
    catch (e2) { setError(e2 instanceof ApiError ? e2.message : String(e2)); }
  };
  const fn = (id?: string | null) => (opts?.functions || []).find((x: any) => x.id === id)?.[lang] || id || "–";
  const pending = items.filter((u) => u.status === "pending");

  return (
    <section>
      <h2>{t("users.title")}</h2>
      <p className="muted">{t("users.note")}</p>
      {error && <p className="error" role="alert">{error}</p>}
      {temp && (
        <div className="card ok" role="status">
          <h3 style={{ marginTop: 0 }}>{t("users.temp.title", { name: temp.name })}</h3>
          <p><code style={{ fontSize: "1.25rem", userSelect: "all" }}>{temp.password}</code></p>
          <p className="muted">{t("users.temp.note")}</p>
          <button onClick={() => setTemp(null)}>{t("users.temp.close")}</button>
        </div>
      )}
      <form className="card" onSubmit={addPerson}>
        <h3 style={{ marginTop: 0 }}>{t("users.add")}</h3>
        <p className="muted">{t("users.add.hint")}</p>
        <div className="inline">
          <label>{t("auth.name")}<input required maxLength={80} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label>{t("users.col.email")}<input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label>{t("users.col.function")}
            <select value={form.function} onChange={(e) => setForm({ ...form, function: e.target.value })}>
              <option value="">{t("users.no_function")}</option>
              {(opts?.functions || []).map((x: any) => <option key={x.id} value={x.id}>{x[lang]}</option>)}
            </select></label>
          <label>{t("users.col.role")}
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {roles.map((r) => <option key={r} value={r}>{r}</option>)}
            </select></label>
          <button disabled={!form.name || !form.email}>{t("users.add.btn")}</button>
        </div>
      </form>
      <div className="card">
        <h3>{t("users.pending")} ({pending.length})</h3>
        {pending.length === 0 ? <p className="muted">{t("users.none_pending")}</p> : (
          <table className="users"><tbody>
            {pending.map((u) => (
              <tr key={u.id}>
                <td><strong>{u.name}</strong><br /><small>{u.email}</small></td>
                <td>{fn(u.function)}</td>
                <td><button onClick={() => patch(u.id, { status: "active" })}>{t("users.approve")}</button></td>
              </tr>
            ))}
          </tbody></table>
        )}
      </div>
      <div className="card">
        <h3>{t("users.all")}</h3>
        <table className="users">
          <thead><tr>
            {["name", "email", "function", "role", "group", "status", "last"].map((k) => <th key={k}>{t(`users.col.${k}`)}</th>)}<th />
          </tr></thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id}>
                <td>{u.name}</td><td>{u.email || "–"}</td><td>{fn(u.function)}</td>
                <td>
                  <select aria-label={`${t("users.col.role")} ${u.name}`} value={u.role} onChange={(e) => patch(u.id, { role: e.target.value })}>
                    {roles.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td>{u.user_group}</td>
                <td><span className={`badge status-${u.status}`}>{t(`users.status.${u.status}`)}</span></td>
                <td>{u.last_login_at ? u.last_login_at.slice(0, 16).replace("T", " ") : t("users.never")}</td>
                <td>
                  {u.email && <button className="secondary" onClick={() => resetPw(u)}>{t("users.reset")}</button>}{" "}
                  {u.status === "active"
                    ? <button className="secondary" disabled={u.id === meId} onClick={() => patch(u.id, { status: "disabled" })}>{t("users.disable")}</button>
                    : <button className="secondary" onClick={() => patch(u.id, { status: "active" })}>{u.status === "pending" ? t("users.approve") : t("users.enable")}</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
