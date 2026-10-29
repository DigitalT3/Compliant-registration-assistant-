import { useState } from "react";
import { useI18n } from "../../i18n";

type Tab = "sites" | "contracts" | "orders";

/** The customer's sites, contracts and orders as three tabbed tables. A row's "Use" button fills the matching form field. */
export default function CustomerData({ ctx, siteId, contractId, orderId, onPickSite, onPickContract, onPickOrder }: {
  ctx: any; siteId: string; contractId: string; orderId: string;
  onPickSite: (id: string) => void; onPickContract: (c: any) => void; onPickOrder: (o: any) => void;
}) {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>("orders");
  const [allSites, setAllSites] = useState(false);
  const siteName = (id: string) => ctx.sites.find((x: any) => x.id === id)?.name || id;

  const contracts = ctx.contracts.filter((c: any) => allSites || !siteId || c.site_id === siteId);
  const orders = ctx.orders.filter((o: any) => allSites || !siteId || o.site_id === siteId);
  const counts: Record<Tab, number> = { sites: ctx.sites.length, contracts: contracts.length, orders: orders.length };

  const useBtn = (selected: boolean, onClick: () => void) =>
    selected
      ? <span className="badge status-active">{t("ctx.selected")}</span>
      : <button className="secondary" onClick={onClick}>{t("ctx.use")}</button>;

  return (
    <section className="card" aria-label={t("ctx.title")}>
      <h3 style={{ marginTop: 0 }}>{t("ctx.title")}</h3>
      <div className="tabs" role="tablist">
        {(["sites", "contracts", "orders"] as Tab[]).map((k) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>
            {t(`ctx.${k}`)} ({counts[k]})
          </button>
        ))}
      </div>

      {tab !== "sites" && siteId && (
        <p className="muted">
          {allSites ? t("ctx.showing_all") : t("ctx.showing_site", { site: siteName(siteId) })}{" "}
          <button className="link" onClick={() => setAllSites(!allSites)}>{allSites ? t("ctx.only_site") : t("ctx.all_sites")}</button>
        </p>
      )}

      {tab === "sites" && (
        <table className="data-table">
          <thead><tr><th>{t("ctx.col.name")}</th><th>{t("ctx.col.reference")}</th><th>{t("ctx.col.postcode")}</th><th /></tr></thead>
          <tbody>
            {ctx.sites.map((x: any) => (
              <tr key={x.id} className={x.id === siteId ? "selected" : ""}>
                <td>{x.name}</td><td>{x.reference}</td><td>{x.postcode}</td>
                <td>{useBtn(x.id === siteId, () => onPickSite(x.id))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === "contracts" && (contracts.length === 0 ? <p className="muted">{t("ctx.empty")}</p> : (
        <table className="data-table">
          <thead><tr><th>{t("ctx.col.reference")}</th><th>{t("ctx.col.site")}</th><th>{t("ctx.col.status")}</th><th>{t("ctx.col.valid_from")}</th><th>{t("ctx.col.valid_to")}</th><th /></tr></thead>
          <tbody>
            {contracts.map((c: any) => (
              <tr key={c.id} className={c.id === contractId ? "selected" : ""}>
                <td>{c.reference}</td><td>{siteName(c.site_id)}</td>
                <td><span className={`badge ${c.active ? "status-active" : "status-disabled"}`}>{c.active ? t("ctx.active") : c.status}</span></td>
                <td>{(c.valid_from || "").slice(0, 10)}</td><td>{(c.valid_to || "").slice(0, 10)}</td>
                <td>{useBtn(c.id === contractId, () => onPickContract(c))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ))}

      {tab === "orders" && (orders.length === 0 ? <p className="muted">{t("ctx.empty")}</p> : (
        <table className="data-table">
          <thead><tr><th>{t("ctx.col.order")}</th><th>{t("ctx.col.container")}</th><th>{t("ctx.col.site")}</th><th>{t("ctx.col.date")}</th><th>{t("ctx.col.status")}</th><th /></tr></thead>
          <tbody>
            {orders.map((o: any) => (
              <tr key={o.id} className={o.id === orderId ? "selected" : ""}>
                <td>{o.reference}</td><td>{o.container}</td><td>{siteName(o.site_id)}</td>
                <td>{(o.date || "").slice(0, 10)}</td><td>{o.status}</td>
                <td>{useBtn(o.id === orderId, () => onPickOrder(o))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ))}
    </section>
  );
}
