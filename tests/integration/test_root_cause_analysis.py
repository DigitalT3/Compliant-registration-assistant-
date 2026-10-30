"""FR-18 to FR-20 tooling (themes, proposed list, re-label test) on the mock assistant: the numbers come from code, not from the model."""
from backend import db
from backend.services import ai, root_cause_analysis as rca
from tests.conftest import ADMIN, EMP
from tests.integration.test_taxonomy_review import owners

TEXTS = ["A seagull built a nest in the container", "Mice found in the container", "Road closure blocked the truck", "Parade event, street afgesloten",
         "Customer asks about the new legislation", "Question about permit rules", "Strange reason nobody else has"]


def records(texts=TEXTS):
    return [{"id": f"R{i}", "text": t} for i, t in enumerate(texts)]


def test_coverage_counts_only_themes_with_enough_records():
    out = rca.analyse_themes(records())
    assert out["n"] == 7 and out["n_themes"] == 3 and out["covered"] == 6 and out["unassigned"] == 1
    assert out["coverage"] == round(6 / 7, 4) and out["meets_target"] is False            # 85.7% < 90%
    assert out["unassigned_ids"] == ["R6"]
    assert sum(t["count"] for t in out["themes"]) == 6 and all(t["new_category"] or t["existing_category"] for t in out["themes"])


def test_one_theme_per_record_cannot_reach_the_target():
    def one_each(op, payload):
        return ai.ThemesOut(themes=[ai.ThemeOut(label=f"t{r['id']}", record_ids=[r["id"]]) for r in payload["records"]])
    out = rca.analyse_themes(records(), call=one_each)
    assert out["coverage"] == 0 and out["in_small_themes"] == 7 and not out["meets_target"]


def test_invented_and_repeated_record_ids_are_ignored():
    def odd(op, payload):
        return ai.ThemesOut(themes=[ai.ThemeOut(label="a", record_ids=["R0", "R0", "R1", "ghost"]), ai.ThemeOut(label="b", record_ids=["R1", "R2"])])
    out = rca.analyse_themes(records(), call=odd)
    assert [t["record_ids"] for t in out["themes"]] == [["R0", "R1"], ["R2"]]               # R1 only once; "ghost" dropped


def test_several_batches_are_merged():
    out = rca.analyse_themes(records(TEXTS * 3), chunk=7)
    assert out["n"] == 21 and out["n_themes"] == 3 and {t["count"] for t in out["themes"] if t["counts"]} == {6}


def test_proposal_covers_every_cause_and_theme_once_and_is_shorter(client):
    from backend.settings import get_config
    cfg = get_config()
    th = rca.analyse_themes(records(), cfg)
    p = rca.propose_list(th, cfg)
    old = [c["id"] for c in cfg["root_causes"] if c["id"] != "other"]
    placed = [e for c in p["categories"] for e in c["covers_existing"]]
    assert sorted(placed) == sorted(old)
    assert sorted(t for c in p["categories"] for t in c["covers_themes"]) == sorted(t["label"] for t in th["themes"] if t["counts"])
    assert p["shorter"] and p["n_categories"] < len(cfg["root_causes"])
    assert all(c["definition"] and len(c["examples"]) >= 2 for c in p["categories"] if c["id"] != "other")


def test_a_cause_the_model_left_out_is_put_back():
    from backend.settings import get_config
    cfg = get_config()
    th = rca.analyse_themes(records(), cfg)
    p = rca.propose_list(th, cfg, call=lambda op, pl: ai.ProposalOut(categories=[]))
    assert sorted(e for c in p["categories"] for e in c["covers_existing"]) == sorted(c["id"] for c in cfg["root_causes"] if c["id"] != "other")
    assert p["repairs"]


def test_relabel_counts_agreement_and_calls_a_small_sample_indicative():
    cats = [{"id": "a", "name_en": "A", "definition": "d"}, {"id": "b", "name_en": "B", "definition": "d"}]

    def label(op, pl):
        c = ai.CandidateOut(root_cause_id="a" if "x" in pl["text"] else "b", reason="r", confidence=0.9)
        return ai.ClassificationOut(complaint_type="request", candidates=[c])
    recs = [{"id": str(i), "text": "x" if i < 6 else "y", "expert": "a" if i < 8 else "b"} for i in range(10)]   # assistant: 6x a, 4x b
    out = rca.relabel(recs + [{"id": "z", "text": "x", "expert": "unknown_cause"}], cats, ["request"], call=label)
    assert (out["n"], out["agree"], out["invalid_labels"]) == (10, 8, 1)                    # records 6,7 are wrong; unknown label left out
    assert out["agreement"] == 0.8 and out["status"] == "indicative"                         # 10 records is never "met"
    assert out["confusions"] == [{"expert": "a", "assistant": "b", "count": 2}]


def test_200_records_decide_met_or_not_met():
    cats = [{"id": "a", "name_en": "A", "definition": "d"}]
    def label(op, pl):
        return ai.ClassificationOut(candidates=[ai.CandidateOut(root_cause_id="a", reason="r", confidence=0.9)])
    ok = rca.relabel([{"id": str(i), "text": "t", "expert": "a"} for i in range(200)], cats, ["request"], call=label)
    assert ok["status"] == "met" and ok["agreement"] == 1.0
    bad = rca.relabel([{"id": str(i), "text": "t", "expert": "a" if i < 160 else "b"} for i in range(200)], cats + [{"id": "b", "name_en": "B", "definition": "d"}], ["request"], call=label)
    assert bad["status"] == "not_met" and bad["agreement"] == 0.8


def test_whole_flow_through_the_api(client):
    assert client.get("/api/rca", headers=EMP).status_code == 403
    first = client.get("/api/rca", headers=ADMIN).json()
    assert first["themes"] is None and first["proposal"] is None and first["targets"]["records"] == 200
    assert client.post("/api/rca/proposal", headers=ADMIN, json={}).status_code == 409        # themes first
    conn = db.connect()
    rows = conn.execute("SELECT id FROM complaints LIMIT 7").fetchall()
    for r, t in zip(rows, TEXTS):
        conn.execute("UPDATE complaints SET root_cause='other', other_reason=? WHERE id=?", (t, r["id"]))
    conn.commit(); conn.close()
    th = client.post("/api/rca/themes", headers=ADMIN, json={"min_theme_size": 2})
    assert th.status_code == 200 and th.json()["n_themes"] >= 3
    prop = client.post("/api/rca/proposal", headers=ADMIN, json={"max_categories": 8}).json()
    assert prop["review"]["state"] == "draft" and prop["version"].startswith("v1-proposal-")
    kwafie, naomi, maikel = owners(client)
    assert client.post("/api/rca/proposal/review", headers=ADMIN, json={"decision": "agree"}).status_code == 403
    for h in (kwafie, naomi):
        client.post("/api/rca/proposal/review", headers=h, json={"decision": "agree"})
    assert client.get("/api/rca", headers=ADMIN).json()["proposal"]["review"]["agreed"] == 2
    done = client.post("/api/rca/proposal/review", headers=maikel, json={"decision": "agree"}).json()
    assert done["review"]["state"] == "agreed" and done["review"]["agreed"] == 3
    new = client.post("/api/rca/proposal", headers=ADMIN, json={"max_categories": 4}).json()  # a different list needs fresh agreement
    assert new["review"]["agreed"] == 0 and new["content_hash"] != done["content_hash"]
