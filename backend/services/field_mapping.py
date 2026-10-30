"""The PoC complaint record in the field structure of the target complaint system (FR-14).

``backend/field_mapping.json`` lists, for every stored complaint column, either the target field it maps to (one-to-one) or
the reason it is not part of the complaint record (technical or test bookkeeping). ``check`` proves the two lists together
cover every stored column exactly once; ``to_target`` / ``from_target`` convert a stored record both ways without loss.
The target names are placeholders: the complaint-system owner's field list is still to come.
"""
import json
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / "field_mapping.json"


# PUBLIC_INTERFACE
def load() -> dict:
    """The mapping file as a dict."""
    return json.loads(FILE.read_text(encoding="utf-8"))


# PUBLIC_INTERFACE
def check(columns: list, mapping: dict | None = None) -> list:
    """Problems that stop the mapping from being one-to-one over ``columns`` (empty list = it is)."""
    m = mapping or load()
    poc = [f["poc_field"] for f in m["fields"]]
    target = [f["target_field"] for f in m["fields"]]
    bad = []
    bad += [f"PoC field mapped twice: {x}" for x in sorted({p for p in poc if poc.count(p) > 1})]
    bad += [f"target field used twice: {x}" for x in sorted({t for t in target if target.count(t) > 1})]
    bad += [f"mapped but not stored: {x}" for x in poc if x not in columns]
    bad += [f"stored but neither mapped nor excluded: {x}" for x in columns if x not in poc and x not in m["not_mapped"]]
    bad += [f"both mapped and excluded: {x}" for x in poc if x in m["not_mapped"]]
    return bad


# PUBLIC_INTERFACE
def to_target(record: dict, mapping: dict | None = None) -> dict:
    """The stored complaint (as the API returns it) with target field names, in the order of the field list."""
    m = mapping or load()
    return {f["target_field"]: record.get(f["poc_field"]) for f in m["fields"]}


# PUBLIC_INTERFACE
def from_target(target: dict, mapping: dict | None = None) -> dict:
    """The inverse of ``to_target``: back to the stored field names."""
    m = mapping or load()
    return {f["poc_field"]: target[f["target_field"]] for f in m["fields"]}


# PUBLIC_INTERFACE
def missing_required(target: dict, mapping: dict | None = None) -> list:
    """Required target fields that are empty (None or blank text)."""
    m = mapping or load()
    return [f["target_field"] for f in m["fields"]
            if f["required"] and (target.get(f["target_field"]) is None or str(target[f["target_field"]]).strip() == "")]
