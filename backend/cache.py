"""A short-lived copy of heavy read-only answers (the dashboard figures).

On a hosted database every query costs a network round trip, and the dashboard needs about twenty of them.
The copy lives for a few seconds and is dropped as soon as anything is written, so a saved registration
shows up at once. It is per process and per database.
"""
import time

from . import db

_STORE: dict = {}
TTL_S = 30


def remember(key: tuple, compute):
    """Return the stored answer for ``key`` if it is fresh, else compute, store and return it."""
    full = (db.location(), key)
    hit = _STORE.get(full)
    if hit and time.monotonic() - hit[0] < TTL_S:
        return hit[1]
    value = compute()
    if len(_STORE) > 200:
        _STORE.clear()
    _STORE[full] = (time.monotonic(), value)
    return value


def clear() -> None:
    _STORE.clear()
