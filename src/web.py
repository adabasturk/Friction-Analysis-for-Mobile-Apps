"""Flask web UI for src/ask.py's answer(). Single page, one search box.

This file owns presentation only: the page template, the /ask JSON
endpoint, and how an Answer gets displayed. All question-answering logic -
routing, SQL generation and validation, embedding search, translation,
every honesty check - lives in ask.py and is reached only through
answer(). Nothing here reimplements it.

Usage:
    python src/web.py
    -> http://localhost:8000
"""

import json

from flask import Flask, jsonify, request

from ask import DB_PATH, LANGUAGE_NAMES, OLLAMA_HOST, answer, check_ollama_health

app = Flask(__name__)

EXAMPLE_QUESTIONS = [
    "Who is Codeway's CEO?",
    "What is Nova's paywall complaint rate?",
    "How many reviews did you collect?",
    "What do Brazilian users say about pricing?",
    "Why did Brazilian users who almost paid change their mind?",
]


# Exact string ask.py's answer() emits for the one QUALITATIVE rejection
# that still happens before any filtering/ranking (no country/app/field
# signal at all) - used below without touching ask.py itself. Part 6.5:
# a filtered-but-empty result is no longer a rejection, it's a pool line
# reading "0 reviews matched" - handled by result.n == 0 below, not here.
AIMLESS_REJECTION_TEXT = "This question doesn't point to a specific topic. Name an app, country, or friction type."
WEIGHTED_RATE_NOTE = "estimation frame, weighted"


def display_text(result):
    return result.text


def footer_note(result):
    """The one small-print line under the answer. For QUALITATIVE the pool
    line in the main text already states the match count, so this is only
    needed for the zero-match case and for AGGREGATE's weighted-rate note."""
    if result.query_type == "QUALITATIVE":
        if result.text == AIMLESS_REJECTION_TEXT:
            return None
        if result.n == 0:
            return "no reviews matched these filters"
        return None

    if result.query_type == "AGGREGATE":
        if WEIGHTED_RATE_NOTE in result.warnings and result.n:
            return f"based on {result.n} randomly sampled reviews"
        return None

    return None


def display_records(result):
    """result.records, reshaped for the page: a ready-made display note
    ("translated from Japanese") instead of a raw source_lang code, and
    only the fields the page actually renders. Full text throughout, by
    design - no truncation."""
    records = []
    for r in result.records:
        lang = r["source_lang"]
        records.append({
            "review_id": r["review_id"],
            "country": r["country"],
            "rating": r["rating"],
            "friction_type": r["friction_type"],
            "text_en": r["text_en"],
            "body": r["body"],
            "translated_note": None if lang == "en" else f"translated from {LANGUAGE_NAMES.get(lang, lang)}",
        })
    return records


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mobile Apps: Funnel Friction Analysis — Q&A</title>
<style>
  :root {
    --bg: #faf7f2;
    --panel: #f1ece3;
    --text: #211d17;
    --muted: #6b6255;
    --accent: #b5502f;
    --border: #ddd3c4;
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    padding: 48px 24px 96px;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    line-height: 1.55;
  }

  main {
    max-width: 70ch;
    margin: 0 auto;
  }

  h1 {
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0 0 8px;
  }

  p.subtitle {
    color: var(--muted);
    margin: 0 0 40px;
  }

  form {
    display: flex;
    gap: 8px;
    margin-bottom: 24px;
  }

  input[type="text"] {
    flex: 1;
    font-size: 1rem;
    padding: 14px 16px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: #fff;
    color: var(--text);
  }

  input[type="text"]:focus {
    outline: none;
    border-color: var(--accent);
  }

  button {
    font-size: 1rem;
    padding: 14px 20px;
    border: none;
    border-radius: 6px;
    background: var(--accent);
    color: #fff;
    cursor: pointer;
  }

  button:hover {
    opacity: 0.9;
  }

  .examples {
    margin-bottom: 40px;
  }

  .examples-label {
    font-size: 0.85rem;
    color: var(--muted);
    margin-bottom: 8px;
  }

  .example-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .example-btn {
    background: var(--panel);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 0.85rem;
    cursor: pointer;
  }

  .example-btn:hover {
    border-color: var(--accent);
    opacity: 1;
  }

  #loading {
    color: var(--muted);
    margin-bottom: 24px;
  }

  #loading[hidden] { display: none; }

  #result[hidden], #error[hidden] { display: none; }

  .query-type {
    display: inline-block;
    font-size: 0.75rem;
    letter-spacing: 0.05em;
    color: var(--muted);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 2px 8px;
    margin-bottom: 12px;
  }

  .answer-text {
    font-size: 1.05rem;
    white-space: pre-wrap;
    margin-bottom: 20px;
  }

  .field {
    margin-bottom: 14px;
  }

  .footer-note {
    font-size: 0.8rem;
    color: var(--muted);
    margin-top: 20px;
  }

  .record-block {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px 14px;
    margin-bottom: 10px;
  }

  .record-meta {
    font-size: 0.75rem;
    color: var(--muted);
    margin-bottom: 6px;
  }

  .record-text {
    white-space: pre-wrap;
  }

  .record-lang-note {
    font-size: 0.75rem;
    color: var(--muted);
    margin-top: 6px;
  }

  .record-original summary {
    font-size: 0.75rem;
    color: var(--accent);
    cursor: pointer;
    margin-top: 4px;
  }

  .record-original div {
    white-space: pre-wrap;
    font-size: 0.9rem;
    color: var(--muted);
    margin-top: 6px;
  }
</style>
</head>
<body>
<main>
  <h1>Mobile Apps: Funnel Friction Analysis</h1>
  <p class="subtitle">Ask questions over App Store reviews</p>

  <form id="ask-form">
    <input type="text" id="question" name="question" placeholder="Ask a question..." autocomplete="off">
    <button type="submit">Ask</button>
  </form>

  <div class="examples">
    <div class="examples-label">example questions</div>
    <div class="example-list" id="example-list"></div>
  </div>

  <div id="loading" hidden>Preparing answer... (gemma3:4b is running on CPU on this machine, can take 10-60 seconds)</div>

  <div id="error" hidden></div>

  <div id="result" hidden>
    <div class="query-type" id="r-query-type"></div>
    <div class="answer-text" id="r-text"></div>

    <div class="field" id="r-records-field" hidden>
      <div id="r-records"></div>
    </div>

    <div class="footer-note" id="r-footer" hidden></div>
  </div>
</main>

<script>
const EXAMPLES = __EXAMPLES_JSON__;

const form = document.getElementById("ask-form");
const input = document.getElementById("question");
const loading = document.getElementById("loading");
const errorBox = document.getElementById("error");
const result = document.getElementById("result");
const exampleList = document.getElementById("example-list");

EXAMPLES.forEach((q) => {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "example-btn";
  btn.textContent = q;
  btn.addEventListener("click", () => {
    input.value = q;
    runQuery(q);
  });
  exampleList.appendChild(btn);
});

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (q) runQuery(q);
});

function setHidden(id, hidden) {
  document.getElementById(id).hidden = hidden;
}

function renderResult(data) {
  document.getElementById("r-query-type").textContent = data.query_type || "";
  document.getElementById("r-text").textContent = data.text || "";

  const records = data.records || [];
  setHidden("r-records-field", records.length === 0);
  const recordsEl = document.getElementById("r-records");
  recordsEl.textContent = "";
  records.forEach((r) => {
    const block = document.createElement("div");
    block.className = "record-block";

    const meta = document.createElement("div");
    meta.className = "record-meta";
    meta.textContent = `${r.country} · ${r.rating}★ · ${r.review_id} · friction_type=${r.friction_type}`;
    block.appendChild(meta);

    const text = document.createElement("div");
    text.className = "record-text";
    text.textContent = r.text_en;
    block.appendChild(text);

    if (r.translated_note) {
      const note = document.createElement("div");
      note.className = "record-lang-note";
      note.textContent = r.translated_note;
      block.appendChild(note);

      const details = document.createElement("details");
      details.className = "record-original";
      const summary = document.createElement("summary");
      summary.textContent = "show original";
      const original = document.createElement("div");
      original.textContent = r.body;
      details.appendChild(summary);
      details.appendChild(original);
      block.appendChild(details);
    }

    recordsEl.appendChild(block);
  });

  const hasFooter = !!data.footer_note;
  setHidden("r-footer", !hasFooter);
  if (hasFooter) document.getElementById("r-footer").textContent = data.footer_note;

  result.hidden = false;
}

async function runQuery(question) {
  errorBox.hidden = true;
  result.hidden = true;
  loading.hidden = false;

  try {
    const resp = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await resp.json();
    loading.hidden = true;

    if (!resp.ok) {
      errorBox.textContent = data.error || "Unknown error";
      errorBox.hidden = false;
      return;
    }
    renderResult(data);
  } catch (err) {
    loading.hidden = true;
    errorBox.textContent = "Request failed: " + err;
    errorBox.hidden = false;
  }
}
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return PAGE.replace("__EXAMPLES_JSON__", json.dumps(EXAMPLE_QUESTIONS, ensure_ascii=False))


@app.route("/ask", methods=["POST"])
def ask_endpoint():
    data = request.get_json(force=True, silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question cannot be empty"}), 400

    try:
        result = answer(question, host=OLLAMA_HOST, db_path=DB_PATH)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the page instead of a bare 500
        return jsonify({"error": f"Could not answer the question: {exc}"}), 500

    return jsonify(
        {
            "query_type": result.query_type,
            "text": display_text(result),
            "records": display_records(result),
            "footer_note": footer_note(result),
        }
    )


if __name__ == "__main__":
    check_ollama_health(OLLAMA_HOST)
    app.run(host="127.0.0.1", port=8000, debug=False)
