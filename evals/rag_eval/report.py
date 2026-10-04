"""evals/rag_eval/report.py — Report generation for RAG eval runs.

Produces JSON and Markdown reports with all required config, strata, CIs,
errors, and non-overwrite behavior.
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from evals.rag_eval.models import RunReport


def build_report(run_report: RunReport, *, include_text: bool = False) -> dict[str, Any]:
    """Convert RunReport to a serializable dict.

    Args:
        run_report: The run report to convert.
        include_text: If True, include retrieval hit text truncated to 200 chars
            (for local debugging only).  Default False — text is never written
            into the public scorecard artifact.
    """
    report = run_report.to_dict()

    # Strip raw filing text from item_results unless explicitly requested
    for ir_dict in report.get("item_results", []):
        for hit_dict in ir_dict.get("hits", []):
            if include_text:
                raw = hit_dict.get("text", "")
                hit_dict["text"] = raw[:200] if raw else ""
            else:
                hit_dict.pop("text", None)
            hit_dict.pop("chunk_text", None)

    # Redact absolute paths in cli_args to basename
    cli_args = report.get("cli_args", {})
    if cli_args:
        def _redact_path(v):
            # Handle pathlib.Path objects directly
            if isinstance(v, Path):
                if v.is_absolute():
                    return v.name
                # Convert relative paths to plain string
                return str(v)
            # Handle string paths
            if isinstance(v, str) and Path(v).is_absolute():
                return Path(v).name
            # Handle any os.PathLike object
            if hasattr(v, '__fspath__'):
                p = Path(v)
                if p.is_absolute():
                    return p.name
                return str(p)
            return v

        report["cli_args"] = {
            k: _redact_path(v)
            for k, v in cli_args.items()
        }

    # Add per-item rows
    item_rows: list[dict[str, Any]] = []
    for ir in run_report.item_results:
        row: dict[str, Any] = {
            "item_id": ir.item.id,
            "ticker": ir.item.ticker,
            "item_type": ir.item.item_type,
            "config": ir.config.label(),
            "mode": ir.config.mode,
            "ticker_filter": ir.config.ticker_filter,
            "n_hits": len(ir.hits),
            "leakage_count": ir.leakage_count,
            "leaked_chunk_ids": ir.leaked_chunk_ids,
            "error": ir.error,
            "allowed_top_hit": ir.allowed_top_hit,
            "abstention_label": ir.abstention_label,
        }
        row.update(ir.metrics)
        item_rows.append(row)

    report["item_rows"] = item_rows
    return report


def render_markdown(report: dict[str, Any]) -> str:
    """Render the report dict as Markdown."""
    lines: list[str] = []
    lines.append("# RAG Eval Report\n")

    # Config
    lines.append("## Configuration\n")
    lines.append(f"- **Run ID:** {report.get('run_id', 'N/A')}")
    lines.append(f"- **Git SHA:** {report.get('git_sha', 'N/A')}")
    lines.append(f"- **Timestamp:** {report.get('timestamp', 'N/A')}")
    lines.append(f"- **Adapter:** {report.get('adapter_type', 'N/A')}")
    lines.append(f"- **Corpus SHA-256:** {report.get('corpus_sha256', 'N/A')[:16]}...")
    lines.append(f"- **Golden SHA-256:** {report.get('golden_sha256', 'N/A')[:16]}...")
    lines.append(f"- **Embedding model:** {report.get('embedding_model', 'N/A')}")
    lines.append(f"- **Embedding dimension:** {report.get('embedding_dimension', 0)}")
    lines.append(f"- **Reranker model:** {report.get('reranker_model', 'N/A')}")
    lines.append(f"- **Reranker disabled reason:** {report.get('reranker_disabled_reason', 'N/A')}")
    lines.append(f"- **RRF k:** {report.get('rrf_k', 60)}")
    lines.append(f"- **Candidate depth multiplier:** {report.get('candidate_depth_multiplier', 2)}")
    lines.append(f"- **Top-k values:** {report.get('top_k_values', [])}")
    lines.append(f"- **Seed:** {report.get('seed', 1729)}")
    lines.append(f"- **CLI args:** `{report.get('cli_args', {})}`")
    lines.append("")

    # PIT Leakage Gate
    lines.append("## PIT Leakage Gate\n")
    pit_total = report.get("pit_leakage_total", 0)
    status = report.get("status", "")
    status_label = status if status else ("PASS" if pit_total == 0 else "FAIL")
    lines.append(f"**Total leakage: {pit_total}** {status_label}\n")
    leakage_by_config = report.get("pit_leakage_by_config", {})
    leaked_ids_by_config = report.get("leaked_chunk_ids_by_config", {})
    if leakage_by_config:
        lines.append("| Config | Leakage | Leaked Chunk IDs |")
        lines.append("|--------|---------|------------------|")
        for cfg, count in sorted(leakage_by_config.items()):
            ids = leaked_ids_by_config.get(cfg, [])
            truncated = ids[:20]
            ids_str = ", ".join(truncated)
            if len(ids) > 20:
                ids_str += f" (+{len(ids) - 20} more)"
            lines.append(f"| {cfg} | {count} | {ids_str} |")
        lines.append("")

    # Overall metrics
    overall = report.get("overall_metrics", {})
    if overall:
        lines.append("## Overall Metrics (Answerable Items)\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for k, v in sorted(overall.items()):
            if isinstance(v, float):
                lines.append(f"| {k} | {v:.4f} |")
            else:
                lines.append(f"| {k} | {v} |")
        lines.append("")

    # Per-type metrics
    per_type = report.get("per_type_metrics", {})
    if per_type:
        lines.append("## Per-Type Metrics\n")
        for item_type, metrics in sorted(per_type.items()):
            lines.append(f"### {item_type}\n")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            for k, v in sorted(metrics.items()):
                if isinstance(v, float):
                    lines.append(f"| {k} | {v:.4f} |")
                else:
                    lines.append(f"| {k} | {v} |")
            lines.append("")

    # Per-ticker metrics
    per_ticker = report.get("per_ticker_metrics", {})
    if per_ticker:
        lines.append("## Per-Ticker Metrics\n")
        for ticker, metrics in sorted(per_ticker.items()):
            lines.append(f"### {ticker}\n")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            for k, v in sorted(metrics.items()):
                if isinstance(v, float):
                    lines.append(f"| {k} | {v:.4f} |")
                else:
                    lines.append(f"| {k} | {v} |")
            lines.append("")

    # Per-mode metrics
    per_mode = report.get("per_mode_metrics", {})
    if per_mode:
        lines.append("## Per-Mode Metrics\n")
        lines.append("| Mode | n_evaluated | n_errors | recall@5 | MRR@10 | nDCG@10 |")
        lines.append("|------|-------------|----------|----------|--------|---------|")
        for mode, metrics in sorted(per_mode.items()):
            ne = metrics.get("n_evaluated", 0)
            nerr = metrics.get("n_errors", 0)
            r5 = metrics.get("recall_at_5", 0.0)
            mrr = metrics.get("mrr_at_10", 0.0)
            ndcg = metrics.get("ndcg_at_10", 0.0)
            lines.append(f"| {mode} | {ne} | {nerr} | {r5:.4f} | {mrr:.4f} | {ndcg:.4f} |")
        lines.append("")

    # Bootstrap CIs
    bootstrap = report.get("bootstrap_cis", {})
    if bootstrap:
        lines.append("## Bootstrap Confidence Intervals\n")
        for metric_name in ("recall_at_5", "mrr_at_10"):
            ci = bootstrap.get(metric_name)
            if ci:
                warn = f" ⚠ {ci['warning']}" if ci.get("warning") else ""
                lines.append(
                    f"- **{metric_name}:** {ci['mean']:.4f} "
                    f"[{ci['lower']:.4f}, {ci['upper']:.4f}] "
                    f"(n={ci['n']}, seed=1729){warn}"
                )
        lines.append("")

    # Abstention/trap results
    abstention = report.get("abstention_results", {})
    if abstention:
        lines.append("## Abstention & Trap Results\n")
        lines.append("| Item | Type | Config | Allowed Top Hit | Label |")
        lines.append("|------|------|--------|-----------------|-------|")
        for key, val in sorted(abstention.items()):
            lines.append(
                f"| {val.get('item_id', '')} | {val.get('item_type', '')} | "
                f"{val.get('config', '')} | {val.get('allowed_top_hit', '')} | "
                f"{val.get('abstention_label', '')} |"
            )
        lines.append("")

    # Errors
    errors = report.get("errors", [])
    if errors:
        lines.append("## Errors\n")
        for err in errors:
            lines.append(f"- {err}")
        lines.append("")

    return "\n".join(lines)


def write_report(
    report: dict[str, Any],
    output_dir: Path,
    run_date: date,
) -> tuple[Path, Path]:
    """Write JSON and Markdown reports to output_dir.

    Avoids overwrite by adding a run ID suffix when the date's files exist.
    Returns (json_path, md_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"rag_eval_{run_date.isoformat()}"
    json_path = output_dir / f"{base_name}.json"
    md_path = output_dir / f"{base_name}.md"

    # Non-overwrite: add suffix if files exist
    if json_path.exists() or md_path.exists():
        run_id = report.get("run_id", "run")
        base_name = f"rag_eval_{run_date.isoformat()}_{run_id}"
        json_path = output_dir / f"{base_name}.json"
        md_path = output_dir / f"{base_name}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    md_content = render_markdown(report)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return json_path, md_path