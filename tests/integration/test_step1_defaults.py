"""Gap-analysis step 1: defaults and fields, prefill metric, richer seed, postcode search."""
from backend import db
from tests.conftest import ADMIN, EMP


def _candidate(client, q):
    r = client.get("/api/customers/search", params={"q": q}, headers=EMP).json()
    assert r["count"] == 1, r
    return r["candidates"][0]


def _prefill(client, c, **extra):
    return client.post("/api/prefill", headers=EMP,
                       json={"customer_id": c["customer_id"], "site_id": c["matched_site_id"], **extra}).json()["fields"]


def test_prefill_fills_most_recent_order_and_container(client):
    c = _candidate(client, "100009")              # two sites: the site is NOT guessed ...
    assert _prefill(client, c)["site_id"]["provenance"] == "blank"
    f = _prefill(client, c, site_id="C009-S1")    # ... but once chosen, order and container follow
    assert f["order_id"] == {"value": "C009-O10", "provenance": "prefilled"}
    assert f["container"] == {"value": "BOX-009-1", "provenance": "prefilled"}
    assert f["contract_id"]["provenance"] == "prefilled"
    assert f["status"] == {"value": "open", "provenance": "default"}   # applies before a type is known


def test_matched_order_wins_over_most_recent(client):
    c = _candidate(client, "ORD-002-10")
    assert _prefill(client, c)["order_id"]["value"] == "C002-O10"


def test_type_defaults_cover_every_defaulted_field(client):
    c = _candidate(client, "100021")              # single-site customer
    for ctype, expect in {"service": ("phone", "normal", "operations", "2"),
                          "billing": ("email", "normal", "customer_service", "5"),
                          "conduct": ("phone", "normal", "customer_service", "3")}.items():
        f = _prefill(client, c, complaint_type=ctype)
        got = tuple(f[k]["value"] for k in ("channel", "priority", "owner_team", "response_target_days"))
        assert got == expect
        assert all(f[k]["provenance"] == "default" for k in ("channel", "priority", "owner_team"))


def test_defaults_never_overwrite_typed_values(client):
    c = _candidate(client, "100021")
    typed = {"priority": {"value": "high", "provenance": "manual"}}
    f = _prefill(client, c, complaint_type="service", current_fields=typed)
    assert f["priority"] == {"value": "high", "provenance": "manual"}


def test_save_stores_defaulted_fields_and_container(client):
    c = _candidate(client, "ORD-002-10")
    body = {"customer_id": c["customer_id"], "site_id": c["matched_site_id"], "order_id": c["matched_order_id"],
            "channel": "phone", "complaint_type": "billing", "root_cause": "invoice", "description": "Charged twice."}
    saved = client.post("/api/complaints", headers=EMP, json=body).json()
    rec = client.get(f"/api/complaints/{saved['id']}", headers=EMP).json()
    assert (rec["priority"], rec["owner_team"], rec["response_target_days"], rec["status"]) == \
           ("normal", "customer_service", 5, "open")
    assert rec["container"] == "BOX-002-1"
    body["priority"] = "high"
    rec2 = client.get(f"/api/complaints/{client.post('/api/complaints', headers=EMP, json=body).json()['id']}",
                      headers=EMP).json()
    assert rec2["priority"] == "high"
    body["priority"] = "urgent!!"
    assert client.post("/api/complaints", headers=EMP, json=body).status_code == 422


def test_prefill_rate_counts_defaults_and_prefills(client):
    s = client.post("/api/sessions", headers=EMP, json={}).json()["session_id"]
    c = _candidate(client, "ORD-002-10")
    prov = {k: "prefilled" for k in ("customer_id", "site_id", "contract_id", "order_id", "container",
                                     "registration_date", "registering_user")}
    prov.update({k: "default" for k in ("channel", "priority", "status", "owner_team")})
    prov.update({"complaint_type": "suggested", "root_cause": "suggested", "description": "manual", "summary": "manual"})
    body = {"customer_id": c["customer_id"], "site_id": c["matched_site_id"], "order_id": c["matched_order_id"],
            "channel": "email", "complaint_type": "billing", "root_cause": "invoice", "description": "Charged twice.",
            "session_id": s, "field_provenance": prov}
    assert client.post("/api/complaints", headers=EMP, json=body).status_code == 201
    rate = client.get("/api/analytics/summary", headers=ADMIN).json()["fields"]["prefill_rate"]
    assert rate == {"value": round(11 / 15, 4), "n": 15}        # 11 of 15 >= the PRD target of 70%
    assert rate["value"] >= 0.70


def test_seed_history_size_and_other_share(client):
    with db.connect() as conn:
        n, other = conn.execute("SELECT count(*), sum(root_cause='other') FROM complaints WHERE is_seed=1").fetchone()
        assert n >= 40 and 0.30 <= other / n <= 0.45
        assert conn.execute("SELECT count(*) FROM complaints WHERE is_seed=1 AND root_cause='other' "
                            "AND coalesce(other_reason,'')=''").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM complaints WHERE is_seed=1 AND priority IS NULL").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM customers WHERE name LIKE 'Fictional%'").fetchone()[0] == 0


def test_postcode_search(client):
    r = client.get("/api/customers/search", params={"q": "1009 zz"}, headers=EMP).json()   # case/space-insensitive
    assert r["match_type"] == "postcode" and r["count"] == 1
    assert r["candidates"][0]["number"] == "100009" and r["candidates"][0]["matched_site_id"] == "C009-S1"
    assert client.get("/api/customers/search", params={"q": "1009"}, headers=EMP).json()["match_type"] == "postcode"
    assert client.get("/api/customers/search", params={"q": "9999ZZ"}, headers=EMP).json()["match_type"] == "none"
    assert client.get("/api/customers/search", params={"q": "999999"}, headers=EMP).json()["match_type"] == "none"
