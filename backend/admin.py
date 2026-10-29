"""Administrator commands that run in the operator's own terminal (never through the web app).

  python -m backend.admin create-admin --email you@company.nl --name "Your Name"
  python -m backend.admin set-password  --email you@company.nl

The password is typed at a hidden prompt. For automated test setups only, POC_ADMIN_PASSWORD supplies it
when there is no terminal. The command uses the database selected by POC_DB / DATABASE_URL (see README).
"""
import argparse
import getpass
import os
import sys

from . import db
from .dbutil import connection
from .errors import ApiError
from .services import accounts


def _password(confirm: bool) -> str:
    if not sys.stdin.isatty():
        pw = os.environ.get("POC_ADMIN_PASSWORD", "")
        if not pw:
            raise SystemExit("No terminal: set POC_ADMIN_PASSWORD (test setups only).")
        return pw
    pw = getpass.getpass("Password: ")
    if confirm and pw != getpass.getpass("Repeat password: "):
        raise SystemExit("The passwords do not match.")
    return pw


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-admin", help="create the first (or another) administrator account")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    s = sub.add_parser("set-password", help="set a new password for an existing account and unlock it")
    s.add_argument("--email", required=True)
    args = ap.parse_args(argv)
    db.initialize()
    try:
        with connection() as conn:
            if args.cmd == "create-admin":
                uid = accounts.create_account(conn, None, args.name, args.email, _password(True), None, "admin",
                                              must_change=False)
                print(f"Administrator created: {args.email} ({uid}). Sign in on the sign-in screen.")
            else:
                row = conn.execute("SELECT id FROM users WHERE lower(email)=?", (args.email.strip().lower(),)).fetchone()
                if not row:
                    raise SystemExit("No account with that e-mail address.")
                pw = _password(True)
                accounts._check_password(pw, args.email)
                conn.execute("UPDATE users SET password_hash=?, must_change_password=0, failed_logins=0, "
                             "locked_until=NULL WHERE id=?", (accounts.hash_password(pw), row["id"]))
                accounts.audit(conn, row["id"], "password_set_by_operator", {})
                conn.commit()
                print("Password updated. Older sessions for this account are now invalid.")
    except ApiError as e:
        raise SystemExit(e.message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
