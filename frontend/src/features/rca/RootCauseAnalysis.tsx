import React, { useEffect, useState } from "react";
import { ApiError, get, post, put } from "../../api/client";
import { useI18n } from "../../i18n";

const pct = (x: number | null | undefined) => (x == null ? "–" : `${(x * 100).toFixed(1)}%`);

/** Root-cause analysis after the build (FR-18 to FR-20): themes in "Other", a proposed shorter list, and the re-label test. */
export default function RootCauseAnalysis({ canRun, canReview, canApply, canFreeze, onListChanged }:
  { canRun: boolean; canReview: boolean; canApply?: boolean; canFreeze?: boolean; onListChanged?: () => void }) {
  const { t } = useI18n();
  const [d, setD] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [live, setLive] = useState<any>(null);
  const [note, setNote] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));
  const load = () => Promise.all([get<any>("/api/rca"), get<any>("/api/rca/live")]).then(([r, l]) => { setD(r); setLive(l); setError(null); }).catch(fail);
  const change = (what: string, path: string, message: string, method: "post" | "put" = "post", body: unknown = { note: note || null }) => {
    setBusy(what); setDone(null);
    (method === "put" ? put(path, body) : post(path, body)).then(() => { setNote(""); setDone(message); onListChanged?.(); return load(); }).catch(fail).finally(() => setBusy(null));
  };
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
          <ul>{pr.review.reviews.map((r: any) => <li key={r.user_id || r.name}>{r.name}: {r.decision}{r.counts === false ? ` (${t("review.no_count")})` : ""}{r.comment ? ` – ${r.comment}` : ""}</li>)}</ul>
          {canReview && <div>
            <input aria-label={t("rca.comment")} placeholder={t("rca.comment")} value={comment} onChange={(e) => setComment(e.target.value)} />
            <button disabled={!!busy} onClick={() => run("agree", "/api/rca/proposal/review", { decision: "agree", comment: comment || null })}>{t("rca.agree")}</button>{" "}
            <button disabled={!!busy} onClick={() => run("changes", "/api/rca/proposal/review", { decision: "changes_requested", comment: comment || null })}>{t("rca.changes")}</button>
          </div>}
        </>}
      </article>

      {pr && live && <article className="card" aria-label={t("rca.live")}><h3>{t("rca.live")}</h3>
        <p className="muted">{t("rca.live.help")}</p>
        <p><strong>{t("rca.live.version", { v: live.taxonomy_version })}</strong></p>
        {done && <p className="ok" role="status">{done}</p>}
        {live.freeze?.frozen && <p className="warn">{t("rca.live.frozen_by", { by: live.freeze.by, at: live.freeze.at?.slice(0, 16).replace("T", " ") })}{live.freeze.note ? ` – ${live.freeze.note}` : ""}</p>}
        {live.blockers.length === 0
          ? <p className="ok">{t("rca.live.ready")}</p>
          : <ul>{live.blockers.map((b: string) => <li key={b} className="warn-text">{t(`rca.live.block.${b}`)}{b === "registration_in_progress" ? ` (${live.in_progress})` : ""}</li>)}</ul>}
        {live.preview && live.preview.mapping.length > 0 && <>
          <h4>{t("rca.live.mapping")}</h4>
          <table><thead><tr><th>{t("rca.live.col.old")}</th><th>{t("rca.live.col.new")}</th><th>{t("rca.live.col.records")}</th></tr></thead>
            <tbody>{live.preview.mapping.map((m: any) => <tr key={m.old_id}><td>{m.old_name}</td><td>{pr.categories.find((c: any) => c.id === m.new_id)?.name_en || m.new_id}</td><td>{m.records}</td></tr>)}</tbody></table>
          <p><small>{t("rca.live.kept", { n: live.preview.kept.length })} {t("rca.live.remapped", { n: live.preview.records_remapped })}</small></p>
        </>}
        {(canApply || canFreeze) && <div className="inline">
          {canApply && <label>{t("rca.live.note")}<input value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} /></label>}
          {canApply && <button disabled={!!busy || !live.can_apply} onClick={() => window.confirm(t("rca.live.apply.confirm")) && change("apply", "/api/rca/proposal/apply", t("rca.live.applied"))}>{t("rca.live.apply")}</button>}
          {canApply && <button className="secondary" disabled={!!busy || !live.can_restore} onClick={() => window.confirm(t("rca.live.restore.confirm")) && change("restore", "/api/rca/live/restore", t("rca.live.restored"))}>{t("rca.live.restore")}</button>}
          {canFreeze && <button className="secondary" disabled={!!busy} onClick={() => change("freeze", "/api/rca/live/freeze", "", "put", { frozen: !live.freeze?.frozen, note: note || null })}>{live.freeze?.frozen ? t("rca.live.unfreeze") : t("rca.live.freeze")}</button>}
        </div>}
        {live.history.length > 0 && <>
          <h4>{t("rca.live.history")}</h4>
          <table><thead><tr><th>{t("rca.live.col.version")}</th><th>{t("rca.live.col.when")}</th><th>{t("rca.live.col.by")}</th><th>{t("rca.live.col.state")}</th></tr></thead>
            <tbody>{live.history.map((h: any) => <tr key={h.version}><td>{h.taxonomy_version}</td><td>{h.applied_at?.slice(0, 16).replace("T", " ")}</td><td>{h.applied_by}</td><td>{h.active ? t("rca.live.active") : t("rca.live.past")}</td></tr>)}</tbody></table>
        </>}
      </article>}

      <article className="card"><h3>{t("rca.relabel")} <small>(FR-20)</small></h3>
        <p>{t("rca.relabel.help", { n: d.expert_labelled, m: d.targets.records })}</p>
        {canRun && <button disabled={!!busy || !d.expert_labelled} onClick={() => run("relabel", "/api/rca/relabel")}>{busy === "relabel" ? t("rca.running") : t("rca.run.relabel")}</button>}
        {rl && <p data-testid="rca-agreement"><strong>{t("rca.agreement")}: {pct(rl.agreement)}</strong> ({rl.agree}/{rl.n}) – {t("rca.target")} {pct(rl.target)} {t("rca.on")} {rl.target_records}: <strong>{t(`rca.status.${rl.status}`)}</strong></p>}
      </article>
    </section>
  );
}
