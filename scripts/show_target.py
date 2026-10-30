"""Print a saved complaint in the target field structure (FR-14), next to what the form stored.

    python -m scripts.show_target --url http://127.0.0.1:8001 --email you@example.nl --id COM-0001
    python -m scripts.show_target --url ... --email ... --last        # the newest complaint

Signs in with your own account (hidden password prompt, or CHECK_PASSWORD). Read-only.
"""
import argparse
import getpass
import json
import os
import sys

from scripts.requirements_check import Api


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8001")
    ap.add_argument("--email", required=True)
    ap.add_argument("--id")
    ap.add_argument("--last", action="store_true")
    a = ap.parse_args()
    api = Api(a.url)
    login, _ = api.call("POST", "/api/auth/login", {"email": a.email, "password": os.environ.get("CHECK_PASSWORD") or getpass.getpass("Password: ")})
    if not login.get("token") or login.get("must_change_password"):
        print("Sign-in failed or a password change is pending: sign in once in the browser first.")
        return 2
    api.token = login["token"]
    cid = a.id
    if a.last or not cid:
        items = api.call("GET", "/api/complaints", params={"page_size": 1, "include_seed": "false"})[0].get("items", [])
        if not items:
            print("No complaint registered yet.")
            return 1
        cid = items[0]["id"]
    t, _ = api.call("GET", f"/api/complaints/{cid}/target")
    if "record" not in t:
        print(t.get("error", t))
        return 1
    mapping, _ = api.call("GET", "/api/field-mapping")
    print(f"{cid} in the target field structure (names are placeholders: validated against the complaint system = {t['validated']})\n")
    for f in mapping["fields"]:
        v = t["record"][f["target_field"]]
        shown = v if isinstance(v, str) and v.isprintable() else json.dumps(v, ensure_ascii=False)     # line breaks and tabs shown as \n \t
        flag = "required" if f["required"] else "        "
        print(f"  {f['target_field']:34} {flag}  {str(shown)[:90]}")
    print(f"\nRequired fields empty: {t['missing_required'] or 'none'}")
    print(f"One-to-one with the stored columns: {mapping['one_to_one']} ({len(mapping['fields'])} mapped, {len(mapping['not_mapped'])} left out on purpose: {', '.join(mapping['not_mapped'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
