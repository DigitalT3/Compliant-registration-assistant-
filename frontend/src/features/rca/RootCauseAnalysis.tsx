import React, { useEffect, useState } from "react";
import { ApiError, get, post } from "../../api/client";
import { useI18n } from "../../i18n";

const pct = (x: number | null | undefined) => (x == null ? "–" : `${(x * 100).toFixed(1)}%`);

/** Root-cause analysis after the build (FR-18 to FR-20): themes in "Other", a proposed shorter list, and the re-label test. */
export default function RootCauseAnalysis({ canRun, canReview }: { canRun: boolean; canReview: boolean }) {
  const { t } = useI18n();
  const [d, setD] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));
  const load = () => get<any>("/api/rca").then((r) => { setD(r); setError(null); }).catch(fail);
  useEffect(() => { load(); }, []);

  const run = (what: string, path: string, body: unknown = {}) => {
    setBusy(what);
    post(path, body).then(() => load()).catch(fail).finally(() => setBusy(null));
  };
  if (!d) return <section><h2>{t("rca.title")}</h2>{error ? <p className="error" role="alert">{error}</p> : <p>…</p>}</section>;
  const th = d.themes, pr = d.proposal, rl = d.relabel;
  return (
    <section>
      <h2>{t("rca.title")}</h2>
      <p>{t("rca.intro")}</p>
      {error && <p className="error" role="alert">{t("error")}: {error}</p>}

      <article className="card"><h3>{t("rca.themes")} <small>(FR-18)</small></h3>
        <p>{t("rca.themes.help", { n: d.other_records })}</p>
        {canRun && <button disabled={!!busy || !d.other_records} onClick={() => run("themes", "/api/rca/themes", { include_seed: true, min_theme_size: 2 })}>{busy === "themes" ? t("rca.running") : t("rca.run.themes")}</button>}
        {th && <>
          <p data-testid="rca-coverage"><strong>{t("rca.coverage")}: {pct(th.coverage)}</strong> ({th.covered}/{th.n}) – {t("rca.target")} {pct(th.target)}: {th.meets_target ? t("rca.met") : t("rca.not_met")}</p>
          <table><thead><tr><th>{t("rca.col.theme")}</th><th>{t("rca.col.count")}</th><th>{t("rca.col.maps")}</th><th>{t("rca.col.examples")}</th></tr></thead>
            <tbody>{th.themes.map((x: any) => <tr key={x.id}><td>{x.label}</td><td>{x.count}{x.counts ? "" : " *"}</td><td>{x.existing_category || `${t("rca.new")}: ${x.new_category}`}</td><td>{x.examples.slice(0, 2).join(" / ")}</td></tr>)}</tbody></table>
          <p><small>{t("rca.themes.note", { n: th.min_theme_size })} {th.unassigned} {t("rca.unassigned")}.</small></p>
        </>}
      </article>

      <article className="card"><h3>{t("rca.proposal")} <small>(FR-19)</small></h3>
        {canRun && <button disabled={!!busy || !th} onClick={() => run("proposal", "/api/rca/proposal", { max_categories: 8 })}>{busy === "proposal" ? t("rca.running") : t("rca.run.proposal")}</button>}
        {pr && <>
          <p><strong>{pr.version}</strong> – {pr.n_categories} {t("rca.categories")} ({t("rca.today")} {pr.current_size}). {t("rca.agreed_by", { n: pr.review.agreed, m: pr.review.required })} <strong data-testid="rca-state">{pr.review.state}</strong></p>
          <table><thead><tr><th>{t("rca.col.category")}</th><th>{t("rca.col.definition")}</th><th>{t("rca.col.examples")}</th></tr></thead>
            <tbody>{pr.categories.map((c: any) => <tr key={c.id}><td>{c.name_en}<br /><small>{c.name_nl}</small></td><td>{c.definition}</td><td>{c.examples.join("; ")}</td></tr>)}</tbody></table>
          <ul>{pr.review.reviews.map((r: any) => <li key={r.user_id || r.name}>{r.name}: {r.decision}{r.comment ? ` – ${r.comment}` : ""}</li>)}</ul>
          {canReview && <div>
            <input aria-label={t("rca.comment")} placeholder={t("rca.comment")} value={comment} onChange={(e) => setComment(e.target.value)} />
            <button disabled={!!busy} onClick={() => run("agree", "/api/rca/proposal/review", { decision: "agree", comment: comment || null })}>{t("rca.agree")}</button>{" "}
            <button disabled={!!busy} onClick={() => run("changes", "/api/rca/proposal/review", { decision: "changes_requested", comment: comment || null })}>{t("rca.changes")}</button>
          </div>}
        </>}
      </article>

      <article className="card"><h3>{t("rca.relabel")} <small>(FR-20)</small></h3>
        <p>{t("rca.relabel.help", { n: d.expert_labelled, m: d.targets.records })}</p>
        {canRun && <button disabled={!!busy || !d.expert_labelled} onClick={() => run("relabel", "/api/rca/relabel")}>{busy === "relabel" ? t("rca.running") : t("rca.run.relabel")}</button>}
        {rl && <p data-testid="rca-agreement"><strong>{t("rca.agreement")}: {pct(rl.agreement)}</strong> ({rl.agree}/{rl.n}) – {t("rca.target")} {pct(rl.target)} {t("rca.on")} {rl.target_records}: <strong>{t(`rca.status.${rl.status}`)}</strong></p>}
      </article>
    </section>
  );
}
