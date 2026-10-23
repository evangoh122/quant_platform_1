"""The installed Polars must provide the keywords the estimators rely on.

The layer passes ``min_samples`` to ``ewm_mean``, ``ewm_var``, ``rolling_std``
and ``rolling_map``; those keywords exist from Polars 1.21.0.  On an older
release every estimator would fail deep inside the expression, so these guards
fail first with a message naming the required version.
"""

from __future__ import annotations

import polars as pl

MINIMUM_POLARS = "1.21.0"


def test_installed_polars_supports_min_samples_on_ewm_and_rolling() -> None:
    frame = pl.DataFrame({"x": [1.0, 2.0, 3.0, None, 5.0, 6.0, 7.0, 8.0]})
    try:
        out = frame.select(
            pl.col("x").ewm_mean(span=3, adjust=False, min_samples=3).alias("m"),
            pl.col("x")
            .ewm_var(bias=False, span=3, adjust=False, min_samples=3)
            .alias("v"),
            pl.col("x")
            .rolling_std(window_size=3, min_samples=3, ddof=1)
            .alias("r"),
        )
    except TypeError as exc:  # pragma: no cover - only on an old Polars
        raise AssertionError(
            f"risk/ requires polars >= {MINIMUM_POLARS}: ewm_mean/ewm_var/"
            f"rolling_std must accept min_samples (installed polars "
            f"{pl.__version__}): {exc}"
        ) from exc
    assert out.height == frame.height
    # min_samples really gates the output: the first rows stay null.
    assert out["m"].null_count() > 0
    assert out["r"].null_count() > 0


def test_installed_polars_supports_min_samples_on_rolling_map() -> None:
    frame = pl.DataFrame({"x": [1.0, 2.0, 3.0, None, 5.0, 6.0, 7.0, 8.0]})
    try:
        out = frame.select(
            pl.col("x")
            .rolling_map(
                lambda window: window.mean(), window_size=3, min_samples=3
            )
            .alias("p")
        )
    except TypeError as exc:  # pragma: no cover - only on an old Polars
        raise AssertionError(
            f"risk/ requires polars >= {MINIMUM_POLARS}: rolling_map must "
            f"accept min_samples (installed polars {pl.__version__}): {exc}"
        ) from exc
    assert out.height == frame.height
    assert out["p"].null_count() > 0
