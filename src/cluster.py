"""KMeans clustering over review embeddings.

Without --k: fits KMeans for k in 8, 12, 16, 20 and prints a silhouette
score table so you can pick a cluster count.

With --k N: fits KMeans at that k and reports, per cluster, the review
count, average rating, per-app composition (so a cluster that's really
just one app dominating is visible), and the 5 reviews closest to the
centroid.

Usage:
    python src/cluster.py                # silhouette table only
    python src/cluster.py --k 12         # full per-cluster report
"""

import argparse
import textwrap

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize

from db import DB_PATH, get_connection

CANDIDATE_KS = [8, 12, 16, 20]
SILHOUETTE_SAMPLE = 3000
RANDOM_STATE = 42
CLOSEST_N = 5


def load_embeddings(conn):
    rows = conn.execute(
        """
        SELECT e.review_id, e.vector, r.app, r.rating, r.body
        FROM embeddings e
        JOIN reviews r ON r.review_id = e.review_id
        ORDER BY e.review_id
        """
    ).fetchall()
    if not rows:
        raise SystemExit("no embeddings found — run src/embed.py first")

    review_ids = [r[0] for r in rows]
    vectors = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
    apps = [r[2] for r in rows]
    ratings = [r[3] for r in rows]
    bodies = [r[4] for r in rows]
    return review_ids, vectors, apps, ratings, bodies


def fit_kmeans(X, k):
    return KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10).fit(X)


def print_silhouette_table(X):
    sample = min(SILHOUETTE_SAMPLE, X.shape[0])
    print(f"silhouette scores (sampled at n={sample}):\n")
    print(f"{'k':<6}{'silhouette':<12}")
    for k in CANDIDATE_KS:
        km = fit_kmeans(X, k)
        score = silhouette_score(X, km.labels_, sample_size=sample, random_state=RANDOM_STATE)
        print(f"{k:<6}{score:<12.4f}")
    print("\nrerun with --k N once you've picked a cluster count")


def print_cluster_report(X, k, apps, ratings, bodies):
    km = fit_kmeans(X, k)
    labels = km.labels_

    for cluster_id in range(k):
        idx = np.where(labels == cluster_id)[0]
        n = len(idx)
        cluster_ratings = [ratings[i] for i in idx if ratings[i] is not None]
        avg_rating = sum(cluster_ratings) / len(cluster_ratings) if cluster_ratings else float("nan")

        print(f"\n{'=' * 78}")
        print(f"cluster {cluster_id}: n={n}, avg_rating={avg_rating:.2f}")

        app_counts = {}
        for i in idx:
            app_counts[apps[i]] = app_counts.get(apps[i], 0) + 1

        print("  app composition:")
        for app, count in sorted(app_counts.items(), key=lambda item: -item[1]):
            pct = 100 * count / n
            dominant = "  <-- dominant" if pct >= 80 else ""
            print(f"    {app:<40} n={count:<5} ({pct:.0f}%){dominant}")

        centroid = km.cluster_centers_[cluster_id]
        dists = np.linalg.norm(X[idx] - centroid, axis=1)
        closest_local = np.argsort(dists)[:CLOSEST_N]

        print(f"  {CLOSEST_N} reviews closest to centroid:")
        for local_i in closest_local:
            i = idx[local_i]
            snippet = textwrap.shorten(bodies[i] or "", width=100, placeholder="...")
            print(f"    [{apps[i]}, rating={ratings[i]}] {snippet}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument(
        "--k",
        type=int,
        default=None,
        help="cluster count for the full report; omit to see the silhouette table",
    )
    args = parser.parse_args()

    conn = get_connection(args.db)
    review_ids, vectors, apps, ratings, bodies = load_embeddings(conn)
    conn.close()

    X = normalize(vectors)  # unit-normalize so Euclidean KMeans behaves like cosine

    print(f"{len(review_ids)} embedded reviews, {vectors.shape[1]}-dim vectors\n")

    if args.k is None:
        print_silhouette_table(X)
    else:
        print_cluster_report(X, args.k, apps, ratings, bodies)


if __name__ == "__main__":
    main()
