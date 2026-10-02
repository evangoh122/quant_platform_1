"""config/universe.py — loads the MVP trading universe from universe.yaml.

Every silver/gold transform reads its symbol filter from this file; no
transform hardcodes a ticker list. Mirrors the loader pattern in
config/tickers.py.
"""
import os
from pathlib import Path
from typing import List

import yaml

_DEFAULT_YAML = str(Path(__file__).parent / "universe.yaml")


def load_universe(path: str | None = None) -> List[str]:
    p = path or os.getenv("UNIVERSE_YAML", _DEFAULT_YAML)
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    raw_symbols = (cfg or {}).get("symbols", [])
    seen = set()
    out = []
    for s in raw_symbols:
        if not isinstance(s, str):
            raise ValueError(
                f"{p}: non-string symbol entry {s!r} — YAML parses unquoted "
                f"scalars like ON/YES/NO/OFF/Y/N/TRUE/FALSE/NULL as booleans or "
                f"null. Quote every ticker as a string (e.g. - \"ON\")."
            )
        s = s.strip().upper()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


if __name__ == "__main__":
    syms = load_universe()
    print(f"universe size: {len(syms)}")
    print(", ".join(syms))
