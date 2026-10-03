"""Module-level worker functions for ProcessPoolExecutor.

Nested functions cannot be pickled, so the pool initializer and task
function must live at module level.  Shared data is passed once via the
initializer and stored in a module global.
"""
from __future__ import annotations

_WORKER_DATA: dict | None = None


def _worker_init(cfg, closes, universe, adv_wide, industry,
                 book_capital, cost_params, panel, build_signals_fn=None):
    """Set module-global shared data for this worker process."""
    global _WORKER_DATA
    _WORKER_DATA = {
        "cfg": cfg,
        "closes": closes,
        "universe": universe,
        "adv_wide": adv_wide,
        "industry": industry,
        "book_capital": book_capital,
        "cost_params": cost_params,
        "panel": panel,
        "build_signals_fn": build_signals_fn,
    }


def _worker_task(args_tuple):
    """Run a single variant.  Called inside the pool worker process."""
    vs, nt = args_tuple
    d = _WORKER_DATA
    if d is None:
        raise RuntimeError("_worker_init was not called — _WORKER_DATA is None")
    from strategies.run_residual_reversion import _run_variant
    return _run_variant(
        vs, d["closes"], d["universe"], d["adv_wide"],
        d["industry"], d["book_capital"], d["cost_params"],
        d["cfg"], panel=d["panel"], n_trials=nt,
        build_signals_fn=d.get("build_signals_fn"),
    )