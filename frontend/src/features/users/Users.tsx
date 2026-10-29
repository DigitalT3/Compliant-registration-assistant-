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

  const [loaded, setLoaded] = useState(false);
  const load = () => get("/api/users").then((r) => { setItems(r.items); setLoaded(true); }).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  useEffect(() => { load(); get("/api/auth/options").then(setOpts).catch(() => undefined); }, []);

  const [busy, setBusy] = useState<string | null>(null);   // "<user id>:<action>" while a request is running

  // Change a user. The row updates at once (the hosted database takes a second or two to answer) and is put back if the server refuses.
  const patch = async (id: string, body: Record<string, string>) => {
    if (busy) return;                                       // ignore double clicks
    setError(null); setBusy(`${id}:${Object.keys(body)[0]}`);
    const before = items;
    setItems(items.map((u) => (u.id === id ? { ...u, ...body } : u)));
    try {
      const saved = await api("PATCH", `/api/users/${id}`, body);
      setItems((cur) => cur.map((u) => (u.id === id ? { ...u, ...saved } : u)));
    } catch (e) {
      setItems(before);
      setError(e instanceof ApiError ? e.message : String(e));
    } finally { setBusy(null); }
  };
  const addPerson = async (e: React.FormEvent) => {
    e.preventDefault(); setError(null);
    if (busy) return;
    setBusy("new:add");
    try {
      const r = await api("POST", "/api/users", { name: form.name, email: form.email, function: form.function || null, role: form.role });
      setTemp({ name: r.user.name, password: r.temporary_password });
      setForm({ name: "", email: "", function: "", role: "employee" });
      await load();
    } catch (e2) { setError(e2 instanceof ApiError ? e2.message : String(e2)); }
    finally { setBusy(null); }
  };
  const resetPw = async (u: any) => {
    if (busy) return;
    setError(null); setBusy(`${u.id}:reset`);
    try { const r = await api("POST", `/api/users/${u.id}/reset-password`); setTemp({ name: u.name, password: r.temporary_password }); }
    catch (e2) { setError(e2 instanceof ApiError ? e2.message : String(e2)); }
    finally { setBusy(null); }
  };
  const saving = (id: string) => busy !== null && busy.startsWith(id + ":");
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
          <label>{form.role === "lead" ? t("users.team_led") : t("users.col.function")}
            <select required={form.role === "lead"} value={form.function} onChange={(e) => setForm({ ...form, function: e.target.value })}>
              <option value="">{t("users.no_function")}</option>
              {(opts?.functions || []).map((x: any) => <option key={x.id} value={x.id}>{x[lang]}</option>)}
            </select></label>
          <label>{t("users.col.role")}
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {roles.map((r) => <option key={r} value={r}>{r}</option>)}
            </select></label>
          <button disabled={!form.name || !form.email || (form.role === "lead" && !form.function) || !!busy}>{busy === "new:add" ? t("saving") : t("users.add.btn")}</button>
        </div>
      </form>
      {!loaded && !error && <p className="muted" role="status">{t("loading")}</p>}
      <div className="card">
        <h3>{t("users.pending")} ({pending.length})</h3>
        {pending.length === 0 ? <p className="muted">{t("users.none_pending")}</p> : (
          <table className="users"><tbody>
            {pending.map((u) => (
              <tr key={u.id}>
                <td><strong>{u.name}</strong><br /><small>{u.email}</small></td>
                <td>{fn(u.function)}</td>
                <td><button disabled={!!busy} onClick={() => patch(u.id, { status: "active" })}>{saving(u.id) ? t("saving") : t("users.approve")}</button></td>
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
                <td>{u.name}</td><td>{u.email || "–"}</td>
                <td>{u.role === "lead"
                  ? <select aria-label={`${t("users.team_led")} ${u.name}`} value={u.function || ""} disabled={!!busy} onChange={(e) => e.target.value && patch(u.id, { function: e.target.value })}>
                      {!u.function && <option value="">{t("users.no_function")}</option>}
                      {(opts?.functions || []).map((x: any) => <option key={x.id} value={x.id}>{x[lang]}</option>)}
                    </select>
                  : fn(u.function)}</td>
                <td>
                  <select aria-label={`${t("users.col.role")} ${u.name}`} value={u.role} disabled={!!busy} onChange={(e) => patch(u.id, { role: e.target.value })}>
                    {roles.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td>{u.user_group}</td>
                <td><span className={`badge status-${u.status}`}>{t(`users.status.${u.status}`)}</span></td>
                <td>{u.last_login_at ? u.last_login_at.slice(0, 16).replace("T", " ") : t("users.never")}</td>
                <td>
                  {u.email && <button className="secondary" disabled={!!busy} onClick={() => resetPw(u)}>{busy === `${u.id}:reset` ? t("saving") : t("users.reset")}</button>}{" "}
                  {u.status === "active"
                    ? <button className="secondary" disabled={u.id === meId || !!busy} onClick={() => patch(u.id, { status: "disabled" })}>{saving(u.id) ? t("saving") : t("users.disable")}</button>
                    : <button className="secondary" disabled={!!busy} onClick={() => patch(u.id, { status: "active" })}>{saving(u.id) ? t("saving") : u.status === "pending" ? t("users.approve") : t("users.enable")}</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
