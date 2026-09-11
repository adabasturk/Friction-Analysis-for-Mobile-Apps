# friction-atlas

## Project

An analysis pipeline that measures conversion friction (paywall, pricing, onboarding)
in AI mobile apps using App Store reviews. It compares two Turkish app studios
(Codeway, HubX) as matched pairs within the same verticals. Final output: data-backed
A/B test hypotheses.

This is a portfolio project. The defensibility of the findings matters as much as
the quality of the code.

## App set

Two matched pairs, four apps total. No control apps.

- **chatbot**: Chat AI (Codeway, app_id 1668787639) vs Nova (HubX, app_id 1669007652)
- **face**: Retake AI (Codeway, app_id 6466298983) vs ReShoot (HubX, app_id 6751296351)

### Temporal comparability

The RSS feed returns up to 500 reviews per app per country, but the time window
those 500 reviews span varies with how fast an app collects reviews (measured
range across candidates: 14 to 1255 days). Pairs whose windows differ by more
than 3x are not comparable — this is why a third pair (education) was dropped
from the study. The two pairs above measure 1.05x and 2.3x, so no clipping is
needed.

Never use App Store `userRatingCount` as a measure of current review activity —
it is cumulative over the app's entire lifetime. Use reviews-per-day computed
from the collected sample instead.

## Hardware constraints — base every technical decision on these

- Intel MacBook Pro 2020, 1.4 GHz i5, 8 GB RAM
- NO GPU acceleration. Ollama runs on CPU.
- Do NOT suggest torch, transformers, spacy large models, or sentence-transformers.
  They either fail to install or lock up the machine.
- Ask before adding any dependency. Keep requirements.txt minimal.

## Stack

- Python 3.11+
- LLM: Ollama, `gemma3:4b` (production), `nomic-embed-text` (embeddings)
  Chosen by benchmark, not by default: gemma3:4b scored 7/8 on friction_type and 8/8
  on would_pay_signal against qwen2.5:3b (6/8, 6/8), llama3.2:3b (3/8, 6/8) and
  granite3.3:2b (4/8, 7/8). It runs ~16 s/record on this machine versus ~7 s for the
  others; for a one-time batch job that trade is worth it.
- Ollama endpoint: http://localhost:11434
- Database: SQLite. Do NOT set up Docker, PostgreSQL, or a vector database —
  unnecessary weight for a single-user analysis project.
- Plotting: matplotlib
- Web output: vanilla HTML/CSS. No React, Next.js, or Tailwind.

## Code rules

1. Each script does one job and runs standalone, e.g. `python src/embed.py`.
   No notebooks.
2. Every long-running operation checkpoints. If a script is interrupted it resumes
   where it stopped rather than starting over.
3. Scripts are idempotent. Running the same script twice must not create duplicates.
4. Long operations show a tqdm progress bar.
5. Network calls are fault-tolerant: on a 404 or empty response, log it and continue
   instead of crashing.
6. Include a `--limit` flag so small test runs are possible.

## Data integrity rules — this is the core of the project

1. NEVER INVENT A METRIC. How every number is computed must be traceable in the code.
   Do not fabricate derived scores of the "maturity score" variety that sound
   meaningful but carry no information.
2. Never trust LLM output directly. Validate every JSON response against the schema,
   check enum fields, count failed records and report them.
3. Show the n value next to every percentage and every chart. Review volume across
   apps is very uneven, so comparing absolute counts is misleading.
4. If a number rests on insufficient data (n < 30), flag it visibly.
5. When asking the LLM to produce hypotheses or commentary, pass only real computed
   numbers in the prompt. Do not let the model generate numbers.

## Ollama usage

- Always use `format="json"` when structured output is required. Validated at ~16 s
  per record on this machine with a 6-field schema; a 600-record batch takes ~2.5 hours.
- `gemma3:4b` has no thinking mode, so no `think` parameter or `/no_think` prompt
  switch is needed. Do not reintroduce a reasoning model here — this task requires
  reading comprehension, not reasoning, and thinking traces triple CPU runtime.
- Make LLM calls inside batch scripts, not in interactive code.

## Extraction principle — do not ask the LLM for what the data already contains

Every review carries a 1–5 star rating from Apple. Never ask the model to infer
sentiment: use `rating` from the reviews table instead. Benchmarking showed all four
candidate models disagreeing with human sentiment labels in the same direction, which
means the field is ambiguous rather than hard — a bad question to ask a model.

Spend LLM calls only on what the star rating cannot express: which friction, at which
moment, and how close the user was to paying.

## How we work

- One stage at a time. I move step by step.
- Do NOT run long scripts (collection, embedding, extraction) yourself. Write them
  and tell me how to run them; I'll start them in my own terminal.
- Say in one sentence what you're about to do before writing code.
- Don't assume when you're unsure. Ask.

## Folder structure

config/     apps.json and other configuration
src/        all scripts
data/raw/   raw JSON (gitignored)
data/       friction.db, embeddings.npy
output/     csv, charts, reports
site/       static page for publishing