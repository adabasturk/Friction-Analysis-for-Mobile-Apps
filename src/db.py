"""SQLite connection and schema for friction-atlas.

Usage:
    python src/db.py                       # create data/friction.db with the schema
    python src/db.py --db path/to.db       # use a different db file
    python src/db.py --reset-extractions   # DROP and recreate extractions with the full v2 schema
"""

import argparse
import sqlite3
from pathlib import Path

DB_PATH = "data/friction.db"

# Full Part 4 (v2) schema for extractions. Used both by SCHEMA (fresh installs
# get every column immediately) and by reset_extractions() (rebuilding an
# existing table from scratch). Kept as its own string so the two never drift.
EXTRACTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS extractions (
    review_id TEXT PRIMARY KEY REFERENCES reviews(review_id),
    friction_type TEXT,
    trigger_moment TEXT,
    mentions_price INTEGER,
    price_mentioned TEXT,
    paid_but_still_limited INTEGER,
    would_pay_signal TEXT,
    feature_praised TEXT,
    gist TEXT,
    cluster_id INTEGER,
    in_estimation_frame INTEGER DEFAULT 0,
    in_discovery_frame INTEGER DEFAULT 0,
    selection_weight REAL,
    model_name TEXT,
    prompt_version TEXT,
    extracted_at TEXT,
    elapsed_sec REAL,
    validation_status TEXT,
    raw_output TEXT
);
"""

# Columns an existing (pre-v2) extractions table might be missing. Used by
# migrate_extractions() to backfill an old table in place, without touching
# rows already extracted. Must stay in sync with EXTRACTIONS_TABLE above.
EXTRACTION_COLUMNS = {
    "friction_type": "TEXT",
    "trigger_moment": "TEXT",
    "mentions_price": "INTEGER",
    "price_mentioned": "TEXT",
    "paid_but_still_limited": "INTEGER",
    "would_pay_signal": "TEXT",
    "feature_praised": "TEXT",
    "gist": "TEXT",
    "cluster_id": "INTEGER",
    "in_estimation_frame": "INTEGER DEFAULT 0",
    "in_discovery_frame": "INTEGER DEFAULT 0",
    "selection_weight": "REAL",
    "model_name": "TEXT",
    "prompt_version": "TEXT",
    "extracted_at": "TEXT",
    "elapsed_sec": "REAL",
    "validation_status": "TEXT",
    "raw_output": "TEXT",
}

EXTRACTIONS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_extractions_estimation_frame ON extractions(in_estimation_frame);
CREATE INDEX IF NOT EXISTS idx_extractions_friction_type ON extractions(friction_type);
"""

SCHEMA = f"""
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

{EXTRACTIONS_TABLE}

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


def migrate_extractions(conn):
    """Add any missing Part 4 columns to an existing extractions table, then
    ensure its indexes exist. Idempotent: columns already present are left
    untouched, so already-extracted rows survive a re-run. Indexes are
    created after the column backfill so CREATE INDEX never runs against a
    column that doesn't exist yet."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(extractions)")}
    added = []
    for col, coltype in EXTRACTION_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE extractions ADD COLUMN {col} {coltype}")
            added.append(col)
    conn.commit()

    conn.executescript(EXTRACTIONS_INDEXES)
    conn.commit()

    if added:
        print(f"migrated extractions table, added columns: {', '.join(added)}")
    else:
        print("extractions table already up to date")


def reset_extractions(conn):
    """DROP and recreate extractions with the full v2 schema. Does not touch
    reviews or embeddings. Only call this when you intend to discard
    whatever is currently in extractions."""
    conn.execute("DROP TABLE IF EXISTS extractions")
    conn.executescript(EXTRACTIONS_TABLE)
    conn.executescript(EXTRACTIONS_INDEXES)
    conn.commit()
    print("extractions table dropped and recreated with the full v2 schema")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument(
        "--reset-extractions",
        action="store_true",
        help="DROP and recreate extractions with the full v2 schema (reviews and embeddings untouched)",
    )
    args = parser.parse_args()

    conn = get_connection(args.db)
    init_db(conn)

    if args.reset_extractions:
        reset_extractions(conn)
    else:
        migrate_extractions(conn)

    conn.close()
    print(f"schema ready at {args.db}")


if __name__ == "__main__":
    main()
