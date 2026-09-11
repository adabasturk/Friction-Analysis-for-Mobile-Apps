"""Load extracted review JSON from data/raw/ into SQLite.

Joins each review record with its app's studio/vertical/pair_id from
config/apps.json, drops reviews with an empty body, and flags short
(non-substantive) reviews without dropping them.

Idempotent: re-running upserts by review_id, so loading the same files
twice never creates duplicates.

Usage:
    python src/load_to_db.py
    python src/load_to_db.py --raw-dir data/raw --db data/friction.db
    python src/load_to_db.py --limit 2   # test on a couple of files
"""

import argparse
import json
import sys
from pathlib import Path

from tqdm import tqdm

from db import DB_PATH, get_connection, init_db

RAW_DIR = "data/raw"
APPS_FILE = "config/apps.json"
SUBSTANTIVE_MIN_CHARS = 10


def load_app_meta(apps_file):
    with open(apps_file) as f:
        apps = json.load(f)
    return {
        app["name"]: {
            "studio": app.get("studio"),
            "vertical": app.get("vertical"),
            "pair_id": app.get("pair_id"),
        }
        for app in apps
    }


def load_raw_files(raw_dir):
    return sorted(Path(raw_dir).glob("*.json"))


def upsert_review(conn, review, meta):
    body = (review.get("body") or "").strip()
    if not body:
        return "empty_body"

    char_count = len(body)
    is_substantive = 0 if char_count < SUBSTANTIVE_MIN_CHARS else 1

    conn.execute(
        """
        INSERT INTO reviews (
            review_id, app, studio, vertical, pair_id, country, rating,
            title, body, version, review_date, author, char_count,
            is_substantive
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(review_id) DO UPDATE SET
            app=excluded.app, studio=excluded.studio, vertical=excluded.vertical,
            pair_id=excluded.pair_id, country=excluded.country, rating=excluded.rating,
            title=excluded.title, body=excluded.body, version=excluded.version,
            review_date=excluded.review_date, author=excluded.author,
            char_count=excluded.char_count, is_substantive=excluded.is_substantive
        """,
        (
            review.get("review_id"),
            review.get("app"),
            meta["studio"],
            meta["vertical"],
            meta["pair_id"],
            review.get("country"),
            review.get("rating"),
            review.get("title"),
            body,
            review.get("version"),
            review.get("date"),
            review.get("author"),
            char_count,
            is_substantive,
        ),
    )
    return "loaded"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", default=RAW_DIR)
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--apps-file", default=APPS_FILE)
    parser.add_argument(
        "--limit", type=int, default=None, help="only process the first N raw files"
    )
    args = parser.parse_args()

    app_meta = load_app_meta(args.apps_file)

    files = load_raw_files(args.raw_dir)
    if args.limit:
        files = files[: args.limit]

    if not files:
        print(f"no raw files found in {args.raw_dir}; nothing to do")
        sys.exit(0)

    conn = get_connection(args.db)
    init_db(conn)

    loaded = 0
    empty_body = 0
    unknown_app = 0
    missing_review_id = 0

    for path in tqdm(files, desc="loading"):
        try:
            reviews = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  skipping {path}: {exc}")
            continue

        for review in reviews:
            if not review.get("review_id"):
                missing_review_id += 1
                continue

            meta = app_meta.get(review.get("app"))
            if meta is None:
                unknown_app += 1
                continue

            result = upsert_review(conn, review, meta)
            if result == "loaded":
                loaded += 1
            elif result == "empty_body":
                empty_body += 1

    conn.commit()
    conn.close()

    print(
        f"\ndone: {loaded} reviews loaded, {empty_body} dropped (empty body), "
        f"{unknown_app} skipped (app not in {args.apps_file}), "
        f"{missing_review_id} skipped (missing review_id)"
    )


if __name__ == "__main__":
    main()
