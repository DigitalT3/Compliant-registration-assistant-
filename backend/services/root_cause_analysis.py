"""Root-cause analysis after the build (FR-18 to FR-20): themes in the "Other" reasons, a proposed shorter list, and a re-label test.

The language model proposes (themes, a list, a label); the numbers that matter are worked out here from what it proposed, never taken
from its own claims: coverage is the share of records that sit in a theme of at least ``min_theme_size`` records (so one theme per
record cannot reach the target), a proposal is repaired until every existing cause and every theme is covered exactly once, and
agreement is counted record by record against the expert's label.
Results are kept in ``app_settings`` (latest of each); every run is written to the audit log. Works on whatever records it is given:
the PoC's synthetic data now, a real export when the data may be used.
"""
import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .. import db
from ..dbutil import audit
from ..errors import ApiError
from ..settings import get_config
from . import agreement, ai

TARGET_COVERAGE = 0.90           # FR-18: themes cover at least 90% of the "Other" records
TARGET_AGREEMENT = 0.85          # FR-20: at least 85% agreement between assistant and expert labels ...
TARGET_RECORDS = 200             # ... on 200 records
KEY_THEMES, KEY_PROPOSAL, KEY_RELABEL, KEY_REVIEW = "rca_themes", "rca_proposal", "rca_relabel", "rca_proposal_review"


def _get(conn, key):
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def _put(conn, key, value):
    conn.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value, ensure_ascii=False)))


def _categories(cfg) -> list:
    return [{"id": c["id"], "name": c.get("en"), "definition": c.get("definition")} for c in cfg["root_causes"] if c["id"] != "other"]


# ---- FR-18: themes in the "Other" free text ---------------------------------------------------------------------------

# PUBLIC_INTERFACE
def other_records(conn, include_seed: bool = True) -> list:
    """The "Other" records that have a reason: ``[{id, text}]``."""
    rows = conn.execute("SELECT id, other_reason FROM complaints WHERE root_cause='other'" + ("" if include_seed else " AND is_seed=0") + " ORDER BY id").fetchall()
    return [{"id": r["id"], "text": r["other_reason"].strip()} for r in rows if (r["other_reason"] or "").strip()]


# PUBLIC_INTERFACE
def analyse_themes(records: list, cfg: dict | None = None, min_theme_size: int = 2, chunk: int = 60, call=None) -> dict:
    """Cluster the free text into themes and map each to an existing category or a new one; report the coverage."""
    cfg, call = cfg or get_config(), call or ai.call
    cats = _categories(cfg)
    known_cats = {c["id"] for c in cats}
    text = {r["id"]: r["text"] for r in records}
    batches = [records[i:i + chunk] for i in range(0, len(records), chunk)]
    found = []                                                                    # themes per batch: (key, label, definition, ids, existing)
    for b, batch in enumerate(batches):
        ids = {r["id"] for r in batch}
        out = call("themes", {"records": batch, "categories": cats})
        for j, t in enumerate(out.themes):
            members = [i for i in dict.fromkeys(t.record_ids) if i in ids]       # unknown ids dropped, repeats counted once
            if members:
                found.append({"key": f"{b}:{j}", "label": t.label.strip(), "definition": t.definition.strip(),
                              "ids": members, "existing": t.existing_category if t.existing_category in known_cats else None})
    merged = found
    new_names: dict = {}
    if len(batches) > 1 and found:                                                # several batches: let the model join the same themes
        items = [{"key": f["key"], "label": f["label"], "definition": f["definition"], "count": len(f["ids"]),
                  "examples": [text[i] for i in f["ids"][:3]], "existing_category": f["existing"]} for f in found]
        out = call("merge_themes", {"themes": items, "categories": cats})
        by_key, merged, used = {f["key"]: f for f in found}, [], set()
        for m in out.themes:
            keys = [k for k in dict.fromkeys(m.member_keys) if k in by_key and k not in used]
            used.update(keys)
            if keys:
                ids = list(dict.fromkeys(i for k in keys for i in by_key[k]["ids"]))
                existing = m.existing_category if m.existing_category in known_cats else None
                merged.append({"key": keys[0], "label": m.label.strip(), "definition": m.definition.strip(), "ids": ids, "existing": existing})
                if not existing and m.new_category_name:
                    new_names[keys[0]] = m.new_category_name.strip()
        merged += [by_key[k] for k in by_key if k not in used]                    # a theme the model forgot to place stays as it was
    seen, themes = set(), []
    for f in merged:
        ids = [i for i in f["ids"] if i not in seen]                             # a record belongs to one theme
        seen.update(ids)
        if ids:
            themes.append({"label": f["label"], "definition": f["definition"], "existing_category": f["existing"],
                           "new_category": None if f["existing"] else new_names.get(f["key"]) or f["label"], "record_ids": ids})
    themes.sort(key=lambda t: (-len(t["record_ids"]), t["label"]))
    n = len(records)
    for k, t in enumerate(themes, 1):
        t.update({"id": f"T{k:02d}", "count": len(t["record_ids"]), "share": round(len(t["record_ids"]) / n, 4) if n else None,
                  "examples": [text[i] for i in t["record_ids"][:3]], "counts": len(t["record_ids"]) >= min_theme_size})
    covered = sum(t["count"] for t in themes if t["counts"])
    coverage = round(covered / n, 4) if n else None
    return {"n": n, "min_theme_size": min_theme_size, "themes": themes, "n_themes": sum(t["counts"] for t in themes),
            "covered": covered, "coverage": coverage, "target": TARGET_COVERAGE, "meets_target": bool(n) and covered / n >= TARGET_COVERAGE,
            "unassigned": n - sum(t["count"] for t in themes), "in_small_themes": sum(t["count"] for t in themes if not t["counts"]),
            "mapped_to_existing": sum(t["count"] for t in themes if t["existing_category"]),
            "new_categories": sorted({t["new_category"] for t in themes if t["counts"] and t["new_category"]}),
            "unassigned_ids": [r["id"] for r in records if r["id"] not in seen], "generated_at": db.now()}


# PUBLIC_INTERFACE
def run_themes(conn, user: dict, include_seed: bool = True, min_theme_size: int = 2) -> dict:
    """Analyse the PoC's own "Other" records, keep the result and audit the run."""
    records = other_records(conn, include_seed)
    if not records:
        raise ApiError(409, "no_other_records", "There are no 'Other' reasons to analyse yet.")
    try:
        result = analyse_themes(records, get_config(), min_theme_size)
    except ai.AIError as e:
        raise ApiError(503, "ai_unavailable", f"The assistant could not analyse the reasons ({e.category}). Try again.")
    result.update({"source": "PoC database", "include_seed": include_seed, "by": user["name"]})
    _put(conn, KEY_THEMES, result)
    audit(conn, user["id"], "rca_themes_run", {"n": result["n"], "themes": result["n_themes"], "coverage": result["coverage"]})
    conn.commit()
    return result


# ---- FR-19: a proposed shorter list ----------------------------------------------------------------------------------

def _slug(s: str) -> str:
    return re.sub(r"[^a-z]+", "_", s.lower()).strip("_")[:40] or "category"


def _hash(categories: list) -> str:
    return hashlib.sha256(json.dumps(categories, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


# PUBLIC_INTERFACE
def propose_list(themes: dict, cfg: dict | None = None, max_categories: int = 8, call=None) -> dict:
    """Combine the existing causes and the themes into a shorter list with a definition and examples for every category."""
    cfg, call = cfg or get_config(), call or ai.call
    cats_by_l1 = {c["id"]: c for c in cfg["root_cause_categories"]}
    existing = [{"id": c["id"], "name": c.get("en"), "definition": c.get("definition"), "examples": c.get("examples"), "level1": c.get("level1"),
                 "category_en": cats_by_l1.get(c.get("level1"), {}).get("en"), "category_nl": cats_by_l1.get(c.get("level1"), {}).get("nl")}
                for c in cfg["root_causes"] if c["id"] != "other"]
    th = [{"label": t["label"], "definition": t["definition"], "count": t["count"], "existing_category": t["existing_category"], "examples": t["examples"]}
          for t in themes["themes"] if t["counts"]]
    out = call("propose_list", {"existing": existing, "themes": th, "max_categories": max_categories})
    existing_ids, labels, repairs = [e["id"] for e in existing], [t["label"] for t in th], []
    cats, used = [], set()
    for c in out.categories:
        cid = _slug(c.id)
        while cid in used:
            cid += "_2"
        used.add(cid)
        cats.append({"id": cid, "name_en": c.name_en.strip(), "name_nl": c.name_nl.strip(), "definition": c.definition.strip(),
                     "examples": [e.strip() for e in c.examples if e.strip()][:4], "covers_existing": [], "covers_themes": [],
                     "_e": list(c.covers_existing), "_t": list(c.covers_themes)})
    seen_e, seen_t = set(), set()
    for c in cats:
        c["covers_existing"] = [e for e in dict.fromkeys(c.pop("_e")) if e in existing_ids and e not in seen_e and not seen_e.add(e)]
        c["covers_themes"] = [t for t in dict.fromkeys(c.pop("_t")) if t in labels and t not in seen_t and not seen_t.add(t)]
    catch_all = next((c for c in cats if c["id"] == "other"), None)

    def home():                                                                  # where something the model left out goes: the catch-all category
        nonlocal catch_all
        if catch_all is None:
            catch_all = {"id": "other", "name_en": "Other", "name_nl": "Overig", "definition": "Anything that fits no other category; reasons are collected to improve the list.",
                         "examples": [], "covers_existing": [], "covers_themes": []}
            cats.append(catch_all)
        return catch_all
    by_l1 = {e["id"]: e["level1"] for e in existing}
    for e in existing_ids:
        if e not in seen_e:
            sibling = next((c for c in cats if any(by_l1.get(x) == by_l1[e] for x in c["covers_existing"])), None)
            (sibling or home())["covers_existing"].append(e)
            repairs.append(f"existing cause '{e}' was not placed; added to '{(sibling or catch_all)['id']}'")
    for t in labels:
        if t not in seen_t:
            ex = next((x["existing_category"] for x in th if x["label"] == t), None)
            target = next((c for c in cats if ex and ex in c["covers_existing"]), None) or home()
            target["covers_themes"].append(t)
            repairs.append(f"theme '{t}' was not placed; added to '{target['id']}'")
    ex_text = {x["label"]: x["examples"] for x in th}
    for c in cats:
        if not c["definition"]:
            c["definition"] = "; ".join(e["definition"] or e["id"] for e in existing if e["id"] in c["covers_existing"])[:400] or c["name_en"]
        if len(c["examples"]) < 2:                                               # two examples at least: from the themes it covers, then from the old causes
            more = [x for t in c["covers_themes"] for x in ex_text.get(t, [])] + [x.strip() for e in existing if e["id"] in c["covers_existing"] for x in (e["examples"] or "").split(",")]
            c["examples"] = list(dict.fromkeys(c["examples"] + [m for m in more if m]))[:3]
    cats = [c for c in cats if c["covers_existing"] or c["covers_themes"] or c["id"] == "other"]
    return {"version": "v1-proposal-" + _hash(cats)[:8], "content_hash": _hash(cats), "categories": cats, "n_categories": len(cats), "current_size": len(existing) + 1,
            "shorter": len(cats) < len(existing) + 1, "max_categories": max_categories, "repairs": repairs,
            "based_on": {"records": themes["n"], "themes": themes["n_themes"], "coverage": themes["coverage"]}, "generated_at": db.now()}


# PUBLIC_INTERFACE
def build_proposal(conn, user: dict, max_categories: int = 8) -> dict:
    themes = _get(conn, KEY_THEMES)
    if not themes:
        raise ApiError(409, "themes_first", "Run the analysis of the 'Other' reasons first.")
    try:
        proposal = propose_list(themes, get_config(), max_categories)
    except ai.AIError as e:
        raise ApiError(503, "ai_unavailable", f"The assistant could not propose a list ({e.category}). Try again.")
    proposal["by"] = user["name"]
    _put(conn, KEY_PROPOSAL, proposal)
    audit(conn, user["id"], "rca_proposal_built", {"version": proposal["version"], "categories": proposal["n_categories"], "repairs": len(proposal["repairs"])})
    conn.commit()
    return proposal_state(conn)


def _required(cfg) -> int:
    return int(cfg.get("taxonomy_review", {}).get("required_agreements", 3))


# PUBLIC_INTERFACE
def proposal_state(conn) -> dict | None:
    """The latest proposal with who agreed to this exact version (``agreed`` once enough people did)."""
    p = _get(conn, KEY_PROPOSAL)
    if not p:
        return None
    return {**p, "review": agreement.status(conn, KEY_REVIEW, p["content_hash"], _required(get_config()))}


# PUBLIC_INTERFACE
def review_proposal(conn, user: dict, decision: str, comment: str | None) -> dict:
    p = _get(conn, KEY_PROPOSAL)
    if not p:
        raise ApiError(409, "no_proposal", "There is no proposed list to review yet.")
    agreement.review(conn, user, KEY_REVIEW, p["content_hash"], decision, comment, ("rca_proposal_agreed", "rca_proposal_changes_requested"), {"version": p["version"]})
    return proposal_state(conn)


# ---- FR-20: re-label a sample with the list and compare with the experts ------------------------------------------------

def _taxonomy(categories: list) -> list:
    return [{"id": c["id"], "en": c.get("name_en") or c.get("en"), "nl": c.get("name_nl") or c.get("nl"), "definition": c.get("definition"),
             "examples": ", ".join(c["examples"]) if isinstance(c.get("examples"), list) else (c.get("examples") or ""), "type": None} for c in categories]


# PUBLIC_INTERFACE
def relabel(records: list, categories: list, types: list, workers: int = 8, call=None) -> dict:
    """Label each record with the list as the assistant would (its first suggestion) and compare with the expert's label.

    ``records`` = ``[{id, text, expert}]``; ``categories`` = the list (id, name_en/en, definition, examples). A record the assistant
    could not label counts as a disagreement. Fewer than 200 records is reported as indicative, never as met.
    """
    call = call or ai.call
    ids = {c["id"] for c in categories}
    valid = [r for r in records if r["expert"] in ids]
    taxonomy = _taxonomy(categories)

    def label(r):
        try:
            out = call("classify", {"text": r["text"], "taxonomy": taxonomy, "types": types})
            top = out.candidates[0] if out.candidates else None
            return {"id": r["id"], "expert": r["expert"], "assistant": top.root_cause_id if top and top.root_cause_id in ids else None,
                    "confidence": top.confidence if top else None, "failed": False, "text": r["text"]}
        except ai.AIError:
            return {"id": r["id"], "expert": r["expert"], "assistant": None, "confidence": None, "failed": True, "text": r["text"]}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = list(pool.map(label, valid))
    for r in rows:
        r["agree"] = r["assistant"] == r["expert"]
    n, agree = len(rows), sum(r["agree"] for r in rows)
    per = {}
    for c in categories:
        mine = [r for r in rows if r["expert"] == c["id"]]
        per[c["id"]] = {"expert_n": len(mine), "agree_n": sum(r["agree"] for r in mine)}
    pairs = Counter((r["expert"], r["assistant"]) for r in rows if not r["agree"])
    agreement_rate = round(agree / n, 4) if n else None
    status = "no_data" if not n else "indicative" if n < TARGET_RECORDS else "met" if agree / n >= TARGET_AGREEMENT else "not_met"
    return {"n": n, "agree": agree, "agreement": agreement_rate, "target": TARGET_AGREEMENT, "target_records": TARGET_RECORDS, "status": status,
            "failed": sum(r["failed"] for r in rows), "invalid_labels": len(records) - len(valid), "per_category": per,
            "confusions": [{"expert": e, "assistant": a, "count": c} for (e, a), c in pairs.most_common(8)],
            "disagreements": [{k: r[k] for k in ("id", "text", "expert", "assistant", "confidence")} for r in rows if not r["agree"]][:50], "generated_at": db.now()}


# PUBLIC_INTERFACE
def expert_labelled(conn) -> list:
    """The PoC's complaints that an expert labelled (blind): ``[{id, text, expert}]``, the latest label per complaint."""
    rows = conn.execute("SELECT e.complaint_id, e.expert_cause, c.original_text FROM evaluations e JOIN complaints c ON c.id=e.complaint_id "
                        "WHERE e.expert_cause IS NOT NULL AND e.id IN (SELECT max(id) FROM evaluations WHERE expert_cause IS NOT NULL GROUP BY complaint_id) ORDER BY e.complaint_id").fetchall()
    return [{"id": r["complaint_id"], "text": r["original_text"] or "", "expert": r["expert_cause"]} for r in rows if r["original_text"]]


# PUBLIC_INTERFACE
def run_relabel(conn, user: dict) -> dict:
    """Re-label the PoC's expert-labelled complaints with the current cause list."""
    cfg = get_config()
    records = expert_labelled(conn)
    if not records:
        raise ApiError(409, "no_labels", "No complaint has an expert label yet (Evaluation, Blind labelling).")
    result = relabel(records, [{"id": c["id"], "name_en": c.get("en"), "name_nl": c.get("nl"), "definition": c.get("definition"), "examples": c.get("examples")} for c in cfg["root_causes"]],
                     [t["id"] for t in cfg["types"]])
    result.update({"list": "current cause list " + cfg["taxonomy_version"], "by": user["name"]})
    _put(conn, KEY_RELABEL, result)
    audit(conn, user["id"], "rca_relabel_run", {"n": result["n"], "agreement": result["agreement"], "status": result["status"]})
    conn.commit()
    return result


# PUBLIC_INTERFACE
def overview(conn) -> dict:
    cfg = get_config()
    return {"themes": _get(conn, KEY_THEMES), "proposal": proposal_state(conn), "relabel": _get(conn, KEY_RELABEL),
            "targets": {"coverage": TARGET_COVERAGE, "agreement": TARGET_AGREEMENT, "records": TARGET_RECORDS}, "current_size": len(cfg["root_causes"]),
            "other_records": len(other_records(conn)), "expert_labelled": len(expert_labelled(conn)), "required_agreements": _required(cfg)}
