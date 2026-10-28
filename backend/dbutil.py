"""Small connection helper that always closes the SQLite connection."""
import json
from contextlib import contextmanager

from . import db


# PUBLIC_INTERFACE
@contextmanager
def connection():
    """Yield a foreign-key-enforcing connection and close it afterwards.

    Transactions are explicit: use ``with conn:`` (commit/rollback) in callers.
    """
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


# PUBLIC_INTERFACE
def audit(conn, actor: str, action: str, data=None) -> None:
    """Append an audit row (PoC audit trail; NOT tamper-proof or production-compliant)."""
    conn.execute("INSERT INTO audit(actor,action,at,data) VALUES(?,?,?,?)",
                 (actor, action, db.now(), json.dumps(data if data is not None else {}, default=str)))
