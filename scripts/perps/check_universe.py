#!/usr/bin/env python3
"""Cross-check the perp universe against offline repository metadata.

This is a **report-only** tool: it never edits ``config/perp_universe.yaml``
and it exits 0 even when it finds suspects, because removing a company is an
owner decision.

For every ticker in ``config/perp_universe.yaml`` it records:

* whether the ticker is in the repository's equity universe
  (``config/universe.yaml``);
* the ticker's group(s) and description in the whole-market list
  (``config/tickers.yaml``);
* whether that description looks like an ETF / fund / preferred security;
* the SEC CIK(s) available from offline files in the repository
  (``config/sec_cik_overrides.yaml`` and
  ``tests/rag/fixtures/sec/company_tickers.json`` by default);
* whether the ticker is unmapped in those offline files.

A full SEC ``company_tickers.json`` snapshot can be supplied with
``--cik-map`` (repeatable) without touching the network.

Usage::

    python scripts/perps/check_universe.py
    python scripts/perps/check_universe.py --json /tmp/perps_universe_check.json
    python scripts/perps/check_universe.py --cik-map /path/to/company_tickers.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config.perp_universe import (  # noqa: E402
    DEFAULT_PATH as DEFAULT_PERP_UNIVERSE,
    PerpUniverse,
    load_perp_universe,
)
from config.universe import load_universe  # noqa: E402

DEFAULT_UNIVERSE = _REPO_ROOT / "config" / "universe.yaml"
DEFAULT_TICKERS = _REPO_ROOT / "config" / "tickers.yaml"
DEFAULT_CIK_MAPS: Tuple[Path, ...] = (
    _REPO_ROOT / "config" / "sec_cik_overrides.yaml",
    _REPO_ROOT / "tests" / "rag" / "fixtures" / "sec" / "company_tickers.json",
)

_TICKER_LINE_RE = re.compile(r"^\s{4}-\s+(?P<ticker>[A-Z][A-Z0-9.\-]*)\s*(?:#\s*(?P<desc>.*))?$")
_GROUP_LINE_RE = re.compile(r"^  (?P<group>[a-z0-9_]+):\s*$")
_ETF_RE = re.compile(r"\bETF\b|\bETN\b|Exchange[- ]Traded|\bIndex Fund\b", re.IGNORECASE)
_FUND_RE = re.compile(r"\bFund\b|\bTrust\b", re.IGNORECASE)
_PREFERRED_RE = re.compile(r"\bPreferred\b|\bPreference\b", re.IGNORECASE)


@dataclass(frozen=True)
class TickerMeta:
    groups: Tuple[str, ...]
    description: str


@dataclass
class TickerRow:
    ticker: str
    provider_symbol: str
    tier: str
    in_repo_universe: bool
    ticker_meta: Optional[TickerMeta]
    ciks: Tuple[str, ...]
    flags: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_suspect(self) -> bool:
        return bool({"etf", "preferred", "fund", "unmapped"} & set(self.flags))


def _clean_description(raw: str) -> str:
    text = raw.strip().strip(",")
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1]
    return text.strip()


def load_ticker_metadata(path: Path) -> Dict[str, TickerMeta]:
    """Parse ``config/tickers.yaml`` while keeping the inline descriptions.

    ``yaml.safe_load`` discards comments, and the human description lives in a
    comment (``- NVDA  # NVIDIA Corporation``).  Parsing the text keeps the
    description available for the ETF/preferred check without re-implementing
    the market data pipeline.
    """
    groups: Dict[str, List[str]] = {}
    descriptions: Dict[str, str] = {}
    current_group: Optional[str] = None
    for line in path.read_text(encoding="utf-8").splitlines():
        group_match = _GROUP_LINE_RE.match(line)
        if group_match:
            current_group = group_match.group("group")
            groups.setdefault(current_group, [])
            continue
        ticker_match = _TICKER_LINE_RE.match(line)
        if not ticker_match:
            continue
        ticker = ticker_match.group("ticker").strip()
        if not ticker:
            continue
        if current_group:
            groups[current_group].append(ticker)
        description = _clean_description(ticker_match.group("desc") or "")
        if description and ticker not in descriptions:
            descriptions[ticker] = description
    meta: Dict[str, TickerMeta] = {}
    for ticker, description in descriptions.items():
        ticker_groups = tuple(
            sorted(group for group, members in groups.items() if ticker in members)
        )
        meta[ticker] = TickerMeta(groups=ticker_groups, description=description)
    # Tickers without a description still exist in the list.
    for group, members in groups.items():
        for ticker in members:
            meta.setdefault(ticker, TickerMeta(groups=(group,), description=""))
    return meta


def _normalise_cik(value: object) -> Optional[str]:
    text = str(value).strip()
    if not text or not text.isdigit():
        return None
    return text.zfill(10)


def _add_cik(mapping: Dict[str, set], ticker: object, cik: object) -> None:
    if not isinstance(ticker, str):
        return
    normalised = _normalise_cik(cik)
    if normalised:
        mapping.setdefault(ticker.strip().upper(), set()).add(normalised)


def load_cik_map(paths: Sequence[Path]) -> Dict[str, Tuple[str, ...]]:
    """Load offline ticker -> CIK mappings.

    Supports the SEC ``company_tickers.json`` shape (``{"0": {"ticker": ...,
    "cik_str": ...}}``) and the repository override shape (``TICKER: [CIK]``).
    """
    mapping: Dict[str, set] = {}
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            document = json.loads(text)
            if isinstance(document, Mapping):
                for entry in document.values():
                    if isinstance(entry, Mapping):
                        _add_cik(mapping, entry.get("ticker"), entry.get("cik_str"))
        else:
            document = yaml.safe_load(text) or {}
            if isinstance(document, Mapping):
                for ticker, ciks in document.items():
                    if isinstance(ciks, (list, tuple)):
                        for cik in ciks:
                            _add_cik(mapping, ticker, cik)
                    else:
                        _add_cik(mapping, ticker, ciks)
    return {ticker: tuple(sorted(values)) for ticker, values in mapping.items()}


def classify(
    ticker: str,
    meta: Optional[TickerMeta],
    ciks: Tuple[str, ...],
    in_repo_universe: bool,
) -> Tuple[str, ...]:
    flags: List[str] = []
    if not in_repo_universe:
        flags.append("not_in_repo_universe")
    if meta is None:
        flags.append("not_in_tickers_yaml")
    else:
        groups = {group.lower() for group in meta.groups}
        if groups & {"etfs", "etf", "exchange_traded_fund"} or _ETF_RE.search(
            meta.description
        ):
            flags.append("etf")
        if any("fund" in group or "trust" in group for group in groups) or _FUND_RE.search(
            meta.description
        ):
            flags.append("fund")
        if _PREFERRED_RE.search(meta.description):
            flags.append("preferred")
    if not ciks:
        flags.append("unmapped")
    return tuple(flags)


def build_rows(
    universe: PerpUniverse,
    *,
    repo_universe: Iterable[str],
    ticker_meta: Mapping[str, TickerMeta],
    cik_map: Mapping[str, Tuple[str, ...]],
) -> List[TickerRow]:
    repo_set = {symbol.upper() for symbol in repo_universe}
    rows: List[TickerRow] = []
    for company in universe.companies:
        ciks = cik_map.get(company.ticker, ())
        meta = ticker_meta.get(company.ticker)
        in_repo = company.ticker in repo_set
        rows.append(
            TickerRow(
                ticker=company.ticker,
                provider_symbol=company.symbol,
                tier=company.tier,
                in_repo_universe=in_repo,
                ticker_meta=meta,
                ciks=ciks,
                flags=classify(company.ticker, meta, ciks, in_repo),
            )
        )
    return rows


def render_markdown(rows: Sequence[TickerRow], universe: PerpUniverse) -> str:
    suspects = [row for row in rows if row.is_suspect]
    classified = [
        row for row in rows if {"etf", "preferred", "fund"} & set(row.flags)
    ]
    unmapped = [row for row in rows if "unmapped" in row.flags]

    lines: List[str] = []
    lines.append("# Perp universe ticker check")
    lines.append("")
    lines.append(f"- Universe: `{universe.path}` (v{universe.version})")
    lines.append(
        f"- Companies: {universe.company_count}; controls: "
        + ", ".join(c.symbol for c in universe.controls)
    )
    lines.append(f"- Checked: {len(rows)} tickers; suspects: {len(suspects)}")
    lines.append("")
    lines.append("## Classified securities (ETF / fund / preferred)")
    lines.append("")
    if classified:
        lines.append("| Ticker | Perp symbol | Class | Evidence |")
        lines.append("|---|---|---|---|")
        for row in classified:
            classes = [
                flag
                for flag in row.flags
                if flag in {"etf", "fund", "preferred"}
            ]
            evidence = row.ticker_meta.description if row.ticker_meta else "(not in tickers.yaml)"
            groups = ", ".join(row.ticker_meta.groups) if row.ticker_meta else "-"
            lines.append(
                f"| {row.ticker} | `{row.provider_symbol}` | "
                f"{', '.join(classes)} | {evidence} ({groups}) |"
            )
    else:
        lines.append("_None detected in the offline metadata._")
    lines.append("")
    lines.append("## Unmapped in offline SEC CIK files")
    lines.append("")
    lines.append(
        f"{len(unmapped)} of {len(rows)} tickers have no CIK in the offline "
        "sources. This reflects the sparse checked-in fixtures, not necessarily "
        "a missing SEC registration; rerun with a full `company_tickers.json` "
        "snapshot via `--cik-map` before drawing conclusions."
    )
    lines.append("")
    lines.append(", ".join(row.ticker for row in unmapped) or "_none_")
    lines.append("")
    lines.append("## Full table")
    lines.append("")
    lines.append("| Ticker | Perp symbol | Tier | Repo universe | Groups | Flags | CIK |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in sorted(rows, key=lambda item: item.ticker):
        groups = ", ".join(row.ticker_meta.groups) if row.ticker_meta else ""
        lines.append(
            f"| {row.ticker} | `{row.provider_symbol}` | {row.tier} | "
            f"{'yes' if row.in_repo_universe else 'no'} | {groups} | "
            f"{', '.join(row.flags)} | {', '.join(row.ciks) or '-'} |"
        )
    lines.append("")
    lines.append(
        "Report only: no entries were removed. Owner decides whether to keep "
        "ETFs, preferreds or unmapped tickers."
    )
    lines.append("")
    return "\n".join(lines)


def render_json(rows: Sequence[TickerRow], universe: PerpUniverse) -> Dict[str, object]:
    suspects = [row.ticker for row in rows if row.is_suspect]
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe": {
            "path": str(universe.path),
            "version": universe.version,
            "companies": universe.company_count,
            "controls": [
                {"venue": control.venue, "symbol": control.symbol}
                for control in universe.controls
            ],
        },
        "summary": {
            "checked": len(rows),
            "suspects": suspects,
            "etf": [row.ticker for row in rows if "etf" in row.flags],
            "preferred": [row.ticker for row in rows if "preferred" in row.flags],
            "fund": [row.ticker for row in rows if "fund" in row.flags],
            "unmapped_offline": [
                row.ticker for row in rows if "unmapped" in row.flags
            ],
            "not_in_repo_universe": [
                row.ticker for row in rows if "not_in_repo_universe" in row.flags
            ],
        },
        "rows": [
            {
                "ticker": row.ticker,
                "provider_symbol": row.provider_symbol,
                "tier": row.tier,
                "in_repo_universe": row.in_repo_universe,
                "groups": list(row.ticker_meta.groups) if row.ticker_meta else [],
                "description": row.ticker_meta.description if row.ticker_meta else "",
                "ciks": list(row.ciks),
                "flags": list(row.flags),
            }
            for row in sorted(rows, key=lambda item: item.ticker)
        ],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--perps", default=str(DEFAULT_PERP_UNIVERSE))
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--tickers", default=str(DEFAULT_TICKERS))
    parser.add_argument(
        "--cik-map",
        action="append",
        default=None,
        help="offline company_tickers.json / CIK override YAML (repeatable)",
    )
    parser.add_argument("--json", default=None, help="write the report as JSON")
    args = parser.parse_args(argv)

    universe = load_perp_universe(args.perps)
    repo_universe = load_universe(args.universe)
    ticker_meta = load_ticker_metadata(Path(args.tickers))
    cik_paths = (
        [Path(item) for item in args.cik_map]
        if args.cik_map
        else list(DEFAULT_CIK_MAPS)
    )
    cik_map = load_cik_map(cik_paths)
    rows = build_rows(
        universe,
        repo_universe=repo_universe,
        ticker_meta=ticker_meta,
        cik_map=cik_map,
    )

    report = render_markdown(rows, universe)
    print(report)
    if args.json:
        target = Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(render_json(rows, universe), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
