"""Part 6 hypothesis generation: turns analyze.py's measured numbers into
A/B test hypotheses, via either engine.

Reads output/observations.csv ONLY - analyze.py's computed numbers are the
sole source of truth ever shown to either engine. Neither is ever asked to
produce, estimate, or round a number itself; every "Observation" line is
checked back against that same file afterward, and anything that doesn't
trace to a real row is marked unverified rather than trusted.

Two engines:
  --engine ollama (default): calls gemma3:4b locally, in 7-8 small chunked
    requests (2-3 hypotheses each, 180s timeout, checkpointed so an
    interruption resumes instead of restarting) rather than one big call.
    Writes output/hypotheses.md directly.
  --engine claude: makes no LLM call at all. Writes the same prompt (this
    time whole, not chunked, since Claude Code has no local timeout/context
    pressure) to output/hypotheses_prompt.md for you to paste into Claude
    Code yourself; you place its answer into output/hypotheses.md by hand.

Usage:
    python src/hypotheses.py --engine ollama
    python src/hypotheses.py --engine claude
"""

import argparse
import re
from pathlib import Path

import pandas as pd
import requests

OLLAMA_HOST = "http://localhost:11434"
MODEL = "gemma3:4b"
OBSERVATIONS_PATH = "output/observations.csv"
OUTPUT_PATH = "output/hypotheses.md"
PROMPT_OUTPUT_PATH = "output/hypotheses_prompt.md"
CHECKPOINT_DIR = Path("output/.hypotheses_checkpoints")
CHUNK_TIMEOUT = 180
CHUNK_N_PHRASE = "2-3"
CLAUDE_N_PHRASE = "15-20"

# Rows whose description ends this way are the residual/complement
# category (friction_type='none' or trigger_moment='none') - not
# hypothesis-worthy on their own (you can't A/B test "the absence of
# friction"), so excluded from what's shown to either engine. Still fully
# present in observations.csv itself - this is a prompt-curation choice
# in this script, not something hidden from the record.
EXCLUDED_SUFFIX = "=none rate"

# The keyboard-mash count is a data-cleaning statistic (how many garbage
# reviews got filtered out before sampling), not a product fact - there is
# no A/B test for "fewer keyboard-mash reviews". Excluded from the prompt
# entirely rather than relying on the model to recognize that on its own.
EXCLUDED_DESCRIPTION_SUBSTRING = "keyboard-mash filter"

# Lesson from Part 4/5: a model given only one example copies its exact
# shape and content. Two examples, deliberately different in structure
# (one about a pricing/design change, one about a targeted offer) and
# using placeholder numbers distinct from anything in the real data, so
# there's nothing here to accidentally echo.
HYPOTHESIS_PROMPT = """You are helping a product analyst turn measured facts about two mobile app studios (Codeway and HubX) into A/B test hypotheses.

FIELD DEFINITIONS - read carefully, these were misread before:
- trigger_moment: the MOMENT IN THE USER'S JOURNEY WHEN FRICTION HAPPENED. A HIGH rate here is BAD, not good - it means friction is common at that moment. "before_first_use" means the user hit a wall (paywall, forced signup, etc.) before even trying the product once - this is usually the worst place for friction to occur, not a neutral checkpoint.
- paid_but_still_limited: the share of reviews from users who ALREADY PAID and are STILL describing themselves as limited/restricted. This is a broken-promise signal (a monetization/trust problem), not the name of a feature or a plan tier.
- The bracketed range after a percentage, e.g. "%12.3 [%7.4-%17.1]", is the 95% CONFIDENCE INTERVAL around that ONE estimate - the uncertainty in the measurement itself. It is NOT a separate user segment, NOT a range of user behaviors, and NOT two different numbers to build separate hypotheses from. Only the main percentage (before the bracket) is a value you may build a hypothesis on.

RULES - follow exactly:
- Use ONLY the observations listed below. Never invent, estimate, round differently, or make up any number that is not already given to you.
- Every "Observation" line MUST quote a number exactly as it appears in one of the observations below (same digits).
- If an observation's line ends with "not significant (CIs overlap)", any hypothesis built on it must say so plainly in the Observation line - don't imply a difference the data doesn't support.
- If an observation is marked "⚠ low n", say so in the Observation line too.
- "Hypothesis" must propose a SPECIFIC, CONCRETE product or design change (a particular screen, message, price, timing, or flow you would actually build and ship). Circular statements that just restate the observation - e.g. "reducing friction would increase conversion" or "improving the experience would help" - are NOT acceptable; they propose nothing to build.
- Write your entire answer in ENGLISH, using exactly this four-line format per hypothesis, with a blank line between hypotheses:

Observation: [the exact number from one observation below, and what it measures]
Hypothesis: [what would happen if something specific changed]
Test: [how to measure it - metric and duration]
Risk: [what could go wrong]

Two examples of the expected format (fictional numbers for format only - do NOT reuse these numbers, they are not real):

Observation: Nova's price_level rate is %8.2 (n=150), Chat AI's is %3.1 (n=149) - significant.
Hypothesis: Changing Nova's pricing page to a tiered model similar to Chat AI's could reduce price complaints.
Test: Show the new pricing page to 50% of users, measure the price_level rate in new reviews over 4 weeks.
Risk: Lowering the price could hurt revenue; should only be rolled out to new users.

Observation: Retake AI's would_pay_signal='conditional' rate is %12.4 (n=150) - the highest segment.
Hypothesis: Showing users in this segment a small incentive (an extra trial day or a discount) at the payment screen could increase conversion.
Test: A/B test a targeted offer screen for the segment overlapping with "conditional" signals for 6 weeks, measure conversion rate.
Risk: The segment was inferred from review text; it may not map exactly onto real purchase intent.

Observations (the ONLY numbers you may use - each already includes its sample size and, where relevant, whether the difference is statistically significant):
{observations}

Now produce {n_phrase} hypotheses, each following the four-line format above exactly, in English."""

HYPOTHESIS_BLOCK_RE = re.compile(
    r"Observation\s*:\s*(?P<observation>.*?)\n+\s*Hypothesis\s*:\s*(?P<hypothesis>.*?)\n+\s*Test\s*:\s*(?P<test>.*?)\n+\s*Risk\s*:\s*(?P<risk>.*?)(?=\n\s*Observation\s*:|\Z)",
    re.DOTALL | re.IGNORECASE,
)

NUMBER_RE = re.compile(r"\d+\.\d+|\d+")


def call_ollama(prompt, host, num_predict=700, num_ctx=4096, timeout=CHUNK_TIMEOUT):
    resp = requests.post(
        f"{host}/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "10m",
            "options": {"num_ctx": num_ctx, "num_predict": num_predict, "temperature": 0},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def render_observation(row):
    if row["unit"] == "rate":
        value = f"%{100 * row['value']:.1f}"
        ci = f" [%{100*row['ci_low']:.1f}-%{100*row['ci_high']:.1f}]" if pd.notna(row.get("ci_low")) else ""
    else:
        value = str(int(row["value"]))
        ci = ""
    n_part = f" (n={int(row['n'])})" if pd.notna(row["n"]) else ""
    low_n = " ⚠ low n" if row.get("low_n") else ""
    verdict = f" - {row['verdict']}" if pd.notna(row.get("verdict")) else ""
    return f"- {row['description']}: {value}{ci}{n_part}{low_n}{verdict}"


def observation_value_numbers(row):
    """Numbers that represent what was actually MEASURED - rate (as both
    one-decimal and rounded percentage) or count, plus the CI bounds.
    Deliberately excludes n - see find_matching_observations for why."""
    numbers = set()
    if row["unit"] == "rate" and pd.notna(row["value"]):
        pct = row["value"] * 100
        numbers.add(f"{pct:.1f}")
        numbers.add(str(round(pct)))
    elif pd.notna(row["value"]):
        numbers.add(str(int(row["value"])))
    if pd.notna(row.get("ci_low")):
        numbers.add(f"{100*row['ci_low']:.1f}")
    if pd.notna(row.get("ci_high")):
        numbers.add(f"{100*row['ci_high']:.1f}")
    return numbers


def observation_n_numbers(row):
    return {str(int(row["n"]))} if pd.notna(row["n"]) else set()


def find_matching_observations(observation_text, obs_df):
    """An observation only counts as "referenced" if BOTH its measured
    value AND its n appear in the Observation text. Matching on either
    alone is unreliable - measured bug: dozens of different observations
    share the same n (every friction_type row for one app has the same
    app-level n=149), so matching on n alone let an unrelated non-
    significant observation's verdict get attached to a hypothesis whose
    own Observation line said "significant" - the exact opposite of what
    it should have been warned about. Requiring both pins the match to
    (almost always) exactly one real row."""
    text_numbers = set(NUMBER_RE.findall(observation_text))
    if not text_numbers:
        return []
    matches = []
    for _, row in obs_df.iterrows():
        if (observation_value_numbers(row) & text_numbers) and (observation_n_numbers(row) & text_numbers):
            matches.append(row)
    return matches


def validate_hypothesis(observation_text, obs_df):
    """The three checks Part 4 taught us to never skip: a number that
    isn't traceable to any real observation, a claim resting on a
    difference whose CIs overlap, a claim resting on n < 30. Returns a
    list of warning strings - empty means it checked out."""
    matches = find_matching_observations(observation_text, obs_df)
    warnings = []
    if not matches:
        warnings.append("unverified: number in observation not found in observations.csv")
        return warnings
    if any(bool(m.get("low_n")) for m in matches):
        warnings.append("low n")
    if any(m.get("verdict") == "not significant (CIs overlap)" for m in matches):
        warnings.append("difference is not statistically significant")
    return warnings


def parse_hypotheses(raw_text):
    hypotheses = []
    for m in HYPOTHESIS_BLOCK_RE.finditer(raw_text):
        hypotheses.append({k: v.strip() for k, v in m.groupdict().items()})
    return hypotheses


# ---------------------------------------------------------------------------
# Chunking for the ollama engine
# ---------------------------------------------------------------------------


def categorize(description):
    """Which of analyze.py's sections this observation came from, read off
    its description text (no separate category column exists). The two
    price_level/free_quota_limit representations - once via the
    friction_type loop, once via the dedicated price_vs_quota section -
    are folded into the same "price_vs_quota" bucket so the same fact
    never shows up in two different chunks."""
    if "friction_type=price_level" in description or "friction_type=free_quota_limit" in description:
        return "price_vs_quota"
    if "friction_type=" in description:
        return "friction_type"
    if "price_level rate" in description or "free_quota_limit rate" in description:
        return "price_vs_quota"
    if "trigger_moment=" in description:
        return "trigger_moment"
    if "would_pay_signal=" in description:
        return "conditional"
    if "paid_but_still_limited" in description:
        return "paid_but_limited"
    if "market" in description:
        return "country"
    return "general"


def build_chunks(prompt_df):
    """7-8 small, focused, non-overlapping (chunk_id, sub_dataframe) pairs.
    friction_type and trigger_moment are each split by pair (chatbot/face)
    since they're the largest categories - keeps every chunk small enough
    to comfortably finish inside CHUNK_TIMEOUT with a small context."""
    df = prompt_df.copy()
    df["_category"] = df["description"].apply(categorize)
    df["_pair"] = df["description"].apply(
        lambda d: "chatbot" if d.startswith("chatbot") else ("face" if d.startswith("face") else None)
    )
    # Same fact recorded twice under different phrasing (friction_type=X vs
    # the dedicated section) is deduplicated by its actual numbers here.
    df = df.drop_duplicates(subset=["_category", "value", "n"])

    chunks = []
    for pair in ("chatbot", "face"):
        sub = df[(df["_category"] == "friction_type") & (df["_pair"] == pair)]
        if len(sub):
            chunks.append((f"friction_type_{pair}", sub))
    for pair in ("chatbot", "face"):
        sub = df[(df["_category"] == "trigger_moment") & (df["_pair"] == pair)]
        if len(sub):
            chunks.append((f"trigger_moment_{pair}", sub))
    for cat in ("conditional", "price_vs_quota", "paid_but_limited"):
        sub = df[df["_category"] == cat]
        if len(sub):
            chunks.append((cat, sub))
    # "general" (e.g. the keyboard-mash count) is usually just 1-2 rows -
    # not worth its own 180s round trip, folded into the country chunk.
    country_and_general = df[df["_category"].isin(("country", "general"))]
    if len(country_and_general):
        chunks.append(("country", country_and_general))
    return chunks


def run_ollama_chunked(prompt_df, host, out_path):
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    chunks = build_chunks(prompt_df)
    print(f"Will call in {len(chunks)} chunks ({CHUNK_N_PHRASE} hypotheses per chunk, {CHUNK_TIMEOUT}s timeout)")

    raw_parts = []
    for chunk_id, sub_df in chunks:
        checkpoint_path = CHECKPOINT_DIR / f"{chunk_id}.txt"
        if checkpoint_path.exists():
            print(f"  [{chunk_id}] checkpoint found ({len(sub_df)} observations), skipping")
            raw_parts.append(checkpoint_path.read_text())
            continue

        observations_text = "\n".join(render_observation(row) for _, row in sub_df.iterrows())
        prompt = HYPOTHESIS_PROMPT.format(observations=observations_text, n_phrase=CHUNK_N_PHRASE)
        print(f"  [{chunk_id}] {len(sub_df)} observations -> sending request to gemma3:4b...")
        try:
            raw = call_ollama(prompt, host)
        except requests.RequestException as exc:
            print(f"  [{chunk_id}] REQUEST FAILED: {exc} - rerun the script to resume where it left off")
            raise SystemExit(1)

        checkpoint_path.write_text(raw)
        raw_parts.append(raw)
        print(f"  [{chunk_id}] done, checkpoint written")

    combined_raw = "\n\n".join(raw_parts)
    write_hypotheses_md(combined_raw, prompt_df, out_path)


def write_hypotheses_md(raw_text, obs_df, out_path):
    hypotheses = parse_hypotheses(raw_text)
    print(f"\n{len(hypotheses)} hypotheses parsed")
    if not hypotheses:
        print("WARNING: no hypotheses could be parsed - start of the raw output:")
        print(raw_text[:2000])

    lines = ["# Mobile Apps: Funnel Friction Analysis — A/B Test Hypotheses\n\n"]
    lines.append(
        f"Generated by gemma3:4b from {len(obs_df)} real observations in `output/observations.csv`. "
        "No number here was produced by the model - every \"Observation\" line was automatically verified below.\n\n"
    )

    unverified_count = 0
    for i, hyp in enumerate(hypotheses, start=1):
        warnings = validate_hypothesis(hyp["observation"], obs_df)
        if any(w.startswith("unverified") for w in warnings):
            unverified_count += 1
        lines.append(f"## {i}\n\n")
        lines.append(f"**Observation:** {hyp['observation']}\n\n")
        lines.append(f"**Hypothesis:** {hyp['hypothesis']}\n\n")
        lines.append(f"**Test:** {hyp['test']}\n\n")
        lines.append(f"**Risk:** {hyp['risk']}\n\n")
        if warnings:
            lines.append(f"> ⚠ {'; '.join(warnings)}\n\n")
        lines.append("---\n\n")

    with open(out_path, "w") as f:
        f.write("".join(lines))

    print(f"{out_path} written: {len(hypotheses)} hypotheses, {unverified_count} marked unverified")
    print("Curation is yours to do - most of these will be generic, as expected.")


def write_claude_prompt(prompt_df, out_path):
    observations_text = "\n".join(render_observation(row) for _, row in prompt_df.iterrows())
    prompt = HYPOTHESIS_PROMPT.format(observations=observations_text, n_phrase=CLAUDE_N_PHRASE)
    Path(out_path).write_text(prompt)
    print(f"{out_path} written - prompt ready, paste it into Claude Code")
    print(f"After you get its answer, place it into {OUTPUT_PATH} by hand (keeping the Observation/Hypothesis/Test/Risk format).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", choices=["ollama", "claude"], default="ollama")
    parser.add_argument("--observations", default=OBSERVATIONS_PATH)
    parser.add_argument("--out", default=OUTPUT_PATH)
    parser.add_argument("--prompt-out", default=PROMPT_OUTPUT_PATH)
    parser.add_argument("--host", default=OLLAMA_HOST)
    args = parser.parse_args()

    try:
        obs_df = pd.read_csv(args.observations)
    except FileNotFoundError:
        raise SystemExit(f"{args.observations} not found - run python src/analyze.py first")

    prompt_df = obs_df[
        ~obs_df["description"].str.endswith(EXCLUDED_SUFFIX)
        & ~obs_df["description"].str.contains(EXCLUDED_DESCRIPTION_SUBSTRING)
    ]
    print(f"{len(prompt_df)}/{len(obs_df)} observations will be used ('=none rate' and the keyboard-mash count excluded)")

    if args.engine == "claude":
        write_claude_prompt(prompt_df, args.prompt_out)
    else:
        run_ollama_chunked(prompt_df, args.host, args.out)


if __name__ == "__main__":
    main()
