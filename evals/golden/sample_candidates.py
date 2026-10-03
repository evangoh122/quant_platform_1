"""Deterministic authoring aid for SEC RAG golden set.

Samples candidate chunks from the corpus, stratified by ticker, filing section,
and form type. Emits full chunk text plus metadata for human review. Never
invents answers.

Usage:
    python evals/golden/sample_candidates.py
    python evals/golden/sample_candidates.py --corpus evals/data/sec_corpus.jsonl --per-ticker 10
    python evals/golden/sample_candidates.py --sections item7_mda,item1a_risk_factors --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable


def load_corpus(path: Path) -> list[dict]:
    """Load the JSONL corpus file and return a list of chunk dicts."""
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def index_corpus(rows: Iterable[dict]) -> dict[str, dict]:
    """Build a chunk_id -> chunk dict index."""
    return {r["chunk_id"]: r for r in rows}


def sample_candidates(
    rows: list[dict],
    *,
    seed: int = 42,
    per_ticker: int = 5,
    sections: set[str] | None = None,
) -> list[dict]:
    """Sample candidate chunks, stratified by ticker, section, and form.

    Returns up to ``per_ticker`` chunks per ticker, trying to cover as many
    distinct sections and form types as possible before filling remaining slots
    randomly.
    """
    if sections:
        rows = [r for r in rows if r["filing_section"] in sections]
        if not rows:
            return []

    rng = random.Random(seed)

    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_ticker[r["ticker"]].append(r)

    candidates: list[dict] = []
    for ticker in sorted(by_ticker):
        ticker_rows = by_ticker[ticker]

        # Stratify by (section, form_type) to maximize diversity
        buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in ticker_rows:
            buckets[(r["filing_section"], r["form_type"])].append(r)

        # Shuffle within each bucket for determinism
        for bucket in buckets.values():
            rng.shuffle(bucket)

        # Round-robin across buckets first, then fill remaining randomly
        selected: list[dict] = []
        bucket_keys = sorted(buckets)
        rng.shuffle(bucket_keys)
        bucket_iters = {k: iter(v) for k, v in buckets.items()}

        # Phase 1: one from each bucket
        for k in bucket_keys:
            try:
                selected.append(next(bucket_iters[k]))
            except StopIteration:
                pass

        # Phase 2: fill remaining from any bucket
        remaining = [r for r in ticker_rows if r not in selected]
        rng.shuffle(remaining)
        for r in remaining:
            if len(selected) >= per_ticker:
                break
            selected.append(r)

        candidates.extend(selected[:per_ticker])

    return candidates


def write_candidate_packet(candidates: list[dict], output: Path) -> None:
    """Write candidate packet to JSONL. Each line includes full chunk metadata."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as fh:
        for c in candidates:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sample candidate chunks for golden-set authoring."
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("evals/data/sec_corpus.jsonl"),
        help="Path to the corpus JSONL file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/data/candidate_packet.jsonl"),
        help="Output path for the candidate packet JSONL.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic sampling.",
    )
    parser.add_argument(
        "--per-ticker",
        type=int,
        default=5,
        help="Maximum chunks to sample per ticker.",
    )
    parser.add_argument(
        "--sections",
        type=str,
        default=None,
        help="Comma-separated list of filing sections to filter on.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if not args.corpus.exists():
        print(f"Error: corpus file not found: {args.corpus}", file=sys.stderr)
        return 1

    sections = None
    if args.sections:
        sections = {s.strip() for s in args.sections.split(",")}

    rows = load_corpus(args.corpus)
    print(f"Loaded {len(rows)} chunks from {args.corpus}")

    candidates = sample_candidates(
        rows,
        seed=args.seed,
        per_ticker=args.per_ticker,
        sections=sections,
    )
    print(f"Sampled {len(candidates)} candidates")

    write_candidate_packet(candidates, args.output)
    print(f"Wrote candidate packet to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())