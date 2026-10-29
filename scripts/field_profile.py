"""Field profile: how often each field is filled and how its values are spread (PoC time sink 2).

Many fields are typed by hand although the answer is nearly always the same. This script finds them: for every
field it prints the fill-rate, the number of distinct values, the most common value and its share, and flags a
field as a default candidate when one value covers at least 80 % of the filled records.

    # a CSV export of complaints (Renewi's history, or any export with one column per field)
    python -m scripts.field_profile --csv export.csv --date-column created --months 12 --out profile.csv

    # the PoC's own complaints (the database the app is configured for)
    python -m scripts.field_profile --poc [--source poc|seed|all]

It runs outside the app and changes nothing. Identifier columns (too many different values) and free-text or personal-detail
columns are never given a default candidate and their values are never printed, so the report is safe to share.
"""
import argparse
import csv
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

MISSING = {"", "null", "none", "n/a", "na", "nan", "-", "–", "—"}
DAYS_PER_MONTH = 30.4375
# PoC columns worth profiling; free text (description, summary) is left out on purpose.
# Columns that hold free text or personal details: profiled for fill-rate, but their values are never printed.
FREE_TEXT_HINTS = ("description", "text", "summary", "comment", "note", "reason", "name", "email", "phone", "address", "remark")
LONG_VALUE = 40                      # a value longer than this is text, not a choice
POC_FIELDS = ["channel", "priority", "owner_team", "complaint_type", "root_cause", "root_cause_category", "language",
              "status", "response_target_days", "site_id", "contract_id", "order_id", "container", "other_reason"]


def is_missing(value) -> bool:
    """True for empty cells and the usual placeholders (null, n/a, -)."""
    return value is None or str(value).strip().casefold() in MISSING


def parse_date(text) -> datetime | None:
    """Parse ISO dates/times and the common day-first formats; ``None`` when it cannot be read."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        d = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        d = None
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M"):
            try:
                d = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if d is not None and d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def read_csv(path: str) -> tuple[list, list]:
    """Return (header, rows) from a CSV file; the delimiter (comma, semicolon or tab) is detected."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        text = fh.read()
    if not text.strip():
        raise SystemExit(f"{path} is empty.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(text.splitlines(), dialect=dialect)
    rows = [dict(r) for r in reader]
    return list(reader.fieldnames or []), rows


def read_poc(source: str) -> tuple[list, list]:
    """Return (header, rows) from the PoC's complaints. ``source``: poc (saved in the app), seed (synthetic history), all."""
    from backend import db

    with db.connect() as conn:
        have = db.columns(conn, "complaints")
        cols = [c for c in POC_FIELDS if c in have]
        where = {"poc": "WHERE is_seed=0", "seed": "WHERE is_seed=1", "all": ""}[source]
        rows = [dict(r) for r in conn.execute(f"SELECT created,{','.join(cols)} FROM complaints {where}")]
    return ["created"] + cols, rows


def window(rows: list, date_column: str | None, months: float | None, as_of: str | None = None) -> tuple[list, dict]:
    """Keep the records of the last ``months`` months (counted back from the newest record, or ``as_of``)."""
    info = {"months_requested": months, "unreadable_dates": 0, "first": None, "last": None, "covered_months": None}
    if not date_column:
        return rows, info
    dated = [(parse_date(r.get(date_column)), r) for r in rows]
    info["unreadable_dates"] = sum(d is None for d, _ in dated)
    dated = [(d, r) for d, r in dated if d is not None]
    if not dated:
        return [], info
    end = parse_date(as_of) if as_of else max(d for d, _ in dated)
    start = end - timedelta(days=months * DAYS_PER_MONTH) if months else min(d for d, _ in dated)
    kept = [(d, r) for d, r in dated if start <= d <= end]
    if kept:
        info["first"], info["last"] = min(d for d, _ in kept), max(d for d, _ in kept)
        info["covered_months"] = round((info["last"] - info["first"]).days / DAYS_PER_MONTH, 1)
    return [r for _, r in kept], info


def profile(rows: list, fields: list, threshold: float = 0.8, min_n: int = 10, varied_share: float = 0.5) -> list:
    """Fill-rate and value spread per field.

    ``flag`` is ``default candidate`` (one value covers ``threshold`` of the filled records), ``varied`` (so many
    different values that it is an identifier), ``free text`` (a text or personal-detail column, or long values),
    ``too few records``, ``empty`` or blank. Values of ``varied`` and ``free text`` fields are never shown.
    """
    out = []
    for field in fields:
        values = [str(r.get(field)).strip() for r in rows if not is_missing(r.get(field))]
        filled = len(values)
        counts = Counter(v.casefold() for v in values)
        shown = {}
        for v in values:
            shown.setdefault(v.casefold(), v)                  # one spelling per value, as first seen
        row = {"field": field, "records": len(rows), "filled": filled,
               "fill_rate": round(filled / len(rows), 4) if rows else None, "distinct": len(counts),
               "top_value": "", "top_count": 0, "top_share": None, "flag": ""}
        if not filled:
            row["flag"] = "empty"
        else:
            key, n = counts.most_common(1)[0]
            row.update(top_value=shown[key], top_count=n, top_share=round(n / filled, 4))
            if any(h in field.casefold() for h in FREE_TEXT_HINTS) or len(shown[key]) > LONG_VALUE:
                row.update(flag="free text", top_value="(hidden)")
            elif len(counts) > 20 and len(counts) / filled > varied_share:
                row.update(flag="varied", top_value="(varied)")
            elif filled < min_n:
                row["flag"] = "too few records"
            elif n / filled >= threshold:
                row["flag"] = "default candidate"
        out.append(row)
    return out


def pct(x) -> str:
    return "–" if x is None else f"{x * 100:.0f}%"


def render(table: list) -> str:
    """Aligned plain-text table."""
    head = ["field", "records", "filled", "fill", "distinct", "most common value", "share", "flag"]
    body = [[t["field"], str(t["records"]), str(t["filled"]), pct(t["fill_rate"]), str(t["distinct"]),
             t["top_value"], pct(t["top_share"]), t["flag"]] for t in table]
    widths = [max(len(r[i]) for r in [head] + body) for i in range(len(head))]
    line = lambda r: "  ".join(c.ljust(widths[i]) for i, c in enumerate(r)).rstrip()
    return "\n".join([line(head), line(["-" * w for w in widths])] + [line(r) for r in body])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", help="CSV export of complaints (one column per field)")
    src.add_argument("--poc", action="store_true", help="profile the PoC's own complaints")
    ap.add_argument("--source", choices=["poc", "seed", "all"], default="all", help="with --poc: saved in the app, synthetic history, or both")
    ap.add_argument("--fields", help="comma-separated columns to profile (default: all, except the date column)")
    ap.add_argument("--date-column", help="column with the complaint date (CSV default: none; --poc uses 'created')")
    ap.add_argument("--months", type=float, help="only the last N months (needs a date column)")
    ap.add_argument("--as-of", help="end of the window (default: the newest record)")
    ap.add_argument("--threshold", type=float, default=0.8, help="share of one value that makes a default candidate (default 0.8)")
    ap.add_argument("--min-n", type=int, default=10, help="fewer filled records than this are not judged (default 10)")
    ap.add_argument("--out", help="also write the table to this CSV file")
    args = ap.parse_args(argv)

    if args.poc:
        header, rows = read_poc(args.source)
        date_column = args.date_column or "created"
        label = f"PoC complaints ({args.source})"
    else:
        header, rows = read_csv(args.csv)
        date_column, label = args.date_column, args.csv
    if args.months and not date_column:
        raise SystemExit("--months needs --date-column.")
    if date_column and date_column not in header:
        raise SystemExit(f"Column '{date_column}' not found. Columns: {', '.join(header)}")
    fields = [f.strip() for f in args.fields.split(",")] if args.fields else [h for h in header if h != date_column]
    missing = [f for f in fields if f not in header]
    if missing:
        raise SystemExit(f"Unknown column(s): {', '.join(missing)}. Columns: {', '.join(header)}")

    rows, info = window(rows, date_column, args.months, args.as_of)
    table = profile(rows, fields, args.threshold, args.min_n)

    print(f"Field profile: {label}: {len(rows)} records")
    if info["first"]:
        print(f"Period: {info['first']:%Y-%m-%d} to {info['last']:%Y-%m-%d} ({info['covered_months']} months)")
    if args.months and info["covered_months"] is not None and info["covered_months"] < args.months * 0.9:
        print(f"WARNING: the data covers {info['covered_months']} months, not the {args.months:g} asked for.")
    if info["unreadable_dates"]:
        print(f"WARNING: {info['unreadable_dates']} record(s) have no readable date and were left out.")
    print()
    print(render(table))
    cands = [t["field"] for t in table if t["flag"] == "default candidate"]
    print(f"\nDefault candidates (one value covers >= {args.threshold * 100:.0f}% of the filled records): "
          f"{', '.join(cands) if cands else 'none'}")
    print("A candidate is a starting point for a default; the process owner decides whether the common value is right.")
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(table[0]) if table else ["field"])
            w.writeheader()
            w.writerows(table)
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
