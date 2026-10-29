import { useEffect, useState } from "react";
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

  const load = () => get("/api/users").then((r) => setItems(r.items)).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  useEffect(() => { load(); get("/api/auth/options").then(setOpts).catch(() => undefined); }, []);

  const patch = async (id: string, body: Record<string, string>) => {
    setError(null);
    try { await api("PATCH", `/api/users/${id}`, body); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
  };
  const fn = (id?: string | null) => (opts?.functions || []).find((x: any) => x.id === id)?.[lang] || id || "–";
  const pending = items.filter((u) => u.status === "pending");

  return (
    <section>
      <h2>{t("users.title")}</h2>
      <p className="muted">{t("users.note")}</p>
      {error && <p className="error" role="alert">{error}</p>}
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
