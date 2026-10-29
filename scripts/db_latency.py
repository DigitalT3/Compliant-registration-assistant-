"""Measure the round trip to the configured database: run it here and on the host to see the difference.

    python -m scripts.db_latency            # from your laptop
    fly ssh console -a YOUR-APP -C "python -m scripts.db_latency"    # from the hosted backend

Reads only (SELECT 1). Prints the median of 12 round trips and the cost of opening a connection.
"""
import statistics
import time

from backend import db


def main() -> int:
    t = time.perf_counter()
    conn = db.connect()
    conn.execute("SELECT 1").fetchone()
    opened = (time.perf_counter() - t) * 1000
    times = []
    for _ in range(12):
        t = time.perf_counter()
        conn.execute("SELECT 1").fetchone()
        times.append((time.perf_counter() - t) * 1000)
    conn.close()
    print(f"database: {db.location()}")
    print(f"round trip: median {statistics.median(times):.1f} ms (min {min(times):.1f}, max {max(times):.1f})")
    print(f"open a new connection and run one query: {opened:.0f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
