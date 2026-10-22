"""config/research_symbols.py — loader for the research/benchmark symbol groups.

Research symbols get daily research coverage (split-adjusted
``silver_ohlcv_day_adjusted`` and ``bronze_corporate_actions``) but never enter
the 39-symbol trading/model universe in ``config/universe.yaml``, the minute
feature spine, the model matrix (``gold_model_features``) or published baseline
signals. ``gold_tradable_universe`` is a separate ADV screen rather than
``config/universe.yaml`` membership, so some of these ETFs (GLD, SLV, IAU, USO)
can enter it independently by ADV; this change does not add them there. The
owning decision, option D of ``.agents/requests/SOL-commodity-etfs-advice.txt``
(2026-10-22), makes this separation explicit; the guard test
``tests/test_research_symbols_pipeline.py`` enforces it.

Mirrors the loader style of ``config/universe.py``: quoted-string symbols,
fail-closed on malformed entries, no hardcoded ticker list in transform code.
Every row must also declare a ``data_source`` from the shared vocabulary in
``config/data_sources.py`` (owner decision 2026-10-22); a missing or unknown
code is an error. :func:`load_research_rows` exposes those validated
``(symbol, data_source)`` rows — the ``research_universe`` temp view contract —
so a consumer never re-reads the YAML to recover provenance.
An overlap with ``config/universe.yaml`` is reported as a warning, not an
error — that is a configuration mistake to fix, not a reason to fail a run.
"""
from __future__ import annotations

import os
import re
import warnings
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import yaml

from config.data_sources import DATA_SOURCES, validate_data_source
from config.universe import load_universe

_DEFAULT_YAML = str(Path(__file__).parent / "research_symbols.yaml")
DEFAULT_GROUP = "commodity_etfs"
ETF_KINDS = frozenset({"physical", "futures"})

# Research symbols are quoted into the corporate-action universe SQL, so the
# character set is restricted to the share-class forms the platform already
# uses (BRK.B, BF-B). This is what makes a quoted SQL literal safe.
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

_OVERLAP_WARNING = (
    "research symbols also present in the trading universe "
    "(config/universe.yaml): {overlap}; research coverage is split-adjusted "
    "daily data only — remove them from one of the two files"
)


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys.

    PyYAML silently keeps the last of two identical mapping keys, which would
    make the "unique symbol" validation vacuous for a hand-edited YAML file.
    """


def _construct_unique_mapping(loader, node, deep=False):
    seen = set()
    for key_node, _value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in seen
            seen.add(key)
        except TypeError:  # unhashable key — let SafeLoader report it
            continue
        if duplicate:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r}", key_node.start_mark
            )
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def normalize_symbol(symbol: object) -> str:
    """Validate and return an upper-case research symbol.

    Raises ``ValueError`` for anything that is not a plain ticker so a symbol
    read from configuration can never inject SQL through a quoted literal.
    """
    if not isinstance(symbol, str):
        raise ValueError(
            f"research symbol must be a string, got {symbol!r} — quote every "
            f"YAML ticker (e.g. \"GLD\")"
        )
    stripped = symbol.strip()
    if stripped != stripped.upper():
        raise ValueError(f"research symbol {symbol!r} must be upper-case")
    if not _SYMBOL_RE.match(stripped):
        raise ValueError(
            f"invalid research symbol {symbol!r}; expected an upper-case "
            f"ticker matching {_SYMBOL_RE.pattern}"
        )
    return stripped


def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        try:
            return yaml.load(f, Loader=_UniqueKeyLoader) or {}
        except yaml.YAMLError as exc:
            raise ValueError(
                f"{path}: invalid research-symbol YAML: {exc}"
            ) from exc


def load_research_registry(
    path: Optional[str] = None,
    group: str = DEFAULT_GROUP,
) -> Dict[str, Dict[str, str]]:
    """Return ``{symbol: {"commodity", "etf_kind", "data_source"}}`` for ``group``.

    Validation is fail-closed: every symbol must be a unique upper-case ticker
    with a non-empty ``commodity``, an ``etf_kind`` in :data:`ETF_KINDS`, and a
    ``data_source`` drawn from :data:`config.data_sources.DATA_SOURCES`.
    Configuration order is preserved.
    """
    p = path or os.getenv("RESEARCH_SYMBOLS_YAML", _DEFAULT_YAML)
    cfg = _load_yaml(p)
    groups = cfg.get("groups")
    if not isinstance(groups, dict):
        raise ValueError(f"{p}: expected a top-level 'groups' mapping")
    entry = groups.get(group)
    if not isinstance(entry, dict):
        raise ValueError(f"{p}: missing research group {group!r}")
    raw_symbols = entry.get("symbols")
    if not isinstance(raw_symbols, dict) or not raw_symbols:
        raise ValueError(
            f"{p}: group {group!r} must declare a non-empty 'symbols' mapping"
        )

    registry: Dict[str, Dict[str, str]] = {}
    for raw_key, meta in raw_symbols.items():
        symbol = normalize_symbol(raw_key)
        if symbol in registry:
            raise ValueError(f"{p}: duplicate research symbol {symbol!r}")
        if not isinstance(meta, dict):
            raise ValueError(
                f"{p}: research symbol {symbol!r} needs a metadata mapping "
                f"with 'commodity', 'etf_kind' and 'data_source'"
            )
        commodity = meta.get("commodity")
        if not isinstance(commodity, str) or not commodity.strip():
            raise ValueError(
                f"{p}: research symbol {symbol!r} is missing 'commodity'"
            )
        etf_kind = meta.get("etf_kind")
        if etf_kind not in ETF_KINDS:
            raise ValueError(
                f"{p}: research symbol {symbol!r} has etf_kind {etf_kind!r}; "
                f"expected one of {sorted(ETF_KINDS)}"
            )
        if "data_source" not in meta:
            raise ValueError(
                f"{p}: research symbol {symbol!r} is missing 'data_source'; "
                f"expected one of {sorted(DATA_SOURCES)}"
            )
        try:
            data_source = validate_data_source(meta["data_source"])
        except ValueError as exc:
            raise ValueError(f"{p}: research symbol {symbol!r}: {exc}") from exc
        registry[symbol] = {
            "commodity": commodity.strip(),
            "etf_kind": etf_kind,
            "data_source": data_source,
        }
    return registry


def load_research_symbols(
    path: Optional[str] = None,
    group: str = DEFAULT_GROUP,
) -> List[str]:
    """Return the research symbols of ``group`` in configuration order.

    Warns (does not raise) when a symbol is also in the trading universe
    ``config/universe.yaml``: the two groups have different downstream
    contracts, so the overlap is a configuration mistake, not a runtime error.
    """
    symbols = list(load_research_registry(path=path, group=group))
    _warn_on_overlap(symbols)
    return symbols


def load_research_rows(
    path: Optional[str] = None,
    group: str = DEFAULT_GROUP,
) -> List[Tuple[str, str]]:
    """Return validated ``(symbol, data_source)`` rows in configuration order.

    This is the ``research_universe`` temp-view contract used by
    ``pipelines/run_silver_gold.py``: every row carries the provenance code its
    prices come from (owner rule: every new view carries ``data_source``). The
    values come from the same validated registry as :func:`load_research_symbols`
    so a consumer never re-reads the YAML to recover provenance, and the
    trading-universe overlap warning is emitted exactly as there.
    """
    registry = load_research_registry(path=path, group=group)
    _warn_on_overlap(list(registry))
    return [(symbol, meta["data_source"]) for symbol, meta in registry.items()]


def _warn_on_overlap(symbols: List[str]) -> None:
    """Warn when a research symbol is also in the trading universe.

    ``stacklevel=3`` points at the caller of the public loader, keeping the
    warning location unchanged now that both loaders share this helper.
    """
    trading = set(_trading_universe())
    overlap = sorted(s for s in symbols if s in trading)
    if overlap:
        warnings.warn(
            _OVERLAP_WARNING.format(overlap=overlap), UserWarning, stacklevel=3
        )


def _trading_universe() -> Iterable[str]:
    """Trading-universe symbols, upper-cased, for the overlap warning."""
    try:
        return [s.upper() for s in load_universe()]
    except (OSError, ValueError):
        # A missing/broken universe.yaml must not make the research group
        # unloadable; the trading pipeline fails on its own loader instead.
        return []


if __name__ == "__main__":
    registry = load_research_registry()
    print(f"research group {DEFAULT_GROUP}: {len(registry)} symbols")
    for symbol, meta in registry.items():
        print(
            f"  {symbol:6} {meta['commodity']:16} {meta['etf_kind']:9} "
            f"{meta['data_source']}"
        )
