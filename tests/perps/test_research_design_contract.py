"""Contract tests for the round-9 research-design decisions (docs + fixture).

These pin the parts of docs/data/PERPS_WEEKEND_PLAN.md that the round-2 final
gates required: one pre-registered primary test at ``sun_1800`` with a single
out-of-time statistic and a small-cluster-corrected inference, the overnight
confounders named next to the pre-market/CME baselines, one executable label
formula used identically in the plan, the schema doc and the universe config, the
committed public probe document, the ``tid`` dedupe rule, and the coverage
definition that counts empty weekends.

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


def _plan() -> str:
    return PLAN.read_text(encoding="utf-8")


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
    assert "CR2" in text
    assert "Rademacher" in text
    assert "5-feature block is a joint test" in text
    # The removed wording: a 5-feature block is not a t-statistic.
    assert "equivalently" not in text.lower()
    assert "t-statistic of the block" not in text


def test_power_is_recomputed_for_the_evaluation_weekends_not_the_panel():
    text = _plan()
    assert "N_eff is the **18 evaluation weekends**" in text
    assert "0.62" in text
    # The tanh-corrected panel bounds replace the untransformed z values.
    assert "0.49" in text
    assert "0.39" in text
    assert "0.54" not in text
    assert "equivalently the t-statistic" not in text
    assert "ΔR² = partial r² × (1 − R²_base)" in text
    assert "partial r²" in text
    assert "tanh" in text


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


def test_recount_script_labels_partial_r2_and_delta_r2():
    """The plan's power numbers come from a tanh-mapped partial correlation."""
    text = (ROOT / "scripts" / "perps" / "recount_weekends.py").read_text(encoding="utf-8")
    assert "math.tanh(z)" in text
    assert "partial_r2 * (1.0 - r2_base)" in text
    assert re.search(r"tanh\(\(z_\{1-alpha/2\}", text) is not None
