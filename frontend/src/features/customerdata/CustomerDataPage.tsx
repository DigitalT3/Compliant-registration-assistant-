import { FormEvent, useEffect, useState } from "react";
import { ApiError, get, post } from "../../api/client";
import { useI18n } from "../../i18n";
import { Loading } from "../../ui";

export type Section = "sites" | "contracts" | "orders" | "containers";
const PAGE = 25;
const EMPTY = { customer_id: "", name: "", postcode: "", site_id: "", valid_from: "", valid_to: "", number: "", container: "", contract_id: "", date: "" };

/** Sites, contracts, orders or containers: all customers at once, or one customer. Employees and admins can add rows. */
export default function CustomerDataPage({ section, onBack }: { section: Section; onBack: () => void }) {
  const { t } = useI18n();
  const [customers, setCustomers] = useState<any[]>([]);
  const [filter, setFilter] = useState(sessionStorage.getItem("cra.currentCustomer") || "");   // "" = all customers
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ items: any[]; total: number } | null>(null);
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState(EMPTY);
  const [formCtx, setFormCtx] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));
  const formCustomer = filter || f.customer_id;

  useEffect(() => { get("/api/customers", { limit: 200 }).then((r) => setCustomers(r.items)).catch(fail); }, []);
  useEffect(() => { setAdding(false); setNotice(null); setError(null); setOffset(0); setQ(""); }, [section]);

  const load = () => get(`/api/customer-data/${section}`, { customer_id: filter, q, limit: PAGE, offset }).then(setData).catch(fail);
  useEffect(() => { const h = setTimeout(load, q ? 250 : 0); return () => clearTimeout(h); }, [section, filter, q, offset]);

  useEffect(() => {                                         // the chosen customer's sites, containers and contracts feed the form's dropdowns
    if (!adding || !formCustomer) { setFormCtx(null); return; }
    get(`/api/customers/${formCustomer}/context`, { all: "true" }).then(setFormCtx).catch(fail);
  }, [adding, formCustomer]);

  const pickFilter = (id: string) => {
    if (id) sessionStorage.setItem("cra.currentCustomer", id); else sessionStorage.removeItem("cra.currentCustomer");
    setFilter(id); setOffset(0); setAdding(false);
  };
  const set = (k: keyof typeof EMPTY, v: string) => setF((p) => ({ ...p, [k]: v }));
  const startAdd = () => { setF({ ...EMPTY, customer_id: filter }); setAdding(true); setNotice(null); setError(null); };
  const siteName = (r: any) => r.site_name || r.site_id;

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError(null);
    const body: Record<string, any> = {
      sites: { name: f.name, postcode: f.postcode || null },
      contracts: { site_id: f.site_id, valid_from: f.valid_from || null, valid_to: f.valid_to || null },
      containers: { site_id: f.site_id, number: f.number || null },
      orders: { site_id: f.site_id, container: f.container, contract_id: f.contract_id || null, date: f.date || null },
    };
    try {
      await post(`/api/customers/${formCustomer}/${section}`, body[section]);
      await load();
      window.dispatchEvent(new CustomEvent("cra:customer-data-changed", { detail: formCustomer }));
      setAdding(false); setNotice(t("cd.added"));
    } catch (e2) { fail(e2); } finally { setBusy(false); }
  };

  const badge = (row: any) => row.source === "poc_added"
    ? <span className="badge mock">{t("cd.source.poc")}</span>
    : <span className="badge status-active">{t("cd.source.seed")}</span>;
  const customerCell = (r: any) => <td>{r.customer_name} <span className="muted">· {r.customer_number}</span></td>;
  const allMode = !filter;
  const cust = <th>{t("cd.customer")}</th>;

  const siteBoxes = formCtx ? formCtx.containers.filter((c: any) => c.site_id === f.site_id) : [];
  const siteContracts = formCtx ? formCtx.contracts.filter((c: any) => c.site_id === f.site_id) : [];
  const total = data?.total ?? 0;

  return (
    <section>
      <h2>{t(`cd.${section}`)}</h2>
      <p className="muted">{t("cd.note")}</p>
      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="ok" role="status">{notice}</p>}

      <div className="card customer-bar">
        <div className="inline">
          <label>{t("cd.customer")}
            <select value={filter} onChange={(e) => pickFilter(e.target.value)}>
              <option value="">{t("cd.all_customers")}</option>
              {customers.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.number}</option>)}
            </select>
          </label>
          <label>{t("search")}
            <input value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} maxLength={100} />
          </label>
        </div>
        <div className="inline">
          {!adding && <button onClick={startAdd}>{t(`cd.add_${section}`)}</button>}
          <button className="secondary" onClick={onBack}>{t("cd.back")}</button>
        </div>
      </div>

      {adding && (
        <form className="card" onSubmit={submit} aria-label={t(`cd.add_${section}`)}>
          {allMode && (
            <label>{t("cd.customer")}
              <select required value={f.customer_id} onChange={(e) => setF({ ...EMPTY, customer_id: e.target.value })}>
                <option value="">{t("choose")}</option>
                {customers.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.number}</option>)}
              </select>
            </label>
          )}
          {formCustomer && section === "sites" && (<>
            <label>{t("ctx.col.name")}<input required maxLength={80} value={f.name} onChange={(e) => set("name", e.target.value)} /></label>
            <label>{t("ctx.col.postcode")}<input value={f.postcode} placeholder="1234 AB" maxLength={10} onChange={(e) => set("postcode", e.target.value)} /></label>
          </>)}
          {formCustomer && section !== "sites" && formCtx && (
            formCtx.sites.length === 0 ? <p className="warn">{t("cd.need_site")}</p> : (
              <label>{t("ctx.col.site")}
                <select required value={f.site_id} onChange={(e) => setF({ ...f, site_id: e.target.value, container: "", contract_id: "" })}>
                  <option value="">{t("choose")}</option>
                  {formCtx.sites.map((s: any) => <option key={s.id} value={s.id}>{s.name} ({s.reference})</option>)}
                </select>
              </label>
            )
          )}
          {formCustomer && section === "contracts" && formCtx && (<>
            <label>{t("ctx.col.valid_from")}<input type="date" value={f.valid_from} onChange={(e) => set("valid_from", e.target.value)} /></label>
            <label>{t("ctx.col.valid_to")}<input type="date" value={f.valid_to} onChange={(e) => set("valid_to", e.target.value)} /></label>
            <p className="muted">{t("cd.dates_hint")}</p>
          </>)}
          {formCustomer && section === "containers" && formCtx && (<>
            <label>{t("cd.number")}<input value={f.number} maxLength={30} onChange={(e) => set("number", e.target.value)} /></label>
            <p className="muted">{t("cd.number_hint")}</p>
          </>)}
          {formCustomer && section === "orders" && formCtx && (<>
            <label>{t("ctx.col.container")}
              <select required value={f.container} onChange={(e) => set("container", e.target.value)}>
                <option value="">{t("choose")}</option>
                {siteBoxes.map((c: any) => <option key={c.id} value={c.number}>{c.number}</option>)}
              </select>
            </label>
            {f.site_id && siteBoxes.length === 0 && <p className="warn">{t("cd.need_container")}</p>}
            <label>{t("f.contract_id")}
              <select value={f.contract_id} onChange={(e) => set("contract_id", e.target.value)}>
                <option value="">{t("choose")}</option>
                {siteContracts.map((c: any) => <option key={c.id} value={c.id}>{c.reference}</option>)}
              </select>
            </label>
            <label>{t("ctx.col.date")}<input type="date" value={f.date} onChange={(e) => set("date", e.target.value)} /></label>
          </>)}
          <div className="inline">
            <button disabled={busy || !formCustomer}>{busy ? t("saving") : t("cd.save")}</button>
            <button type="button" className="secondary" onClick={() => setAdding(false)}>{t("pw.cancel")}</button>
          </div>
        </form>
      )}

      {!data ? <Loading label={t("loading")} lines={5} block={false} /> : total === 0 ? <p className="muted">{t("cd.none")}</p> : (
        <>
          <table className="data-table">
            {section === "sites" && (<>
              <thead><tr>{allMode && cust}<th>{t("ctx.col.name")}</th><th>{t("ctx.col.reference")}</th><th>{t("ctx.col.postcode")}</th><th>{t("cd.source")}</th></tr></thead>
              <tbody>{data.items.map((r) => <tr key={r.id}>{allMode && customerCell(r)}<td>{r.name}</td><td>{r.reference}</td><td>{r.postcode}</td><td>{badge(r)}</td></tr>)}</tbody>
            </>)}
            {section === "contracts" && (<>
              <thead><tr>{allMode && cust}<th>{t("ctx.col.reference")}</th><th>{t("ctx.col.site")}</th><th>{t("ctx.col.status")}</th><th>{t("ctx.col.valid_from")}</th><th>{t("ctx.col.valid_to")}</th><th>{t("cd.source")}</th></tr></thead>
              <tbody>{data.items.map((r) => (
                <tr key={r.id}>{allMode && customerCell(r)}<td>{r.reference}</td><td>{siteName(r)}</td><td>{r.status}</td><td>{(r.valid_from || "").slice(0, 10)}</td><td>{(r.valid_to || "").slice(0, 10)}</td><td>{badge(r)}</td></tr>
              ))}</tbody>
            </>)}
            {section === "orders" && (<>
              <thead><tr>{allMode && cust}<th>{t("ctx.col.order")}</th><th>{t("ctx.col.container")}</th><th>{t("ctx.col.site")}</th><th>{t("ctx.col.date")}</th><th>{t("ctx.col.status")}</th><th>{t("cd.source")}</th></tr></thead>
              <tbody>{data.items.map((r) => (
                <tr key={r.id}>{allMode && customerCell(r)}<td>{r.reference}</td><td>{r.container}</td><td>{siteName(r)}</td><td>{(r.date || "").slice(0, 10)}</td><td>{r.status}</td><td>{badge(r)}</td></tr>
              ))}</tbody>
            </>)}
            {section === "containers" && (<>
              <thead><tr>{allMode && cust}<th>{t("cd.number")}</th><th>{t("ctx.col.site")}</th><th>{t("ctx.col.status")}</th><th>{t("cd.source")}</th></tr></thead>
              <tbody>{data.items.map((r) => <tr key={r.id}>{allMode && customerCell(r)}<td>{r.number}</td><td>{siteName(r)}</td><td>{r.status}</td><td>{badge(r)}</td></tr>)}</tbody>
            </>)}
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
