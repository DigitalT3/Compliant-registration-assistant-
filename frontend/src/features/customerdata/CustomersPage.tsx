import { FormEvent, useEffect, useState } from "react";
import { ApiError, get, post } from "../../api/client";
import { useI18n } from "../../i18n";

const PAGE = 25;

/** Every customer with how much data each has; employees and admins can add a customer. */
export default function CustomersPage({ onOpen }: { onOpen: () => void }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ items: any[]; total: number } | null>(null);
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ name: "", postcode: "", first_site: "Main site" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));

  const load = () => get("/api/customers", { q, limit: PAGE, offset }).then(setData).catch(fail);
  useEffect(() => { const h = setTimeout(load, q ? 250 : 0); return () => clearTimeout(h); }, [q, offset]);

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      const c = await post("/api/customers", { name: f.name, postcode: f.postcode || null, first_site: f.first_site || null });
      setAdding(false); setF({ name: "", postcode: "", first_site: "Main site" });
      setNotice(t("cd.customer_added", { name: c.name, number: c.number }));
      setQ(""); setOffset(0); await load();
    } catch (e2) { fail(e2); } finally { setBusy(false); }
  };
  const open = (id: string) => { sessionStorage.setItem("cra.currentCustomer", id); onOpen(); };
  const total = data?.total ?? 0;

  return (
    <section>
      <h2>{t("cd.customers")}</h2>
      <p className="muted">{t("cd.note")}</p>
      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="ok" role="status">{notice}</p>}
      <div className="card customer-bar">
        <label>{t("search")}
          <input value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} maxLength={100} placeholder={t("cd.customer_search")} />
        </label>
        {!adding && <button onClick={() => { setAdding(true); setNotice(null); setError(null); }}>{t("cd.add_customers")}</button>}
      </div>

      {adding && (
        <form className="card" onSubmit={submit} aria-label={t("cd.add_customers")}>
          <label>{t("ctx.col.name")}<input required maxLength={120} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
          <label>{t("ctx.col.postcode")}<input value={f.postcode} placeholder="1234 AB" maxLength={10} onChange={(e) => setF({ ...f, postcode: e.target.value })} /></label>
          <label>{t("cd.first_site")}<input maxLength={80} value={f.first_site} onChange={(e) => setF({ ...f, first_site: e.target.value })} /></label>
          <p className="muted">{t("cd.first_site_hint")} {t("cd.number_auto")}</p>
          <div className="inline">
            <button disabled={busy}>{busy ? t("saving") : t("cd.save")}</button>
            <button type="button" className="secondary" onClick={() => setAdding(false)}>{t("pw.cancel")}</button>
          </div>
        </form>
      )}

      {!data ? <p className="muted" role="status">{t("loading")}</p> : total === 0 ? <p className="muted">{t("cd.none")}</p> : (
        <>
          <table className="data-table">
            <thead><tr>
              <th>{t("f.customer_number")}</th><th>{t("ctx.col.name")}</th><th>{t("ctx.col.postcode")}</th>
              <th>{t("cd.sites")}</th><th>{t("cd.contracts")}</th><th>{t("cd.orders")}</th><th>{t("cd.containers")}</th><th>{t("cd.source")}</th><th />
            </tr></thead>
            <tbody>
              {data.items.map((c) => (
                <tr key={c.id}>
                  <td>{c.number}</td><td>{c.name}</td><td>{c.postcode}</td>
                  <td>{c.sites}</td><td>{c.contracts}</td><td>{c.orders}</td><td>{c.containers}</td>
                  <td>{c.source === "poc_added" ? <span className="badge mock">{t("cd.source.poc")}</span> : <span className="badge status-active">{t("cd.source.seed")}</span>}</td>
                  <td><button className="secondary" onClick={() => open(c.id)}>{t("cd.open")}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="inline pager">
            <span className="muted">{t("cd.showing", { from: offset + 1, to: Math.min(offset + PAGE, total), total })}</span>
            <button className="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>{t("cd.prev")}</button>
            <button className="secondary" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>{t("cd.next")}</button>
          </div>
        </>
      )}
    </section>
  );
}
