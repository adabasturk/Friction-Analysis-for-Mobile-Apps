"""Collect App Store reviews via Apple's public customer-reviews RSS feed.

For every (app, country) pair from config/apps.json x --countries, fetches
up to 10 pages (50 reviews/page, ~500 reviews max) and stores the extracted
reviews as data/raw/{app}_{country}.json. A file already existing on disk is
treated as "already collected" and skipped unless --force is passed, so an
interrupted run can simply be re-run to pick up where it left off.

Usage:
    python src/collect_reviews.py
    python src/collect_reviews.py --countries us,tr,gb --limit 5
    python src/collect_reviews.py --force
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from tqdm import tqdm

REVIEWS_URL_TEMPLATE = (
    "https://itunes.apple.com/{country}/rss/customerreviews/"
    "id={app_id}/sortBy=mostRecent/page={page}/json"
)

MAX_PAGES = 10
RAW_DIR = Path("data/raw")

DEFAULT_COUNTRIES = ["us", "gb", "tr", "de", "fr", "ca", "au", "in", "br", "mx"]


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def load_apps(path):
    with open(path) as f:
        apps = json.load(f)

    valid = []
    for app in apps:
        if not app.get("app_id"):
            print(f"skipping '{app.get('name')}': no app_id set in {path}")
            continue
        valid.append(app)
    return valid


def is_review_entry(entry):
    # The first entry on page 1 is the app's own info card, not a review —
    # it lacks both of these fields.
    return "author" in entry and "im:rating" in entry


def extract_review(entry, app_name, country):
    id_label = entry.get("id", {}).get("label", "")
    match = re.search(r"[?&]id=(\d+)", id_label)
    review_id = match.group(1) if match else (id_label or None)

    content = entry.get("content")
    if isinstance(content, list):
        body = next(
            (c.get("label") for c in content if c.get("attributes", {}).get("type") == "text"),
            content[0].get("label") if content else None,
        )
    elif isinstance(content, dict):
        body = content.get("label")
    else:
        body = None

    try:
        rating = int(entry["im:rating"]["label"])
    except (KeyError, TypeError, ValueError):
        rating = None

    return {
        "review_id": review_id,
        "app": app_name,
        "country": country,
        "rating": rating,
        "title": entry.get("title", {}).get("label"),
        "body": body,
        "version": entry.get("im:version", {}).get("label"),
        "date": entry.get("updated", {}).get("label"),
        "author": entry.get("author", {}).get("name", {}).get("label"),
    }


def fetch_page(app_id, country, page, timeout=15):
    url = REVIEWS_URL_TEMPLATE.format(country=country, app_id=app_id, page=page)
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        return None, f"network error: {exc}"

    if resp.status_code == 404:
        return None, "404 (not published in this country)"
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}"

    try:
        data = resp.json()
    except ValueError:
        return None, "invalid JSON (empty or non-JSON response)"

    entries = data.get("feed", {}).get("entry")
    if entries is None:
        return [], None  # valid feed, no reviews on this page
    if isinstance(entries, dict):
        entries = [entries]
    return entries, None


def collect_app_country(app, country, delay, force):
    app_name = app["name"]
    app_id = app["app_id"]
    raw_path = RAW_DIR / f"{slugify(app_name)}_{country}.json"

    if raw_path.exists() and not force:
        return {"status": "skipped", "reviews": 0, "malformed": 0}

    reviews = []
    malformed = 0

    for page in range(1, MAX_PAGES + 1):
        entries, error = fetch_page(app_id, country, page)
        time.sleep(delay)

        if error:
            print(f"  [{app_name}/{country}] page {page}: {error}")
            break
        if not entries:
            break  # ran out of reviews before hitting MAX_PAGES

        for entry in entries:
            if not is_review_entry(entry):
                continue
            parsed = extract_review(entry, app_name, country)
            if parsed["rating"] not in (1, 2, 3, 4, 5) or parsed["review_id"] is None:
                malformed += 1
                continue
            reviews.append(parsed)

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with open(raw_path, "w") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)

    return {"status": "collected", "reviews": len(reviews), "malformed": malformed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apps-file", default="config/apps.json")
    parser.add_argument(
        "--countries",
        default=",".join(DEFAULT_COUNTRIES),
        help="comma-separated storefront country codes",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="seconds to sleep after each HTTP request (default: 1.5)",
    )
    parser.add_argument(
        "--force", action="store_true", help="re-fetch and overwrite existing raw files"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="only process the first N (app, country) pairs — for test runs",
    )
    args = parser.parse_args()

    apps = load_apps(args.apps_file)
    if not apps:
        print(f"no apps with an app_id set in {args.apps_file}; nothing to do")
        sys.exit(0)

    countries = [c.strip() for c in args.countries.split(",") if c.strip()]
    pairs = [(app, country) for app in apps for country in countries]
    if args.limit:
        pairs = pairs[: args.limit]

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    skipped = 0
    empty = 0
    total_reviews = 0
    total_malformed = 0

    for app, country in tqdm(pairs, desc="collecting"):
        result = collect_app_country(app, country, args.delay, args.force)
        if result["status"] == "skipped":
            skipped += 1
            continue
        total_reviews += result["reviews"]
        total_malformed += result["malformed"]
        if result["reviews"] == 0:
            empty += 1

    print(
        f"\ndone: {len(pairs)} pairs — {skipped} skipped (already collected), "
        f"{empty} returned zero reviews, {total_reviews} reviews collected, "
        f"{total_malformed} malformed entries dropped"
    )


if __name__ == "__main__":
    main()
