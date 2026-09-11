"""Resolve a studio's app portfolio from its iTunes publisher (artist) ID.

Fetches every app listed under the known Codeway and HubX publisher IDs and
writes them to output/portfolio.csv. Also supports a --search mode to look
up an app by name when it doesn't show up under either publisher — the app
likely sits under a second, unlisted publisher account, so this reports the
app's own artistId for follow-up.

Usage:
    python src/resolve_apps.py
    python src/resolve_apps.py --search "Reface"
"""

import argparse
import csv
import sys
import time

import requests

LOOKUP_URL = "https://itunes.apple.com/lookup"
SEARCH_URL = "https://itunes.apple.com/search"

# Known publisher (artist) IDs. A studio can own more than one publisher
# account; list all of them under the studio name they should be grouped as.
PUBLISHERS = {
    "Codeway": ["1503508447", "1833881740"],
    "HubX": ["1619331387", "1590841932"],
}

PORTFOLIO_FIELDS = [
    "trackId",
    "trackName",
    "primaryGenreName",
    "userRatingCount",
    "averageUserRating",
    "price",
    "releaseDate",
    "studio",
    "artistId",
]

OUTPUT_PATH = "output/portfolio.csv"


def fetch_publisher_apps(artist_id, country="us"):
    params = {
        "id": artist_id,
        "entity": "software",
        "limit": 200,
        "country": country,
    }
    try:
        resp = requests.get(LOOKUP_URL, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  lookup failed for artistId={artist_id}: {exc}", file=sys.stderr)
        return []

    try:
        results = resp.json().get("results", [])
    except ValueError:
        print(f"  invalid JSON for artistId={artist_id}", file=sys.stderr)
        return []

    # The lookup can include the artist record itself alongside its apps;
    # keep only actual software entries.
    return [r for r in results if r.get("kind") == "software"]


def search_apps(term, country="us"):
    params = {"term": term, "entity": "software", "country": country}
    try:
        resp = requests.get(SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"search failed for '{term}': {exc}", file=sys.stderr)
        return []

    try:
        return resp.json().get("results", [])
    except ValueError:
        print(f"invalid JSON for search '{term}'", file=sys.stderr)
        return []


def build_portfolio(country):
    rows = []
    for studio, artist_ids in PUBLISHERS.items():
        for artist_id in artist_ids:
            apps = fetch_publisher_apps(artist_id, country=country)
            print(f"{studio} (artistId={artist_id}): {len(apps)} apps")
            for app in apps:
                rows.append(
                    {
                        "trackId": app.get("trackId"),
                        "trackName": app.get("trackName"),
                        "primaryGenreName": app.get("primaryGenreName"),
                        "userRatingCount": app.get("userRatingCount") or 0,
                        "averageUserRating": app.get("averageUserRating"),
                        "price": app.get("price"),
                        "releaseDate": app.get("releaseDate"),
                        "studio": studio,
                        "artistId": artist_id,
                    }
                )
            time.sleep(1)

    rows.sort(key=lambda r: r["userRatingCount"], reverse=True)
    return rows


def write_portfolio(rows, path=OUTPUT_PATH):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PORTFOLIO_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} apps to {path}")


def print_search_results(term, country):
    results = search_apps(term, country=country)
    if not results:
        print(f"no results for '{term}'")
        return

    print(f"{len(results)} result(s) for '{term}':")
    for r in results:
        print(
            f"  artistId={r.get('artistId')}  artistName={r.get('artistName')!r}  "
            f"trackId={r.get('trackId')}  trackName={r.get('trackName')!r}  "
            f"genre={r.get('primaryGenreName')}"
        )
    print(
        "\nIf the studio you expected isn't the artistName above, this app "
        "likely sits under a second publisher account — add its artistId to "
        "PUBLISHERS in this script to pull that studio's full portfolio."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--search",
        metavar="NAME",
        help="search iTunes by app name instead of building the full "
        "portfolio; reports each match's artistId",
    )
    parser.add_argument(
        "--country", default="us", help="storefront country code (default: us)"
    )
    args = parser.parse_args()

    if args.search:
        print_search_results(args.search, args.country)
        return

    rows = build_portfolio(args.country)
    write_portfolio(rows)


if __name__ == "__main__":
    main()
