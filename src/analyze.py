"""Part 6 analysis: matched-pair friction comparison with confidence intervals.

Reads data/friction.db, writes tables to output/*.csv, charts to
output/charts/*.png, and a narrative summary to output/analysis_summary.md. Also
writes output/observations.csv - the single, sole input hypotheses.py
reads, so every number that reaches the LLM traces back to a row this
script actually computed.

NEVER INVENT A METRIC: every number here is either a direct count over the
full population, or a weighted_rate() call over the estimation frame.
Nothing derived-and-unexplainable like a "maturity score".

Usage:
    python src/analyze.py
    python src/analyze.py --db data/friction.db --out output
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from db import DB_PATH, get_connection
from sample import is_keyboard_mash, rating_band

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PAIRS = {
    "chatbot": {"Codeway": "Chat AI: Ask Agent Anything", "HubX": "AI Chatbot - Nova"},
    "face": {"Codeway": "Retake AI Face & Selfie Editor", "HubX": "ReShoot: AI Face Photo Editor"},
}

SHORT_APP_NAME = {
    "Chat AI: Ask Agent Anything": "Chat AI",
    "AI Chatbot - Nova": "Nova",
    "Retake AI Face & Selfie Editor": "Retake AI",
    "ReShoot: AI Face Photo Editor": "ReShoot",
}

FRICTION_TYPES = [
    "paywall_timing", "price_level", "subscription_trap", "free_quota_limit",
    "referral_gate", "quality_gap", "onboarding_confusion", "performance", "none",
]
TRIGGER_MOMENTS = ["before_first_use", "after_first_result", "after_free_quota", "none"]

LOW_N_THRESHOLD = 30
TOP_N_COUNTRIES = 4

ACCENT = "#A8503A"
NEUTRAL = "#6b6255"
BG = "#FAF7F2"
BORDER = "#ddd3c4"

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor": BG,
    "savefig.facecolor": BG,
    "axes.edgecolor": BORDER,
    "axes.grid": False,
    "font.size": 13,
    "axes.titlesize": 14,
    "axes.labelsize": 12,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_strata_populations(conn):
    """N_h per (app, rating band) - the population sample.py stratified its
    random draw from. Every rate in this script is weighted against this,
    computed once, not re-derived per call."""
    rows = conn.execute(
        "SELECT app, rating FROM reviews WHERE is_substantive = 1 AND rating IS NOT NULL"
    ).fetchall()
    populations = {}
    for app, rating in rows:
        key = (app, rating_band(rating))
        populations[key] = populations.get(key, 0) + 1
    return populations


def load_estimation_frame(conn):
    """The ONLY dataframe percentages are computed from: in_estimation_frame=1,
    validation_status='valid'. Discovery-frame rows never reach this."""
    query = """
        SELECT e.review_id, e.friction_type, e.trigger_moment, e.mentions_price,
               e.paid_but_still_limited, e.would_pay_signal, e.selection_weight,
               e.in_estimation_frame, e.validation_status,
               r.app, r.studio, r.pair_id, r.country, r.rating
        FROM extractions e JOIN reviews r ON r.review_id = e.review_id
        WHERE e.in_estimation_frame = 1 AND e.validation_status = 'valid'
    """
    df = pd.read_sql_query(query, conn)
    assert df["rating"].notna().all(), "estimation frame has a null rating - sample.py invariant broken"
    return df


def load_discovery_conditional_quotes(conn, per_app=2):
    """Illustrative quotes only - NEVER a rate. would_pay_signal='conditional'
    is the most valuable segment to read, not just count."""
    query = """
        SELECT r.app, r.country, r.rating, r.body, e.gist
        FROM extractions e JOIN reviews r ON r.review_id = e.review_id
        WHERE e.in_discovery_frame = 1 AND e.validation_status = 'valid'
          AND e.would_pay_signal = 'conditional'
        ORDER BY r.review_id
    """
    df = pd.read_sql_query(query, conn)
    return df.groupby("app").head(per_app)


# ---------------------------------------------------------------------------
# The one function every percentage goes through
# ---------------------------------------------------------------------------


def weighted_rate(df, condition, strata_populations):
    """Stratified-sample weighted proportion with a 95% CI, per PLAN.md:

        p_st = Σ W_h p_h                          W_h = N_h / N
        Var  = Σ W_h² p_h(1-p_h)/n_h (1 - n_h/N_h)
        95% CI = p_st ± 1.96 sqrt(Var)

    A simple binomial CI is WRONG here because the sample is stratified by
    app x rating-band, not drawn uniformly - ignoring that understates
    variance in some bands and overstates it in others.

    df MUST already be filtered to in_estimation_frame=1 AND
    validation_status='valid' - the asserts below are a hard stop, not a
    warning: the discovery frame is purposively oversampled toward
    complaints and would bias every rate upward if it ever leaked in here.

    condition: boolean Series aligned to df's index (True = event occurred).
    strata_populations: {(app, band): N_h}, from load_strata_populations.

    Finite-population correction (1 - n_h/N_h) is included. When a stratum
    was fully censused (ReShoot's 3-star band: population 11, sample 11),
    that factor is exactly 0 and the stratum contributes zero variance -
    correct, not a bug. No division here is ever by (N_h - n_h), only by
    n_h and by total_N, both guaranteed > 0 for any non-empty df, so this
    never raises a division-by-zero for that case.

    Returns (rate, ci_low, ci_high, n).
    """
    assert (df["in_estimation_frame"] == 1).all(), "weighted_rate saw a non-estimation-frame record"
    assert (df["validation_status"] == "valid").all(), "weighted_rate saw a non-valid record"

    n = len(df)
    if n == 0:
        return float("nan"), float("nan"), float("nan"), 0

    bands = df["rating"].apply(rating_band)
    event = condition.astype(bool)

    strata_keys = list({(app, band) for app, band in zip(df["app"], bands)})
    total_N = sum(strata_populations[key] for key in strata_keys)

    p_st = 0.0
    var = 0.0
    for app, band in strata_keys:
        mask = (df["app"] == app) & (bands == band)
        n_h = int(mask.sum())
        N_h = strata_populations[(app, band)]
        p_h = event[mask].mean()
        W_h = N_h / total_N
        p_st += W_h * p_h
        var += (W_h ** 2) * (p_h * (1 - p_h) / n_h) * (1 - n_h / N_h)

    se = var ** 0.5
    ci_low = max(0.0, p_st - 1.96 * se)
    ci_high = min(1.0, p_st + 1.96 * se)
    return p_st, ci_low, ci_high, n


def cis_overlap(low_a, high_a, low_b, high_b):
    return not (high_a < low_b or high_b < low_a)


def significance_note(ci_a, ci_b):
    return "not significant (CIs overlap)" if cis_overlap(*ci_a, *ci_b) else "significant"


def low_n_flag(n):
    return " ⚠" if n < LOW_N_THRESHOLD else ""


# ---------------------------------------------------------------------------
# Observations - the sole bridge to hypotheses.py
# ---------------------------------------------------------------------------

OBSERVATIONS = []


def record_observation(description, value, unit, n, ci_low=None, ci_high=None, verdict=None):
    """Every number that might reach hypotheses.py's prompt goes through
    this. hypotheses.py reads output/observations.csv and ONLY that file -
    the model is never given a chance to invent a number, because it's
    never given a chance to see anything BUT this file's numbers."""
    OBSERVATIONS.append({
        "description": description,
        "value": value,
        "unit": unit,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "n": n,
        "low_n": n < LOW_N_THRESHOLD,
        "verdict": verdict,
    })


# ---------------------------------------------------------------------------
# Section 1: findings that need no LLM and no sample - full population
# ---------------------------------------------------------------------------


def section_no_llm_findings(conn, out_dir):
    print("\n" + "=" * 78)
    print("SECTION 1 - findings that need no LLM (all 6,961 substantive records)")
    print("=" * 78)
    lines = ["## 1. Findings that need no LLM\n", "No sampling error - over all 6,961 substantive records.\n"]

    # Keyboard-mash count: exact reconstruction of what sample.py's filter
    # caught. load_to_db.py's own filter already excludes char_count < 10,
    # so sample.py's dedicated keyboard-mash check only ever sees rows at
    # or above that - reusing char_count >= 10 here reproduces exactly
    # what that step flagged, not the unrelated too-short exclusions.
    rows = conn.execute("SELECT body, char_count FROM reviews").fetchall()
    mash_count = sum(1 for body, cc in rows if cc >= 10 and is_keyboard_mash(body))
    print(f"\nRecords dropped by the keyboard-mash filter: {mash_count}")
    lines.append(f"- Records dropped by the keyboard-mash filter: **{mash_count}**\n")
    record_observation("Records dropped by the keyboard-mash filter", mash_count, "count", n=mash_count)

    # Cluster 5 and 10 composition
    for cluster_id, note in [(5, "n=630, avg rating 1.60 - gold mine"), (10, "n=367 - face-editor cluster")]:
        df = pd.read_sql_query(
            "SELECT app, country, rating FROM reviews WHERE cluster_id = ?", conn, params=(cluster_id,)
        )
        app_counts = df["app"].value_counts()
        print(f"\nCluster {cluster_id} ({note}), n={len(df)}, avg rating={df['rating'].mean():.2f}")
        print(app_counts.to_string())
        app_counts.rename("n").to_csv(out_dir / f"cluster{cluster_id}_composition.csv")
        lines.append(f"- Cluster {cluster_id} ({note}): n={len(df)}, avg rating={df['rating'].mean():.2f}\n")
        for app, count in app_counts.items():
            lines.append(f"  - {SHORT_APP_NAME.get(app, app)}: {count} ({100*count/len(df):.0f}%)\n")
        if cluster_id == 5:
            country_counts = df["country"].value_counts()
            country_counts.rename("n").to_csv(out_dir / "cluster5_country_composition.csv")

    # Rating distribution per app (full population)
    rating_df = pd.read_sql_query(
        "SELECT app, rating, COUNT(*) as n FROM reviews WHERE rating IS NOT NULL GROUP BY app, rating", conn
    )
    rating_df.to_csv(out_dir / "rating_distribution_by_app.csv", index=False)
    print("\nRating distribution, per app (full population):")
    pivot = rating_df.pivot(index="app", columns="rating", values="n").fillna(0).astype(int)
    print(pivot.to_string())

    # Volume imbalance per app and country
    volume_df = pd.read_sql_query("SELECT app, country, COUNT(*) as n FROM reviews GROUP BY app, country", conn)
    volume_df.to_csv(out_dir / "review_volume_by_app_country.csv", index=False)
    app_totals = pd.read_sql_query("SELECT app, COUNT(*) as n FROM reviews GROUP BY app ORDER BY n DESC", conn)
    print("\nReview volume, per app:")
    print(app_totals.to_string(index=False))
    lines.append("\n**Review volume imbalance (per app):**\n\n")
    for _, row in app_totals.iterrows():
        lines.append(f"- {SHORT_APP_NAME.get(row['app'], row['app'])}: {row['n']}\n")

    (out_dir / "findings_section1.md").write_text("".join(lines))
    return lines


# ---------------------------------------------------------------------------
# Section 2-3: matched-pair tables (all weighted, all from estimation frame)
# ---------------------------------------------------------------------------


def compute_for_app(df, app, condition, strata_populations):
    mask = df["app"] == app
    return weighted_rate(df[mask], condition[mask], strata_populations)


def compare_pair(df, pair_id, condition, strata_populations):
    codeway_app = PAIRS[pair_id]["Codeway"]
    hubx_app = PAIRS[pair_id]["HubX"]
    rate_c, lo_c, hi_c, n_c = compute_for_app(df, codeway_app, condition, strata_populations)
    rate_h, lo_h, hi_h, n_h = compute_for_app(df, hubx_app, condition, strata_populations)
    verdict = significance_note((lo_c, hi_c), (lo_h, hi_h))
    return {
        "pair": pair_id,
        "codeway_app": codeway_app, "codeway_rate": rate_c, "codeway_ci_low": lo_c, "codeway_ci_high": hi_c, "codeway_n": n_c,
        "hubx_app": hubx_app, "hubx_rate": rate_h, "hubx_ci_low": lo_h, "hubx_ci_high": hi_h, "hubx_n": n_h,
        "verdict": verdict,
    }


def section_friction_type_by_pair(df, strata_populations, out_dir):
    print("\n" + "=" * 78)
    print("SECTION 2a - friction_type distribution, within pair (weighted, 95% CI)")
    print("=" * 78)
    rows = []
    findings = ["## 2a. friction_type distribution, within pair\n"]
    for pair_id in PAIRS:
        for ft in FRICTION_TYPES:
            cond = df["friction_type"] == ft
            result = compare_pair(df, pair_id, cond, strata_populations)
            result["friction_type"] = ft
            rows.append(result)
            c_label = f"{SHORT_APP_NAME[result['codeway_app']]} %{100*result['codeway_rate']:.1f} (n={result['codeway_n']}{low_n_flag(result['codeway_n'])})"
            h_label = f"{SHORT_APP_NAME[result['hubx_app']]} %{100*result['hubx_rate']:.1f} (n={result['hubx_n']}{low_n_flag(result['hubx_n'])})"
            print(f"[{pair_id}] {ft:22s} {c_label:28s} vs {h_label:28s} -> {result['verdict']}")
            findings.append(f"- **{pair_id} / {ft}**: {c_label} vs {h_label} -> {result['verdict']}\n")
            for side in ("codeway", "hubx"):
                record_observation(
                    f"{pair_id} pair, {result[f'{side}_app']} friction_type={ft} rate",
                    result[f"{side}_rate"], "rate", n=result[f"{side}_n"],
                    ci_low=result[f"{side}_ci_low"], ci_high=result[f"{side}_ci_high"], verdict=result["verdict"],
                )
    pd.DataFrame(rows).to_csv(out_dir / "friction_type_by_pair.csv", index=False)
    (out_dir / "findings_section2a.md").write_text("".join(findings))
    return rows


def section_trigger_moment_by_pair(df, strata_populations, out_dir):
    print("\n" + "=" * 78)
    print("SECTION 2b - trigger_moment distribution, within pair")
    print("=" * 78)
    print("(note: 'none' = this record has friction_type='none', i.e. no trigger moment)")
    rows = []
    findings = ["## 2b. trigger_moment distribution, within pair\n", "note: 'none' = friction_type='none' (no trigger moment)\n\n"]
    for pair_id in PAIRS:
        for tm in TRIGGER_MOMENTS:
            cond = df["trigger_moment"] == tm
            result = compare_pair(df, pair_id, cond, strata_populations)
            result["trigger_moment"] = tm
            rows.append(result)
            c_label = f"{SHORT_APP_NAME[result['codeway_app']]} %{100*result['codeway_rate']:.1f} (n={result['codeway_n']}{low_n_flag(result['codeway_n'])})"
            h_label = f"{SHORT_APP_NAME[result['hubx_app']]} %{100*result['hubx_rate']:.1f} (n={result['hubx_n']}{low_n_flag(result['hubx_n'])})"
            print(f"[{pair_id}] {tm:20s} {c_label:28s} vs {h_label:28s} -> {result['verdict']}")
            findings.append(f"- **{pair_id} / {tm}**: {c_label} vs {h_label} -> {result['verdict']}\n")
            for side in ("codeway", "hubx"):
                record_observation(
                    f"{pair_id} pair, {result[f'{side}_app']} trigger_moment={tm} rate",
                    result[f"{side}_rate"], "rate", n=result[f"{side}_n"],
                    ci_low=result[f"{side}_ci_low"], ci_high=result[f"{side}_ci_high"], verdict=result["verdict"],
                )
    pd.DataFrame(rows).to_csv(out_dir / "trigger_moment_by_pair.csv", index=False)
    (out_dir / "findings_section2b.md").write_text("".join(findings))
    return rows


def section_conditional_would_pay(df, strata_populations, out_dir, conn):
    print("\n" + "=" * 78)
    print("SECTION 2c - would_pay_signal='conditional' (most valuable segment), within pair")
    print("=" * 78)
    rows = []
    findings = ["## 2c. would_pay_signal='conditional' - most valuable segment\n"]
    cond = df["would_pay_signal"] == "conditional"
    for pair_id in PAIRS:
        result = compare_pair(df, pair_id, cond, strata_populations)
        rows.append(result)
        c_label = f"{SHORT_APP_NAME[result['codeway_app']]} %{100*result['codeway_rate']:.1f} (n={result['codeway_n']}{low_n_flag(result['codeway_n'])})"
        h_label = f"{SHORT_APP_NAME[result['hubx_app']]} %{100*result['hubx_rate']:.1f} (n={result['hubx_n']}{low_n_flag(result['hubx_n'])})"
        print(f"[{pair_id}] {c_label:28s} vs {h_label:28s} -> {result['verdict']}")
        findings.append(f"- **{pair_id}**: {c_label} vs {h_label} -> {result['verdict']}\n")
        for side in ("codeway", "hubx"):
            record_observation(
                f"{pair_id} pair, {result[f'{side}_app']} would_pay_signal='conditional' rate",
                result[f"{side}_rate"], "rate", n=result[f"{side}_n"],
                ci_low=result[f"{side}_ci_low"], ci_high=result[f"{side}_ci_high"], verdict=result["verdict"],
            )
    pd.DataFrame(rows).to_csv(out_dir / "would_pay_conditional_by_pair.csv", index=False)

    quotes = load_discovery_conditional_quotes(conn)
    quotes.to_csv(out_dir / "conditional_quotes_sample.csv", index=False)
    findings.append(f"\nExample quotes (discovery frame, NOT a rate, illustration only): {len(quotes)} records -> conditional_quotes_sample.csv\n")
    (out_dir / "findings_section2c.md").write_text("".join(findings))
    return rows


def section_price_vs_quota(df, strata_populations, out_dir):
    print("\n" + "=" * 78)
    print("SECTION 2d - price_level vs free_quota_limit, SEPARATELY, within pair")
    print("=" * 78)
    rows = []
    findings = ["## 2d. price_level vs free_quota_limit - never combined\n"]
    for ft in ("price_level", "free_quota_limit"):
        cond = df["friction_type"] == ft
        for pair_id in PAIRS:
            result = compare_pair(df, pair_id, cond, strata_populations)
            result["friction_type"] = ft
            rows.append(result)
            c_label = f"{SHORT_APP_NAME[result['codeway_app']]} %{100*result['codeway_rate']:.1f} (n={result['codeway_n']}{low_n_flag(result['codeway_n'])})"
            h_label = f"{SHORT_APP_NAME[result['hubx_app']]} %{100*result['hubx_rate']:.1f} (n={result['hubx_n']}{low_n_flag(result['hubx_n'])})"
            print(f"[{pair_id}] {ft:18s} {c_label:28s} vs {h_label:28s} -> {result['verdict']}")
            findings.append(f"- **{pair_id} / {ft}**: {c_label} vs {h_label} -> {result['verdict']}\n")
            for side in ("codeway", "hubx"):
                record_observation(
                    f"{pair_id} pair, {result[f'{side}_app']} {ft} rate",
                    result[f"{side}_rate"], "rate", n=result[f"{side}_n"],
                    ci_low=result[f"{side}_ci_low"], ci_high=result[f"{side}_ci_high"], verdict=result["verdict"],
                )
    pd.DataFrame(rows).to_csv(out_dir / "price_vs_quota_by_pair.csv", index=False)
    (out_dir / "findings_section2d.md").write_text("".join(findings))
    return rows


def section_paid_but_limited(df, strata_populations, out_dir):
    print("\n" + "=" * 78)
    print("SECTION 2e - paid_but_still_limited=true rate, within pair")
    print("=" * 78)
    rows = []
    findings = ["## 2e. paid_but_still_limited=true rate\n"]
    cond = df["paid_but_still_limited"] == 1
    for pair_id in PAIRS:
        result = compare_pair(df, pair_id, cond, strata_populations)
        rows.append(result)
        c_label = f"{SHORT_APP_NAME[result['codeway_app']]} %{100*result['codeway_rate']:.1f} (n={result['codeway_n']}{low_n_flag(result['codeway_n'])})"
        h_label = f"{SHORT_APP_NAME[result['hubx_app']]} %{100*result['hubx_rate']:.1f} (n={result['hubx_n']}{low_n_flag(result['hubx_n'])})"
        print(f"[{pair_id}] {c_label:28s} vs {h_label:28s} -> {result['verdict']}")
        findings.append(f"- **{pair_id}**: {c_label} vs {h_label} -> {result['verdict']}\n")
        for side in ("codeway", "hubx"):
            record_observation(
                f"{pair_id} pair, {result[f'{side}_app']} paid_but_still_limited rate",
                result[f"{side}_rate"], "rate", n=result[f"{side}_n"],
                ci_low=result[f"{side}_ci_low"], ci_high=result[f"{side}_ci_high"], verdict=result["verdict"],
            )
    pd.DataFrame(rows).to_csv(out_dir / "paid_but_limited_by_pair.csv", index=False)
    (out_dir / "findings_section2e.md").write_text("".join(findings))
    return rows


def section_friction_by_rating_crosstab(df, out_dir):
    """Deliberately UNWEIGHTED: this cross-tab conditions on friction_type,
    which is a measured (sampled) field, not a stratification variable.
    Applying the stratified-population weights here would be a domain-
    estimation problem the given formula isn't built for (some app x band
    strata have zero sampled records of a rare friction_type, which would
    silently distort total_N). Reported as plain sample proportions
    instead, clearly labeled as such - honest and simple beats forcing
    every number through one formula outside where it's valid."""
    print("\n" + "=" * 78)
    print("SECTION 2f - friction_type x star rating (RAW IN-SAMPLE RATE, unweighted)")
    print("=" * 78)
    print("(rating is the real value from Apple; this table is NOT population-weighted, it's the sample distribution)")
    cross = pd.crosstab(df["friction_type"], df["rating"], normalize="index") * 100
    counts = df["friction_type"].value_counts()
    cross["n"] = counts
    cross = cross.round(1)
    print(cross.to_string())
    cross.to_csv(out_dir / "friction_type_by_rating_crosstab.csv")
    return cross


def section_country_breakdown(df, strata_populations, out_dir):
    """No CI here, on purpose. Measured bug: weighted_rate's finite-
    population correction used app x rating-band N_h (the FULL app
    population) as the denominator while n_h came from a country-filtered
    subset - a mismatched numerator/denominator that produced the
    statistically backwards result of n=18 (fr) reporting a NARROWER
    interval than n=135 (us). The sample was never stratified by country,
    so there is no valid N_h to correct against here at all - not "an
    approximation", an actually wrong number. Reporting the plain
    unweighted sample proportion instead is less impressive-looking and
    more honest: it doesn't claim a population inference the sampling
    design can't support."""
    print("\n" + "=" * 78)
    print(f"SECTION 5 - country breakdown, top {TOP_N_COUNTRIES} markets, POOLED within pair")
    print("=" * 78)
    print("NOTE: the estimation frame is stratified by app x rating, NOT by country.")
    print("So no CI is computed here - only the raw in-sample rate and n are shown.\n")

    top_countries = df["country"].value_counts().head(TOP_N_COUNTRIES).index.tolist()
    print(f"Top {TOP_N_COUNTRIES} markets (in this sample): {', '.join(top_countries)}\n")

    CAVEAT = "the sample was not stratified by country, this rate is in-sample and cannot be generalized to the population"

    rows = []
    findings = [
        "## 5. Country breakdown (top markets, pooled within pair)\n",
        f"NOTE: {CAVEAT}. No CI computed, only raw rate and n shown.\n\n",
    ]
    for pair_id, apps in PAIRS.items():
        pair_df = df[df["app"].isin(apps.values())]
        for country in top_countries:
            country_df = pair_df[pair_df["country"] == country]
            n = len(country_df)
            if n == 0:
                continue
            cond = country_df["friction_type"] != "none"
            rate = cond.mean()
            flag = low_n_flag(n)
            print(f"[{pair_id}] {country}: any-friction raw rate %{100*rate:.1f} (n={n}{flag})")
            findings.append(f"- **{pair_id} / {country}**: any-friction raw rate %{100*rate:.1f} (n={n}{flag})\n")
            rows.append({"pair": pair_id, "country": country, "rate": rate, "ci_low": None, "ci_high": None, "n": n, "low_n": n < LOW_N_THRESHOLD})
            record_observation(
                f"{pair_id} pair, {country} market any-friction raw rate ({CAVEAT})",
                rate, "rate", n=n, ci_low=None, ci_high=None, verdict=None,
            )
    pd.DataFrame(rows).to_csv(out_dir / "country_breakdown_by_pair.csv", index=False)
    (out_dir / "findings_section5.md").write_text("".join(findings))
    return rows


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def bar_chart_with_ci(rows, title, filename, chart_dir, ylabel="oran (%)"):
    """rows: list of (label, rate, ci_low, ci_high, n)."""
    labels = [r[0] for r in rows]
    rates = [r[1] * 100 for r in rows]
    err_low = [max(0.0, (r[1] - r[2]) * 100) for r in rows]
    err_high = [max(0.0, (r[3] - r[1]) * 100) for r in rows]
    ns = [r[4] for r in rows]

    fig, ax = plt.subplots(figsize=(8, 5))
    x = list(range(len(labels)))
    ax.bar(x, rates, color=ACCENT, width=0.5, yerr=[err_low, err_high], capsize=4, ecolor=NEUTRAL)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    for xi, rate, hi, n in zip(x, rates, [r[3] * 100 for r in rows], ns):
        ax.annotate(f"n={n}", (xi, hi), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=10, color=NEUTRAL)
    fig.tight_layout()
    fig.savefig(chart_dir / filename, dpi=150)
    plt.close(fig)


def make_charts(df, strata_populations, conn, chart_dir):
    chart_dir.mkdir(parents=True, exist_ok=True)

    # 1. paywall_timing rate, all 4 apps grouped by pair - the preliminary
    # finding this whole script exists to verify.
    rows = []
    for pair_id, apps in PAIRS.items():
        for studio, app in apps.items():
            rate, lo, hi, n = compute_for_app(df, app, df["friction_type"] == "paywall_timing", strata_populations)
            rows.append((f"{SHORT_APP_NAME[app]}\n({studio})", rate, lo, hi, n))
    bar_chart_with_ci(rows, "paywall_timing rate (weighted, 95% CI)", "paywall_timing_rate.png", chart_dir)

    # 2. would_pay_signal='conditional' - the most valuable segment
    rows = []
    for pair_id, apps in PAIRS.items():
        for studio, app in apps.items():
            rate, lo, hi, n = compute_for_app(df, app, df["would_pay_signal"] == "conditional", strata_populations)
            rows.append((f"{SHORT_APP_NAME[app]}\n({studio})", rate, lo, hi, n))
    bar_chart_with_ci(rows, "would_pay_signal='conditional' rate", "conditional_rate.png", chart_dir)

    # 3. paid_but_still_limited
    rows = []
    for pair_id, apps in PAIRS.items():
        for studio, app in apps.items():
            rate, lo, hi, n = compute_for_app(df, app, df["paid_but_still_limited"] == 1, strata_populations)
            rows.append((f"{SHORT_APP_NAME[app]}\n({studio})", rate, lo, hi, n))
    bar_chart_with_ci(rows, "paid_but_still_limited rate", "paid_but_limited_rate.png", chart_dir)

    # 4. cluster 5 app composition - full population, no CI (not a sample)
    cluster_df = pd.read_sql_query("SELECT app FROM reviews WHERE cluster_id = 5", conn)
    counts = cluster_df["app"].value_counts()
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [SHORT_APP_NAME.get(a, a) for a in counts.index]
    ax.bar(labels, counts.values, color=ACCENT, width=0.5)
    ax.set_ylabel("review count")
    ax.set_title(f"Cluster 5 (n={len(cluster_df)}, avg rating 1.60) - app distribution")
    for i, c in enumerate(counts.values):
        ax.annotate(str(c), (i, c), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=10, color=NEUTRAL)
    fig.tight_layout()
    fig.savefig(chart_dir / "cluster5_composition.png", dpi=150)
    plt.close(fig)

    # 5. rating distribution per app, as % of that app's own volume - full
    # population, no CI - comparable despite volume imbalance.
    rating_df = pd.read_sql_query("SELECT app, rating FROM reviews WHERE rating IS NOT NULL", conn)
    apps_sorted = sorted(rating_df["app"].unique(), key=lambda a: SHORT_APP_NAME.get(a, a))
    fig, ax = plt.subplots(figsize=(9, 5))
    width = 0.15
    x_base = range(len(apps_sorted))
    for i, star in enumerate([1, 2, 3, 4, 5]):
        pct = [100 * ((rating_df[(rating_df.app == a) & (rating_df.rating == star)].shape[0]) / rating_df[rating_df.app == a].shape[0]) for a in apps_sorted]
        offsets = [xi + (i - 2) * width for xi in x_base]
        shade = 0.35 + 0.65 * (star - 1) / 4  # darker accent for higher stars, still one hue family
        ax.bar(offsets, pct, width=width, color=ACCENT, alpha=shade, label=f"{star}★")
    ax.set_xticks(list(x_base))
    ax.set_xticklabels([SHORT_APP_NAME.get(a, a) for a in apps_sorted])
    ax.set_ylabel("share within app (%)")
    ax.set_title("Rating distribution, per app (full population)")
    ax.legend(frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    fig.tight_layout()
    fig.savefig(chart_dir / "rating_distribution.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--out", default="output")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    chart_dir = out_dir / "charts"

    conn = get_connection(args.db)

    strata_populations = load_strata_populations(conn)
    df = load_estimation_frame(conn)
    print(f"estimation frame (in_estimation_frame=1, validation_status='valid'): {len(df)} records")

    all_findings = []
    all_findings += section_no_llm_findings(conn, out_dir)
    section_friction_type_by_pair(df, strata_populations, out_dir)
    section_trigger_moment_by_pair(df, strata_populations, out_dir)
    section_conditional_would_pay(df, strata_populations, out_dir, conn)
    section_price_vs_quota(df, strata_populations, out_dir)
    section_paid_but_limited(df, strata_populations, out_dir)
    section_friction_by_rating_crosstab(df, out_dir)
    section_country_breakdown(df, strata_populations, out_dir)

    print("\n" + "=" * 78)
    print("CHARTS")
    print("=" * 78)
    make_charts(df, strata_populations, conn, chart_dir)
    print(f"5 charts written: {chart_dir}/")

    obs_df = pd.DataFrame(OBSERVATIONS)
    obs_df.to_csv(out_dir / "observations.csv", index=False)
    print(f"\n{len(obs_df)} observations written to output/observations.csv (hypotheses.py's ONLY input)")

    # Assemble analysis_summary.md from all section files written above, in
    # order. Named distinctly from the hand-authored FINDINGS.md at the repo
    # root - on a case-insensitive filesystem (default macOS/APFS), a file
    # here literally named findings.md would collide with that one.
    section_files = [
        "findings_section1.md", "findings_section2a.md", "findings_section2b.md",
        "findings_section2c.md", "findings_section2d.md", "findings_section2e.md",
        "findings_section5.md",
    ]
    with open(out_dir / "analysis_summary.md", "w") as f:
        f.write("# Mobile Apps: Funnel Friction Analysis — Bulgular\n\n")
        f.write(f"Estimation frame: {len(df)} records (in_estimation_frame=1, validation_status='valid').\n")
        f.write(f"Every cell with n < {LOW_N_THRESHOLD} is flagged with ⚠.\n\n")
        for fname in section_files:
            path = out_dir / fname
            if path.exists():
                f.write(path.read_text())
                f.write("\n")
    print(f"output/analysis_summary.md written")

    conn.close()


if __name__ == "__main__":
    main()
