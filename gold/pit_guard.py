"""gold/pit_guard.py — Point-in-time (PIT) leakage guard.

Enforces the no-look-ahead rule for every joined feature:

    For a prediction made at ``prediction_ts``, only records whose
    ``information_available_ts <= prediction_ts`` may be joined.

The gold layer builds ``gold_model_features`` with AS-OF joins that carry this
invariant; this module is the independent enforcement point that the build and
the test suite both call. Any leaking row raises ``LookaheadLeakError``.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Mapping, Union


class LookaheadLeakError(ValueError):
    """Raised when a joined feature is available only after the prediction."""


Timestamp = Union[datetime, date, str, None]


def _coerce(ts: Timestamp) -> datetime:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, date):
        return datetime(ts.year, ts.month, ts.day)
    s = str(ts).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def find_lookahead_leaks(
    features: Iterable[Mapping],
    info_field: str = "information_available_ts",
    pred_field: str = "prediction_ts",
) -> list[Mapping]:
    """Return the subset of ``features`` whose info_ts is strictly after pred_ts.

    ``features`` is an iterable of mappings where each record carries both the
    feature's availability timestamp and the prediction timestamp.
    """
    leaks = []
    for row in features:
        info = _coerce(row.get(info_field))
        pred = _coerce(row.get(pred_field))
        if info is None or pred is None:
            continue
        if info > pred:
            leaks.append(row)
    return leaks


def validate_no_lookahead(
    features: Iterable[Mapping],
    prediction_ts: Timestamp,
    info_field: str = "information_available_ts",
) -> None:
    """Validate a set of features against a single prediction timestamp.

    Raises ``LookaheadLeakError`` if any feature has
    ``information_available_ts > prediction_ts``. Used by the model-features
    build to fail the pipeline on leakage.
    """
    pred = _coerce(prediction_ts)
    if pred is None:
        raise LookaheadLeakError("prediction_ts is None")
    leaks = []
    for row in features:
        info = _coerce(row.get(info_field))
        if info is not None and info > pred:
            leaks.append(row)
    if leaks:
        n = len(leaks)
        raise LookaheadLeakError(
            f"PIT leakage: {n} joined feature(s) have "
            f"information_available_ts > prediction_ts={prediction_ts}"
        )


def validate_rows_no_lookahead(
    rows: Iterable[Mapping],
    info_field: str = "information_available_ts",
    pred_field: str = "prediction_ts",
) -> int:
    """Validate joined rows where each row carries both timestamps.

    Returns the count of leaking rows (does not raise). The SQL-backed build
    check calls this against the joined result and aborts when the count > 0.
    """
    return len(find_lookahead_leaks(rows, info_field, pred_field))
