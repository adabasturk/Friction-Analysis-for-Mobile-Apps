"""Print a summary of the reviews loaded into SQLite.

Reports total reviews, per-app and per-country distributions, average
rating, each app's review-date range and reviews/day, and count/rating
balance within each matched pair — including a flag when a pair's
review-date windows differ by more than 3x (see CLAUDE.md's temporal
comparability note).

Usage:
    python src/stats.py
    python src/stats.py --db data/friction.db
"""

import argparse
from datetime import datetime

from db import DB_PATH, get_connection

MIN_RELIABLE_N = 30


def parse_date(s):
    return datetime.fromisoformat(s)


def fmt_avg(value):
    return f"{value:.2f}" if value is not None else "n/a"


def flag(n):
    return " (n<30, low confidence)" if n < MIN_RELIABLE_N else ""


def print_totals(conn):
    total = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    substantive = conn.execute(
        "SELECT COUNT(*) FROM reviews WHERE is_substantive = 1"
    ).fetchone()[0]
    avg_rating = conn.execute("SELECT AVG(rating) FROM reviews").fetchone()[0]

    print(f"total reviews: {total} ({substantive} substantive, n={total})")
    print(f"average rating: {fmt_avg(avg_rating)} (n={total})")


def print_distribution(conn, column, label):
    rows = conn.execute(
        f"SELECT {column}, COUNT(*) AS n, AVG(rating) AS avg_rating "
        f"FROM reviews GROUP BY {column} ORDER BY n DESC"
    ).fetchall()
    print(f"\n{label} distribution:")
    for value, n, avg_rating in rows:
        print(f"  {value:<40} n={n:<5} avg_rating={fmt_avg(avg_rating)}{flag(n)}")


def print_date_ranges(conn):
    rows = conn.execute(
        "SELECT app, COUNT(*) AS n, MIN(review_date) AS min_d, MAX(review_date) AS max_d "
        "FROM reviews GROUP BY app ORDER BY app"
    ).fetchall()
    print("\ndate range per app:")
    spans = {}
    for app, n, min_d, max_d in rows:
        if not min_d or not max_d:
            print(f"  {app:<40} n={n:<5} no valid dates")
            continue
        span_days = max(1, (parse_date(max_d) - parse_date(min_d)).days)
        rate = n / span_days
        spans[app] = span_days
        print(
            f"  {app:<40} n={n:<5} {min_d[:10]} to {max_d[:10]} "
            f"({span_days}d, {rate:.2f} reviews/day){flag(n)}"
        )
    return spans


def print_pair_balance(conn, spans):
    pairs = conn.execute("SELECT DISTINCT pair_id FROM reviews ORDER BY pair_id").fetchall()
    print("\nbalance within each pair:")
    for (pair_id,) in pairs:
        rows = conn.execute(
            "SELECT app, studio, COUNT(*) AS n, AVG(rating) AS avg_rating "
            "FROM reviews WHERE pair_id = ? GROUP BY app, studio",
            (pair_id,),
        ).fetchall()
        print(f"  pair '{pair_id}':")
        for app, studio, n, avg_rating in rows:
            print(f"    {app} ({studio}): n={n}, avg_rating={fmt_avg(avg_rating)}{flag(n)}")

        pair_spans = [spans[app] for app, _, _, _ in rows if app in spans]
        if len(pair_spans) == 2:
            ratio = max(pair_spans) / min(pair_spans)
            warning = " -- exceeds 3x, NOT comparable per CLAUDE.md" if ratio > 3 else ""
            print(f"    review-window ratio: {ratio:.2f}x{warning}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    conn = get_connection(args.db)

    print_totals(conn)
    print_distribution(conn, "app", "per-app")
    print_distribution(conn, "country", "per-country")
    spans = print_date_ranges(conn)
    print_pair_balance(conn, spans)

    conn.close()


if __name__ == "__main__":
    main()
