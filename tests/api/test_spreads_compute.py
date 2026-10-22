"""Polars rules for the Market Spreads screen (api/spreads.py).

Every test calls the production functions — the formulas are never re-implemented
here.  Covers: inner-join alignment (no forward-fill), rebasing to 100 at the
first common date, short history, FRED vintage dedupe, and the 10s2s spread.
"""
from __future__ import annotations

import itertools
import math
from datetime import date
from pathlib import Path

import pytest

from api.spreads import (
    price_series,
    rebased_relative_index,
    yield_curve,
)


def bars(pairs):
    """Build silver-shaped rows: [(ISO date, adj close)]."""
    return [{"symbol": "X", "event_date": d, "close": v} for d, v in pairs]


def fed_rows(series_id, pairs, *, vintage="2024-02-01", ingest="2024-02-01T12:00:00Z"):
    """Build bronze_fed_series-shaped rows."""
    return [
        {
            "series_id": series_id,
            "observation_date": d,
            "value": v,
            "vintage_date": vintage,
            "ingest_ts": ingest,
            "revision_class": "market_rate",
        }
        for d, v in pairs
    ]


# ── 1. inner-join alignment, never forward-fill ──────────────────────────────
def test_inner_join_drops_dates_missing_in_one_leg_and_never_forward_fills():
    # Leg A trades on 2024-01-03, leg B does not.
    a = bars([("2024-01-02", 10.0), ("2024-01-03", 11.0), ("2024-01-04", 12.0), ("2024-01-05", 13.0)])
    b = bars([("2024-01-02", 5.0), ("2024-01-04", 6.0), ("2024-01-05", 7.0)])

    result = rebased_relative_index(a, b, symbol_a="A", symbol_b="B")

    dates = [p[0] for p in result["points"]]
    assert result["empty"] is False
    assert dates == ["2024-01-02", "2024-01-04", "2024-01-05"]
    assert "2024-01-03" not in dates
    assert result["dropped_dates"] == 1
    assert result["first_common_date"] == "2024-01-02"

    # 2024-01-04 index uses that date's own prices: (12/6) / (10/5) * 100 = 100.
    # A forward-filled 2024-01-03 price (11) would give 11/6/2*100 ≈ 91.7.
    assert result["points"][1][1] == pytest.approx(100.0)
    # 2024-01-05: (13/7) / 2 * 100
    assert result["points"][2][1] == pytest.approx(13.0 / 7.0 / 2.0 * 100.0, rel=1e-6)


def test_dropped_dates_counts_dates_missing_from_either_leg():
    a = bars([("2024-01-02", 10.0), ("2024-01-03", 11.0), ("2024-01-05", 13.0)])
    b = bars([("2024-01-02", 5.0), ("2024-01-04", 6.0), ("2024-01-05", 7.0)])

    result = rebased_relative_index(a, b)

    assert result["dropped_dates"] == 2  # 01-03 (A only) + 01-04 (B only)
    assert [p[0] for p in result["points"]] == ["2024-01-02", "2024-01-05"]


# ── 1b. an undefined base is empty, never an exception (fix round 1, F1) ────
BASE_DATES = ["2026-10-19", "2026-10-20", "2026-10-21"]


@pytest.mark.parametrize(
    ("a_values", "b_values", "case"),
    [
        ([10.0, 12.0, 13.0], [0.0, 5.0, 6.0], "zero denominator (MiMo fixture)"),
        ([0.0, 12.0, 13.0], [5.0, 5.0, 6.0], "zero numerator"),
        ([0.0, 12.0, 13.0], [0.0, 5.0, 6.0], "both legs zero"),
        ([10.0, 12.0, 13.0], [-1.0, 5.0, 6.0], "negative denominator"),
        ([-10.0, 12.0, 13.0], [5.0, 5.0, 6.0], "negative numerator"),
    ],
)
def test_undefined_base_returns_empty_instead_of_raising(a_values, b_values, case):
    """A zero/negative close at the first common date is empty, not a 500."""
    a = bars(list(zip(BASE_DATES, a_values)))
    b = bars(list(zip(BASE_DATES, b_values)))

    result = rebased_relative_index(a, b, symbol_a="A", symbol_b="B")

    assert result["empty"] is True, case
    assert result["points"] == [], case
    assert result["first_common_date"] == BASE_DATES[0], case
    assert result["latest_value"] is None, case
    assert result["window_pct_change"] is None, case


def test_nan_close_at_the_base_is_dropped_not_divided_by():
    # NaN never survives coercion: the date leaves leg A, the base moves to the
    # next common date and every emitted value stays finite.
    a = bars([(BASE_DATES[0], float("nan")), (BASE_DATES[1], 12.0), (BASE_DATES[2], 13.0)])
    b = bars(list(zip(BASE_DATES, [5.0, 5.0, 6.0])))

    result = rebased_relative_index(a, b, symbol_a="A", symbol_b="B")

    assert result["empty"] is False
    assert result["first_common_date"] == BASE_DATES[1]
    assert [p[0] for p in result["points"]] == BASE_DATES[1:]
    assert result["points"][0][1] == pytest.approx(100.0)
    assert result["dropped_dates"] == 1
    assert all(math.isfinite(p[1]) for p in result["points"])


def test_price_series_with_a_zero_first_close_reports_no_window_change():
    uso = bars([("2024-01-02", 0.0), ("2024-01-03", 5.0)])

    result = price_series(uso)

    assert result["empty"] is False
    assert result["window_pct_change"] is None


# ── 2. rebasing at the first COMMON date ─────────────────────────────────────
def test_index_starts_at_exactly_100_at_first_common_date():
    # Leg A has a leading date that leg B lacks: the base must be the first
    # COMMON date (2024-01-02), not leg A's first row (2024-01-01).
    a = bars([("2024-01-01", 900.0), ("2024-01-02", 10.0), ("2024-01-03", 12.0)])
    b = bars([("2024-01-02", 5.0), ("2024-01-03", 5.0)])

    result = rebased_relative_index(a, b)

    assert result["first_common_date"] == "2024-01-02"
    assert result["points"][0][0] == "2024-01-02"
    assert result["points"][0][1] == pytest.approx(100.0)
    assert result["dropped_dates"] == 1
    # 12/5 / (10/5) * 100 = 120
    assert result["points"][-1][1] == pytest.approx(120.0)
    assert result["window_pct_change"] == pytest.approx(20.0)


def test_inverted_ratio_is_reciprocal_consistent():
    a = bars([("2024-01-02", 10.0), ("2024-01-03", 11.0), ("2024-01-04", 12.0)])
    b = bars([("2024-01-02", 5.0), ("2024-01-03", 5.5), ("2024-01-04", 5.0)])

    forward = rebased_relative_index(a, b, symbol_a="A", symbol_b="B")
    inverted = rebased_relative_index(b, a, symbol_a="B", symbol_b="A")

    # A outperformed B: the A/B index ends above 100, B/A below.
    assert forward["points"][-1][1] > 100.0
    assert inverted["points"][-1][1] < 100.0
    # (1 + r_ab) * (1 + r_ba) == 1 exactly for a rebased price-return index.
    growth_fwd = 1.0 + forward["window_pct_change"] / 100.0
    growth_inv = 1.0 + inverted["window_pct_change"] / 100.0
    assert growth_fwd * growth_inv == pytest.approx(1.0, rel=1e-5)
    assert forward["points"][-1][1] * inverted["points"][-1][1] == pytest.approx(100.0 ** 2, rel=1e-6)


# ── 3. short history ─────────────────────────────────────────────────────────
def test_first_common_date_is_the_later_leg_start():
    # MAGS launched in April 2023: a leg that starts later wins the window start.
    a = bars([("2023-01-03", 10.0), ("2023-01-04", 10.5), ("2023-04-03", 11.0), ("2023-04-04", 11.5)])
    b = bars([("2023-04-03", 20.0), ("2023-04-04", 20.5)])

    result = rebased_relative_index(a, b, window_start=date(2022, 12, 1))

    assert result["first_common_date"] == "2023-04-03"
    assert [p[0] for p in result["points"]] == ["2023-04-03", "2023-04-04"]
    assert result["empty"] is False


def test_fewer_than_two_common_points_is_empty_not_zero():
    a = bars([("2024-01-02", 10.0), ("2024-01-03", 11.0)])
    b = bars([("2024-01-02", 5.0)])

    result = rebased_relative_index(a, b)

    assert result["empty"] is True
    assert result["points"] == []
    assert result["first_common_date"] == "2024-01-02"
    assert result["latest_value"] is None
    assert result["window_pct_change"] is None


def test_window_start_later_than_requested_keeps_only_the_window():
    a = bars([("2024-01-02", 10.0), ("2024-01-03", 11.0), ("2024-01-04", 12.0)])
    b = bars([("2024-01-02", 5.0), ("2024-01-03", 5.0), ("2024-01-04", 6.0)])

    result = rebased_relative_index(a, b, window_start=date(2024, 1, 4))

    assert result["first_common_date"] == "2024-01-04"
    assert result["points"] == []
    assert result["empty"] is True  # one point cannot form a series
    assert result["dropped_dates"] == 0  # both legs have only 2024-01-04 left after the window cut


def test_single_symbol_price_series_reports_level_and_change():
    uso = bars([("2024-01-02", 70.0), ("2024-01-03", 71.4), ("2024-01-04", 77.0)])

    result = price_series(uso)

    assert result["points"] == [["2024-01-02", 70.0], ["2024-01-03", 71.4], ["2024-01-04", 77.0]]
    assert result["latest_value"] == pytest.approx(77.0)
    assert result["as_of"] == "2024-01-04"
    assert result["window_pct_change"] == pytest.approx(10.0)
    assert result["dropped_dates"] == 0
    assert result["empty"] is False


# ── 4. bronze_fed_series vintage dedupe ─────────────────────────────────────
# Row order between vintages is UNDEFINED in production: the real read
# (db/delta_adapter.py) orders only by ``observation_date DESC, series_id``, so
# two vintages of the same observation can arrive in either order.  Every
# fixture below is therefore replayed in several orders and must give the same
# answer.  A fixture that only ever lists the winning row last would pass with
# the de-vintaging sort removed.

#: DGS2 leg, two observations, so ``yield_curve`` has >= 2 common dates.
DGS2_BASE = fed_rows(
    "DGS2",
    [("2024-01-02", 4.40), ("2024-01-03", 4.20)],
    vintage="2024-01-05",
    ingest="2024-01-05T22:00:00Z",
)

#: A second DGS10 observation with a single vintage (keeps the date count at 2).
DGS10_EXTRA = fed_rows(
    "DGS10", [("2024-01-03", 4.30)], vintage="2024-01-04", ingest="2024-01-04T21:00:00Z"
)

VINTAGE_OLD = fed_rows(
    "DGS10", [("2024-01-02", 4.00)], vintage="2024-01-03", ingest="2024-01-03T21:00:00Z"
)
VINTAGE_NEW = fed_rows(
    "DGS10", [("2024-01-02", 4.10)], vintage="2024-01-05", ingest="2024-01-05T21:00:00Z"
)

INGEST_EARLY = fed_rows(
    "DGS10", [("2024-01-02", 4.00)], vintage="2024-01-05", ingest="2024-01-05T20:00:00Z"
)
INGEST_LATE = fed_rows(
    "DGS10", [("2024-01-02", 4.25)], vintage="2024-01-05", ingest="2024-01-05T22:00:00Z"
)


def _curve(dgs10_rows):
    """Run the yield curve with the given DGS10 rows and a fixed DGS2 leg."""
    return yield_curve([*dgs10_rows, *DGS10_EXTRA, *DGS2_BASE])


def test_latest_vintage_wins_and_null_or_dot_values_are_dropped():
    rows = [
        # Two vintages for the same observation: the later vintage (4.10) wins.
        *VINTAGE_OLD,
        *VINTAGE_NEW,
        *DGS10_EXTRA,
        # FRED missing observation: null and the literal "." are both dropped.
        {
            "series_id": "DGS10",
            "observation_date": "2024-01-04",
            "value": None,
            "vintage_date": "2024-01-05",
            "ingest_ts": "2024-01-05T21:00:00Z",
        },
        {
            "series_id": "DGS10",
            "observation_date": "2024-01-05",
            "value": ".",
            "vintage_date": "2024-01-06",
            "ingest_ts": "2024-01-06T21:00:00Z",
        },
        *DGS2_BASE,
    ]

    curve = yield_curve(rows)

    ten_dates = [p[0] for p in curve["points"]["DGS10"]]
    assert ten_dates == ["2024-01-02", "2024-01-03"]
    # One point per (series, date) — the latest vintage, not both.
    assert len(ten_dates) == len(set(ten_dates))
    assert curve["points"]["DGS10"][0][1] == pytest.approx(4.10)
    assert "2024-01-04" not in ten_dates
    assert "2024-01-05" not in ten_dates


@pytest.mark.parametrize(
    "dgs10_rows",
    [
        pytest.param([*VINTAGE_NEW, *VINTAGE_OLD], id="newer-vintage-listed-first"),
        pytest.param([*VINTAGE_OLD, *VINTAGE_NEW], id="newer-vintage-listed-last"),
    ],
)
def test_latest_vintage_wins_whatever_the_row_order(dgs10_rows):
    curve = _curve(dgs10_rows)

    assert [p[0] for p in curve["points"]["DGS10"]] == ["2024-01-02", "2024-01-03"]
    # The 2024-01-05 vintage wins in both orders; a plain keep="last" on the
    # unsorted rows would return 4.00 when the older row arrives last.
    assert curve["points"]["DGS10"][0][1] == pytest.approx(4.10)


@pytest.mark.parametrize(
    "dgs10_rows",
    [
        # Opus's failing input: the 22:00 ingest (4.25) is listed BEFORE the
        # 20:00 ingest (4.00) and must still win the tie-break.
        pytest.param([*INGEST_LATE, *INGEST_EARLY], id="newer-ingest-listed-first"),
        pytest.param([*INGEST_EARLY, *INGEST_LATE], id="newer-ingest-listed-last"),
    ],
)
def test_vintage_tie_break_uses_the_latest_ingest_ts_in_either_order(dgs10_rows):
    curve = _curve(dgs10_rows)

    assert curve["points"]["DGS10"][0][0] == "2024-01-02"
    assert curve["points"]["DGS10"][0][1] == pytest.approx(4.25)
    assert len(curve["points"]["DGS10"]) == 2


@pytest.mark.parametrize(
    "dgs10_rows",
    [list(order) for order in itertools.permutations([*VINTAGE_OLD, *INGEST_EARLY, *INGEST_LATE])],
    ids=lambda rows: "|".join(
        f"{r['vintage_date']}@{r['ingest_ts'][11:16]}" for r in rows
    ),
)
def test_three_vintages_in_any_order_pick_the_latest_vintage_then_ingest(dgs10_rows):
    curve = _curve(dgs10_rows)

    # Latest vintage_date (2024-01-05) wins, then the latest ingest (22:00) of
    # that vintage: 4.25, never the 4.00 from 2024-01-03 / 20:00.
    assert curve["points"]["DGS10"][0][1] == pytest.approx(4.25)
    assert len(curve["points"]["DGS10"]) == 2


# ── 5. 10s2s = DGS10 - DGS2 on common dates, matches T10Y2Y ─────────────────
def test_ten_two_spread_is_on_common_dates_and_matches_t10y2y():
    rows = [
        *fed_rows("DGS10", [
            ("2024-01-02", 4.10),
            ("2024-01-03", 4.05),
            ("2024-01-04", 4.20),
            ("2024-01-05", 4.00),  # DGS10-only date
        ]),
        *fed_rows("DGS2", [
            ("2024-01-02", 4.50),
            ("2024-01-03", 4.00),
            ("2024-01-04", 4.30),
            ("2024-01-06", 3.90),  # DGS2-only date
        ]),
        # FRED's own published 10-year minus 2-year spread for the common dates.
        *fed_rows("T10Y2Y", [
            ("2024-01-02", -0.40),
            ("2024-01-03", 0.05),
            ("2024-01-04", -0.10),
        ]),
    ]

    curve = yield_curve(rows)

    spread_dates = [p[0] for p in curve["spread_points"]]
    assert spread_dates == ["2024-01-02", "2024-01-03", "2024-01-04"]
    assert curve["dropped_dates"] == 2  # 01-05 (10Y only) + 01-06 (2Y only)
    assert curve["empty"] is False

    # DGS10 - DGS2 on each common date.
    by_date = {d: v for d, v in curve["spread_points"]}
    ten = {d: v for d, v in curve["points"]["DGS10"]}
    two = {d: v for d, v in curve["points"]["DGS2"]}
    for day in spread_dates:
        assert by_date[day] == pytest.approx(ten[day] - two[day])

    # ... matches FRED's T10Y2Y within 0.01 on dates where both are present.
    reference = {row["observation_date"]: row["value"] for row in fed_rows(
        "T10Y2Y",
        [("2024-01-02", -0.40), ("2024-01-03", 0.05), ("2024-01-04", -0.10)],
    )}
    common = [d for d in spread_dates if d in reference]
    assert len(common) == 3
    for day in common:
        assert abs(by_date[day] - reference[day]) <= 0.01, (day, by_date[day], reference[day])


# ── 9. no pandas in the new backend files ───────────────────────────────────
def test_no_pandas_in_new_backend_files():
    needle = "pan" + "das"  # built by concatenation so this test does not match itself
    repo_root = Path(__file__).resolve().parents[2]
    for path in ("api/spreads.py", "api/routes/spreads.py"):
        source = (repo_root / path).read_text(encoding="utf-8").lower()
        assert needle not in source, f"{path} must not use {needle}"
        assert "to_" + needle not in source
