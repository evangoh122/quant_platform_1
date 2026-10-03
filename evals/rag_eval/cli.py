"""evals/rag_eval/cli.py — CLI entry point for the RAG eval harness."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from evals.rag_eval.models import (
    RETRIEVAL_MODES,
    GoldenItem,
    RetrievalConfig,
    RunReport,
)


def _git_sha() -> str:
    """Best-effort short commit SHA."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _load_golden(path: Path) -> list[GoldenItem]:
    """Load golden items from JSONL."""
    items: list[GoldenItem] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            items.append(GoldenItem(
                id=obj["id"],
                ticker=obj.get("ticker", ""),
                question=obj.get("question", ""),
                gold_chunk_ids=tuple(obj.get("gold_chunk_ids", [])),
                gold_accession_sections=tuple(
                    tuple(x) for x in obj.get("gold_accession_sections", [])
                ),
                item_type=obj.get("item_type", "answerable"),
                allowed_older_chunk_ids=tuple(obj.get("allowed_older_chunk_ids", [])),
                as_of=obj.get("as_of"),
                gold_answer=obj.get("gold_answer"),
            ))
    return items


def _validate_golden(items: list[GoldenItem]) -> list[str]:
    """Validate golden items. Returns list of error messages."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    for item in items:
        if not item.id:
            errors.append("Golden item missing 'id'")
        if item.id in seen_ids:
            errors.append(f"Duplicate golden item id: {item.id}")
        seen_ids.add(item.id)
        if not item.question:
            errors.append(f"Golden item {item.id} missing 'question'")
        if item.item_type not in ("answerable", "unanswerable", "point_in_time_trap"):
            errors.append(f"Golden item {item.id} has invalid item_type: {item.item_type}")
    return errors


def _file_sha256(path: Path) -> str:
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    """Main entry point for the RAG eval harness.

    Returns 0 on success, nonzero on failure.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="SEC RAG retrieval evaluation harness",
        prog="python -m evals.rag_eval",
    )
    parser.add_argument(
        "--golden", type=Path, required=True,
        help="Path to golden JSONL file",
    )
    parser.add_argument(
        "--corpus", type=Path, required=True,
        help="Path to corpus JSONL file",
    )
    parser.add_argument(
        "--embeddings", type=Path, default=None,
        help="Path to embedding sidecar .npz file",
    )
    parser.add_argument(
        "--adapter", choices=["jsonl", "delta"], default="jsonl",
        help="Corpus adapter to use",
    )
    parser.add_argument(
        "--mode", action="append", default=None,
        help="Retrieval mode(s) to test. Can be repeated. Use 'all' for all modes.",
    )
    parser.add_argument(
        "--ticker-filter", choices=["on", "off", "both"], default="both",
        help="Ticker filter mode",
    )
    parser.add_argument(
        "--top-k", type=int, default=10,
        help="Top-k for retrieval",
    )
    parser.add_argument(
        "--seed", type=int, default=1729,
        help="Random seed for bootstrap",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("evals/results"),
        help="Output directory for reports",
    )
    parser.add_argument(
        "--generation", action="store_true",
        help="Enable generation mode (phase 2)",
    )
    parser.add_argument(
        "--allow-paid-calls", action="store_true",
        help="Allow paid LLM API calls for generation judging",
    )
    parser.add_argument(
        "--smoke-ids", type=str, default=None,
        help="Comma-separated golden item IDs for smoke run",
    )

    args = parser.parse_args(argv)

    # Load and validate golden set
    golden_items = _load_golden(args.golden)
    errors = _validate_golden(golden_items)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    # Filter to smoke IDs if specified
    if args.smoke_ids:
        smoke_set = set(args.smoke_ids.split(","))
        golden_items = [item for item in golden_items if item.id in smoke_set]
        if not golden_items:
            print("ERROR: No golden items matched smoke IDs", file=sys.stderr)
            return 1

    # Determine modes
    if args.mode is None or "all" in args.mode:
        modes = list(RETRIEVAL_MODES)
    else:
        modes = args.mode
        for m in modes:
            if m not in RETRIEVAL_MODES:
                print(f"ERROR: Unknown mode '{m}'. Valid: {RETRIEVAL_MODES}", file=sys.stderr)
                return 1

    # Determine ticker filter settings
    if args.ticker_filter == "on":
        ticker_filters = [True]
    elif args.ticker_filter == "off":
        ticker_filters = [False]
    else:
        ticker_filters = [True, False]

    # Build configs (8 ablations: 4 modes x 2 ticker filters)
    configs: list[RetrievalConfig] = []
    for mode in modes:
        for tf in ticker_filters:
            configs.append(RetrievalConfig(
                mode=mode,
                ticker_filter=tf,
                top_k=args.top_k,
            ))

    # Load corpus adapter
    if args.adapter == "jsonl":
        from evals.rag_eval.corpus import JsonlCorpusAdapter
        adapter = JsonlCorpusAdapter.from_files(
            corpus_path=args.corpus,
            embeddings_path=args.embeddings,
        )
    elif args.adapter == "delta":
        from evals.rag_eval.corpus import DeltaCorpusAdapter
        adapter = DeltaCorpusAdapter.load()
    else:
        print(f"ERROR: Unknown adapter '{args.adapter}'", file=sys.stderr)
        return 1

    # Check: dense modes require embeddings
    for mode in modes:
        if mode in ("dense", "hybrid_rrf", "hybrid_rerank"):
            try:
                adapter.embedding_map()
            except (FileNotFoundError, RuntimeError) as e:
                if args.adapter == "jsonl":
                    print(
                        f"ERROR: Mode '{mode}' requires embeddings but none available: {e}",
                        file=sys.stderr,
                    )
                    return 1
                # For delta adapter, embeddings should be available from Delta

    # Run retrieval
    from evals.rag_eval.retrieve import run_retrieval

    print(f"Running {len(golden_items)} items x {len(configs)} configs = "
          f"{len(golden_items) * len(configs)} evaluations...")

    item_results = run_retrieval(golden_items, configs, adapter)

    # Check for PIT leakage — hard gate
    pit_leakage_total = 0
    pit_leakage_by_config: dict[str, int] = {}
    for ir in item_results:
        cfg_label = ir.config.label()
        if ir.leakage_count > 0:
            pit_leakage_total += ir.leakage_count
            pit_leakage_by_config[cfg_label] = (
                pit_leakage_by_config.get(cfg_label, 0) + ir.leakage_count
            )
            print(f"  PIT LEAKAGE: {ir.item.id} @ {cfg_label}: {ir.leakage_count} chunk(s)")

    # Score items
    from evals.rag_eval.metrics import aggregate_results

    corpus_map = {rec.chunk_id: rec for rec in adapter.records()}
    agg = aggregate_results(item_results, corpus_map)

    # Build report
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report = RunReport(
        run_id=run_id,
        git_sha=_git_sha(),
        corpus_sha256=getattr(adapter, "corpus_sha256", ""),
        golden_sha256=_file_sha256(args.golden),
        embedding_model=getattr(adapter, "embedding_model_name", ""),
        embedding_dimension=getattr(adapter, "embedding_dimension", 0),
        rrf_k=60,
        candidate_depth_multiplier=2,
        top_k_values=[args.top_k],
        seed=args.seed,
        adapter_type=args.adapter,
        cli_args=vars(args),
        timestamp=datetime.now(timezone.utc).isoformat(),
        environment={"platform": sys.platform, "python": sys.version},
        item_results=item_results,
        overall_metrics=agg["overall"],
        per_type_metrics=agg["per_type"],
        per_ticker_metrics=agg["per_ticker"],
        per_mode_metrics=agg.get("per_mode", {}),
        secondary_metrics=agg["secondary"],
        bootstrap_cis=agg["bootstrap"],
        abstention_results=agg["abstention"],
        pit_leakage_total=pit_leakage_total,
        pit_leakage_by_config=pit_leakage_by_config,
    )

    # Write report
    from evals.rag_eval.report import build_report, write_report

    report_dict = build_report(report)
    json_path, md_path = write_report(report_dict, args.output_dir, date.today())

    print(f"\nReports written:")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")

    # Print summary
    error_count = sum(1 for ir in item_results if ir.error)
    total_items = len(item_results)
    n_evaluated = total_items - error_count

    pit_status = "PASS"
    if error_count:
        pit_status = "INCOMPLETE"
    elif pit_leakage_total > 0:
        pit_status = "FAIL"

    print(f"\n{'='*60}")
    print(f"  Items: {total_items} total, {n_evaluated} evaluated, {error_count} errors")
    print(f"  PIT Leakage: {pit_leakage_total} {pit_status}")
    print(f"  Overall recall@5: {agg['overall'].get('recall_at_5', 0):.4f}")
    print(f"  Overall MRR@10: {agg['overall'].get('mrr_at_10', 0):.4f}")
    print(f"  Overall nDCG@10: {agg['overall'].get('ndcg_at_10', 0):.4f}")

    # Per-mode summary
    per_mode = agg.get("per_mode", {})
    if per_mode:
        print(f"\n  Per-mode breakdown:")
        for mode, mode_agg in sorted(per_mode.items()):
            me = mode_agg.get("n_evaluated", 0)
            merr = mode_agg.get("n_errors", 0)
            mr5 = mode_agg.get("recall_at_5", 0.0)
            print(f"    {mode}: n_evaluated={me}, n_errors={merr}, recall@5={mr5:.4f}")

    print(f"{'='*60}")

    # Exit nonzero for any failure condition
    if pit_leakage_total > 0:
        print("FAIL: PIT leakage detected", file=sys.stderr)
        return 1

    # Check for errors in item results — any error makes the run FAIL
    if error_count:
        print(f"FAIL: {error_count} item(s) had errors", file=sys.stderr)
        return 1

    return 0