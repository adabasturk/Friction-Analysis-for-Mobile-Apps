"""Embed review bodies with Ollama's nomic-embed-text encoder.

This uses an encoder model, not the chat LLM, so it's fast in comparison
to the extraction step. Processes substantive reviews in batches of 100,
calling the local Ollama /api/embed endpoint once per batch, writing
vectors to the embeddings table after each batch (checkpoint), and
skipping reviews that already have an embedding so an interrupted run
resumes cleanly. Also exports the full embedding matrix to
data/embeddings.npy (with a parallel data/embeddings_ids.npy) once done.

Usage:
    python src/embed.py
    python src/embed.py --limit 200      # test run
    python src/embed.py --batch-size 50
"""

import argparse

import numpy as np
import requests
from tqdm import tqdm

from db import DB_PATH, get_connection

MODEL = "nomic-embed-text"
OLLAMA_HOST = "http://localhost:11434"
BATCH_SIZE = 100
EMBEDDINGS_NPY = "data/embeddings.npy"
EMBEDDINGS_IDS_NPY = "data/embeddings_ids.npy"


def fetch_pending(conn, limit=None):
    query = """
        SELECT r.review_id, r.body
        FROM reviews r
        LEFT JOIN embeddings e ON e.review_id = r.review_id
        WHERE r.is_substantive = 1 AND e.review_id IS NULL
        ORDER BY r.review_id
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    return conn.execute(query).fetchall()


def embed_batch(texts, host, timeout=120):
    resp = requests.post(
        f"{host}/api/embed", json={"model": MODEL, "input": texts}, timeout=timeout
    )
    resp.raise_for_status()
    return resp.json()["embeddings"]


def write_batch(conn, review_ids, vectors):
    rows = [
        (review_id, np.asarray(vec, dtype=np.float32).tobytes())
        for review_id, vec in zip(review_ids, vectors)
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO embeddings (review_id, vector) VALUES (?, ?)", rows
    )
    conn.commit()


def export_npy(conn):
    rows = conn.execute("SELECT review_id, vector FROM embeddings ORDER BY review_id").fetchall()
    if not rows:
        return
    ids = np.array([r[0] for r in rows])
    matrix = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
    np.save(EMBEDDINGS_NPY, matrix)
    np.save(EMBEDDINGS_IDS_NPY, ids)
    print(f"exported {matrix.shape[0]} vectors ({matrix.shape[1]}-dim) to {EMBEDDINGS_NPY}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="only embed the first N pending reviews — for test runs",
    )
    parser.add_argument("--host", default=OLLAMA_HOST)
    args = parser.parse_args()

    conn = get_connection(args.db)
    pending = fetch_pending(conn, args.limit)

    if not pending:
        print("nothing to embed — all substantive reviews already have vectors")
    else:
        failed = 0
        with tqdm(total=len(pending), desc="embedding") as pbar:
            for i in range(0, len(pending), args.batch_size):
                batch = pending[i : i + args.batch_size]
                review_ids = [r[0] for r in batch]
                texts = [r[1] for r in batch]
                try:
                    vectors = embed_batch(texts, args.host)
                except (requests.RequestException, KeyError, ValueError) as exc:
                    print(f"  batch starting at {review_ids[0]} failed: {exc}")
                    failed += len(batch)
                    pbar.update(len(batch))
                    continue

                write_batch(conn, review_ids, vectors)
                pbar.update(len(batch))

        print(f"\ndone: {len(pending) - failed} embedded, {failed} failed")

    export_npy(conn)
    conn.close()


if __name__ == "__main__":
    main()
