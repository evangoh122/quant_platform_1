#!/usr/bin/env python3
"""Recount the buildable weekend panel from a perp history probe.

Why this exists
---------------
``scripts/perps/probe_history.py`` records the first observed ``1h`` and ``1d``
candle per instrument, never a listing date.  The research design only cares
about the *weekend panel* those first observations imply, and the two streams
disagree:

* ``1d`` bars reach back to each listing, so a ``1d`` recount is the optimistic
  "history exists somewhere" number;
* the weekend feature set needs ``1h`` bars.  Hyperliquid's public
  ``candleSnapshot`` returns at most 5,000 candles per interval, so the oldest
  ``1h`` candle is a **rolling floor** (5,000 hours is ~208 days).  This script
  therefore reports the **API-only lower bound**: the flat-file fills backfill
  is not subject to that window and can raise the panel to the ``1d`` count once
  HIP-3 coverage is confirmed (docs/data/PERPS_WEEKEND_PLAN.md §2.5).

Rule (deliberately simple and identical for both streams)
---------------------------------------------------------
A weekend is identified by its Friday (``weekend_id``).  It counts for an
instrument when

    first_candle_date <= weekend_id <= last_weekend_id

where ``first_candle_date`` is the UTC date of the first observed candle for
that stream and ``last_weekend_id`` is the last Friday strictly before the
probe's ``generated_at``.  Applying the *same* rule to ``1d`` and ``1h`` means
the difference between the totals is the ``1h`` retention floor and nothing
else.

Effective sample size / minimum detectable effect
-------------------------------------------------
The panel has one row per ``(weekend, instrument)``, but each weekend is a
single common shock (one macro/crypto event), so the panel is **clustered by
weekend**.  The honest effective N is the number of distinct weekends, not the
row count.  The script reports both and derives a minimum detectable effect
(MDE) with the Fisher-z approximation for a **partial correlation** (two-sided
alpha = 0.05, power = 0.80):

    r_mde        = tanh((z_{1-alpha/2} + z_power) / sqrt(N_eff - 3))
    partial_r2   = r_mde^2
    delta_r2     = partial_r2 * (1 - R2_base)

The raw Fisher-z value is *not* a correlation (it is unbounded above 1), so it
is converted back with ``tanh``: at N_eff = 30 the bound is r ≈ 0.49, not 0.54.
``partial_r2`` is the partial R² of the **added block**, which is not the same
as the increment to the model's multiple R²: the increment is
``partial_r2 * (1 - R2_base)`` and shrinks as the baseline explains more.

This is an approximation, not a substitute for a simulation, but it is enough to
show that the study cannot detect a small incremental R².  ``n_eff`` is the
weekend count; the pooled row count is printed only as the wrong (anticonservative)
comparison it is.  The pre-registered primary test uses only its evaluation
weekends (docs/data/PERPS_WEEKEND_PLAN.md §6.2); applying the same 1-df heuristic
to those 18 weekends is an illustrative bound, not that test's power, which is
undetermined until the plan's pre-registered simulation (§6.2.1) runs.

Usage::

    python scripts/perps/recount_weekends.py \
        --probe .agents/requests/FACTS-perps-history-probe-2026-10-21.json
    python scripts/perps/recount_weekends.py --probe probe.json \
        --out-json /tmp/weekend_panel.json

Pure stdlib: no network, no pandas, no DuckDB.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

STREAM_1D = "candle_1d"
STREAM_1H = "candle_1h"
STREAMS = (STREAM_1D, STREAM_1H)

#: Standard normal quantiles for a two-sided 5% test at 80% power.
Z_975 = 1.959963984540054
Z_80 = 0.8416212335729143
#: Weekend features are built from 1h bars: one bar per hour.
BAR_HOURS = 1


class RecountError(ValueError):
    """Raised when the probe document is missing required fields."""


# ---------------------------------------------------------------------------
# Pure helpers (exercised by the tests)
# ---------------------------------------------------------------------------

def parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp that must carry an offset."""
    if not isinstance(value, str) or not value.strip():
        raise RecountError(f"timestamp must be a non-empty ISO-8601 string, got {value!r}")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise RecountError(f"cannot parse timestamp {value!r}") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise RecountError(
            f"timestamp {value!r} has no UTC offset; the probe records UTC "
            "instants, so an offset is required"
        )
    return moment.astimezone(timezone.utc)


def last_friday_before(moment: datetime) -> date:
    """Last Friday strictly before *moment* (UTC) — the last closed weekend."""
    day = moment.astimezone(timezone.utc).date() - timedelta(days=1)
    while day.weekday() != 4:
        day -= timedelta(days=1)
    return day


def first_friday_on_or_after(day: date) -> date:
    """The first weekend id (Friday) on or after *day*."""
    return day + timedelta(days=(4 - day.weekday()) % 7)


def weekend_ids(first: date, last: date) -> List[date]:
    """Every Friday in ``[first, last]`` (empty when the range has none)."""
    friday = first_friday_on_or_after(first)
    if friday > last:
        return []
    return [friday + timedelta(days=7 * step) for step in range((last - friday).days // 7 + 1)]


def count_weekends(first: date, last: date) -> int:
    """Number of weekends whose id is in ``[first, last]``."""
    return len(weekend_ids(first, last))


def _stream_first(doc: Any) -> Optional[date]:
    if doc is None:
        return None
    if not isinstance(doc, Mapping):
        raise RecountError(f"stream record must be an object, got {type(doc).__name__}")
    raw = doc.get("first_iso")
    if raw is None:
        return None
    return parse_utc(raw).date()


def instrument_first_dates(
    document: Mapping[str, Any], stream: str
) -> Dict[str, date]:
    """Return ``{ticker: first candle date}`` for one stream (skipping n/a)."""
    instruments = _instruments(document)
    out: Dict[str, date] = {}
    for instrument in instruments:
        ticker = instrument.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip():
            raise RecountError("every instrument record needs a non-empty ticker")
        streams = instrument.get("streams") or {}
        if not isinstance(streams, Mapping):
            raise RecountError(f"{ticker}: streams must be an object")
        first = _stream_first(streams.get(stream))
        if first is not None:
            out[ticker] = first
    return out


def _instruments(document: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    if not isinstance(document, Mapping):
        raise RecountError("probe document must be an object")
    hyperliquid = document.get("hyperliquid")
    if not isinstance(hyperliquid, Mapping):
        raise RecountError("probe document has no 'hyperliquid' section")
    instruments = hyperliquid.get("instruments")
    if not isinstance(instruments, list) or not instruments:
        raise RecountError("probe document has no 'hyperliquid.instruments' records")
    return instruments


def probe_generated_at(document: Mapping[str, Any]) -> datetime:
    raw = document.get("generated_at") if isinstance(document, Mapping) else None
    if raw is None:
        raise RecountError("probe document has no 'generated_at' timestamp")
    return parse_utc(str(raw))


def mde(
    neff: int,
    *,
    alpha: float = 0.05,
    power: float = 0.8,
    r2_base: float = 0.0,
) -> Dict[str, float]:
    """Smallest detectable partial correlation and the implied ΔR² at *neff*.

    The Fisher-z bound is a bound on a **partial correlation** ``r``, not on R²:
    ``atanh(r) * sqrt(n - 3)`` is approximately standard normal under the null,
    so the detectable correlation is
    ``tanh((z_{1-alpha/2} + z_power) / sqrt(n - 3))``.  The raw z value is
    unbounded and must be converted back; at ``n = 30`` the bound is
    ``r ≈ 0.492`` (not 0.539 as the untransformed value suggested).

    ``partial_r2 = r**2`` is the partial R² of the added block.  The increment to
    the model's multiple R² is ``delta_r2 = partial_r2 * (1 - r2_base)``, where
    ``r2_base`` is the baseline R² for the same rows; the default 0 reports the
    upper bound (the increment if the baseline explained nothing).
    """
    if neff <= 4:
        raise RecountError(f"neff must be > 4 for the Fisher-z approximation, got {neff}")
    if not (0 < alpha < 1) or not (0 < power < 1):
        raise RecountError("alpha and power must be in (0, 1)")
    if not (0 <= r2_base < 1):
        raise RecountError(f"r2_base must be in [0, 1), got {r2_base}")
    if alpha == 0.05 and power == 0.8:
        z_alpha, z_power = Z_975, Z_80
    else:
        z_alpha, z_power = _z_quantile(1 - alpha / 2), _z_quantile(power)
    z = (z_alpha + z_power) / math.sqrt(neff - 3)
    partial_r = math.tanh(z)
    partial_r2 = partial_r * partial_r
    return {
        "n_eff": neff,
        "partial_r": partial_r,
        "partial_r2": partial_r2,
        "r2_base": r2_base,
        "delta_r2": partial_r2 * (1.0 - r2_base),
    }


def _z_quantile(probability: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation)."""
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    low, high = 0.02425, 1 - 0.02425
    if probability < low:
        q = math.sqrt(-2 * math.log(probability))
        return (
            ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
        ) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if probability > high:
        q = math.sqrt(-2 * math.log(1 - probability))
        return -(
            ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
        ) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = probability - 0.5
    r = q * q
    return (
        ((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]
    ) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def build_report(
    document: Mapping[str, Any], *, last_weekend: Optional[date] = None
) -> Dict[str, Any]:
    """Compute the weekend-panel recount for every stream."""
    generated_at = probe_generated_at(document)
    last_id = last_weekend or last_friday_before(generated_at)
    if last_id.weekday() != 4:
        raise RecountError(f"last weekend id must be a Friday, got {last_id}")
    instruments = _instruments(document)
    report: Dict[str, Any] = {
        "probe_generated_at": generated_at.isoformat(),
        "last_weekend_id": last_id.isoformat(),
        "last_weekend_rule": "last Friday strictly before the probe generated_at",
        "total_instruments": len(instruments),
        "streams": {},
        "per_instrument": {},
    }
    weekend_sets: Dict[str, set] = {}
    for stream in STREAMS:
        first_dates = instrument_first_dates(document, stream)
        total = 0
        covered: set = set()
        counts: Dict[str, int] = {}
        for ticker in (row.get("ticker") for row in instruments):
            first = first_dates.get(ticker)
            ids = weekend_ids(first, last_id) if first is not None else []
            counts[ticker] = len(ids)
            total += len(ids)
            covered.update(ids)
        weekend_sets[stream] = covered
        report["streams"][stream] = {
            "company_weekends": total,
            "distinct_weekends": len(covered),
            "first_weekend_id": min(covered).isoformat() if covered else None,
            "last_weekend_id": max(covered).isoformat() if covered else None,
            "instruments_with_data": len(first_dates),
            "instruments_without_data": len(instruments) - len(first_dates),
            "company_weekends_per_weekend": (
                round(total / len(covered), 2) if covered else None
            ),
        }
        report["per_instrument"][stream] = dict(
            sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        )

    one_day = report["streams"][STREAM_1D]
    one_hour = report["streams"][STREAM_1H]
    unbuildable = sorted(weekend_sets[STREAM_1D] - weekend_sets[STREAM_1H])
    report["one_hour_floor"] = {
        "why": (
            "weekend features need 1h bars; the public candleSnapshot window is "
            "at most 5,000 candles (~208 days) and rolls forward, so this is the "
            "API-only lower bound (a flat-file fills backfill is not subject to it)"
        ),
        "weekends_unbuildable_from_1h": len(unbuildable),
        "company_weekends_unbuildable_from_1h": (
            one_day["company_weekends"] - one_hour["company_weekends"]
        ),
        "first_buildable_from_1h": one_hour["first_weekend_id"],
        "unbuildable_weekends_before_1h_floor": [
            day.isoformat() for day in unbuildable
        ],
        "shrinks_weekends_per_week": 1,
    }
    effective_n = one_hour["distinct_weekends"]
    power = mde(effective_n) if effective_n > 4 else None
    report["power"] = {
        "effective_n_basis": "distinct 1h buildable weekends (weekend clusters)",
        "effective_n": effective_n,
        "mde": power,
        "delta_r2_basis": "partial_r2 * (1 - r2_base); r2_base = 0 is the upper bound",
        "r2_base": 0.0,
        "pooled_rows": one_hour["company_weekends"],
        "pooled_rows_mde": (
            mde(one_hour["company_weekends"])
            if one_hour["company_weekends"] > 4
            else None
        ),
        "alpha_two_sided": 0.05,
        "power": 0.80,
        "note": (
            "Rows in the same weekend share one macro/crypto shock, so the row "
            "count is not the effective N; the pooled-row MDE is shown only to "
            "demonstrate the anticonservative comparison. This is a 1-df "
            "illustrative bound, not the power of the pre-registered primary "
            "test, which uses only its evaluation weekends and whose power is "
            "undetermined until the pre-registered simulation in "
            "docs/data/PERPS_WEEKEND_PLAN.md §6.2.1 runs."
        ),
    }
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    """Markdown summary suitable for the plan/README."""
    lines: List[str] = []
    lines.append(
        f"Probe generated {report['probe_generated_at']}; last buildable weekend "
        f"{report['last_weekend_id']} ({report['last_weekend_rule']})."
    )
    lines.append("")
    lines.append("| Stream | Company-weekends | Distinct weekends | First weekend | Instruments |")
    lines.append("|---|---|---|---|---|")
    for stream in STREAMS:
        row = report["streams"][stream]
        lines.append(
            f"| `{stream}` | {row['company_weekends']} | {row['distinct_weekends']} | "
            f"{row['first_weekend_id']} | {row['instruments_with_data']} |"
        )
    floor = report["one_hour_floor"]
    lines.append("")
    lines.append(
        f"1h retention floor: **{floor['weekends_unbuildable_from_1h']} weekends "
        f"({floor['company_weekends_unbuildable_from_1h']} company-weekends) cannot "
        f"be built from 1h bars**; on the API-only path the window shrinks by about "
        f"{floor['shrinks_weekends_per_week']} weekend per instrument per week "
        "(a flat-file fills backfill is not subject to that window)."
    )
    power = report["power"]
    if power["mde"]:
        lines.append("")
        pooled = power.get("pooled_rows_mde")
        pooled_text = (
            f"The {power['pooled_rows']} pooled rows suggest r "
            f"{pooled['partial_r']:.3f} (ΔR² {pooled['delta_r2']:.3f}) only because "
            "rows inside a weekend are not independent."
            if pooled
            else ""
        )
        lines.append(
            f"Effective N = {power['effective_n']} weekend clusters → smallest "
            f"detectable partial r {power['mde']['partial_r']:.2f} "
            f"(partial r² {power['mde']['partial_r2']:.2f}; ΔR² = partial r² × "
            f"(1 − R²_base), {power['mde']['delta_r2']:.2f} at R²_base 0) "
            f"at 80% power, two-sided 5%. {pooled_text}"
        )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--probe",
        default="docs/data/perps_history_probe.json",
        help="probe JSON written by scripts/perps/probe_history.py --live",
    )
    parser.add_argument(
        "--last-weekend",
        default=None,
        help="override the last weekend id (YYYY-MM-DD, must be a Friday)",
    )
    parser.add_argument("--out-json", default=None, help="write the report JSON here")
    parser.add_argument("--out-md", default=None, help="write the markdown summary here")
    args = parser.parse_args(argv)

    probe = Path(args.probe)
    try:
        document = json.loads(probe.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"cannot read probe JSON {probe}: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"{probe}: invalid JSON: {exc}", file=sys.stderr)
        return 2
    try:
        report = build_report(
            document,
            last_weekend=(
                date.fromisoformat(args.last_weekend) if args.last_weekend else None
            ),
        )
    except RecountError as exc:
        print(f"recount failed: {exc}", file=sys.stderr)
        return 2

    markdown = render_markdown(report)
    print(markdown)
    if args.out_json:
        target = Path(args.out_json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        print(f"wrote {target}")
    if args.out_md:
        target = Path(args.out_md)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown + "\n", encoding="utf-8")
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
