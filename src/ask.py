"""Part 5 hybrid query layer.

answer(question) is the whole system: it classifies the question as AGGREGATE
(a number/rate/ranking — resolved with generated SQL) or QUALITATIVE (what
users say — resolved with embedding search + synthesis), and returns a
structured result. It takes no input/output beyond that — no printing, no
argparse — so a future Flask app can import and call it exactly as the CLI
below does.

The CLI at the bottom is a thin wrapper: call answer(), print the result.
All the logic that matters lives above it.

Usage:
    python src/ask.py "kaç yorum topladın?"
    python src/ask.py --debug "Nova'nın paywall şikayeti oranı nedir?"
"""

import argparse
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import requests

from db import DB_PATH, get_connection
from extract import FRICTION_TYPES, TRIGGER_MOMENTS, WOULD_PAY_SIGNALS

OLLAMA_HOST = "http://localhost:11434"
CHAT_MODEL = "gemma3:4b"
EMBED_MODEL = "nomic-embed-text"

QUALITATIVE_TOP_K = 15
MIN_MATCHES_WARN = 5

# Calibrated against probe questions run on this exact corpus, not guessed:
# on-topic questions (about prices/cancellation, in Turkish and English) scored
# nearest-neighbor cosine 0.72-0.83; generic off-topic questions in a language
# NOT dominant in the corpus ("who is the CEO of Codeway", a pizza recipe)
# scored 0.54-0.59. 0.65 sits in that gap.
# KNOWN GAP, left open rather than hidden: an off-topic question phrased in a
# language the corpus is heavy in (Turkish makes up a large share of reviews)
# can still score ~0.70 on nearest neighbor, because nomic-embed-text encodes
# language before topic (see PLAN.md's clustering-by-language finding). This
# threshold does not catch that case — the printed country distribution is
# what makes it visible instead: a lopsided distribution is the tell.
MIN_TOP1_SIMILARITY_DEFAULT = 0.65

# Two-tier threshold: a country filter already narrows the pool by metadata
# before similarity runs at all, so most off-topic content is excluded by
# construction - the semantic score doesn't have to do that work alone, and
# doesn't need to be held to the same bar. Observed directly: "Japon
# kullanıcılar iptal hakkında ne diyor" scored top1=0.63 against a
# country=jp-filtered, 465-record pool (a real, on-topic match - it just
# fell a hair under 0.65) versus 0.54-0.59 for genuinely off-topic questions
# with NO filter applied. 0.58 sits above the off-topic range and below the
# observed on-topic-but-filtered score.
MIN_TOP1_SIMILARITY_COUNTRY_FILTERED = 0.58

FORBIDDEN_SQL_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|DETACH|CREATE|REPLACE|PRAGMA|VACUUM|REINDEX|TRIGGER)\b",
    re.IGNORECASE,
)

# Heuristic for "this SQL computes a rate/proportion": a division between two
# aggregates, or a result column explicitly named like a rate. Not perfect,
# but it only has one job — catch the canonical mistake (an unweighted count
# ratio with no frame filter) before it runs.
RATIO_HINT_RE = re.compile(
    r"/\s*SUM\s*\(|/\s*COUNT\s*\(|\)\s*/\s*\(|AS\s+\w*(rate|pct|percentage|oran|yuzde)\w*",
    re.IGNORECASE,
)

LOW_N_THRESHOLD = 30

# reviews has no language column — country is the only proxy available, and
# a rough one (a "de" review can be written in Turkish by a Turkish tourist,
# etc.). Used two ways below: (1) as the always-shown "language distribution"
# on every qualitative answer, and (2) here, to let a question that names a
# country pre-filter the embedding search pool instead of relying on the
# question's own language matching the reviews it's asking about. This is a
# known, load-bearing limitation for PART 8's Sınırlılıklar section, not an
# incidental detail.
#
# Plain dictionary lookup, no LLM call. Split into three tiers, because a
# single matching rule got this wrong: "Brezilyalı" (Brazilian, with the
# Turkish "-lı" suffix) didn't match bare "brezilya" under a \bword\b rule,
# the same class of bug as AGGREGATE_PREFIX_KEYWORDS below ("oranı" vs
# "oran"). Turkish demonyms/place names take suffixes with no apostrophe
# ("Brezilyalı", "Hintli", "Amerikalı"), so those are PREFIX matched.
# Bare ISO codes ("tr", "br", "fr"...) are kept as strict whole-word
# matches instead - prefix-matching a 2-letter code would fire inside
# ordinary words ("travel", "bring", "true").
COUNTRY_STEMS = {
    "jp": ["japon", "japan"],
    "br": ["brezilya", "brazil"],
    "de": ["alman", "german", "germany"],
    "fr": ["fransız", "french", "france"],
    "tr": ["türk", "turkish", "turkey"],
    "in": ["hint", "hindistan", "indian", "india"],
    "gb": ["ingiliz", "ingiltere", "british", "britain"],
    "us": ["abd", "amerika", "american"],
}

# Deliberately excludes bare "de" (Turkish "de/da" = "too"), "in" (English
# preposition), "us" (English pronoun) - real collisions, not oversights.
COUNTRY_CODES = {
    "jp": ["jp"],
    "br": ["br"],
    "fr": ["fr"],
    "tr": ["tr"],
    "gb": ["gb", "uk"],
}

COUNTRY_PHRASES = {
    "gb": ["united kingdom"],
    "us": ["united states"],
}


def _normalize_for_match(text):
    # .lower() alone mishandles Turkish İ/I (İ -> "i̇" with a combining dot,
    # not plain "i"), which would silently break matches like "İngiliz".
    return text.replace("İ", "i").replace("I", "i").lower()


def detect_countries(question):
    """Country codes named in the question, by plain keyword lookup (no LLM
    call). Can return more than one code if the question names more than
    one country — the caller treats that as ambiguous and skips filtering."""
    normalized = _normalize_for_match(question)
    matched = set()
    for code, stems in COUNTRY_STEMS.items():
        if any(re.search(rf"\b{re.escape(stem)}", normalized) for stem in stems):
            matched.add(code)
    for code, codes in COUNTRY_CODES.items():
        if any(re.search(rf"\b{re.escape(c)}\b", normalized) for c in codes):
            matched.add(code)
    for code, phrases in COUNTRY_PHRASES.items():
        if any(p in normalized for p in phrases):
            matched.add(code)
    return matched


def _enum_list(values):
    return ", ".join(sorted(values))


SCHEMA_TEXT = f"""Database: SQLite, two relevant tables.

TABLE reviews — every collected review (9,432 rows), not just the sampled ones.
  review_id TEXT PRIMARY KEY
  app TEXT      -- one of: 'Chat AI: Ask Agent Anything', 'AI Chatbot - Nova',
                 --         'Retake AI Face & Selfie Editor', 'ReShoot: AI Face Photo Editor'
  studio TEXT   -- 'Codeway' or 'HubX'
  vertical TEXT -- 'ai_chatbot' or 'face_editor'
  pair_id TEXT  -- 'chatbot' or 'face' (matched-pair key)
  country TEXT  -- one of: us, gb, de, tr, br, in, fr, jp
  rating INTEGER    -- Apple's 1-5 star rating. Ground truth, never LLM output.
  title TEXT
  body TEXT
  version TEXT
  review_date TEXT
  is_substantive INTEGER -- 0/1, filters keyboard-mash / too-short reviews
  cluster_id INTEGER     -- KMeans cluster (k=12) over embeddings; clusters formed
                          -- by LANGUAGE, not topic (nomic-embed-text encodes
                          -- language before topic on this corpus)

TABLE extractions — ONLY the ~1,035 reviews sampled for LLM extraction (not all
reviews). Has NO app/studio/pair_id/country columns of its own — JOIN reviews
ON reviews.review_id = extractions.review_id to filter or GROUP BY any of
those.
  review_id TEXT PRIMARY KEY REFERENCES reviews(review_id)
  friction_type TEXT  -- one of: {_enum_list(FRICTION_TYPES)}
  trigger_moment TEXT -- one of: {_enum_list(TRIGGER_MOMENTS)}
  mentions_price INTEGER          -- 0/1
  price_mentioned TEXT
  paid_but_still_limited INTEGER  -- 0/1
  would_pay_signal TEXT           -- one of: {_enum_list(WOULD_PAY_SIGNALS)}
  feature_praised TEXT
  gist TEXT
  cluster_id INTEGER
  in_estimation_frame INTEGER -- 1 = in the random, stratified sample used for
                               -- EVERY rate/percentage
  in_discovery_frame INTEGER  -- 1 = in the purposive sample (quotes/exploration
                               -- only, NEVER used to compute a rate)
  selection_weight REAL       -- inverse selection probability; weight every
                               -- rate/percentage by this
  validation_status TEXT      -- 'valid' or 'invalid' (LLM output failed schema
                               -- validation and was not trusted)

RULE - raw counts vs rates, this distinction matters:
  A raw count ("how many reviews", "cluster size", "how many 1-star reviews")
  runs over the FULL population (reviews, or extractions unfiltered) with NO
  in_estimation_frame filter and NO selection_weight. Frame filtering only
  applies to RATES/PERCENTAGES.

  A rate or percentage ("what fraction", "what percent", "rate of X") MUST
  read from extractions, MUST filter WHERE in_estimation_frame = 1, and MUST
  weight by selection_weight. Canonical shape - follow this exactly, including
  the join (app lives on reviews, not extractions):

    SELECT r.app,
           SUM(CASE WHEN e.friction_type != 'none'
                    THEN e.selection_weight ELSE 0 END)
             / SUM(e.selection_weight) AS rate,
           COUNT(*) AS n
    FROM extractions e
    JOIN reviews r ON r.review_id = e.review_id
    WHERE e.in_estimation_frame = 1
    GROUP BY r.app;

  COUNT(*) AS n is NOT optional, and NOT only for the unfiltered/GROUP BY
  case above - it belongs in EVERY rate query, including one scoped to a
  single app. Example, filtered to one app, n still present:

    SELECT r.app,
           SUM(CASE WHEN e.friction_type = 'paywall_timing'
                    THEN e.selection_weight ELSE 0 END)
             / SUM(e.selection_weight) AS rate,
           COUNT(*) AS n
    FROM extractions e
    JOIN reviews r ON r.review_id = e.review_id
    WHERE e.in_estimation_frame = 1 AND r.app = 'AI Chatbot - Nova'
    GROUP BY r.app;

  Same again, filtered to one country AND one app, n still present:

    SELECT r.app,
           SUM(CASE WHEN e.friction_type != 'none'
                    THEN e.selection_weight ELSE 0 END)
             / SUM(e.selection_weight) AS rate,
           COUNT(*) AS n
    FROM extractions e
    JOIN reviews r ON r.review_id = e.review_id
    WHERE e.in_estimation_frame = 1 AND r.country = 'tr' AND r.app = 'AI Chatbot - Nova'
    GROUP BY r.app;

  Always alias a record-count column as `n` whenever your query computes a
  rate - that's how the caller reports how much data a percentage rests on.
  A rate returned without n will be rejected and not shown to the user.

Output ONLY a single read-only SELECT statement. No INSERT/UPDATE/DELETE/DROP/
ALTER/ATTACH/CREATE/PRAGMA, and no multiple statements."""

ROUTER_TEMPLATE = """Classify the question below as exactly one type.

AGGREGATE: asks for a count, percentage, rate, ranking, or comparison of numbers
- "how many", "what percent", "which country has the most" - anything a SQL
query over a database answers.

QUALITATIVE: asks what users say, feel, describe, or complain about in their
own words - anything that requires reading review text, not counting rows.

If genuinely unsure, choose AGGREGATE - giving a text answer to a numeric
question is worse than the reverse.

Output ONLY JSON: {{"query_type": "AGGREGATE" or "QUALITATIVE"}}

Question: \"\"\"{question}\"\"\"

JSON:"""

SQL_GEN_TEMPLATE = """{schema}

Question: \"\"\"{question}\"\"\"

Output ONLY JSON in exactly this shape: {{"sql": "<a single SELECT statement, no trailing semicolon>"}}

JSON:"""

SQL_RETRY_TEMPLATE = """{schema}

Your previous SQL was rejected.

Previous SQL:
{previous_sql}

Problem: {reason}

Question: \"\"\"{question}\"\"\"

Output ONLY corrected JSON: {{"sql": "<a single SELECT statement, no trailing semicolon>"}}

JSON:"""

QUALITATIVE_SYNTH_TEMPLATE = """Below are up to {k} real app store reviews retrieved for a question. \
Answer the question using ONLY what these reviews say. Cite the review_id in \
brackets after every claim you make, e.g. [123456789]. If these reviews don't \
actually address the question, say so plainly instead of guessing. Never \
invent facts, numbers, or reviews beyond what's given below.

Reviews:
{context}

Question: \"\"\"{question}\"\"\"

Answer (with [review_id] citations):"""

# Mechanical country -> language mapping, used only when a country filter is
# active: lowering the similarity threshold (MIN_TOP1_SIMILARITY_COUNTRY_
# FILTERED) fixed the case where the pool was already language-matched
# (Japan: 0.63, comfortably above 0.58). It did NOT fix Brazil (0.51, still
# below even the relaxed threshold) - that one isn't a threshold problem,
# it's the query being in Turkish while the filtered pool is in Portuguese.
# Translating the query into the pool's language addresses the actual
# mismatch instead of loosening the gate further (which would risk letting
# genuinely unrelated matches through).
# English names, for the translation PROMPT specifically - measured that
# gemma3:4b doesn't reliably follow the Turkish name as an instruction.
# "Portekizce" got paraphrased in Turkish instead of translated; "Japonca"
# happened to work but that's not something to rely on holding for every
# language. "Portuguese" worked correctly on the first try. Never shown to
# the user - COUNTRY_LANGUAGE_DATIVE below is the display name.
COUNTRY_LANGUAGE = {
    "br": "Portuguese",
    "jp": "Japanese",
    "de": "German",
    "fr": "French",
    "tr": "Turkish",
    "us": "English",
    "gb": "English",
    "in": "English",
}

# Turkish dative forms ("to Portuguese"), for the transparency note - vowel
# harmony means these can't be generated by string concatenation.
COUNTRY_LANGUAGE_DATIVE = {
    "br": "Portekizce'ye",
    "jp": "Japonca'ya",
    "de": "Almanca'ya",
    "fr": "Fransızca'ya",
    "us": "İngilizce'ye",
    "gb": "İngilizce'ye",
    "in": "İngilizce'ye",
}

TRANSLATE_TEMPLATE = """Translate the text below into {language}. Output ONLY the translation - no quotes, no explanation, no original text, nothing else.

Text: \"\"\"{text}\"\"\"

Translation:"""


def translate_query(question, language, host):
    prompt = TRANSLATE_TEMPLATE.format(language=language, text=question)
    return call_ollama_text(prompt, host, num_predict=120).strip()


@dataclass
class Answer:
    query_type: str  # "AGGREGATE" | "QUALITATIVE"
    text: str
    sql: str | None = None
    review_ids: list = field(default_factory=list)
    n: int | None = None
    raw_result: dict | None = None  # {"columns": [...], "rows": [[...], ...]} - the
                                     # unformatted SQL result, for AGGREGATE answers.
                                     # `text` is the human-readable (e.g. percentage)
                                     # rendering; this is the real value underneath it.
    country_distribution: dict | None = None
    warnings: list = field(default_factory=list)


def check_ollama_health(host):
    """CLI-only concern: fail fast with a clear message instead of answer()
    raising deep inside a request. Not called by answer() itself, since a
    caller embedding this module (e.g. Flask) may want to handle that
    differently than exiting the process."""
    try:
        resp = requests.get(f"{host}/api/tags", timeout=5)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"error: Ollama not reachable at {host} ({exc}) - start Ollama and retry")
        raise SystemExit(1)


def call_ollama_json(prompt, host, num_predict=200):
    # Tried num_thread=1 here to fix router nondeterminism (see
    # keyword_says_aggregate below for what actually fixes it) - it did NOT
    # make classification reproducible (still flipped across repeats) and
    # made the schema-heavy SQL-gen prompt slow enough to blow past a 60s
    # timeout on this CPU. Reverted: no benefit, real cost.
    resp = requests.post(
        f"{host}/api/generate",
        json={
            "model": CHAT_MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "keep_alive": "10m",
            "options": {"num_ctx": 2048, "num_predict": num_predict, "temperature": 0},
        },
        timeout=90,
    )
    resp.raise_for_status()
    raw = resp.json().get("response", "")
    return json.loads(raw)


def call_ollama_text(prompt, host, num_predict=700):
    resp = requests.post(
        f"{host}/api/generate",
        json={
            "model": CHAT_MODEL,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "10m",
            "options": {"num_ctx": 4096, "num_predict": num_predict, "temperature": 0},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def embed_text(text, host):
    resp = requests.post(
        f"{host}/api/embed", json={"model": EMBED_MODEL, "input": [text]}, timeout=30
    )
    resp.raise_for_status()
    vec = np.array(resp.json()["embeddings"][0], dtype=np.float32)
    return vec / np.linalg.norm(vec)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


# Measured empirically (5 repeats of one unambiguous rate question, at
# temperature=0, single-threaded): AGGREGATE/QUALITATIVE/AGGREGATE/
# QUALITATIVE/AGGREGATE. Ollama's JSON-grammar-constrained decoding isn't
# reproducible on this CPU even with num_thread=1, so a question with an
# unambiguous rate/count marker is routed here directly, without ever
# calling the LLM classifier - deterministic by construction instead of by
# hope. The LLM router below only ever sees questions that don't match any
# of these.
# Turkish is agglutinative — "oran" (rate) shows up as "oranı", "oranın",
# "oranla", never as the bare stem alone in a real question. A \bword\b
# match against the bare stem misses every inflected form (caught this
# empirically: "oranı" didn't match "\boran\b" and fell through to the
# flaky LLM router below). These are matched as PREFIXES instead.
AGGREGATE_PREFIX_KEYWORDS = ["oran", "yüzde", "kaç"]

# English/exact tokens - kept as whole-word matches, not prefixes, so "rate"
# doesn't fire inside "rating" (a star rating, not a rate question) and
# "count" doesn't fire inside "discount".
AGGREGATE_WORD_KEYWORDS = ["rate", "percent", "percentage", "count", "ranking", "compare"]

# Multi-word phrases and the "%" sign - safe as plain substrings.
AGGREGATE_PHRASE_KEYWORDS = [
    "%", "how many", "how much", "ne kadarı", "en çok", "en fazla", "en az",
    "which country", "which app",
]


def keyword_says_aggregate(question):
    normalized = _normalize_for_match(question)
    if any(kw in normalized for kw in AGGREGATE_PHRASE_KEYWORDS):
        return True
    if any(re.search(rf"\b{re.escape(stem)}", normalized) for stem in AGGREGATE_PREFIX_KEYWORDS):
        return True
    if any(re.search(rf"\b{re.escape(w)}\b", normalized) for w in AGGREGATE_WORD_KEYWORDS):
        return True
    return False


def classify_question(question, host):
    """Returns (query_type, warning). warning is None unless classification
    was forced by keyword, failed, or was ambiguous - in every one of those
    cases query_type is "AGGREGATE" (a text answer to a numeric question is
    worse than the reverse)."""
    if keyword_says_aggregate(question):
        return "AGGREGATE", None

    prompt = ROUTER_TEMPLATE.format(question=question)
    try:
        data = call_ollama_json(prompt, host, num_predict=20)
        qtype = str(data.get("query_type", "")).upper()
        if qtype in ("AGGREGATE", "QUALITATIVE"):
            return qtype, None
    except (requests.RequestException, json.JSONDecodeError, AttributeError):
        pass
    return "AGGREGATE", "sınıflandırma başarısız ya da belirsiz - varsayılan olarak AGGREGATE seçildi"


# ---------------------------------------------------------------------------
# AGGREGATE path
# ---------------------------------------------------------------------------


def generate_sql(question, host, retry_reason=None, previous_sql=None):
    if retry_reason:
        prompt = SQL_RETRY_TEMPLATE.format(
            schema=SCHEMA_TEXT, question=question, previous_sql=previous_sql, reason=retry_reason
        )
    else:
        prompt = SQL_GEN_TEMPLATE.format(schema=SCHEMA_TEXT, question=question)
    data = call_ollama_json(prompt, host, num_predict=300)
    sql = data.get("sql", "")
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError(f"model returned no usable sql field: {data!r}")
    return sql.strip()


def is_safe_select(sql):
    """Returns (True, cleaned_sql) or (False, reason). Only a single
    SELECT statement is ever allowed to run."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return False, "boş SQL"
    if not re.match(r"(?is)^\s*SELECT\b", stripped):
        return False, "SELECT ile başlamıyor"
    if ";" in stripped:
        return False, "birden fazla ifade içeriyor"
    if FORBIDDEN_SQL_RE.search(stripped):
        return False, "yasaklı anahtar kelime içeriyor (yalnızca SELECT'e izin var)"
    return True, stripped


def looks_like_ratio_query(sql):
    return bool(RATIO_HINT_RE.search(sql))


def has_n_alias(sql):
    return bool(re.search(r"\bAS\s+n\b", sql, re.IGNORECASE))


def ratio_query_issues(sql):
    """Everything a rate-computing query is missing, out of the three
    mandatory requirements: frame filter, weighting, and a record-count
    column to report the rate against. A rate without n cannot be reported
    at all - that omission is caught here as seriously as the other two,
    not just noted after the fact."""
    issues = []
    lower = sql.lower()
    if "in_estimation_frame" not in lower:
        issues.append("WHERE in_estimation_frame = 1 filtresi eksik")
    if "selection_weight" not in lower:
        issues.append("selection_weight ile ağırlıklandırma eksik")
    if not has_n_alias(sql):
        issues.append("COUNT(*) AS n sütunu eksik - n olmadan bir oran raporlanamaz")
    return issues


def inject_n_column(sql):
    """Mechanical fix for a ratio query missing COUNT(*) AS n: splice it
    into the SELECT list right before the first FROM keyword. Purely
    textual - it does not interpret what the query means, it just adds the
    missing column. Returns the fixed SQL, or None if the result doesn't
    actually validate (e.g. FROM appeared somewhere unexpected, like inside
    a subquery), in which case the caller falls through to the LLM retry
    instead of trusting a rewrite that might be broken."""
    match = re.search(r"\bFROM\b", sql, re.IGNORECASE)
    if not match:
        return None
    fixed = f"{sql[:match.start()].rstrip()}, COUNT(*) AS n {sql[match.start():]}"
    ok, cleaned = is_safe_select(fixed)
    if ok and has_n_alias(cleaned):
        return cleaned
    return None


def run_select(sql, db_path):
    """Executes against a read-only connection (defense in depth on top of
    is_safe_select - belt and suspenders for arbitrary LLM-generated SQL)."""
    uri = f"file:{Path(db_path).resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
    finally:
        conn.close()
    return columns, rows


def format_aggregate_text(columns, rows):
    """Human-readable rendering. A `rate` column (the canonical alias for a
    computed proportion) is shown as a percentage with its n right next to
    it, per the project's rule that a percentage never appears without the
    record count it rests on - never as the raw fraction. The underlying
    unrounded value is never discarded, just not what's shown here (see
    Answer.raw_result)."""
    if not rows:
        return "Sorgu sonuç döndürmedi."

    lower_cols = [c.lower() for c in columns]
    if "rate" in lower_cols:
        rate_idx = lower_cols.index("rate")
        n_idx = lower_cols.index("n") if "n" in lower_cols else None
        lines = []
        for row in rows:
            label = ", ".join(
                f"{col}={val}"
                for i, (col, val) in enumerate(zip(columns, row))
                if i not in (rate_idx, n_idx)
            )
            pct = f"%{row[rate_idx] * 100:.1f}"
            n_part = f" (n={row[n_idx]})" if n_idx is not None else " (n=?)"
            lines.append(f"{label}: {pct}{n_part}" if label else f"{pct}{n_part}")
        return "\n".join(lines)

    if len(rows) == 1 and len(columns) == 1:
        return str(rows[0][0])
    return "\n".join(", ".join(f"{col}={val}" for col, val in zip(columns, row)) for row in rows)


def extract_n(columns, rows):
    """n is only ever read from what the SQL itself reports - never
    recomputed or guessed. Looks for a column literally named `n`; falls
    back to a single scalar result being treated as its own n (a plain
    COUNT(*) query IS the record count)."""
    lower_cols = [c.lower() for c in columns]
    if "n" in lower_cols:
        idx = lower_cols.index("n")
        try:
            return sum(int(row[idx]) for row in rows)
        except (TypeError, ValueError):
            return None
    if len(rows) == 1 and len(columns) == 1:
        try:
            return int(rows[0][0])
        except (TypeError, ValueError):
            return None
    return None


def low_n_warnings(columns, rows, threshold=LOW_N_THRESHOLD):
    lower_cols = [c.lower() for c in columns]
    if "n" not in lower_cols:
        return []
    idx = lower_cols.index("n")
    warnings = []
    for row in rows:
        try:
            n_val = int(row[idx])
        except (TypeError, ValueError):
            continue
        if n_val < threshold:
            label = ", ".join(f"{c}={v}" for c, v in zip(columns, row) if c.lower() != "n")
            warnings.append(f"⚠ n={n_val} (<{threshold}) - {label}")
    return warnings


def answer_aggregate(question, host, db_path, debug=False):
    warnings = []
    sql = generate_sql(question, host)
    if debug:
        print(f"[debug] generated SQL:\n{sql}\n")

    ok, result = is_safe_select(sql)
    if not ok:
        return Answer(
            query_type="AGGREGATE",
            text=f"Üretilen SQL güvenli değil, çalıştırılmadı: {result}",
            sql=sql,
        )
    sql = result

    if looks_like_ratio_query(sql):
        issues = ratio_query_issues(sql)

        # Mechanical fix first: if n is the only thing missing, splice in
        # COUNT(*) AS n ourselves rather than spending an LLM call asking
        # the model to do something this deterministic. Only touches the
        # n requirement - frame/weight issues always need the LLM retry,
        # since fixing those means changing WHAT the query filters on, not
        # just adding a column.
        if issues == ["COUNT(*) AS n sütunu eksik - n olmadan bir oran raporlanamaz"]:
            fixed_sql = inject_n_column(sql)
            if fixed_sql:
                sql = fixed_sql
                issues = []
                warnings.append("n sütunu otomatik eklendi (COUNT(*) AS n)")
                if debug:
                    print(f"[debug] mechanically fixed SQL:\n{sql}\n")

        if issues:
            reason = "; ".join(issues)
            retry_sql = generate_sql(question, host, retry_reason=reason, previous_sql=sql)
            if debug:
                print(f"[debug] retry SQL:\n{retry_sql}\n")
            ok2, result2 = is_safe_select(retry_sql)
            issues2 = ratio_query_issues(result2) if ok2 and looks_like_ratio_query(result2) else []
            if ok2 and not issues2:
                sql = result2
            else:
                return Answer(
                    query_type="AGGREGATE",
                    text=(
                        "Oran hesaplayan SQL iki denemede de gerekli şartları taşımadı "
                        f"({'; '.join(issues2) if ok2 else issues[0]}); n olmadan bir oran "
                        "raporlanamaz, bu yüzden çalıştırılmadı."
                    ),
                    sql=retry_sql,
                    warnings=["ağırlıklı oran kontrolü başarısız: " + "; ".join(issues2 or issues)],
                )

    try:
        columns, rows = run_select(sql, db_path)
    except sqlite3.Error as exc:
        return Answer(query_type="AGGREGATE", text=f"SQL çalıştırılamadı: {exc}", sql=sql)

    if debug:
        print(f"[debug] raw result: columns={columns} rows={rows}\n")

    text = format_aggregate_text(columns, rows)
    n = extract_n(columns, rows)
    warnings.extend(low_n_warnings(columns, rows))
    if looks_like_ratio_query(sql):
        warnings.append("kestirim çerçevesi, ağırlıklı")
    if n is None:
        warnings.append("kayıt sayısı (n) SQL çıktısından çıkarılamadı")

    return Answer(
        query_type="AGGREGATE",
        text=text,
        sql=sql,
        n=n,
        warnings=warnings,
        raw_result={"columns": columns, "rows": [list(row) for row in rows]},
    )


# ---------------------------------------------------------------------------
# QUALITATIVE path
# ---------------------------------------------------------------------------


def load_corpus(conn, country=None):
    """country, when given, filters the search pool BEFORE similarity is
    computed — not after. Filtering after the fact would just be a smaller
    top-K over the same language-skewed ranking; filtering the pool is what
    actually lets a Turkish-phrased question reach Japanese reviews."""
    query = """
        SELECT e.review_id, e.vector, r.body, r.country, r.rating
        FROM embeddings e JOIN reviews r ON r.review_id = e.review_id
    """
    params = ()
    if country:
        query += " WHERE r.country = ?"
        params = (country,)
    rows = conn.execute(query, params).fetchall()
    if not rows:
        where = f" (country={country!r})" if country else ""
        raise RuntimeError(f"no embeddings found{where} - run src/embed.py first")
    review_ids = [r[0] for r in rows]
    vectors = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
    bodies = [r[2] for r in rows]
    countries = [r[3] for r in rows]
    ratings = [r[4] for r in rows]
    norm_vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    return review_ids, norm_vectors, bodies, countries, ratings


def build_synth_prompt(question, context):
    return QUALITATIVE_SYNTH_TEMPLATE.format(k=QUALITATIVE_TOP_K, context=context, question=question)


def answer_qualitative(question, host, db_path, debug=False):
    matched_countries = detect_countries(question)
    country_filter = None
    warnings = []

    if len(matched_countries) == 1:
        country_filter = next(iter(matched_countries))
    elif len(matched_countries) > 1:
        warnings.append(
            f"soruda birden fazla ülke/pazar adı geçiyor ({', '.join(sorted(matched_countries))}) "
            "- filtre uygulanmadı, tüm korpusta arandı"
        )

    conn = get_connection(db_path)
    try:
        review_ids, norm_vectors, bodies, countries, ratings = load_corpus(conn, country=country_filter)
    finally:
        conn.close()

    pool_size = len(review_ids)
    if country_filter:
        threshold = MIN_TOP1_SIMILARITY_COUNTRY_FILTERED
        threshold_note = f"eşik {threshold} - ülke filtresi aktif"
    else:
        threshold = MIN_TOP1_SIMILARITY_DEFAULT
        threshold_note = f"eşik {threshold} - ülke filtresi yok"

    # Filtering the pool to one country doesn't fix a query written in a
    # different language than that country's reviews (measured: Brazil
    # stayed at top1=0.51 even after country=br filtering, well below
    # threshold - the pool was right, the query's language wasn't). Only
    # translate when the target language actually differs from Turkish,
    # since every question in practice arrives in Turkish already - "tr"
    # named as the country is the one case that needs no LLM call at all.
    search_text = question
    if country_filter and country_filter != "tr":
        target_language = COUNTRY_LANGUAGE[country_filter]
        search_text = translate_query(question, target_language, host)
        warnings.append(
            f"sorgu {COUNTRY_LANGUAGE_DATIVE[country_filter]} çevrildi: '{search_text}'"
        )

    qv = embed_text(search_text, host)
    sims = norm_vectors @ qv
    k = min(QUALITATIVE_TOP_K, pool_size)
    top_idx = np.argsort(-sims)[:k]
    top_sims = sims[top_idx]
    top1_sim = float(top_sims[0])
    n_matches = len(top_idx)

    if debug:
        print(
            f"[debug] country_filter={country_filter} pool={pool_size} search_text={search_text!r} "
            f"top1={top1_sim:.3f} top15_mean={float(top_sims.mean()):.3f} threshold={threshold}\n"
        )

    country_counts = Counter(countries[i] for i in top_idx)
    country_dist = {
        c: {"n": cnt, "pct": round(100 * cnt / n_matches, 1)} for c, cnt in country_counts.items()
    }

    if country_filter:
        # Country named and matched -> pool pre-filtered before similarity
        # ran, so a Turkish-phrased question about Japan actually reaches
        # Japanese reviews instead of the nearest Turkish ones.
        warnings.append(
            f"country={country_filter} ile sınırlandı, {pool_size} kayıt havuzu "
            "(reviews tablosunda ayrı bir dil sütunu yok, ülke dil için proxy olarak kullanıldı)"
        )
    else:
        # No country named -> old behavior: search runs over the full
        # corpus, and nomic-embed-text encodes language before topic, so
        # results skew toward the question's own language. Structural, not
        # conditional - shown every time this branch is taken.
        warnings.append(
            "ülke belirtilmedi: anlamsal arama sorunun dilinde yoğunlaşma eğiliminde "
            "(nomic-embed-text çok dilli korpusta önce dili kodluyor, konuyu sonra) - "
            "aşağıdaki ülke dağılımına bakın; reviews tablosunda ayrı bir dil sütunu yok"
        )

    # Threshold used is always shown, not just on refusal - which gate
    # applied is as much a part of the answer as the answer itself.
    warnings.append(threshold_note)

    if top1_sim < threshold:
        return Answer(
            query_type="QUALITATIVE",
            text=(
                f"Bu soruyu yanıtlayacak veri yok (en yakın kaydın benzerlik skoru "
                f"{top1_sim:.2f}, {threshold_note})."
            ),
            n=0,
            country_distribution=country_dist,
            warnings=warnings,
        )

    if n_matches < MIN_MATCHES_WARN:
        warnings.append(f"sonuç {MIN_MATCHES_WARN}'ten az kayda dayanıyor (n={n_matches})")

    context = "\n".join(
        f"[{review_ids[i]}] (ülke={countries[i]}, puan={ratings[i]}) "
        f"{(bodies[i] or '').strip().replace(chr(10), ' ')}"
        for i in top_idx
    )
    raw = call_ollama_text(build_synth_prompt(question, context), host)

    return Answer(
        query_type="QUALITATIVE",
        text=raw.strip(),
        review_ids=[review_ids[i] for i in top_idx],
        n=n_matches,
        country_distribution=country_dist,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Entry point - this is what a future Flask route calls
# ---------------------------------------------------------------------------


def answer(question, host=OLLAMA_HOST, db_path=DB_PATH, debug=False):
    query_type, classify_warning = classify_question(question, host)
    if debug:
        note = f" ({classify_warning})" if classify_warning else ""
        print(f"[debug] classified as {query_type}{note}\n")

    try:
        if query_type == "AGGREGATE":
            result = answer_aggregate(question, host, db_path, debug=debug)
        else:
            result = answer_qualitative(question, host, db_path, debug=debug)
    except (requests.RequestException, sqlite3.Error, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        result = Answer(query_type=query_type, text=f"Soru yanıtlanamadı: {exc}")

    if classify_warning:
        result.warnings.insert(0, classify_warning)
    return result


# ---------------------------------------------------------------------------
# CLI - prints what answer() returns, nothing more
# ---------------------------------------------------------------------------


def print_answer(result):
    print(f"[{result.query_type}]\n")
    print(result.text)

    if result.n is not None:
        print(f"\nn={result.n} kayda dayanıyor")

    if result.sql:
        print(f"\nSQL:\n{result.sql}")

    if result.review_ids:
        print(f"\nkaynak review_id'ler: {', '.join(result.review_ids)}")

    if result.country_distribution:
        print("\nülke dağılımı (dil için yaklaşıklık):")
        for country, info in sorted(result.country_distribution.items(), key=lambda kv: -kv[1]["n"]):
            print(f"  {country}: {info['n']} ({info['pct']}%)")

    if result.warnings:
        print("\nuyarılar:")
        for w in result.warnings:
            print(f"  - {w}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", help="doğal dilde soru")
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--host", default=OLLAMA_HOST)
    parser.add_argument("--debug", action="store_true", help="ara adımları (sınıflandırma, SQL, benzerlik skorları) yazdır")
    args = parser.parse_args()

    check_ollama_health(args.host)
    result = answer(args.question, host=args.host, db_path=args.db, debug=args.debug)
    print_answer(result)


if __name__ == "__main__":
    main()
