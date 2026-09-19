"""Part 4 LLM extraction: friction_type, trigger_moment, would_pay_signal, etc.

Reads review_ids pre-registered by src/sample.py — the extractions table
already has cluster_id / in_estimation_frame / in_discovery_frame /
selection_weight for every selected review. This script only fills in the
LLM fields, and only for rows where extracted_at is still NULL, so an
interrupted run resumes automatically without redoing finished rows.

Usage:
    python src/extract.py --selftest          # regression check for the prompt-echo bug, no DB needed
    python src/extract.py --limit 20
    python src/extract.py --limit 5 --debug   # print raw model output + why validation failed
    python src/extract.py --frame estimation
    caffeinate -i python src/extract.py --frame all
"""

import argparse
import json
import time
from datetime import datetime, timezone

import requests
from tqdm import tqdm

from db import DB_PATH, get_connection, init_db, migrate_extractions

OLLAMA_HOST = "http://localhost:11434"
MODEL = "gemma3:4b"
PROMPT_VERSION = "v2"
CHECKPOINT_EVERY = 25

FRICTION_TYPES = {
    "paywall_timing",
    "price_level",
    "subscription_trap",
    "free_quota_limit",
    "referral_gate",
    "quality_gap",
    "onboarding_confusion",
    "performance",
    "none",
}
TRIGGER_MOMENTS = {
    "before_first_use",
    "after_first_result",
    "after_free_quota",
    "at_export",
    "unclear",
    "none",
}
WOULD_PAY_SIGNALS = {"yes", "no", "conditional", "unclear"}

# Concrete example values (e.g. "9.99/week") got copy-pasted verbatim by the
# model into unrelated reviews that never mentioned a price — a French 5-star
# review with no price came back with trigger_moment/price_mentioned lifted
# straight from the example. Every value below is a non-literal placeholder
# for exactly that reason: nothing here should ever be a valid answer to
# echo. Allowed values are listed separately underneath.
PROMPT_TEMPLATE = """You are extracting structured facts from a single app store review. Output ONLY valid JSON, no extra keys, no commentary, in exactly this shape:

{{
  "friction_type": "<exactly one value from the friction_type list below>",
  "trigger_moment": "<exactly one value from the trigger_moment list below>",
  "mentions_price": <true or false>,
  "price_mentioned": "<price text exactly as it appears in the review, or null>",
  "paid_but_still_limited": <true or false>,
  "would_pay_signal": "<exactly one value from the would_pay_signal list below>",
  "feature_praised": "<feature the review praises, or null>",
  "gist": "<at most 12 words, in English>"
}}

Rules:
- For friction_type, choose EXACTLY ONE value from its allowed list below. Never combine values, never use "|".
- For trigger_moment, choose EXACTLY ONE value from its allowed list below.
- price_mentioned must be a price that literally appears in the review's text. If the review contains no number, write null. Never invent a price.
- If the review is short or ambiguous, choose "none" for friction_type. Do not guess.
- Base every field on the review's actual text. Do not write a value that has no basis in what the review says.
- If price_mentioned or feature_praised has no value, write JSON null (not the text "null" in quotes).
- gist is always in English, at most 12 words, regardless of the review's language.

friction_type allowed values:
- paywall_timing
- price_level
- subscription_trap
- free_quota_limit
- referral_gate
- quality_gap
- onboarding_confusion
- performance
- none

trigger_moment allowed values:
- before_first_use
- after_first_result
- after_free_quota
- at_export
- unclear (there is friction, but the moment it happened is not clear)
- none (use this when friction_type is "none" — no friction means no trigger moment)

would_pay_signal allowed values:
- yes
- no
- conditional
- unclear

Review (Apple star rating: {rating}/5):
\"\"\"{body}\"\"\"

JSON:"""

RETRY_TEMPLATE = """Your previous answer for this review did not match the required schema.

Previous answer:
{previous}

Problem: {reason}

Fix the JSON so it matches the schema exactly, then output ONLY the corrected JSON — no commentary.

Review (Apple star rating: {rating}/5):
\"\"\"{body}\"\"\"

Corrected JSON:"""


def build_prompt(rating, body):
    return PROMPT_TEMPLATE.format(rating=rating, body=body)


def build_retry_prompt(rating, body, previous, reason):
    return RETRY_TEMPLATE.format(rating=rating, body=body, previous=previous, reason=reason)


def validate(record):
    """Returns None if record passes, else a string naming which field
    failed and why (missing / wrong type / enum mismatch) — surfaced by
    --debug and, on final failure, not stored (only the raw text is)."""
    if not isinstance(record, dict):
        return f"top-level JSON is not an object (got {type(record).__name__})"

    if "friction_type" not in record:
        return "missing field: friction_type"
    if record["friction_type"] not in FRICTION_TYPES:
        return f"friction_type: invalid enum value {record['friction_type']!r}"

    if "trigger_moment" not in record:
        return "missing field: trigger_moment"
    if record["trigger_moment"] not in TRIGGER_MOMENTS:
        return f"trigger_moment: invalid enum value {record['trigger_moment']!r}"

    if "mentions_price" not in record:
        return "missing field: mentions_price"
    if not isinstance(record["mentions_price"], bool):
        return f"mentions_price: not a boolean (got {record['mentions_price']!r})"

    if "paid_but_still_limited" not in record:
        return "missing field: paid_but_still_limited"
    if not isinstance(record["paid_but_still_limited"], bool):
        return f"paid_but_still_limited: not a boolean (got {record['paid_but_still_limited']!r})"

    if "would_pay_signal" not in record:
        return "missing field: would_pay_signal"
    if record["would_pay_signal"] not in WOULD_PAY_SIGNALS:
        return f"would_pay_signal: invalid enum value {record['would_pay_signal']!r}"

    if "gist" not in record:
        return "missing field: gist"
    if not isinstance(record["gist"], str) or not record["gist"]:
        return f"gist: not a non-empty string (got {record['gist']!r})"

    return None


def check_ollama_health(host):
    """Fail fast with a clear error if Ollama isn't reachable, instead of
    burning a whole batch run retrying against a dead endpoint."""
    try:
        resp = requests.get(f"{host}/api/tags", timeout=5)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"error: Ollama not reachable at {host} ({exc}) — start Ollama and retry")
        raise SystemExit(1)


def call_ollama(prompt, host):
    resp = requests.post(
        f"{host}/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "keep_alive": "30m",
            "options": {"num_ctx": 2048, "num_predict": 256, "temperature": 0},
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", ""), data.get("model", MODEL)


def parse(raw):
    """Returns (record, None) on success, or (None, reason) on failure —
    reason is either a JSON parse error or whatever validate() reports."""
    try:
        record = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        return None, f"JSON parse error: {exc}"
    reason = validate(record)
    if reason:
        return None, reason
    return record, None


def extract_one(rating, body, host, review_id=None, debug=False):
    prompt = build_prompt(rating, body)

    raw, model_name = call_ollama(prompt, host)
    if debug:
        tqdm.write(f"  [{review_id}] raw (attempt 1): {raw!r}")
    record, reason = parse(raw)
    if record is not None:
        return record, model_name, "valid", None
    if debug:
        tqdm.write(f"  [{review_id}] invalid (attempt 1): {reason}")

    # temperature=0 means re-sending the same prompt gets the same wrong
    # answer — tell the model what it got wrong instead of asking again blind.
    retry_prompt = build_retry_prompt(rating, body, raw, reason)
    raw, model_name = call_ollama(retry_prompt, host)
    if debug:
        tqdm.write(f"  [{review_id}] raw (retry): {raw!r}")
    record, reason = parse(raw)
    if record is not None:
        return record, model_name, "valid", None
    if debug:
        tqdm.write(f"  [{review_id}] invalid (retry): {reason}")

    return None, model_name, "invalid", raw


# Neither review has a price in its text, so price_mentioned must come back
# null on both — and friction_type must not come back as the old prompt
# example's value. Those two are CRITICAL: a model that's copying the
# example instead of reading the review reproduces exactly those values.
# friction_type/would_pay_signal expectations below are informational: a
# genuine reading-comprehension miss on an ambiguous review, not the bug
# this test exists to catch.
PROMPT_ECHO_FRICTION_TYPE = "subscription_trap"  # old example's value

SELFTEST_CASES = [
    {
        "rating": 5,
        "body": "Surpris par cette appli",
        "info_expect": {"friction_type": "none"},
    },
    {
        "rating": 5,
        # "そのうち" = "eventually/at some point" — a deferral, not a yes.
        "body": "そのうち課金したいです",
        "info_expect": {"would_pay_signal": "conditional"},
    },
]


def run_selftest(host):
    print("self-test: checks the model reads the review instead of echoing the prompt's example\n")
    critical_ok = True
    for case in SELFTEST_CASES:
        record, model_name, status, raw_output = extract_one(
            case["rating"], case["body"], host, review_id=f"selftest:{case['body']!r}", debug=True
        )
        print(f"review: {case['body']!r} (rating {case['rating']})")
        print(f"  status: {status}")

        if status != "valid":
            print(f"  CRITICAL: extraction failed, raw={raw_output!r}\n")
            critical_ok = False
            continue

        print(f"  record: {record}")

        price_mentioned = record.get("price_mentioned")
        price_ok = price_mentioned is None
        critical_ok = critical_ok and price_ok
        flag = "" if price_ok else "  <-- CRITICAL: expected null, review has no price"
        print(f"  price_mentioned: {price_mentioned!r}{flag}")

        friction_type = record.get("friction_type")
        echo_ok = friction_type != PROMPT_ECHO_FRICTION_TYPE
        critical_ok = critical_ok and echo_ok
        flag = "" if echo_ok else "  <-- CRITICAL: matches the old example's value, looks like an echo"
        print(f"  friction_type: {friction_type!r}{flag}")

        for field, expected in case.get("info_expect", {}).items():
            actual = record.get(field)
            note = "" if actual == expected else f"  (info: expected {expected!r})"
            print(f"  {field}: {actual!r}{note}")
        print()

    if critical_ok:
        print("critical checks passed — no prompt echo detected")
    else:
        print("DO NOT RUN — critical check failed, the model appears to be echoing the prompt's example")
    return critical_ok


def fetch_pending(conn, frame, limit):
    where = "e.extracted_at IS NULL"
    if frame == "estimation":
        where += " AND e.in_estimation_frame = 1"
    elif frame == "discovery":
        where += " AND e.in_discovery_frame = 1"

    query = f"""
        SELECT e.review_id, r.rating, r.body
        FROM extractions e
        JOIN reviews r ON r.review_id = e.review_id
        WHERE {where}
        ORDER BY e.review_id
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    return conn.execute(query).fetchall()


def save_result(conn, review_id, record, model_name, elapsed, status, raw_output=None):
    now = datetime.now(timezone.utc).isoformat()
    if record:
        conn.execute(
            """
            UPDATE extractions SET
                friction_type=?, trigger_moment=?, mentions_price=?, price_mentioned=?,
                paid_but_still_limited=?, would_pay_signal=?, feature_praised=?, gist=?,
                model_name=?, prompt_version=?, extracted_at=?, elapsed_sec=?, validation_status=?,
                raw_output=NULL
            WHERE review_id=?
            """,
            (
                record.get("friction_type"),
                record.get("trigger_moment"),
                int(bool(record.get("mentions_price"))),
                record.get("price_mentioned"),
                int(bool(record.get("paid_but_still_limited"))),
                record.get("would_pay_signal"),
                record.get("feature_praised"),
                record.get("gist"),
                model_name,
                PROMPT_VERSION,
                now,
                elapsed,
                status,
                review_id,
            ),
        )
    else:
        # invalid: keep the model's raw text so failures are debuggable later
        # without needing --debug to have been on during the run.
        conn.execute(
            """
            UPDATE extractions SET
                model_name=?, prompt_version=?, extracted_at=?, elapsed_sec=?, validation_status=?,
                raw_output=?
            WHERE review_id=?
            """,
            (model_name, PROMPT_VERSION, now, elapsed, status, raw_output, review_id),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--host", default=OLLAMA_HOST)
    parser.add_argument("--limit", type=int, default=None, help="only process the first N pending reviews")
    parser.add_argument(
        "--frame",
        choices=["estimation", "discovery", "all"],
        default="all",
        help="which frame's pending rows to process (default: all)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="print each record's raw model output and, on failure, why validation rejected it",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run two fixed regression cases for the prompt-echo bug and exit (no DB access)",
    )
    args = parser.parse_args()

    check_ollama_health(args.host)

    if args.selftest:
        passed = run_selftest(args.host)
        raise SystemExit(0 if passed else 1)

    conn = get_connection(args.db)
    init_db(conn)
    migrate_extractions(conn)

    pending = fetch_pending(conn, args.frame, args.limit)
    if not pending:
        print("nothing to extract — all selected reviews already processed (or none sampled: run src/sample.py first)")
        conn.close()
        return

    print(f"{len(pending)} reviews to extract (frame={args.frame}, model={MODEL})\n")

    invalid_count = 0
    network_error_count = 0
    consecutive_network_errors = 0
    durations = []

    pbar = tqdm(pending, desc="extracting")
    for i, (review_id, rating, body) in enumerate(pbar, start=1):
        start = time.monotonic()
        raw_output = None
        try:
            record, model_name, status, raw_output = extract_one(
                rating, body or "", args.host, review_id=review_id, debug=args.debug
            )
        except requests.RequestException as exc:
            network_error_count += 1
            consecutive_network_errors += 1
            tqdm.write(
                f"  network error on {review_id}: {exc} — leaving extracted_at NULL "
                f"for retry ({consecutive_network_errors}/5 consecutive)"
            )
            if consecutive_network_errors >= 5:
                tqdm.write("Ollama unreachable — 5 consecutive network errors, stopping run")
                conn.commit()
                conn.close()
                raise SystemExit(1)
            continue

        consecutive_network_errors = 0
        elapsed = time.monotonic() - start
        durations.append(elapsed)

        if status == "invalid":
            invalid_count += 1
            tqdm.write(f"  invalid output for {review_id}, validation_status=invalid")

        save_result(conn, review_id, record, model_name, elapsed, status, raw_output=raw_output)

        if i % CHECKPOINT_EVERY == 0:
            conn.commit()

        if durations:
            avg = sum(durations) / len(durations)
            remaining_min = (len(pending) - i) * avg / 60
            pbar.set_postfix(sec_per_record=f"{avg:.1f}", eta_min=f"{remaining_min:.1f}")

    conn.commit()
    conn.close()

    processed = len(durations)
    avg = sum(durations) / processed if processed else 0.0
    pct = f" ({100 * invalid_count / processed:.1f}%)" if processed else ""
    print(f"\ndone: {processed} processed, {invalid_count} invalid{pct}")
    if processed:
        print(f"avg {avg:.1f} sec/record")
    if network_error_count:
        print(f"{network_error_count} network errors — left for retry (extracted_at still NULL)")


if __name__ == "__main__":
    main()
