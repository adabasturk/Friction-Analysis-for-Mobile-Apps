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

from ask import DB_PATH, OLLAMA_HOST, answer, check_ollama_health

app = Flask(__name__)

EXAMPLE_QUESTIONS = [
    "Codeway'in CEO'su kim?",
    "Nova'nın paywall şikâyeti oranı nedir?",
    "kaç yorum topladın?",
    "Brezilyalı kullanıcılar fiyat hakkında ne diyor",
    "Japon kullanıcılar iptal hakkında ne diyor",
]


# Exact strings ask.py's answer() emits - used below to recognize a
# rejection and a weighted-rate answer without touching ask.py itself.
# ask.py keeps returning full detail (the threshold, translation note,
# "0 kayda dayanıyor", full warnings list) for the CLI; this file just
# doesn't put all of it on screen. Simplification lives here, not there.
QUALITATIVE_REJECTION_PREFIX = "Bu soruyu yanıtlayacak veri yok"
WEIGHTED_RATE_NOTE = "kestirim çerçevesi, ağırlıklı"


def display_text(result):
    """Same rejection, minus the technical parenthetical (similarity
    score, threshold, filter state) - that detail is for the CLI/debug
    audience, not this screen."""
    if result.query_type == "QUALITATIVE" and result.text.startswith(QUALITATIVE_REJECTION_PREFIX):
        return "Bu soruyu yanıtlayacak veri yok."
    return result.text


def footer_note(result):
    """The one small-print line under the answer, replacing the removed
    threshold/translation/n=0 detail with something a non-technical reader
    can use: how many reviews this rests on, in plain words."""
    if result.query_type == "QUALITATIVE":
        if result.text.startswith(QUALITATIVE_REJECTION_PREFIX):
            return "yeterince yakın eşleşme bulunamadı"
        if result.n:
            return f"{result.n} yorumdan derlendi"
        return None

    if result.query_type == "AGGREGATE":
        if WEIGHTED_RATE_NOTE in result.warnings and result.n:
            return f"rastgele seçilmiş {result.n} yorum üzerinden"
        return None

    return None


PAGE = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Friction Atlas — Soru-Cevap</title>
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

  .field-label {
    font-size: 0.8rem;
    color: var(--muted);
    margin-bottom: 4px;
  }

  .review-ids {
    font-size: 0.85rem;
    color: var(--muted);
    word-break: break-word;
  }

  .footer-note {
    font-size: 0.8rem;
    color: var(--muted);
    margin-top: 20px;
  }
</style>
</head>
<body>
<main>
  <h1>Friction Atlas</h1>
  <p class="subtitle">App Store yorumları üzerinde soru-cevap</p>

  <form id="ask-form">
    <input type="text" id="question" name="question" placeholder="Bir soru sorun..." autocomplete="off">
    <button type="submit">Sor</button>
  </form>

  <div class="examples">
    <div class="examples-label">örnek sorular</div>
    <div class="example-list" id="example-list"></div>
  </div>

  <div id="loading" hidden>Yanıt hazırlanıyor... (gemma3:4b bu makinede CPU üzerinde çalışıyor, 10–60 saniye sürebilir)</div>

  <div id="error" hidden></div>

  <div id="result" hidden>
    <div class="query-type" id="r-query-type"></div>
    <div class="answer-text" id="r-text"></div>

    <div class="field" id="r-review-ids-field" hidden>
      <div class="field-label">kaynak review_id'ler</div>
      <div class="review-ids" id="r-review-ids"></div>
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

function fillList(id, items) {
  const el = document.getElementById(id);
  el.textContent = "";
  items.forEach((item, i) => {
    if (i > 0) el.appendChild(document.createTextNode(", "));
    el.appendChild(document.createTextNode(item));
  });
}

function renderResult(data) {
  document.getElementById("r-query-type").textContent = data.query_type || "";
  document.getElementById("r-text").textContent = data.text || "";

  const hasReviewIds = data.review_ids && data.review_ids.length > 0;
  setHidden("r-review-ids-field", !hasReviewIds);
  if (hasReviewIds) fillList("r-review-ids", data.review_ids);

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
      errorBox.textContent = data.error || "Bilinmeyen hata";
      errorBox.hidden = false;
      return;
    }
    renderResult(data);
  } catch (err) {
    loading.hidden = true;
    errorBox.textContent = "İstek başarısız: " + err;
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
        return jsonify({"error": "soru boş olamaz"}), 400

    try:
        result = answer(question, host=OLLAMA_HOST, db_path=DB_PATH)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the page instead of a bare 500
        return jsonify({"error": f"Soru yanıtlanamadı: {exc}"}), 500

    return jsonify(
        {
            "query_type": result.query_type,
            "text": display_text(result),
            "review_ids": result.review_ids,
            "footer_note": footer_note(result),
        }
    )


if __name__ == "__main__":
    check_ollama_health(OLLAMA_HOST)
    app.run(host="127.0.0.1", port=8000, debug=False)
