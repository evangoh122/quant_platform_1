"""Contract tests for the round-9 research-design decisions (docs + fixture).

These pin the parts of docs/data/PERPS_WEEKEND_PLAN.md that the round-2 final
gates required: one pre-registered primary test at ``sun_1800`` with a single
out-of-time statistic and a small-cluster-corrected inference, the overnight
confounders named next to the pre-market/CME baselines, one executable label
formula used identically in the plan, the schema doc and the universe config, the
committed public probe document, the ``tid`` dedupe rule, and the coverage
definition that counts empty weekends.

Round 10 adds the honest power labelling (the Fisher-z numbers are illustrative
1-df bounds; the primary test's power is undetermined until the pre-registered
simulation in §6.2.1), the Clark-West-adjusted one-sided primary, the Friday
after-hours confounders and Friday-holiday sensitivity exclusion, the
not-populated ``dividend_unadjusted`` flag, and the frozen pre-rule probe
snapshot.

Round 11 (r6 F1, F2) pins the ontology ``open_gap`` wording to the plan's
not-populated dividend flag and the simulation's 999-draw feasibility count
against the real test's 9,999.

Round 12 pins the executable pre-registered simulation (training-only DGP over
the 12 pinned weekends, joint circular block bootstrap of whole rows, the effect
calibration equation and the plausible ΔR² set), bans the unsupported "larger
effect" ordering against the Fisher-z heuristic, and separates the Clark-West
significance decision from the unadjusted effect size P6 reports.

Round 13 calibrates the simulation against the *refit* test: residuals come from
the training **full-model** OLS (baseline **and** the five perp features), so
`s = u'E[Zε] = 0` and `κ = 0` is the true no-incremental-predictability null;
`q = u'Σ_{Z|X}u` uses the **residualised** perp features; the calibration is
`κ = sqrt(ΔR² · σ²_ε / ((1 − ΔR²) · q))`; and instrument alignment is
deterministic per instrument (no rejection loop, no intersection fallback).

Round 14 (owner decision 2026-10-23) marks the simulation as a **DRAFT**:
finalised and validated together with the P6 implementation, not yet a
pre-registered, executable specification; it lists the two Codex Sol open issues
(aligned-sampling orthogonality and zero/one-instrument slots) and keeps the
primary test's power UNDETERMINED until the finalised simulation runs.

They are offline and stdlib + PyYAML only. They fail on the pre-round-9 docs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs" / "data" / "PERPS_WEEKEND_PLAN.md"
SCHEMAS = ROOT / "docs" / "DATA_SCHEMAS.md"
README = ROOT / "README.md"
UNIVERSE = ROOT / "config" / "perp_universe.yaml"
PROBE = ROOT / "docs" / "data" / "perps_history_probe.json"
ONTOLOGY_README = ROOT / "ontology" / "README.md"

LABEL_FORMULA = (
    "open_gap = session_open * label_split_factor / prev_session_close - 1"
)
EVALUATION_WEEKENDS = (
    "2026-06-19",
    "2026-06-26",
    "2026-07-03",
    "2026-07-10",
    "2026-07-17",
    "2026-07-24",
    "2026-07-31",
    "2026-08-07",
    "2026-08-14",
    "2026-08-21",
    "2026-08-28",
    "2026-09-04",
    "2026-09-11",
    "2026-09-18",
    "2026-09-25",
    "2026-10-02",
    "2026-10-09",
    "2026-10-16",
)
TRAINING_WEEKENDS = (
    "2026-03-27",
    "2026-04-03",
    "2026-04-10",
    "2026-04-17",
    "2026-04-24",
    "2026-05-01",
    "2026-05-08",
    "2026-05-15",
    "2026-05-22",
    "2026-05-29",
    "2026-06-05",
    "2026-06-12",
)


def _plan() -> str:
    return PLAN.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Collapse markdown wrapping so multi-line phrases can be asserted."""
    return " ".join(text.split())


def test_primary_cutoff_is_sun_1800_and_mon_0900_is_secondary():
    text = _plan()
    assert "`sun_1800`" in text
    assert "PRIMARY confirmatory" in text
    assert "only `sun_1800` is confirmatory" in text
    assert "may be claimed only with ES/NQ futures" in text
    # The old plan pre-registered mon_0900 as the confirmatory cutoff.
    assert "the pre-registered test in §6.2 is `sun_1800`" in text
    assert "H1 at cutoff" not in text
    assert "pre-market complete" not in text.lower()


def test_sun_2000_is_after_the_esnq_reopen_and_confounded():
    rows = [line for line in _plan().splitlines() if line.startswith("| `sun_2000`")]
    assert len(rows) == 1, rows
    row = rows[0]
    # Round 10: sun_2000 trades after the 18:00 ET ES/NQ reopen, so it cannot
    # be presented as an unconfounded "one more evening" of perp bars.
    assert "after" in row
    assert "ES/NQ" in row
    assert "reopen" in row
    assert "confounded" in row
    assert "never part of H1" in row


def test_overnight_confounders_are_named_everywhere_they_belong():
    text = _plan()
    # CME equity-index futures reopen ahead of the later cutoffs, and overnight
    # equity ATS sessions resume on Sunday evening: both belong next to the
    # pre-market baseline in the sources, cutoffs, P1 scope and risks sections.
    assert text.count("ES/NQ") >= 4
    assert text.count("ATS") >= 4
    assert "CME equity-index futures" in text
    assert "overnight equity ATS" in text
    assert "US pre-market equity prints" in text or "US pre-market equity bars" in text
    schemas = SCHEMAS.read_text(encoding="utf-8")
    assert "ES/NQ" in schemas


def test_primary_test_has_one_statistic_and_an_expanding_origin_design():
    text = _plan()
    assert "expanding-origin walk-forward by weekend" in text
    assert "the first 12 weekends" in text
    # The exact evaluation weekends are pinned, not described loosely.
    for weekend in EVALUATION_WEEKENDS:
        assert weekend in text, weekend
    assert len(EVALUATION_WEEKENDS) == 18
    assert "ΔR²_oot" in text
    assert "mean_w(d_w) / mean_w(MSE_base,w)" in text
    assert "wild cluster bootstrap-t" in text
    assert "Rademacher" in text
    assert "5-feature block is a joint test" in text
    # The statistic is one observation per weekend, so the CR2 variance reduces
    # to the classical cluster-mean variance; round 10 retires the CR2 label.
    assert "variance `s/√G`" in text
    assert "CR2 cluster-robust variance reduces to exactly that classical" in text
    assert "so the CR2 label is not used" in text
    # The bootstrap distribution is centered; "null imposed" was ambiguous.
    assert "bootstrap is **centered**" in text
    assert "null imposed" not in text.lower()
    # H1 is "> 0", so the pre-registered alternative is one-sided.
    assert "H1 is one-sided" in text
    assert "the hypothesis is two-sided" not in text
    # The removed wording: a 5-feature block is not a t-statistic.
    assert "equivalently" not in text.lower()
    assert "t-statistic of the block" not in text


def test_illustrative_correlation_bounds_are_not_the_primary_tests_power():
    """Round 10 (Codex Sol P2): the Fisher-z numbers are not the test's power."""
    text = _plan()
    flat = _flat(text)
    assert "N_eff is the **18 evaluation weekends**" in text
    assert "0.62" in text
    # The tanh-corrected panel bounds replace the untransformed z values.
    assert "0.49" in text
    assert "0.39" in text
    assert "0.54" not in text
    assert "ΔR² = partial r² × (1 − R²_base)" in text
    assert "partial r²" in text
    assert "tanh" in text
    # The numbers are relabelled as what they are: a 1-df heuristic.
    assert "illustrative correlation bounds, not the power of the primary test." in flat
    assert "1-df heuristic" in flat
    assert "joint 5-feature block" in flat
    # Round 12 (Codex Sol P2): the unsupported ordering against the heuristic is
    # gone in both places that carried it.
    assert "larger effect" not in flat
    assert "needs a **larger** effect" not in flat
    assert "joint block buys no precision" not in flat
    assert "conservative for the direction tested" not in flat
    # The primary test's power is explicitly undetermined until §6.2.1 runs.
    assert "The primary test's power is UNDETERMINED." in flat
    # The round-9 claim, and the heading that carried it, must be gone.
    assert "Power for THIS test" not in text
    assert "### 6.1 Statistical power" not in text
    assert "powered for a large effect" not in flat
    assert "a null is the expected outcome" not in flat


def test_primary_power_simulation_is_a_draft_with_its_open_issues():
    """Round 14 (owner decision 2026-10-23): the simulation is a P6 draft.

    The specification is finalised and validated together with the P6
    implementation, so the docs must not present it as a pre-registered,
    executable specification; both Codex Sol open issues must be listed, and the
    primary test's power stays UNDETERMINED until the finalised simulation runs.
    Removing the DRAFT label fails this test.
    """
    flat = _flat(_plan())
    # The DRAFT label, on the heading and in the opening line.
    assert "DRAFT" in flat
    assert "finalised and validated with the P6 implementation" in flat
    assert "not yet a pre-registered, executable specification" in flat
    assert "#### 6.2.1 Pre-registered power simulation" not in flat
    assert "**DRAFT.**" in flat
    # Exactly the two open issues from the Sol final gate, stated neutrally.
    assert "Open issues (Codex Sol final gate, 2026-10-23)" in flat
    assert (
        "Aligned sampling versus the orthogonality the calibration assumes"
        in flat
    )
    assert (
        "nearest-following per-weekend instrument alignment changes row "
        "probabilities in the unbalanced panel"
    ) in flat
    assert "(`E[Xε] = E[Zε] = 0`)" in flat
    assert "need not hold under the aligned sampling measure" in flat
    assert "`κ = 0` is not a null and the calibration is biased" in flat
    assert "1.86e-16 before versus 0.135 after alignment" in flat
    assert "0.0138 at `κ = 0`" in flat
    assert "0.0322 at target 0.01" in flat
    assert "0.0753 at target 0.05" in flat
    assert "aligned sampling distribution (or a balanced design)" in flat
    assert "Slots with zero or one eligible instrument" in flat
    assert "fail such replications or prescribe a fixed disposition" in flat
    # Power is undetermined until P6 runs the finalised simulation.
    assert "The primary test's power remains UNDETERMINED" in flat
    assert "until P6 runs the finalised simulation" in flat
    assert "no confirmatory claim may be made before then" in flat
    assert "This simulation fixes it" not in flat
    # README and the schema doc say the same: draft, finalised in P6.
    readme = _flat(README.read_text(encoding="utf-8"))
    assert "**draft; finalised in P6**" in readme
    assert "pre-registered simulation in the plan" not in readme
    schemas = _flat(SCHEMAS.read_text(encoding="utf-8"))
    assert "is a draft, finalised in P6" in schemas
    assert "pre-registered power simulation" not in schemas
    # The draft still specifies the simulation it will implement: training-only
    # DGP over the 12 pinned weekends.
    assert "Training-only data-generating process." in flat
    assert "12 pinned training weekends only" in flat
    for weekend in TRAINING_WEEKENDS:
        assert weekend in flat, weekend
    # No evaluation weekend appears in the DGP window: mutating the window to
    # include one fails this test.
    dgp = flat.split("Training-only data-generating process.", 1)[1]
    dgp = dgp.split("Joint circular block bootstrap", 1)[0]
    for weekend in EVALUATION_WEEKENDS:
        assert weekend not in dgp, weekend
    # Joint resampling of whole rows, with a stated block-length rule.
    assert "whole weekend-instrument rows by weekend blocks" in flat
    assert "b = 4" in flat
    assert "circularly" in flat
    assert "Politis–White" in flat
    # Round 13: deterministic per-instrument alignment; the rejection loop and
    # the random-intersection fallback are gone.
    assert "actual instrument set `I_w` of that evaluation" in flat
    assert "drawn **per instrument** from training weekends" in flat
    assert "`E_i = {training weekends containing i}`" in flat
    assert "block-aligned" in flat
    assert "excluded from the simulation for that slot" in flat
    assert "exclusion count is reported per slot and in total" in flat
    assert "Acceptance/failure rule, stated explicitly" in flat
    assert "whole weekend block draw is rejected and redrawn" not in flat
    assert "100 consecutive draws" not in flat
    assert "shortfall" not in flat
    assert "no rejection-and-redraw loop" in flat
    assert "100-draw limit" in flat
    assert "random intersection fallback" in flat
    # Block-length wording: 3 non-overlapping blocks over 12 circular starts.
    assert "3 non-overlapping blocks" in flat
    assert "12 circular start points" in flat
    # Fixed direction and the round-13 effect-calibration equation.
    assert "u = (1/√5, …, 1/√5)'" in flat
    assert "κ = sqrt(ΔR² · σ²_ε / ((1 − ΔR²) · q))" in flat
    assert "population unadjusted out-of-time R² gain" in flat
    # The plausible set is declared explicitly.
    assert "plausible = {0.005, 0.01, 0.02}" in flat
    # Design: the 18 evaluation weekends and the joint block.
    assert "18 evaluation weekends" in flat
    assert "5-feature block" in flat
    # The simulated test is the real one, Clark-West included.
    assert "Clark-West-adjusted `d_w`" in flat
    assert "Nominal α:** 0.05, **one-sided**" in flat
    # Replication counts and what is reported.
    assert "2,000" in flat
    assert "999" in flat
    # F2: 999 is the simulation's feasibility count, not the real test's 9,999,
    # so the plan must not claim the procedure is reproduced "exactly".
    assert "the §6.2 procedure exactly" not in flat
    assert "not the real test's 9,999" in flat
    assert "±0.003" in flat
    assert "power curve" in flat
    assert "minimum detectable `ΔR²` at 80% power" in flat
    assert "size at population `ΔR² = 0`" in flat
    assert "Monte Carlo standard error" in flat
    assert "seed" in flat
    # The finalised simulation runs before any P6 loss is inspected.
    assert "P6 **before** any evaluation loss is inspected" in flat


def test_simulation_calibration_matches_the_refit_test_and_kappa_zero_is_a_null():
    """Round 13 (Opus MAJOR = Codex Sol P2 #1): κ = 0 must be a true null.

    The calibration has to describe the *refit* comparison: residuals from the
    training full-model OLS (baseline **and** the five perp features), so the
    sample covariance ``s = u'E[Zε]`` is zero, ``q`` is the variance of the
    injected index **after** residualising the perp features on the baseline
    design, and ``κ = 0`` injects no incremental predictability at all.
    """
    flat = _flat(_plan())
    # Residual source: the full-model OLS, not a baseline-only fit.
    assert "full-model OLS" in flat
    assert (
        "`open_gap` on the pre-declared baseline columns **and** the five perp "
        "features"
    ) in flat
    assert "from that full-model fit" in flat
    assert "baseline-only OLS" in flat
    assert "Fit the primary baseline OLS" not in flat
    assert "drawn baseline residual" not in flat
    assert "baseline residual `ε̂`" not in flat
    # s = 0 follows from that fit, so κ = 0 is the no-increment null.
    assert "X'ε̂ = 0" in flat
    assert "Z'ε̂ = 0" in flat
    assert "s = u'E[Zε] = 0" in flat
    assert "true no-incremental-predictability null" in flat
    # q uses the residualised perp features, weekend-weighted like the statistic.
    assert "q = u'Σ_{Z|X}u" in flat
    assert (
        "after residualising the five perp features on the baseline design"
        in flat
    )
    assert "weekend-weighted, as the statistic is" in flat
    assert "q = u'Σ_Z u" not in flat
    # The s-dependent root is gone; the closed form above replaces it.
    assert "−s + sqrt(s² + q · ΔR²" not in flat
    # The grid is the population gain of the REFIT models, and realised gains
    # are reported next to their targets.
    assert "population unadjusted out-of-time R² gain of the refit full" in flat
    assert "model over the refit baseline" in flat
    assert "makes **small realised gains differ from the target**" in flat
    assert "realised** unadjusted `ΔR²_oot`" in flat
    # README and the schema doc repeat the same calibration and null.
    readme = _flat(README.read_text(encoding="utf-8"))
    assert "**full-model** OLS" in readme
    assert "no-incremental-predictability null" in readme
    assert "κ = sqrt(ΔR² · σ²_ε / ((1 − ΔR²) · q))" in readme
    schemas = _flat(SCHEMAS.read_text(encoding="utf-8"))
    assert "FULL-model OLS residuals" in schemas
    assert "no-incremental-predictability null" in schemas
    assert "κ = sqrt(ΔR² * σ²_ε / ((1 - ΔR²) * q))" in schemas
    assert "q = u'Σ_{Z|X}u" in schemas


def test_reported_effect_is_unadjusted_and_cw_decides_significance_only():
    """Round 12 (Opus MINOR 2): significance and effect size are separate."""
    flat = _flat(_plan())
    assert "decides **significance only**" in flat
    assert "ΔR²_cw = mean_w(d_w) / mean_w(MSE_base,w)" in flat
    assert "unadjusted out-of-time R² gain" in flat
    assert (
        "ΔR²_oot = mean_w(MSE_base,w − MSE_full,w) / mean_w(MSE_base,w)"
        in flat
    )
    assert "The effect size P6 reports is **not** the Clark-West ratio" in flat
    # The schema doc and README describe the same split.
    schemas = _flat(SCHEMAS.read_text(encoding="utf-8"))
    assert "decides SIGNIFICANCE ONLY" in schemas
    assert "UNADJUSTED out-of-time R² gain" in schemas
    assert "mean(MSE_base - MSE_full) / mean(MSE_base)" in schemas
    readme = _flat(README.read_text(encoding="utf-8"))
    assert "decides **significance only**" in readme
    assert "**unadjusted** out-of-time ratio" in readme


def test_clark_west_and_the_friday_holiday_weekends_are_predeclared():
    """Opus MINOR 1 and 2: the baseline's edge and the nested-model adjustment."""
    text = _plan()
    flat = _flat(text)
    # Clark-West decides significance; the reported effect is unadjusted.
    assert "Clark-West adjusted" in flat
    assert "mean_{rows in w}(ŷ_base − ŷ_full)²" in flat
    assert "decides **significance only**" in flat
    # One-sided alternative, matching H1.
    assert "H1 is one-sided: `mean_w(d_w) > 0` at the 5% level" in flat
    # The claim is only "beyond the Friday regular-session close + crypto".
    assert "Friday regular-session close + crypto" in flat
    assert "16:00-20:00 ET" in flat
    assert "17:00 ET" in flat
    assert "Friday after-hours and the last ES/NQ hour" in flat
    # Labor Day and July 3 are in the primary, flagged; July 3 also has a
    # pre-declared sensitivity exclusion.
    assert "Labor Day weekend (2026-09-04" in flat
    assert "Friday-holiday weekend (2026-07-03" in flat
    assert "The primary report covers **all 18** evaluation weekends" in flat
    assert "pre-declared sensitivity run excludes the Friday-holiday weekend" in flat
    assert "**includes** those weekends, flagged" in flat
    assert "The primary **includes** these weekends, flagged" in flat


def test_dividend_flag_is_not_shipped_all_false():
    """Opus MINOR 3 + r6 F1: declared, unpopulated in P0, and honest about it."""
    flat = _flat(_plan())
    assert "not populated in P0" in flat
    assert "no all-false flag shipped silently" in flat
    assert "populated only from that point" in flat
    # F1: the ontology term must carry the same meaning as the plan. The flag is
    # populated only from P1 dividend ingestion, so its absence is not evidence
    # that a weekend had no ex-dividend event.
    ontology = yaml.safe_load(
        (ROOT / "ontology" / "business_terms.yaml").read_text(encoding="utf-8")
    )
    definition = _flat(ontology["terms"]["open_gap"]["definition"])
    assert "declared but not populated in P0" in definition
    assert "populated only from P1 dividend ingestion" in definition
    assert "absence must not be read as 'no ex-dividend weekend'" in definition
    # The pre-r11 wording implied the flag was already set for such weekends.
    assert "ex-dividend weekends are flagged dividend_unadjusted" not in definition



def test_evaluation_weekend_list_matches_the_production_calendar_helper():
    from datetime import date

    from scripts.perps import recount_weekends as recount

    weekends = recount.weekend_ids(date(2026, 6, 19), date(2026, 10, 16))
    assert tuple(day.isoformat() for day in weekends) == EVALUATION_WEEKENDS
    training = recount.weekend_ids(date(2026, 3, 27), date(2026, 6, 12))
    assert len(training) == 12


def test_one_label_formula_is_used_identically_everywhere():
    documents = {
        "plan": _plan(),
        "schemas": SCHEMAS.read_text(encoding="utf-8"),
        "universe": UNIVERSE.read_text(encoding="utf-8"),
        "ontology": ONTOLOGY_README.read_text(encoding="utf-8"),
    }
    for name, text in documents.items():
        assert LABEL_FORMULA in text, name
        # The old ambiguous definition must be gone.
        assert "open_gap = session_open / prev_session_close - 1" not in text, name
    assert "new shares / old shares" in documents["plan"]
    assert "new shares / old shares" in documents["universe"]
    # Worked 2:1 example: prev close 100, open 50, ratio 2.0 -> a zero gap.
    assert "50.00 × 2.0 / 100.00 − 1 = 0.00%" in documents["plan"]
    assert "2:1 split" in documents["plan"]


def test_label_is_split_only_until_dividend_ingestion_lands():
    plan = _plan()
    schemas = SCHEMAS.read_text(encoding="utf-8")
    for text in (plan, schemas):
        lowered = text.lower()
        assert "dividend" in lowered
        assert "p1 prerequisite" in lowered
    assert "split-adjusted only" in plan
    assert "has no dividend amounts" in plan.replace("**", "")
    assert "SPLIT-ADJUSTED ONLY" in schemas
    assert "no dividend amounts" in schemas.replace("NO ", "no ")
    assert "dividend_unadjusted" in plan


def test_label_names_the_opening_price_column_and_its_difference():
    plan = _plan()
    schemas = SCHEMAS.read_text(encoding="utf-8")
    for text in (plan, schemas):
        assert "silver_ohlcv_day_adjusted.open" in text or "silver_ohlcv_day_adjusted`" in text
        assert "consolidated" in text
        assert "auction" in text
    assert "**not** the primary-listing" in plan
    assert "NOT the primary-listing" in schemas


def test_binance_quote_is_not_attributed():
    plan = _plan()
    schemas = SCHEMAS.read_text(encoding="utf-8")
    # The caveat is Hyperliquid's; the repo carries no sourced Binance statement.
    assert "no guarantee of timely updates and data may be missing" in plan
    assert "Binance states" not in plan
    assert "no guarantee of timely updates" not in schemas


def test_fill_dedupe_is_by_trade_id_and_reconciliation_is_an_acceptance_item():
    plan = _plan()
    assert "trade id (`tid`)" in plan
    assert "once per counterparty" in plan
    assert (
        "reconcile aggregated volume against `candleSnapshot` over an overlapping window"
        in plan
    )


def test_coverage_documentation_counts_empty_post_listing_weekends():
    plan = _plan()
    readme = README.read_text(encoding="utf-8")
    assert "including a weekend with no bars" in plan
    assert "bars are the numerator, the calendar is the denominator" in plan
    assert "missing_weekends" in plan
    assert "pre_listing_weekends" in plan
    assert "pre-listing" in plan
    assert "missing data, not full coverage" in readme
    ontology = yaml.safe_load((ROOT / "ontology" / "business_terms.yaml").read_text(encoding="utf-8"))
    terms = ontology["terms"]
    assert "post-listing" in terms["closed_market_liquidity"]["definition"]
    assert "no bar count as zero-volume" in terms["sparse_flag"]["definition"]
    assert "open_gap" in terms
    assert LABEL_FORMULA in terms["open_gap"]["definition"]


def test_plan_sections_are_ordered_and_dry_run_wording_is_exact():
    text = _plan()
    assert text.index("### 1.1 ") < text.index("### 1.2 ")
    assert "no object downloads" in text
    assert "`ListObjectsV2` listing only" in text
    assert "zero `GET`" not in text


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def test_committed_probe_is_public_data_and_cited_by_the_plan():
    assert PROBE.is_file(), (
        "docs/data/perps_history_probe.json must be committed so the recount "
        "assertion runs in CI"
    )
    document = json.loads(PROBE.read_text(encoding="utf-8"))
    assert document["version"] == 1
    assert document["generated_at"] == "2026-10-21T20:00:52.381708+00:00"
    assert len(document["hyperliquid"]["instruments"]) == 78
    keys = " ".join(_walk_keys(document)).lower()
    for forbidden in ("secret", "token", "password", "api_key", "private_key", "wallet"):
        assert forbidden not in keys, forbidden
    text = PROBE.read_text(encoding="utf-8").lower()
    for forbidden in ("aws_secret", "private key", "bearer ", "signature="):
        assert forbidden not in text, forbidden
    assert "docs/data/perps_history_probe.json" in _plan()
    assert "test_recount_weekends.py" in _plan()


def test_probe_json_is_a_frozen_prerule_snapshot():
    """Opus MINOR 4: the committed JSON predates the data_source rule.

    The file is a dated measurement, not a live view: it has no ``data_source``
    field and its Binance rows record the pre-fix S3 listing. The plan must say
    so, and this test pins the frozen artifact so a later edit cannot quietly
    "fix" it; P1 re-runs the probe instead.
    """
    flat = _flat(_plan())
    assert "pre-rule snapshot" in flat
    assert "carries no `data_source` field" in flat
    assert "pre-fix S3 listing" in flat
    assert "no monthly archives" in flat
    assert "HTTP 200" in flat
    document = json.loads(PROBE.read_text(encoding="utf-8"))
    assert "data_source" not in set(_walk_keys(document))
    instruments = document["binance_usdm"]["instruments"]
    assert len(instruments) == 2
    for instrument in instruments:
        for stream in instrument["streams"].values():
            assert stream["error"] == "no monthly archives"


def test_recount_script_labels_partial_r2_and_delta_r2():
    """The plan's illustrative bounds come from a tanh-mapped partial correlation."""
    text = (ROOT / "scripts" / "perps" / "recount_weekends.py").read_text(encoding="utf-8")
    assert "math.tanh(z)" in text
    assert "partial_r2 * (1.0 - r2_base)" in text
    assert re.search(r"tanh\(\(z_\{1-alpha/2\}", text) is not None
    # Round 10: the script must not call this the primary test's power.
    assert "not that test's power" in text
