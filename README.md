# Mobile Apps: Funnel Friction Analysis

Conversion-friction analysis from App Store reviews, comparing two Turkish AI app studios as matched pairs within the same verticals.

Comparing arbitrary popular apps can't separate a studio's monetization choices from category norms. Holding the vertical fixed (chatbot vs chatbot, face editor vs face editor) makes the remaining difference attributable to the studio itself, not the category it competes in.

## Demo

<video src="demo/demo-short.mp4" controls></video>

Full walkthrough — all eight example questions: [demo-full.mp4](demo/demo-full.mp4)

Numeric questions mostly run live-generated SQL, or resolve through a fixed template for comparison-shaped ones; text questions apply a filter and list the matching reviews with their translation and metadata; when there's no data to answer a question, the system says so rather than answering anyway.

## Runs entirely locally at runtime

No external API calls at runtime. `gemma3:4b` (structured extraction), `nomic-embed-text` (embeddings), Ollama, SQLite. Hardware: 2020 MacBook Pro, Intel i5, 8 GB RAM, no GPU. 998 records were extracted over two nights, 6 hours 41 minutes of LLM time. The model was chosen by benchmarking four candidates, not by default — see [FINDINGS.md](FINDINGS.md) for the comparison.

One exception, outside the runtime path: the query layer's qualitative pool (1,022 reviews) was translated to English once, by hand, with Claude — not Ollama, and not at query time. Nothing in the running system calls an external API; that translation pass was a one-time data-preparation step, done ahead of time the same way the hand-labelled benchmark set above was.

## Findings

- The studio difference isn't uniform — it's absent in the chatbot pair, present in the face-editor pair
- Paywall timing provokes a harsher reaction than price
- Face editors stop the user before they've even seen the product

Full write-up, method and limitations: [FINDINGS.md](FINDINGS.md)

![paywall_timing rate by app](output/charts/paywall_timing_rate.png)
![rating distribution by app](output/charts/rating_distribution.png)

## Query layer

Flask UI plus a CLI (`src/ask.py`). Numeric questions are routed to live-generated SQL, always shown back to the user, with rate queries restricted to the stratified estimation frame and weighted accordingly.

Text questions no longer get a generated summary at all — gemma3:4b was too slow for live synthesis, and a one-sentence summary carries less than the reviews themselves. Instead, the question is turned into a filter (country / app / friction type or would-pay signal, reusing the same keyword detectors as the SQL path), the filtered pool is ranked by semantic similarity, and the top 25 matching reviews are returned as-is — original text, English translation, country, star rating, `review_id`, `friction_type`, `would_pay_signal` — with the match count always shown against the full pool size (`N reviews matched — from 1,022 extracted records (6,961 substantive reviews total)`).

That pool is `translations` + `embeddings_en`: every valid extraction's review body translated to English once, by hand (`translated_by='claude'`), ahead of time, then embedded with `nomic-embed-text` via `python src/embed.py --english`. A non-English question is translated to English with a single live call (reusing the project's existing translation mechanism, just always targeting English now — skipped when the question is already English) before it's embedded and ranked against that pool; embedding a non-English question directly against the English-only pool was tried first and ranked generic positive reviews above on-topic ones, so the translation call stays. The project's older multilingual search path (per-query translation toward a country's own language, country-language fan-out) is still in `src/ask.py`, just no longer called from here.

Every QUALITATIVE answer also opens with a `filters: ...` line naming exactly which country/app/friction-type/would-pay-signal filter was detected (or `filters: none`), so a mismatch between what was asked and what was matched is visible immediately rather than discovered by reading the records.

## Setup

```bash
pip install -r requirements.txt          # dependencies
python src/collect_reviews.py            # fetch App Store reviews into data/raw/
python src/db.py && python src/load_to_db.py  # create schema, load reviews into SQLite
python src/embed.py                      # embed reviews with nomic-embed-text
python src/cluster.py --k 12 --save      # cluster embeddings, persist cluster_id
python src/sample.py                     # select the stratified + purposive extraction sample
python src/extract.py --frame all        # run structured LLM extraction (long-running)
python src/analyze.py                    # compute weighted rates, CIs, charts, observations.csv
python src/hypotheses.py --engine ollama # generate A/B test hypotheses from observations.csv
#   (translations table: every valid extraction's review body translated to English by
#   hand, not by a script - see "Query layer" above; translated_by='claude' in the DB)
python src/embed.py --english            # embed translations.text_en (the query layer's qualitative pool)
python src/ask.py "your question"        # or: python src/web.py, for the browser UI
```

## Repo layout

```
config/     apps.json and other configuration
src/        all scripts
data/raw/   raw JSON (gitignored)
data/       friction.db, embeddings.npy
output/     csv, charts, reports
site/       static page for publishing
```

`output/hypotheses_ollama.md` and `output/hypotheses_claude.md` are hypotheses generated from the exact same observations by two different models — kept side by side in the repo for comparison.
