"""SQLite connection and schema for friction-atlas.

Usage:
    python src/db.py                    # create data/friction.db with the schema
    python src/db.py --db path/to.db    # use a different db file
"""

import argparse
import sqlite3
from pathlib import Path

DB_PATH = "data/friction.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    app TEXT NOT NULL,
    studio TEXT NOT NULL,
    vertical TEXT NOT NULL,
    pair_id TEXT NOT NULL,
    country TEXT NOT NULL,
    rating INTEGER,
    title TEXT,
    body TEXT,
    version TEXT,
    review_date TEXT,
    author TEXT,
    char_count INTEGER NOT NULL,
    is_substantive INTEGER NOT NULL DEFAULT 1
);

-- Populated by the Part 4 extraction script. That schema (friction_type,
-- moment, would_pay_signal, etc.) isn't defined yet, so this table carries
-- only the key for now.
CREATE TABLE IF NOT EXISTS extractions (
    review_id TEXT PRIMARY KEY REFERENCES reviews(review_id)
);

CREATE TABLE IF NOT EXISTS embeddings (
    review_id TEXT PRIMARY KEY REFERENCES reviews(review_id),
    vector BLOB
);
"""


def get_connection(db_path=DB_PATH):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    conn = get_connection(args.db)
    init_db(conn)
    conn.close()
    print(f"schema ready at {args.db}")


if __name__ == "__main__":
    main()
