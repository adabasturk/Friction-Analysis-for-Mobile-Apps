"""Part 4 sample selection. NO LLM calls — cleaning + selection only.

Order matters: filter (keyboard-mash) -> sample (frames A/B) -> weight.
Running this twice is safe: the keyboard-mash filter only ever looks at
rows still flagged is_substantive=1, and the extractions upsert only
touches the sampling columns (cluster_id, in_*_frame, selection_weight),
so it never clobbers friction_type etc. once src/extract.py has run.

Cluster labels are read from reviews.cluster_id, written by
`python src/cluster.py --k 12 --save`. Run that first — if any embedded
review is missing a cluster_id, this script refuses to sample rather than
guess.

Usage:
    python src/sample.py
    python src/sample.py --db data/friction.db --out output/sample.csv
"""

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

from db import DB_PATH, get_connection, init_db, migrate_extractions

SEED = 42

KEYBOARD_MASH_UNIQUE_RATIO = 0.35
KEYBOARD_MASH_VOWEL_RATIO = 0.2
VOWELS = set("aeiou")

ESTIMATION_PER_APP = 150
BAND_MIN = 15
BANDS = ["1-2", "3", "4-5"]

CLUSTER5_TARGET = 250
CLUSTER10_TARGET = 100
LANGUAGE_CLUSTERS = [0, 2, 3, 4, 8]
LANGUAGE_CLUSTER_CAP = 30

KEYWORDS_LATIN = {
    "TR": ["abonelik", "ücret", "pahalı", "iptal", "deneme", "para"],
    "DE": ["teuer", "abo", "kündigen", "kostenlos"],
    "PT": ["caro", "assinatura", "cancelar", "grátis"],
    "FR": ["cher", "abonnement", "résilier", "gratuit"],
    "EN": ["subscription", "paywall", "price", "expensive", "trial", "refund", "cancel"],
}
KEYWORDS_JP = ["解約", "課金", "高い", "サブスク"]

# Ranges checked to keep the keyboard-mash filter off non-Latin scripts
# (Japanese reviews legitimately have no spaces; don't cut them).
NON_LATIN_RANGES = [
    (0x0400, 0x04FF),  # cyrillic
    (0x0600, 0x06FF),  # arabic
    (0x0900, 0x097F),  # devanagari
    (0x3040, 0x30FF),  # hiragana + katakana
    (0x3400, 0x4DBF),  # CJK ext A
    (0x4E00, 0x9FFF),  # CJK unified ideographs
    (0xAC00, 0xD7A3),  # hangul
]


def is_latin_script(text):
    for ch in text:
        cp = ord(ch)
        for lo, hi in NON_LATIN_RANGES:
            if lo <= cp <= hi:
                return False
    return True


def is_keyboard_mash(body):
    text = (body or "").strip()
    if not text or " " in text or not is_latin_script(text):
        return False
    lower = text.lower()
    unique_ratio = len(set(lower)) / len(lower)
    vowel_ratio = sum(1 for c in lower if c in VOWELS) / len(lower)
    return unique_ratio < KEYBOARD_MASH_UNIQUE_RATIO and vowel_ratio < KEYBOARD_MASH_VOWEL_RATIO


def matches_keywords(body):
    lower = (body or "").lower()
    if any(kw in lower for kw_list in KEYWORDS_LATIN.values() for kw in kw_list):
        return True
    raw = body or ""
    return any(kw in raw for kw in KEYWORDS_JP)  # no \b: Japanese has no word boundaries


def load_cluster_assignments(conn):
    """cluster_id per review, for every review that has an embedding (i.e.
    was substantive when src/embed.py ran). Raises if src/cluster.py --save
    hasn't been run, or hasn't been re-run after new embeddings landed."""
    rows = conn.execute(
        """
        SELECT r.review_id, r.cluster_id
        FROM reviews r
        JOIN embeddings e ON e.review_id = r.review_id
        """
    ).fetchall()
    missing = [rid for rid, cid in rows if cid is None]
    if missing:
        raise SystemExit(
            f"{len(missing)} embedded reviews have no cluster_id in reviews — "
            "run `python src/cluster.py --k 12 --save` first"
        )
    return {rid: cid for rid, cid in rows}


def apply_keyboard_mash_filter(conn, cluster_of):
    rows = conn.execute("SELECT review_id, body FROM reviews WHERE is_substantive = 1").fetchall()
    dropped = [review_id for review_id, body in rows if is_keyboard_mash(body)]

    if dropped:
        conn.executemany(
            "UPDATE reviews SET is_substantive = 0 WHERE review_id = ?",
            [(rid,) for rid in dropped],
        )
        conn.commit()

    by_cluster = defaultdict(int)
    for rid in dropped:
        by_cluster[cluster_of.get(rid, "unknown")] += 1

    print(f"keyboard-mash filter: {len(dropped)} records flagged is_substantive=0 (not deleted)")
    for cid, n in sorted(by_cluster.items(), key=lambda kv: -kv[1]):
        print(f"  cluster {cid}: {n}")
    print()


def rating_band(rating):
    if rating is None:
        return None
    if rating <= 2:
        return "1-2"
    if rating == 3:
        return "3"
    return "4-5"


def allocate_strata(pop_by_band, target, min_n):
    """Proportional allocation with a floor of min_n per non-empty band,
    capped at each band's population, adjusted to sum exactly to target."""
    bands = list(pop_by_band)
    total_pop = sum(pop_by_band.values())
    if total_pop == 0:
        return {b: 0 for b in bands}

    alloc = {}
    for b in bands:
        pop = pop_by_band[b]
        effective_min = min(min_n, pop)
        proportional = round(target * pop / total_pop)
        alloc[b] = min(pop, max(effective_min, proportional))

    diff = target - sum(alloc.values())
    while diff > 0:
        candidates = [b for b in bands if alloc[b] < pop_by_band[b]]
        if not candidates:
            break
        b = max(candidates, key=lambda x: pop_by_band[x] - alloc[x])
        alloc[b] += 1
        diff -= 1
    while diff < 0:
        candidates = [b for b in bands if alloc[b] > 0]
        if not candidates:
            break
        b = max(candidates, key=lambda x: alloc[x])
        alloc[b] -= 1
        diff += 1
    return alloc


def build_frame_a(conn):
    rows = conn.execute(
        "SELECT review_id, app, rating FROM reviews WHERE is_substantive = 1 AND rating IS NOT NULL"
    ).fetchall()
    null_rating_n = conn.execute(
        "SELECT COUNT(*) FROM reviews WHERE is_substantive = 1 AND rating IS NULL"
    ).fetchone()[0]
    if null_rating_n:
        print(f"note: {null_rating_n} substantive reviews have no rating, excluded from frame A\n")

    by_app_band = defaultdict(list)
    for review_id, app, rating in rows:
        by_app_band[(app, rating_band(rating))].append(review_id)

    apps = sorted({app for app, _band in by_app_band})
    selection = {}
    report_rows = []

    for app in apps:
        pop_by_band = {b: len(by_app_band.get((app, b), [])) for b in BANDS}
        alloc = allocate_strata(pop_by_band, ESTIMATION_PER_APP, BAND_MIN)
        app_total = 0
        for band in BANDS:
            pop_ids = by_app_band.get((app, band), [])
            n_sample = alloc[band]
            chosen = random.Random(SEED).sample(pop_ids, n_sample) if n_sample else []
            weight = len(pop_ids) / n_sample if n_sample else None
            for rid in chosen:
                selection[rid] = {"selection_weight": weight}
            report_rows.append((app, band, len(pop_ids), n_sample, weight))
            app_total += n_sample
        if app_total < ESTIMATION_PER_APP:
            print(f"note: {app} only reached {app_total}/{ESTIMATION_PER_APP} (population exhausted)")

    print("frame A (estimation) — per app x rating band:")
    print(f"  {'app':<45}{'band':<8}{'pop':<8}{'n':<6}{'weight':<8}")
    for app, band, pop, n, weight in report_rows:
        w = f"{weight:.2f}" if weight else "-"
        print(f"  {app:<45}{band:<8}{pop:<8}{n:<6}{w:<8}")
    print(f"  total frame A: {len(selection)}\n")

    return selection


def build_frame_b(conn, cluster_of):
    substantive_ids = {rid for (rid,) in conn.execute("SELECT review_id FROM reviews WHERE is_substantive = 1")}
    body_of = dict(conn.execute("SELECT review_id, body FROM reviews"))

    by_cluster = defaultdict(list)
    for rid, cid in cluster_of.items():
        if rid in substantive_ids:
            by_cluster[cid].append(rid)

    selection = {}
    report_rows = []

    def add(rid):
        selection.setdefault(rid, True)

    pop5 = by_cluster.get(5, [])
    chosen5 = random.Random(SEED).sample(pop5, min(CLUSTER5_TARGET, len(pop5)))
    for rid in chosen5:
        add(rid)
    report_rows.append(("cluster 5", len(pop5), len(chosen5)))

    pop10 = by_cluster.get(10, [])
    chosen10 = random.Random(SEED).sample(pop10, min(CLUSTER10_TARGET, len(pop10)))
    for rid in chosen10:
        add(rid)
    report_rows.append(("cluster 10", len(pop10), len(chosen10)))

    for cid in LANGUAGE_CLUSTERS:
        pop = by_cluster.get(cid, [])
        matches = [rid for rid in pop if matches_keywords(body_of.get(rid, ""))]
        chosen = random.Random(SEED).sample(matches, min(LANGUAGE_CLUSTER_CAP, len(matches)))
        for rid in chosen:
            add(rid)
        report_rows.append((f"cluster {cid} (keyword)", len(matches), len(chosen)))

    print("frame B (discovery) — per source:")
    print(f"  {'source':<28}{'match_pop':<12}{'n':<6}")
    for source, pop, n in report_rows:
        print(f"  {source:<28}{pop:<12}{n:<6}")
    print(f"  total frame B (unique): {len(selection)}\n")

    return selection


def merge_frames(frame_a, frame_b):
    merged = {}
    for rid, info in frame_a.items():
        merged[rid] = {
            "in_estimation_frame": 1,
            "in_discovery_frame": 0,
            "selection_weight": info["selection_weight"],
        }
    for rid in frame_b:
        if rid in merged:
            merged[rid]["in_discovery_frame"] = 1
        else:
            merged[rid] = {"in_estimation_frame": 0, "in_discovery_frame": 1, "selection_weight": None}
    return merged


def write_selection(conn, merged, cluster_of):
    conn.executemany(
        """
        INSERT INTO extractions (review_id, cluster_id, in_estimation_frame, in_discovery_frame, selection_weight)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(review_id) DO UPDATE SET
            cluster_id=excluded.cluster_id,
            in_estimation_frame=excluded.in_estimation_frame,
            in_discovery_frame=excluded.in_discovery_frame,
            selection_weight=excluded.selection_weight
        """,
        [
            (rid, cluster_of.get(rid), info["in_estimation_frame"], info["in_discovery_frame"], info["selection_weight"])
            for rid, info in merged.items()
        ],
    )
    conn.commit()


def write_csv(path, merged, conn, cluster_of):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    meta = {rid: (app, rating) for rid, app, rating in conn.execute("SELECT review_id, app, rating FROM reviews")}
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["review_id", "app", "rating", "cluster_id", "in_estimation_frame", "in_discovery_frame", "selection_weight"]
        )
        for rid in sorted(merged):
            info = merged[rid]
            app, rating = meta.get(rid, (None, None))
            writer.writerow(
                [rid, app, rating, cluster_of.get(rid), info["in_estimation_frame"], info["in_discovery_frame"], info["selection_weight"]]
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--out", default="output/sample.csv")
    args = parser.parse_args()

    conn = get_connection(args.db)
    init_db(conn)
    migrate_extractions(conn)

    cluster_of = load_cluster_assignments(conn)

    apply_keyboard_mash_filter(conn, cluster_of)

    frame_a = build_frame_a(conn)
    frame_b = build_frame_b(conn, cluster_of)
    merged = merge_frames(frame_a, frame_b)

    overlap = sum(1 for v in merged.values() if v["in_estimation_frame"] and v["in_discovery_frame"])
    print(f"overlap (selected by both frames): {overlap}")
    print(f"total unique reviews selected: {len(merged)}\n")

    write_selection(conn, merged, cluster_of)
    write_csv(args.out, merged, conn, cluster_of)
    print(f"selection written to {args.out} and to the extractions table")

    conn.close()


if __name__ == "__main__":
    main()
