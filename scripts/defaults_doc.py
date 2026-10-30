"""Write docs/DEFAULTS.md (FR-05: defaults documented per type) from config.json, or check that it is up to date.

    python -m scripts.defaults_doc           # rewrite docs/DEFAULTS.md
    python -m scripts.defaults_doc --check   # exit 1 when the file differs from config.json (a test runs this)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "DEFAULTS.md"
FIELDS = [("channel", "Channel"), ("priority", "Priority"), ("status", "Status"), ("owner_team", "Owner team"),
          ("response_target_days", "Response target (days)")]


def render(cfg: dict) -> str:
    defaults, types = cfg["defaults"], cfg["types"]
    meta = cfg["provisional_meta"]["defaults"]
    row = lambda name, d: "| " + " | ".join([name] + [str(d.get(k, "–")) for k, _ in FIELDS]) + " |"
    merged = lambda tid: {**defaults.get("_all", {}), **defaults.get(tid, {})}
    lines = [
        "# Defaults per complaint type (FR-05)",
        "",
        "Generated from `config.json` by `python -m scripts.defaults_doc`; a test fails when this file is out of date. Do not edit it by hand.",
        "",
        f"Status: **provisional**, to be confirmed by {meta['owner_to_confirm']} (last updated {meta['updated']}). "
        "The values come from the typical complaints. They are refined later with the 12 months of real data (see below).",
        "",
        "## The defaults",
        "",
        "| Complaint type | " + " | ".join(label for _, label in FIELDS) + " |",
        "|---|" + "---|" * len(FIELDS),
    ]
    lines += [row(f"{t['en']} (`{t['id']}`)", merged(t["id"])) for t in types]
    lines += [
        "",
        "Options: " + "; ".join(f"{k.replace('_', ' ')}: {', '.join(v)}" for k, v in cfg["field_options"].items()) + ".",
        "",
        "## When they apply",
        "",
        "- **Status and priority** apply as soon as the Review details step opens (the `_all` entry: "
        + ", ".join(f"{k} = {v}" for k, v in defaults.get("_all", {}).items()) + ").",
        "- **The rest** (owner team, response target and the type's own values) apply the moment a complaint type is chosen, "
        "or as soon as the assistant's suggested type is accepted. Choosing another type replaces the defaults that were not typed by hand.",
        "- **Never over a value the employee typed or edited.** Those stay, whatever the type.",
        "- **Channel follows how the complaint arrived**: "
        + " and ".join(f"**{v}** when started from {'a search (the customer is on the phone)' if k == 'search' else 'a pasted email'}"
                       for k, v in cfg.get("origin_defaults", {}).items())
        + ". The channel in the table is used only when the arrival is unknown (a direct API call).",
        "- Every default is shown with the label *Default*, and the response target is stored with the complaint.",
        "",
        "## Changing and refining them",
        "",
        "- Edit `defaults` in `config.json`, or an administrator calls `PUT /api/config/defaults` (a new version and an audit entry are written). "
        "Then run `python -m scripts.defaults_doc` to update this file.",
        "- `python -m scripts.field_profile --csv export.csv` reads the 12 months of real complaints (outside the app) and flags fields where "
        "one value covers at least 80% of the records: those are the default candidates.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    text = render(json.loads((ROOT / "config.json").read_text(encoding="utf-8")))
    if "--check" in sys.argv:
        ok = DOC.exists() and DOC.read_text(encoding="utf-8") == text
        print("docs/DEFAULTS.md is up to date" if ok else "docs/DEFAULTS.md is out of date: run python -m scripts.defaults_doc")
        return 0 if ok else 1
    DOC.write_text(text, encoding="utf-8")
    print(f"wrote {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
