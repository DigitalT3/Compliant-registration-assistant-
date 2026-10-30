"""Making an agreed proposed list the live cause list, with a way back.

Three safeguards:

* **Mapping.** Every old cause that is not in the new list stays on file as a *retired* cause that points to the new
  category that replaced it. Saved registrations keep their cause id, the screens still show its name, and the repeat rule
  sees the retired cause in its replacement's category, so earlier and later complaints still match.
* **Backup.** The list that was live is never overwritten: each change is a new version in ``config_versions`` and
  ``restore`` simply brings the previous one back (together with the agreements that were given to it).
* **Freeze.** While the list is frozen, or while someone is in the middle of a registration, it cannot be changed.
"""
import copy
import json

from .. import db
from ..dbutil import audit
from ..errors import ApiError
from ..settings import get_config, invalidate_config
from . import agreement, root_cause_analysis as rca, sessions as sessions_svc, taxonomy_review

KIND = "cause_list"
KEY_FREEZE = "taxonomy_freeze"


def _freeze(conn) -> dict:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (KEY_FREEZE,)).fetchone()
    return json.loads(row[0]) if row else {"frozen": False}


# PUBLIC_INTERFACE
def set_freeze(conn, user: dict, frozen: bool, note: str | None) -> dict:
    """Freeze or unfreeze the cause list (for example for the length of a user test)."""
    state = {"frozen": bool(frozen), "by": user["name"], "at": db.now(), "note": (note or "").strip()[:200] or None}
    conn.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (KEY_FREEZE, json.dumps(state, ensure_ascii=False)))
    audit(conn, user["id"], "taxonomy_frozen" if frozen else "taxonomy_unfrozen", {"note": state["note"]})
    conn.commit()
    return state


def _in_progress(conn) -> int:
    """Registrations somebody is working on right now (idle ones are first marked abandoned)."""
    sessions_svc.sweep_abandoned(conn)
    return conn.execute("SELECT count(*) FROM sessions WHERE status='active'").fetchone()[0]


def _majority_type(old: list):
    types = [c.get("type") for c in old if c.get("type")]
    return max(set(types), key=types.count) if types else None


def build_live(cfg: dict, proposal: dict) -> dict:
    """The live list, its categories and the retired causes that the proposal produces."""
    active_old = {c["id"]: c for c in cfg["root_causes"]}
    causes, cats = [], []
    for c in proposal["categories"]:
        covered = [active_old[e] for e in c["covers_existing"] if e in active_old]
        cid = c["id"]
        causes.append({"id": cid, "level1": cid, "level2": cid, "en": c["name_en"], "nl": c["name_nl"], "definition": c["definition"],
                       "examples": ", ".join(c["examples"]), "type": None if cid == "other" else _majority_type(covered)})
        cats.append({"id": cid, "en": c["name_en"], "nl": c["name_nl"]})
    new_by_id = {c["id"]: c for c in causes}
    target_of = {}                                                       # old cause id -> category id that replaces it
    for c in proposal["categories"]:
        for e in c["covers_existing"]:
            target_of[e] = c["id"]
    retired = []
    for old in cfg.get("retired_causes", []):                            # earlier retirements follow their replacement along
        to = target_of.get(old.get("merged_into"), old.get("merged_into"))
        if to in new_by_id and old["id"] not in new_by_id:
            retired.append({**old, "merged_into": to, "level1": new_by_id[to]["level1"], "level2": new_by_id[to]["level2"]})
    for oid, old in active_old.items():
        if oid in new_by_id:
            continue
        to = target_of.get(oid, "other" if "other" in new_by_id else causes[-1]["id"])
        retired.append({**old, "retired": True, "merged_into": to, "level1": new_by_id[to]["level1"], "level2": new_by_id[to]["level2"]})
    return {"root_causes": causes, "root_cause_categories": cats, "retired_causes": retired}


def _records_by_cause(conn) -> dict:
    return {r[0]: r[1] for r in conn.execute("SELECT root_cause, count(*) FROM complaints GROUP BY root_cause")}


def _history(conn) -> list:
    out = []
    for r in conn.execute("SELECT version, content, activated_at, active FROM config_versions WHERE kind=? ORDER BY id DESC", (KIND,)):
        c = json.loads(r["content"])
        out.append({"version": r["version"], "taxonomy_version": c.get("taxonomy_version"), "applied_at": r["activated_at"], "applied_by": c.get("applied_by"),
                    "from_proposal": c.get("from_proposal"), "active": bool(r["active"]), "n_causes": len(c.get("root_causes", []))})
    return out


# PUBLIC_INTERFACE
def state(conn) -> dict:
    """What the screen needs: can the proposal be applied, what stops it, what would change, and what can be restored."""
    cfg = get_config()
    prop = rca.proposal_state(conn)
    frozen = _freeze(conn)
    blockers = []
    if not prop:
        blockers.append("no_proposal")
    else:
        if prop["review"]["state"] != "agreed":
            blockers.append("not_agreed")
        if prop["content_hash"] == (cfg.get("applied_from") or {}).get("content_hash"):
            blockers.append("already_live")
    if frozen.get("frozen"):
        blockers.append("frozen")
    busy = _in_progress(conn)
    if busy:
        blockers.append("registration_in_progress")
    preview = None
    if prop:
        built = build_live(cfg, prop)
        counts = _records_by_cause(conn)
        live_ids = {c["id"] for c in built["root_causes"]}
        names = {c["id"]: c for c in cfg["root_causes"]}
        retired_ids = {c["id"] for c in built["retired_causes"] if c["id"] in names}
        preview = {"mapping": [{"old_id": c["id"], "old_name": c["en"], "new_id": c["merged_into"], "records": counts.get(c["id"], 0)}
                               for c in built["retired_causes"] if c["id"] in names],
                   "kept": [c["id"] for c in cfg["root_causes"] if c["id"] in live_ids], "n_live": len(live_ids),
                   "records_remapped": sum(counts.get(i, 0) for i in retired_ids)}
    history = _history(conn)
    return {"can_apply": not blockers, "blockers": blockers, "freeze": frozen, "in_progress": busy, "preview": preview, "history": history,
            "can_restore": any(h["active"] for h in history), "taxonomy_version": cfg["taxonomy_version"],
            "retired": cfg.get("retired_causes", [])}


def _guard(conn) -> None:
    if _freeze(conn).get("frozen"):
        raise ApiError(409, "list_frozen", "The cause list is frozen. Unfreeze it first.")
    if _in_progress(conn):
        raise ApiError(409, "registration_in_progress", "Somebody is registering a complaint right now. Try again when they have finished.")


# PUBLIC_INTERFACE
def apply(conn, user: dict, note: str | None) -> dict:
    """Make the agreed proposal the live list: a new version, the old causes retired with a mapping, the agreement carried over."""
    cfg = get_config()
    prop = rca.proposal_state(conn)
    if not prop:
        raise ApiError(409, "no_proposal", "There is no proposed list.")
    if prop["review"]["state"] != "agreed":
        raise ApiError(409, "not_agreed", "The proposed list has not been agreed by all the process owners.")
    if prop["content_hash"] == (cfg.get("applied_from") or {}).get("content_hash"):
        raise ApiError(409, "already_live", "This proposal is already the live list.")
    _guard(conn)
    built = build_live(cfg, prop)
    content = {**built, "taxonomy_version": f"live-{prop['version']}", "applied_by": user["name"], "applied_at": db.now(), "note": (note or "").strip()[:300] or None,
               "from_proposal": prop["version"], "applied_from": {"content_hash": prop["content_hash"], "version": prop["version"]},
               "replaced": {"taxonomy_version": cfg["taxonomy_version"], "n_causes": len(cfg["root_causes"])}}
    n = conn.execute("SELECT count(*) FROM config_versions WHERE kind=?", (KIND,)).fetchone()[0] + 1
    conn.execute("UPDATE config_versions SET active=0 WHERE kind=?", (KIND,))
    conn.execute("INSERT INTO config_versions(kind,version,content,activated_at,active) VALUES(?,?,?,?,1)",
                 (KIND, f"override-cause-list-{n}", json.dumps(content, sort_keys=True, ensure_ascii=False), db.now()))
    audit(conn, user["id"], "taxonomy_applied", {"proposal": prop["version"], "from": cfg["taxonomy_version"], "to": content["taxonomy_version"],
                                                  "retired": [c["id"] for c in built["retired_causes"]], "note": content["note"]})
    conn.commit()
    invalidate_config()
    new_cfg = get_config()                                             # the owners already agreed to exactly this list: carry that over
    agreement.carry_over(conn, rca.KEY_REVIEW, prop["content_hash"], taxonomy_review.KEY, taxonomy_review.content_hash(new_cfg),
                         f"Agreed as the proposed list {prop['version']}; applied by {user['name']}.")
    return state(conn)


# PUBLIC_INTERFACE
def restore(conn, user: dict, note: str | None) -> dict:
    """Bring the previous list back (the one that was live before the latest change, or the one in the file)."""
    row = conn.execute("SELECT id, version, content FROM config_versions WHERE kind=? AND active=1 ORDER BY id DESC LIMIT 1", (KIND,)).fetchone()
    if not row:
        raise ApiError(409, "nothing_to_restore", "The original list is already live.")
    _guard(conn)
    before = get_config()["taxonomy_version"]
    conn.execute("UPDATE config_versions SET active=0 WHERE id=?", (row["id"],))
    prev = conn.execute("SELECT id FROM config_versions WHERE kind=? AND id<? ORDER BY id DESC LIMIT 1", (KIND, row["id"])).fetchone()
    if prev:
        conn.execute("UPDATE config_versions SET active=1 WHERE id=?", (prev["id"],))
    audit(conn, user["id"], "taxonomy_restored", {"from": before, "removed": row["version"], "note": (note or "").strip()[:300] or None})
    conn.commit()
    invalidate_config()
    return state(conn)
