"""Date-order guards shared by the frame-level entry points.

The expression helpers in :mod:`risk.estimators` are bare ``pl.Expr``
builders: they read row order and therefore assume the caller passes rows in
ascending date order.  The frame-level functions are the public entry points,
so each one runs its inputs through :func:`sorted_by_date` before building
those expressions.  Sorting removes the row-order trap; duplicate dates are
rejected because a trailing window cannot choose between two observations
dated the same day, and null dates are rejected because a row with no date
cannot be placed in time at all.
"""
from __future__ import annotations

import polars as pl


def require_date_column(frame: pl.DataFrame, column: str = "date") -> None:
    """Raise unless ``column`` exists, is ``pl.Date`` and has no nulls.

    A missing column raises ``KeyError``, a wrong dtype ``TypeError`` and a
    null date ``ValueError`` naming how many dates are missing.
    """
    if column not in frame.columns:
        raise KeyError(f"missing date column {column!r}")
    if frame.schema[column] != pl.Date:
        raise TypeError(
            f"column {column!r} must be pl.Date, got {frame.schema[column]!r}"
        )
    null_dates = frame.get_column(column).null_count()
    if null_dates:
        raise ValueError(
            f"{null_dates} null date(s) in column {column!r}: "
            "every row must carry a date"
        )


def require_unique_dates(frame: pl.DataFrame, column: str = "date") -> None:
    """Raise ``ValueError`` naming up to five duplicated dates."""
    duplicates = frame.filter(pl.col(column).is_duplicated())[column].unique().sort()
    if duplicates.len() == 0:
        return
    shown = ", ".join(str(value) for value in duplicates.head(5).to_list())
    suffix = " ..." if duplicates.len() > 5 else ""
    raise ValueError(f"duplicate dates in column {column!r}: {shown}{suffix}")


def date_column(frame: pl.DataFrame) -> str:
    """Return the frame's date column, preferring one literally named ``date``.

    Resolution order:

    1. a column literally named ``date`` when its dtype is ``pl.Date`` -- a
       frame that keeps its canonical ``date`` still sorts by it even when a
       join added another ``pl.Date`` column (say ``listing_date``);
    2. otherwise the frame's single ``pl.Date`` column, whatever its name;
    3. otherwise raise ``TypeError`` listing the ``pl.Date`` candidates (none,
       or several with none of them named ``date``).

    Only the first rule changes anything: a frame that was rejected for
    carrying a second ``pl.Date`` column next to ``date`` is now accepted, and
    every frame that was accepted before keeps exactly the same column choice.
    """
    candidates = [
        name for name, dtype in frame.schema.items() if dtype == pl.Date
    ]
    if "date" in candidates:
        return "date"
    if len(candidates) == 1:
        return candidates[0]
    raise TypeError(
        "expected a pl.Date column named 'date' or exactly one pl.Date column, "
        f"found {candidates!r}"
    )


def sorted_by_date(
    frame: pl.DataFrame,
    column: str | None = None,
) -> pl.DataFrame:
    """Return ``frame`` in stable ascending date order.

    ``column`` defaults to the frame's date column (see :func:`date_column`): a
    ``pl.Date`` column literally named ``date`` when there is one, otherwise
    the frame's only ``pl.Date`` column.  A missing column raises ``KeyError``,
    a non-date column ``TypeError`` and a null date ``ValueError``; duplicate
    dates raise ``ValueError`` rather than silently picking one row's position
    for a trailing window.  Stable sorting keeps the operation deterministic
    for the rejected duplicate keys and harmless for unique ones.
    """
    name = column if column is not None else date_column(frame)
    require_date_column(frame, name)
    require_unique_dates(frame, name)
    return frame.sort(name, maintain_order=True)
