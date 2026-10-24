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

# Part 6.5: how many ranked records a QUALITATIVE answer shows at most, out
# of however many matched the detected filters (see answer_qualitative).
QUALITATIVE_TOP_K_RESULTS = 25

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
  app TEXT      -- EXACTLY one of these four full strings - never shorten or
                 -- abbreviate one (not "Retake AI", not "Nova" alone):
                 --   'Chat AI: Ask Agent Anything'
                 --   'AI Chatbot - Nova'
                 --   'Retake AI Face & Selfie Editor'
                 --   'ReShoot: AI Face Photo Editor'
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
  A raw count ("how many reviews", "how many reviews from country X", "how
  many 1-star reviews") runs over the FULL population and reads from
  reviews ONLY - no JOIN to extractions at all. extractions only has the
  ~1,035 sampled rows, so joining it into a count silently shrinks the
  population and the count comes out wrong (measured: "how many reviews
  from Germany" returned 113 with an extractions JOIN instead of the
  correct ~800 from reviews alone). JOIN extractions ONLY when the query
  actually reads one of ITS OWN columns (friction_type, would_pay_signal,
  in_estimation_frame, selection_weight, etc.) - never join it just because
  a query filters by app/country/rating, since those columns live on
  reviews regardless.

  Example - a raw count filtered by country, reviews only, no join:

    SELECT COUNT(*) FROM reviews WHERE country = 'de';

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

# Mechanical country -> language mapping, used only when a country filter is
# active: lowering the similarity threshold (MIN_TOP1_SIMILARITY_COUNTRY_
# FILTERED) fixed the case where the pool was already language-matched
# (Japan: 0.63, comfortably above 0.58). It did NOT fix Brazil (0.51, still
# below even the relaxed threshold) - that one isn't a threshold problem,
# it's the query being in Turkish while the filtered pool is in Portuguese.
# Translating the query into the pool's language addresses the actual
# mismatch instead of loosening the gate further (which would risk letting
# genuinely unrelated matches through).
# English names, for the translation PROMPT and for the user-facing
# transparency note alike - measured that gemma3:4b doesn't reliably
# follow the Turkish name as an instruction. "Portekizce" got paraphrased
# in Turkish instead of translated; "Japonca" happened to work but that's
# not something to rely on holding for every language. "Portuguese"
# worked correctly on the first try.
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

# ISO 639-1 -> full English name, for translations.source_lang (the actual
# language Claude detected per review while translating by hand - see
# README - not the country-proxy mapping above). Covers every code that
# shows up in the translated pool; add to this, don't guess, if a future
# translation pass introduces a new one.
LANGUAGE_NAMES = {
    "en": "English",
    "pt": "Portuguese",
    "de": "German",
    "fr": "French",
    "tr": "Turkish",
    "ja": "Japanese",
    "es": "Spanish",
    "ar": "Arabic",
    "zh": "Chinese",
    "ru": "Russian",
    "ro": "Romanian",
    "hi": "Hindi",
}

TRANSLATE_TEMPLATE = """Translate the text below into {language}. Output ONLY the translation - no quotes, no explanation, no original text, nothing else.

Text: \"\"\"{text}\"\"\"

Translation:"""


def translate_query(question, language, host):
    prompt = TRANSLATE_TEMPLATE.format(language=language, text=question)
    return call_ollama_text(prompt, host, num_predict=120).strip()


# When no country is named, a question still gets embedded only once, in
# whatever language it was typed in - and nomic-embed-text's language-first
# encoding means it then only ever reaches reviews in that same language
# (measured: a Turkish question with no country name scored 100% tr in its
# top 15, regardless of topic). Fanning the same query out across the
# corpus's other major languages and merging the results fixes this the
# same way the single-country translation fix did, just without a country
# name to anchor the target language. Always includes the original text
# untranslated (assumed Turkish, since every real question in this system
# is) alongside translations into these five.
FANOUT_LANGUAGES = ["English", "Portuguese", "German", "French", "Japanese"]

# Deterministic keyword pre-check, no LLM call: does the question target
# one specific structured field/value pair from Part 4's extraction schema
# rather than open text? "ödemeye yakın olup vazgeçen kullanıcılar" is
# asking about would_pay_signal='conditional' specifically - semantic
# search alone has no way to hit that reliably, since "conditional" isn't
# a word review authors use about themselves. Single words are PREFIX
# matched (Turkish suffixes - same class of fix as AGGREGATE_PREFIX_
# KEYWORDS); phrases are substring matched.
#
# would_pay_signal rows expanded after "Neredeyse ödeme yapacak olan
# Brezilyalı kullanıcılar neden caydı" matched no rule at all (only the
# country filter applied) - "neden caydı" names the exact same
# near-payment-then-backed-out idea as "vazgeç", just with a different
# verb. friction_type rows for performance/onboarding_confusion below are
# new entries (previously uncovered by any rule at all), drawn from
# phrasing seen repeatedly in the translated review corpus itself (Part
# 6.5), not invented - "sunucu meşgul"/"sunucular meşgul" ("servers busy")
# in particular recurs verbatim across many Turkish reviews.
FIELD_KEYWORD_RULES = [
    (
        [
            "ödemeye yakın", "vazgeç", "ikna olsa öderdi", "ikna olsa",
            "caydı", "cayma", "ödeyecektim", "neredeyse ödeyecek",
            "bir şey olsa öderdi",
        ],
        "would_pay_signal", "conditional",
    ),
    (
        ["ödemem diyen", "asla ödemem", "ödemem", "para vermem", "bedava olmalı"],
        "would_pay_signal", "no",
    ),
    (
        ["iptal", "abonelik tuzağı", "deneme", "otomatik yenile", "fark etmeden", "bilgim dışında", "izinsiz"],
        "friction_type", "subscription_trap",
    ),
    (["paywall", "ne zaman çıkıyor", "daha denemeden", "açar açmaz"], "friction_type", "paywall_timing"),
    (["kota", "limit", "günlük hak", "soru hakkı", "mesaj hakkı"], "friction_type", "free_quota_limit"),
    (["pahalı", "fiyat", "ücret yüksek", "fiyatı yüksek"], "friction_type", "price_level"),
    (["arkadaş davet", "referans", "davet et", "arkadaşını davet"], "friction_type", "referral_gate"),
    (["sunucu meşgul", "sunucular meşgul", "yavaş çalış", "çöküyor"], "friction_type", "performance"),
    (["nasıl kullanılacağını", "kullanımı karışık", "arayüz karışık"], "friction_type", "onboarding_confusion"),
]


def _keyword_matches(normalized, keywords):
    for kw in keywords:
        if " " in kw:
            if kw in normalized:
                return True
        elif re.search(rf"\b{re.escape(kw)}", normalized):
            return True
    return False


def detect_structured_field(question):
    """Returns (field, value) when exactly one rule matches, else None -
    including when more than one distinct field/value pair matches
    (ambiguous: which one was meant is no longer a keyword lookup's call,
    so this falls back to the existing unfiltered search rather than
    guessing)."""
    normalized = _normalize_for_match(question)
    matched = {
        (field, value)
        for keywords, field, value in FIELD_KEYWORD_RULES
        if _keyword_matches(normalized, keywords)
    }
    if len(matched) == 1:
        return next(iter(matched))
    return None


AIMLESS_PHRASES = [
    "ne önerirsin", "ne öneriyorsun", "ne tavsiye edersin", "tavsiyen ne",
    "ne yapmalıyım", "ne yapmalı", "özetle", "özet ver", "yorumla",
    "ne düşünüyorsun", "ne dersin",
]


def is_aimless_question(question):
    """Rejects a question with no target at all - "ne önerirsin" (what do
    you recommend) pulled back 15 arbitrary reviews and produced a
    repetitive non-answer, because there was nothing for the search to
    aim at. A topic signal is a country, an app, a structured field (which
    itself already covers every friction/would-pay keyword in
    FIELD_KEYWORD_RULES), or a plain numeric/count intent ("kaç yorum
    topladın" names no country/app/field, but "kaç" alone is a perfectly
    aimed question). Anything with one of those signals is never aimless.

    Deliberately a denylist, not a general heuristic: a "<=3 words with no
    topic signal" length fallback was tried and also caught "Codeway'in
    CEO'su kim?" (3 words, names no country/app/field). That question
    isn't aimless, it's out-of-domain - it has a clear target (Codeway's
    CEO), just not one this corpus can answer, and the similarity-
    threshold rejection already handles that case correctly and more
    informatively. Conflating "no target" with "target we can't answer"
    would lose that distinction, so only the exact phrasings below reject.
    mentions_app/keyword_says_aggregate are defined further down but
    that's fine - this function isn't called until module load finishes."""
    normalized = _normalize_for_match(question)
    has_topic_signal = (
        bool(detect_countries(question))
        or mentions_app(normalized)
        or bool(detect_structured_field(question))
        or any(_keyword_matches(normalized, keywords) for keywords, _field, _value in FIELD_KEYWORD_RULES)
        or keyword_says_aggregate(question)
    )
    if has_topic_signal:
        return False
    return any(phrase in normalized for phrase in AIMLESS_PHRASES)


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
    records: list = field(default_factory=list)  # Part 6.5: [{"review_id", "text_en", "body",
                                                   # "country", "rating", "app", "friction_type",
                                                   # "would_pay_signal"}, ...] - the ranked,
                                                   # filtered records a QUALITATIVE question
                                                   # returns. No generated summary sentence and
                                                   # no live translation call for this path
                                                   # (see answer_qualitative) - every review in
                                                   # the pool was translated once, by hand,
                                                   # ahead of time (see README).
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


def embed_texts(texts, host):
    """One /api/embed call for one or more texts - used both for a single
    query and for the multilingual fan-out's several query variants at
    once, cheaper than one round trip per text."""
    resp = requests.post(
        f"{host}/api/embed", json={"model": EMBED_MODEL, "input": texts}, timeout=60
    )
    resp.raise_for_status()
    vecs = np.array(resp.json()["embeddings"], dtype=np.float32)
    return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)


def embed_text(text, host):
    return embed_texts([text], host)[0]


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
    return "AGGREGATE", "classification failed or ambiguous - defaulted to AGGREGATE"


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
        return False, "empty SQL"
    if not re.match(r"(?is)^\s*SELECT\b", stripped):
        return False, "doesn't start with SELECT"
    if ";" in stripped:
        return False, "contains multiple statements"
    if FORBIDDEN_SQL_RE.search(stripped):
        return False, "contains a forbidden keyword (only SELECT is allowed)"
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
        issues.append("missing WHERE in_estimation_frame = 1 filter")
    if "selection_weight" not in lower:
        issues.append("missing selection_weight weighting")
    if not has_n_alias(sql):
        issues.append("missing COUNT(*) AS n column - a rate cannot be reported without n")
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


def remove_unrequested_condition(sql, column):
    """Mechanical fix symmetric to inject_n_column: strips a WHERE
    condition on `column` that the question never asked for, keeping the
    rest of the WHERE clause's AND-structure valid - no dangling AND, no
    bare WHERE left behind if it was the only condition. Returns
    (fixed_sql, removed_value), or (None, None) if no such condition is
    found or the rewrite doesn't validate, in which case the caller falls
    through to the LLM retry instead of trusting a rewrite that might be
    broken."""
    value_match = re.search(
        rf"(?:\w+\.)?{re.escape(column)}\s*(?:=|!=|<>|<=|>=|<|>)\s*('[^']*'|\d+)", sql, re.IGNORECASE
    )
    if not value_match:
        return None, None
    removed_value = value_match.group(1).strip("'")

    # Three shapes, tried in order of leftmost match (re.sub always finds
    # the earliest starting position regardless of alternative order): a
    # condition with a leading AND (middle or last in the WHERE clause), a
    # condition with a trailing AND (first in the clause), or a bare
    # condition with no adjacent AND at all (the only condition present).
    cond_pattern = re.compile(
        rf"(?:\s+AND\s+(?:\w+\.)?{re.escape(column)}\s*(?:=|!=|<>|<=|>=|<|>)\s*(?:'[^']*'|\d+))"
        rf"|(?:(?:\w+\.)?{re.escape(column)}\s*(?:=|!=|<>|<=|>=|<|>)\s*(?:'[^']*'|\d+)\s+AND\s+)"
        rf"|(?:(?:\w+\.)?{re.escape(column)}\s*(?:=|!=|<>|<=|>=|<|>)\s*(?:'[^']*'|\d+))",
        re.IGNORECASE,
    )
    fixed, count = cond_pattern.subn("", sql, count=1)
    if count == 0:
        return None, None

    # If that was the only condition, WHERE is now dangling (nothing left
    # before GROUP BY/ORDER BY/HAVING or the end of the string).
    fixed = re.sub(r"\bWHERE\s*(?=GROUP\b|ORDER\b|HAVING\b|$)", "", fixed, flags=re.IGNORECASE)
    fixed = re.sub(r"\s+", " ", fixed).strip()

    ok, cleaned = is_safe_select(fixed)
    if not ok:
        return None, None
    return cleaned, removed_value


# App names/short aliases people actually type, mapped to the exact value
# stored in reviews.app. Shared by the SQL missing-filter check below and
# by the aimless-question check in the qualitative path.
APP_ALIASES = {
    "retake ai": "Retake AI Face & Selfie Editor",
    "retake": "Retake AI Face & Selfie Editor",
    "reshoot": "ReShoot: AI Face Photo Editor",
    "nova": "AI Chatbot - Nova",
    "chat ai": "Chat AI: Ask Agent Anything",
}

STAR_RATING_RE = re.compile(r"\b[1-5]\s*yıldız", re.IGNORECASE)
LOW_HIGH_RATING_PHRASES = ["düşük puanlı", "yüksek puanlı", "düşük puan", "yüksek puan"]
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
DATE_PHRASES = [
    "geçen ay", "bu yıl", "geçen yıl", "son bir ay", "son 3 ay", "son üç ay",
    "son 6 ay", "son altı ay", "bu ay", "ocak", "şubat", "mart", "nisan",
    "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık",
]


def mentions_rating(normalized):
    return bool(STAR_RATING_RE.search(normalized)) or any(p in normalized for p in LOW_HIGH_RATING_PHRASES)


def mentions_app(normalized):
    return any(alias in normalized for alias in APP_ALIASES)


def matched_app(normalized):
    """The canonical app name the question names, or None. Distinct from
    mentions_app (which only says yes/no) - cell-key lookup needs to know
    WHICH app, not just that one was mentioned."""
    for alias, app in APP_ALIASES.items():
        if alias in normalized:
            return app
    return None


APP_TO_PAIR = {
    "Chat AI: Ask Agent Anything": "chatbot",
    "AI Chatbot - Nova": "chatbot",
    "Retake AI Face & Selfie Editor": "face",
    "ReShoot: AI Face Photo Editor": "face",
}


def mentions_date(normalized):
    return bool(YEAR_RE.search(normalized)) or any(p in normalized for p in DATE_PHRASES)


def has_column_condition(sql, column):
    """True if the SQL actually restricts on `column` (any comparison
    operator, optionally alias-qualified) - not just mentions it in SELECT
    or GROUP BY, which references a column without restricting the
    population at all. Without this distinction, "SELECT r.app ... GROUP
    BY r.app" (no WHERE app filter, just per-app rows in the output) would
    look identical to an actual "WHERE r.app = 'X'" restriction to both
    directions of detect_filter_mismatches below."""
    return bool(
        re.search(
            rf"(?:\w+\.)?{re.escape(column)}\s*(?:=|!=|<>|<=|>=|<|>|IN\s*\(|BETWEEN|LIKE)",
            sql,
            re.IGNORECASE,
        )
    )


FILTER_COLUMN_LABELS = {"rating": "rating/star", "country": "country", "app": "app", "review_date": "date/period"}


def _question_wants(question):
    """Which of the four checked filter columns the question's own
    wording actually calls for. Shared by both directions below, and by
    the mechanical-removal step in answer_aggregate, so all three agree
    on exactly the same definition of "the question asked for this"."""
    normalized = _normalize_for_match(question)
    return {
        "rating": mentions_rating(normalized),
        "country": bool(detect_countries(question)),
        "app": mentions_app(normalized),
        "review_date": mentions_date(normalized),
    }


def missing_filter_columns(question, sql):
    wants = _question_wants(question)
    return [col for col, wanted in wants.items() if wanted and not has_column_condition(sql, col)]


def extra_filter_columns(question, sql):
    """Columns where the SQL applies a condition the question never asked
    for. in_estimation_frame and validation_status are exempt on purpose
    - not via special-case code, but because this only ever checks the
    four columns in _question_wants, and every rate query needs those two
    regardless of the question's wording, so they were never candidates
    for "unrequested filter" in the first place."""
    wants = _question_wants(question)
    return [col for col, wanted in wants.items() if not wanted and has_column_condition(sql, col)]


def detect_filter_mismatches(question, sql):
    """Both directions of "does the SQL match what the question actually
    asked" - checked together because they're the same failure mode: a
    plausible-looking number for a different question than the one asked.

    1) in the question but not in the SQL: "Retake AI'da 1 yıldızlı
       yorumların yüzde kaçı paywall ile ilgili?" came back with an app
       filter but no rating filter - the SQL ran and returned a number
       for a broader question than the one actually asked.
    2) in the SQL but not in the question: the very next fix for that
       same question came back with an unrequested country='tr' filter
       nobody asked for - 25.0% (n=12) instead of the real 30.2% (n=63)
       across all countries. Same failure, opposite direction."""
    issues = []
    for column in missing_filter_columns(question, sql):
        issues.append(f"question mentions {FILTER_COLUMN_LABELS[column]} but SQL has no {column} filter")
    for column in extra_filter_columns(question, sql):
        match = re.search(rf"(?:\w+\.)?{column}\s*(?:=|!=|<>)\s*'?([^'\s)]+)'?", sql, re.IGNORECASE)
        detail = f"={match.group(1)!r}" if match else ""
        issues.append(f"question doesn't mention {FILTER_COLUMN_LABELS[column]} but SQL applies a {column}{detail} filter")
    return issues


# Columns that exist ONLY on extractions - not review_id/cluster_id, which
# exist on both tables and so don't justify a join on their own.
EXTRACTIONS_ONLY_COLUMNS = {
    "friction_type", "trigger_moment", "mentions_price", "price_mentioned",
    "paid_but_still_limited", "would_pay_signal", "feature_praised", "gist",
    "in_estimation_frame", "in_discovery_frame", "selection_weight",
    "validation_status", "extracted_at", "elapsed_sec", "model_name",
    "prompt_version", "raw_output",
}

JOIN_EXTRACTIONS_RE = re.compile(
    r"FROM\s+extractions\s+(\w+)\s+JOIN\s+reviews\s+(\w+)\s+ON\s+.+?(?=\s+WHERE\b|\s+GROUP\b|\s+ORDER\b|\s+HAVING\b|$)",
    re.IGNORECASE,
)


def uses_extractions_only_column(sql):
    lower = sql.lower()
    return any(col in lower for col in EXTRACTIONS_ONLY_COLUMNS)


def remove_unnecessary_extractions_join(sql):
    """If the SQL joins extractions but references none of its own
    columns, that join only narrows the population to the ~1,035 sampled
    rows for no reason (measured: "how many reviews from Germany" came
    back 113 via an extractions join instead of the correct ~800 from
    reviews alone). Best-effort mechanical removal for the shape our own
    schema prompt actually produces (extractions first, reviews second);
    returns None if that shape isn't matched or the rewrite doesn't
    validate, so the caller can fall back instead of trusting a rewrite
    that might be broken."""
    if uses_extractions_only_column(sql):
        return None
    match = JOIN_EXTRACTIONS_RE.search(sql)
    if not match:
        return None
    e_alias, r_alias = match.group(1), match.group(2)
    fixed = f"{sql[:match.start()]}FROM reviews {r_alias}{sql[match.end():]}"
    # Any leftover reference to the extractions alias (e.g. COUNT(e.review_id))
    # is safe to repoint at the reviews alias - uses_extractions_only_column
    # already confirmed nothing extractions-exclusive is referenced here.
    fixed = re.sub(rf"\b{re.escape(e_alias)}\.", f"{r_alias}.", fixed)
    ok, cleaned = is_safe_select(fixed)
    return cleaned if ok else None


# Cached per db_path so a long-running process (the Flask app) reads these
# once, not on every question. Loaded from the database itself, not
# hardcoded, so validation can never drift from what's actually in it.
_VALID_VALUES_CACHE = {}


def load_valid_values(db_path):
    conn = get_connection(db_path)
    try:
        return {
            "app": {r[0] for r in conn.execute("SELECT DISTINCT app FROM reviews")},
            "country": {r[0] for r in conn.execute("SELECT DISTINCT country FROM reviews")},
            "friction_type": {
                r[0] for r in conn.execute("SELECT DISTINCT friction_type FROM extractions WHERE friction_type IS NOT NULL")
            },
            "trigger_moment": {
                r[0] for r in conn.execute("SELECT DISTINCT trigger_moment FROM extractions WHERE trigger_moment IS NOT NULL")
            },
            "would_pay_signal": {
                r[0] for r in conn.execute("SELECT DISTINCT would_pay_signal FROM extractions WHERE would_pay_signal IS NOT NULL")
            },
        }
    finally:
        conn.close()


def get_valid_values(db_path):
    if db_path not in _VALID_VALUES_CACHE:
        _VALID_VALUES_CACHE[db_path] = load_valid_values(db_path)
    return _VALID_VALUES_CACHE[db_path]


# Matches <optional alias.><validated column> compared to either a single
# quoted literal or an IN (...) list of them - the two shapes our own
# schema prompt's examples actually produce.
LITERAL_COLUMN_RE = re.compile(
    r"(?:\w+\.)?(app|country|friction_type|trigger_moment|would_pay_signal)\s*"
    r"(?:=|!=|<>|IN)\s*(\([^)]*\)|'(?:[^'\\]|\\.)*')",
    re.IGNORECASE,
)


def extract_literal_checks(sql):
    """(column, literal) for every string literal compared against one of
    the five validated columns, whether via = or an IN (...) list."""
    checks = []
    for match in LITERAL_COLUMN_RE.finditer(sql):
        column = match.group(1).lower()
        for literal in re.findall(r"'((?:[^'\\]|\\.)*)'", match.group(2)):
            checks.append((column, literal))
    return checks


def find_close_match(literal, valid_values):
    """Case-insensitive exact match first, then a substring match in
    either direction - catches a shortened value like 'Retake AI' for the
    real 'Retake AI Face & Selfie Editor'. Returns the corrected value, or
    None if zero or more than one candidate qualifies - an ambiguous match
    is treated the same as no match, since guessing which of two
    plausible values was meant isn't this function's job."""
    lit_lower = literal.lower()
    for v in valid_values:
        if v.lower() == lit_lower:
            return v
    candidates = [v for v in valid_values if lit_lower in v.lower() or v.lower() in lit_lower]
    return candidates[0] if len(candidates) == 1 else None


def validate_literals(sql, valid_values):
    """Checks every string literal compared against app/country/
    friction_type/trigger_moment/would_pay_signal against the real values
    read from the database - a literal matching no real row (measured:
    r.app = 'Retake AI' instead of 'Retake AI Face & Selfie Editor') would
    otherwise return an honest-looking zero silently instead of erroring.
    Runs before the query is ever executed. Returns (sql, corrections,
    rejection): rejection is None on success; corrections lists every
    literal this fixed on its own without asking the model again -
    swapping a value for its one unambiguous real counterpart doesn't need
    an LLM round trip, unlike a missing filter (which changes what the
    query means, not just how one value is spelled)."""
    corrections = []
    for column, literal in extract_literal_checks(sql):
        valid = valid_values.get(column)
        if not valid or literal in valid:
            continue
        fix = find_close_match(literal, valid)
        if fix:
            sql = re.sub(rf"'{re.escape(literal)}'", f"'{fix}'", sql)
            corrections.append(f"'{literal}' -> corrected to '{fix}'")
        else:
            values_list = ", ".join(sorted(valid))
            rejection = f"'{literal}' is not a valid value for column {column}. Valid values: {values_list}"
            return sql, corrections, rejection
    return sql, corrections, None


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
        return "Query returned no results."

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
            text=f"Generated SQL is not safe, not executed: {result}",
            sql=sql,
        )
    sql = result

    fixed_join_sql = remove_unnecessary_extractions_join(sql)
    if fixed_join_sql:
        sql = fixed_join_sql
        warnings.append("removed unnecessary extractions JOIN (query used no extractions-specific column)")
        if debug:
            print(f"[debug] join removed:\n{sql}\n")

    N_MISSING = "missing COUNT(*) AS n column - a rate cannot be reported without n"

    def collect_issues(candidate_sql):
        found = detect_filter_mismatches(question, candidate_sql)
        if looks_like_ratio_query(candidate_sql):
            found = found + ratio_query_issues(candidate_sql)
        return found

    def mechanical_fix(candidate_sql):
        """Every deterministic fix that doesn't need the model, applied in
        order: strip any filter condition the question never asked for
        (symmetric to the injection below - both are things we can just
        compute, not things that need the model to decide), then, if the
        record-count column is the only thing left missing, splice in
        COUNT(*) AS n. Returns (sql, warnings earned, remaining issues)."""
        local_warnings = []
        for column in extra_filter_columns(question, candidate_sql):
            fixed, removed_value = remove_unrequested_condition(candidate_sql, column)
            if fixed:
                candidate_sql = fixed
                local_warnings.append(f"removed {column}='{removed_value}' filter not present in the question")

        remaining = collect_issues(candidate_sql)
        if remaining == [N_MISSING]:
            fixed_n = inject_n_column(candidate_sql)
            if fixed_n:
                candidate_sql = fixed_n
                local_warnings.append("n column added automatically (COUNT(*) AS n)")
                remaining = []

        return candidate_sql, local_warnings, remaining

    # Order: mechanical fixes first (free, deterministic), LLM retry
    # second (needed when a fix requires understanding what the question
    # meant, not just computing a value), refusal last.
    sql, fix_warnings, issues = mechanical_fix(sql)
    warnings.extend(fix_warnings)
    if debug and fix_warnings:
        print(f"[debug] mechanical fixes applied: {fix_warnings}\n")

    if issues:
        reason = "; ".join(issues)
        retry_sql = generate_sql(question, host, retry_reason=reason, previous_sql=sql)
        if debug:
            print(f"[debug] retry SQL:\n{retry_sql}\n")
        ok2, result2 = is_safe_select(retry_sql)
        if ok2:
            fixed_join2 = remove_unnecessary_extractions_join(result2)
            if fixed_join2:
                result2 = fixed_join2
            result2, fix_warnings2, issues2 = mechanical_fix(result2)
        else:
            fix_warnings2, issues2 = [], [result2]
        if ok2 and not issues2:
            sql = result2
            warnings.extend(fix_warnings2)
            if debug and fix_warnings2:
                print(f"[debug] mechanical fixes applied after retry: {fix_warnings2}\n")
        else:
            return Answer(
                query_type="AGGREGATE",
                text=(
                    "Generated SQL didn't meet the question's requirements after two attempts "
                    f"({'; '.join(issues2) if ok2 else issues[0]}); not executed."
                ),
                sql=retry_sql,
                warnings=["SQL validation failed: " + "; ".join(issues2 if ok2 else issues)],
            )

    valid_values = get_valid_values(db_path)
    sql, literal_corrections, rejection = validate_literals(sql, valid_values)
    if debug and literal_corrections:
        print(f"[debug] literal corrections: {literal_corrections}\n")
    if rejection:
        return Answer(
            query_type="AGGREGATE",
            text=f"Generated SQL not executed: {rejection}",
            sql=sql,
            warnings=warnings,
        )
    warnings.extend(literal_corrections)

    try:
        columns, rows = run_select(sql, db_path)
    except sqlite3.Error as exc:
        return Answer(query_type="AGGREGATE", text=f"SQL execution failed: {exc}", sql=sql)

    if debug:
        print(f"[debug] raw result: columns={columns} rows={rows}\n")

    text = format_aggregate_text(columns, rows)
    n = extract_n(columns, rows)
    warnings.extend(low_n_warnings(columns, rows))
    if looks_like_ratio_query(sql):
        warnings.append("estimation frame, weighted")
    if n is None:
        warnings.append("record count (n) could not be extracted from the SQL output")

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


def load_corpus(conn, country=None, field_filter=None):
    """country and field_filter both filter the search pool BEFORE
    similarity is computed - not after. Filtering after the fact would
    just be a smaller top-K over the same skewed ranking; filtering the
    pool is what actually lets a Turkish-phrased question reach Japanese
    reviews, or a "vazgeçen kullanıcılar" question reach only
    would_pay_signal='conditional' rows instead of the whole corpus.

    field_filter's field name is never user-supplied text - it only ever
    comes from FIELD_KEYWORD_RULES, a fixed constant in this file - so
    interpolating it into the query is not an injection risk."""
    query = """
        SELECT e.review_id, e.vector, r.body, r.country, r.rating, r.app
        FROM embeddings e JOIN reviews r ON r.review_id = e.review_id
    """
    conditions = []
    params = []
    if field_filter:
        field_name, field_value = field_filter
        query += " JOIN extractions ext ON ext.review_id = e.review_id"
        conditions.append(f"ext.{field_name} = ?")
        params.append(field_value)
    if country:
        conditions.append("r.country = ?")
        params.append(country)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    rows = conn.execute(query, params).fetchall()
    if not rows:
        where = f" (country={country!r}, field_filter={field_filter!r})" if (country or field_filter) else ""
        raise RuntimeError(f"no embeddings found{where} - run src/embed.py first")
    review_ids = [r[0] for r in rows]
    vectors = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
    bodies = [r[2] for r in rows]
    countries = [r[3] for r in rows]
    ratings = [r[4] for r in rows]
    apps = [r[5] for r in rows]
    norm_vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    return review_ids, norm_vectors, bodies, countries, ratings, apps


# ---------------------------------------------------------------------------
# Part 6.5: raw filtered + ranked listing over the English translation pool
# ---------------------------------------------------------------------------
#
# Summary generation, the summaries-table lookup, and the "precomputed"
# badge are gone (see README) - live synthesis on gemma3:4b was too slow
# for interactive use, and a one-sentence summary carries less than the
# reviews themselves. Text questions now search only the translations/
# embeddings_en pool: every valid extraction's review body, translated to
# English once by hand (translations.translated_by='claude' - see README),
# then embedded with nomic-embed-text (src/embed.py --english) so the pool
# is monolingual. The country-pre-filter-then-multilingual-fanout machinery
# just above (load_corpus, FANOUT_LANGUAGES, COUNTRY_LANGUAGE, the two
# similarity thresholds) is no longer called from this path - kept in
# place, not deleted, since it is exactly what this project would need
# again if the qualitative pool ever goes back to being multilingual.
#
# translate_query IS still called from here, just always toward English
# now instead of toward whatever language a named country implied: the
# pool is English-only, so a non-English question has to be translated
# before embedding or the match degrades (measured: a Turkish question
# embedded directly against the English pool ranked generic positive
# reviews above the on-topic ones - cross-lingual similarity alone wasn't
# enough, contrary to the initial assumption that a monolingual pool would
# make translation unnecessary).


def is_likely_english(question):
    """Cheap, no-LLM heuristic: True when the question has no non-ASCII
    character. Every real question in this system is typed in Turkish or
    English, and Turkish all but always uses at least one of ğ/ı/ş/ç/ö/ü -
    so a pure-ASCII question is treated as already English and the
    translation call below is skipped for it."""
    return question.isascii()


def detect_text_filters(question):
    """(country, app, field_name, field_value) detected in the question,
    each None when not matched. Reuses the exact same detectors as the
    AGGREGATE path and the rest of this module (detect_countries,
    matched_app, detect_structured_field) - the question is parsed once,
    not by a second parser. More than one country named is treated as no
    country filter, the same ambiguity convention used everywhere else in
    this file."""
    normalized = _normalize_for_match(question)
    countries = detect_countries(question)
    country = next(iter(countries)) if len(countries) == 1 else None
    app = matched_app(normalized)
    field = detect_structured_field(question)
    field_name, field_value = field if field else (None, None)
    return country, app, field_name, field_value


def load_text_pool(conn, country, app, field_name, field_value):
    """Every translated, embedded review matching the detected filters,
    AND'ed together. translations only ever holds review_ids from valid
    extractions (see README), so no separate validation_status check is
    needed on top of that join. field_name is never user-supplied text -
    it only ever comes from FIELD_KEYWORD_RULES, a fixed constant in this
    file - so interpolating it into the query is not an injection risk."""
    query = """
        SELECT t.review_id, t.text_en, t.source_lang, r.body, r.country, r.rating, r.app,
               e.friction_type, e.would_pay_signal, em.vector
        FROM translations t
        JOIN reviews r ON r.review_id = t.review_id
        JOIN extractions e ON e.review_id = t.review_id
        JOIN embeddings_en em ON em.review_id = t.review_id
    """
    conditions = []
    params = []
    if country:
        conditions.append("r.country = ?")
        params.append(country)
    if app:
        conditions.append("r.app = ?")
        params.append(app)
    if field_name:
        conditions.append(f"e.{field_name} = ?")
        params.append(field_value)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    return conn.execute(query, params).fetchall()


def pool_totals(conn):
    """(translated pool size, full substantive-review count) - always real
    SQL counts, never hardcoded, so the pool line stays correct as both
    tables grow."""
    total_pool = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
    total_substantive = conn.execute("SELECT COUNT(*) FROM reviews WHERE is_substantive = 1").fetchone()[0]
    return total_pool, total_substantive


def answer_qualitative(question, host, db_path, debug=False):
    country, app, field_name, field_value = detect_text_filters(question)
    warnings = []

    # One line, always present, right above the pool line - so the user
    # can see at a glance whether what they asked actually matched a
    # filter, not just trust that it did.
    active_filters = []
    if country:
        active_filters.append(f"country={country}")
    if app:
        active_filters.append(f"app={app}")
    if field_name:
        active_filters.append(f"{field_name}={field_value}")
    filters_line = "filters: " + (", ".join(active_filters) if active_filters else "none")

    if country:
        warnings.append(f"country filter: {country}")
    if app:
        warnings.append(f"app filter: {app}")
    if field_name:
        warnings.append(f"field filter: {field_name}='{field_value}'")

    conn = get_connection(db_path)
    try:
        rows = load_text_pool(conn, country, app, field_name, field_value)
        total_pool, total_substantive = pool_totals(conn)
    finally:
        conn.close()

    matched = len(rows)
    pool_line = (
        f"{matched} reviews matched — from {total_pool} extracted records "
        f"({total_substantive} substantive reviews total)"
    )

    if debug:
        print(f"[debug] filters: country={country} app={app} field={field_name}={field_value}")
        print(f"[debug] {matched} rows matched before ranking\n")

    if matched == 0:
        return Answer(query_type="QUALITATIVE", text=f"{filters_line}\n{pool_line}", n=0, warnings=warnings)

    vectors = np.stack([np.frombuffer(r[9], dtype=np.float32) for r in rows])
    norm_vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    # The pool is English-only (see module note above), so a non-English
    # question has to be translated to English before embedding, or the
    # match degrades - skip the call only when the question is already
    # English (is_likely_english), the same reuse of translate_query the
    # multilingual path above used, just always toward English now.
    if is_likely_english(question):
        search_text = question
    else:
        search_text = translate_query(question, "English", host)
        warnings.append(f"query translated to English: '{search_text}'")

    query_vector = embed_text(search_text, host)
    sims = norm_vectors @ query_vector
    order = np.argsort(-sims)[:QUALITATIVE_TOP_K_RESULTS]

    records = []
    for i in order:
        review_id, text_en, source_lang, body, r_country, rating, r_app, friction_type, would_pay_signal, _vec = rows[i]
        records.append({
            "review_id": review_id,
            "text_en": text_en,
            "source_lang": source_lang,
            "body": body,
            "country": r_country,
            "rating": rating,
            "app": r_app,
            "friction_type": friction_type,
            "would_pay_signal": would_pay_signal,
        })

    text = f"{filters_line}\n{pool_line}"
    if matched > QUALITATIVE_TOP_K_RESULTS:
        text += f"\nShowing {QUALITATIVE_TOP_K_RESULTS} of {matched}."

    return Answer(
        query_type="QUALITATIVE",
        text=text,
        review_ids=[r["review_id"] for r in records],
        n=matched,
        records=records,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Entry point - this is what a future Flask route calls
# ---------------------------------------------------------------------------


AIMLESS_REJECTION_TEXT = "This question doesn't point to a specific topic. Name an app, country, or friction type."


def answer(question, host=OLLAMA_HOST, db_path=DB_PATH, debug=False):
    # Checked before routing at all, so a question like "ne önerirsin" (no
    # topic, country, app, or field) never reaches either path - it can't
    # be misrouted to AGGREGATE and produce nonsense SQL, and it doesn't
    # depend on the (measured-flaky) LLM router's classification either.
    if is_aimless_question(question):
        return Answer(query_type="QUALITATIVE", text=AIMLESS_REJECTION_TEXT, n=0)

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
        result = Answer(query_type=query_type, text=f"Could not answer the question: {exc}")

    if classify_warning:
        result.warnings.insert(0, classify_warning)
    return result


# ---------------------------------------------------------------------------
# CLI - prints what answer() returns, nothing more
# ---------------------------------------------------------------------------


def print_answer(result):
    print(f"[{result.query_type}]\n")
    # text holds the pool line (+ "Showing N of M.") for QUALITATIVE, or
    # AGGREGATE's formatted result / a rejection message.
    if result.text:
        print(result.text)

    if result.records:
        print("\nrecords:")
        for r in result.records:
            print(
                f"\n  [{r['country']} · {r['rating']}★ · {r['review_id']} · "
                f"friction_type={r['friction_type']} · would_pay_signal={r['would_pay_signal']}]"
            )
            print(f"  {r['text_en']}")
            if r["source_lang"] != "en":
                lang = LANGUAGE_NAMES.get(r["source_lang"], r["source_lang"])
                print(f"  (translated from {lang}: {r['body']})")

    if result.n is not None:
        print(f"\nn={result.n} records")

    if result.sql:
        print(f"\nSQL:\n{result.sql}")

    if result.review_ids and not result.records:
        print(f"\nsource review_ids: {', '.join(result.review_ids)}")

    if result.country_distribution:
        print("\ncountry distribution (approximation for language):")
        for country, info in sorted(result.country_distribution.items(), key=lambda kv: -kv[1]["n"]):
            print(f"  {country}: {info['n']} ({info['pct']}%)")

    if result.warnings:
        print("\nwarnings:")
        for w in result.warnings:
            print(f"  - {w}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", help="question in natural language")
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--host", default=OLLAMA_HOST)
    parser.add_argument("--debug", action="store_true", help="print intermediate steps (classification, SQL, similarity scores)")
    args = parser.parse_args()

    check_ollama_health(args.host)
    result = answer(args.question, host=args.host, db_path=args.db, debug=args.debug)
    print_answer(result)


if __name__ == "__main__":
    main()
