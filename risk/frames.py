"""Date-order guards shared by the frame-level entry points.

The expression helpers in :mod:`risk.estimators` are bare ``pl.Expr``
builders: they read row order and therefore assume the caller passes rows in
ascending date order.  The frame-level functions are the public entry points,
so each one runs its inputs through :func:`sorted_by_date` before building
those expressions.  Sorting removes the row-order trap; duplicate dates are
rejected because a trailing window cannot choose between two observations
dated the same day.
"""
from __future__ import annotations

import polars as pl


def require_date_column(frame: pl.DataFrame, column: str = "date") -> None:
    """Raise unless ``column`` exists and has the ``pl.Date`` dtype."""
    if column not in frame.columns:
        raise KeyError(f"missing date column {column!r}")
    if frame.schema[column] != pl.Date:
        raise TypeError(
            f"column {column!r} must be pl.Date, got {frame.schema[column]!r}"
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
    """Return the name of the frame's single ``pl.Date`` column."""
    names = [name for name, dtype in frame.schema.items() if dtype == pl.Date]
    if len(names) != 1:
        raise TypeError(f"expected exactly one pl.Date column, found {names!r}")
    return names[0]


def sorted_by_date(
    frame: pl.DataFrame,
    column: str | None = None,
) -> pl.DataFrame:
    """Return ``frame`` in stable ascending date order.

    ``column`` defaults to the frame's only ``pl.Date`` column.  A missing or
    non-date column raises ``TypeError``; duplicate dates raise ``ValueError``
    rather than silently picking one row's position for a trailing window.
    Stable sorting keeps the operation deterministic for the rejected
    duplicate keys and harmless for unique ones.
    """
    name = column if column is not None else date_column(frame)
    require_date_column(frame, name)
    require_unique_dates(frame, name)
    return frame.sort(name, maintain_order=True)
