"""Strict validation for SEC RAG golden set v1.

Validates schema, corpus references, point-in-time constraints, answer support,
coverage quotas, and provenance. Returns 0 only when all checks pass.

Usage:
    python evals/golden/validate.py --golden evals/golden/golden_v1.jsonl \
        --schema evals/golden/golden_v1.schema.json \
        --corpus evals/data/sec_corpus.jsonl
    python evals/golden/validate.py --golden ... --schema ... --corpus ... --allow-unverified
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Exact frozen quotas
# ---------------------------------------------------------------------------
TYPE_QUOTA: dict[str, int] = {
    "factual_lookup": 24,
    "risk_factor": 8,
    "business_description": 8,
    "quantitative_market_risk": 8,
    "cross_filing_comparison": 10,
    "point_in_time_trap": 12,
    "unanswerable": 10,
}
TOTAL_ITEMS = 80
ITEMS_PER_TICKER = 5
TICKERS = {
    "ADI", "AMAT", "AMD", "AVGO", "INTC", "KLAC", "LRCX", "MCHP",
    "MPWR", "MU", "NVDA", "QCOM", "SNPS", "SWKS", "TER", "TXN",
}
SECTIONS = {
    "item7_mda", "item1_business", "item7a_quant_risk",
    "item8_financial_statements", "item1a_risk_factors", "full_document",
}
DIFFICULTIES = {"easy", "medium", "hard"}
TRICKY_NUMERIC_MIN = 20
MIN_10K = 24
MIN_10Q = 24

# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file into a list of dicts."""
    items: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON parse error at line {lineno}: {exc}") from exc
    return items


def load_schema(path: Path) -> dict:
    """Load a JSON Schema file."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_question(text: str) -> str:
    """Normalize a question for duplicate detection."""
    # NFKC normalization
    text = unicodedata.normalize("NFKC", text)
    # Lowercase
    text = text.lower()
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Remove terminal punctuation
    text = text.rstrip("?.! ")
    return text


def parse_utc(text: str) -> datetime:
    """Parse an RFC 3339 UTC timestamp ending in Z."""
    # Expect exactly YYYY-MM-DDTHH:MM:SSZ
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", text):
        raise ValueError(f"Timestamp does not match RFC 3339 UTC format: {text}")
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def normalize_numeric_values(text: str) -> list[tuple[str, float]]:
    """Extract and normalize numeric values from text.

    Returns list of (original_text, normalized_value) pairs.
    Handles: $, commas, parenthesized negatives, %, thousand/million/billion.
    Does NOT equate different units.
    """
    results: list[tuple[str, float]] = []

    # Pattern: currency amounts with optional multiplier
    # e.g., "$1,234.5 million", "($253 million)", "$0.65 per share"
    currency_pat = re.compile(
        r"\(?\$?\s*([\d,]+(?:\.\d+)?)\s*(?:million|billion|trillion)?\)?",
        re.IGNORECASE,
    )

    for m in currency_pat.finditer(text):
        raw = m.group(0).strip()
        num_str = m.group(1).replace(",", "")
        try:
            value = float(num_str)
        except ValueError:
            continue

        # Parenthesized negative
        if raw.startswith("(") and raw.endswith(")"):
            value = -value

        # Multiplier
        lower = raw.lower()
        if "trillion" in lower:
            value *= 1_000_000_000_000
        elif "billion" in lower:
            value *= 1_000_000_000
        elif "million" in lower:
            value *= 1_000_000

        results.append((raw, value))

    # Pattern: percentages
    pct_pat = re.compile(r"([\d,]+(?:\.\d+)?)\s*%")
    for m in pct_pat.finditer(text):
        num_str = m.group(1).replace(",", "")
        try:
            value = float(num_str)
        except ValueError:
            continue
        results.append((m.group(0), value))

    return results


def answer_supported(answer: str, evidence: str) -> bool:
    """Check whether the gold answer is supported by the evidence span.

    First tries normalized literal substring matching, then conservative
    numeric equivalence over values extracted from the verbatim evidence.
    ABSTAIN is exempt only where the item contract permits it.
    """
    if answer == "ABSTAIN":
        return True  # Caller must check item contract separately

    # Normalized literal substring
    norm_answer = normalize_question(answer)
    norm_evidence = normalize_question(evidence)
    if norm_answer in norm_evidence:
        return True

    # Conservative numeric equivalence
    answer_nums = normalize_numeric_values(answer)
    evidence_nums = normalize_numeric_values(evidence)

    if not answer_nums:
        return False

    for _, a_val in answer_nums:
        found = False
        for _, e_val in evidence_nums:
            if abs(a_val - e_val) < 0.01 * max(abs(a_val), 1.0):
                found = True
                break
        if not found:
            return False

    return bool(answer_nums)


def _has_tricky_numeric(text: str) -> bool:
    """Check if text contains tricky numeric renderings."""
    patterns = [
        r"\$[\d,]+",           # dollar with commas
        r"\d+\.\d+%",          # decimal percentage
        r"\(\$\d",             # parenthesized negative
        r"\d+(?:\.\d+)?\s*(?:million|billion|trillion)",  # unit multipliers
        r"\d+(?:\.\d+)?\s*(?:per\s+share|basis\s+points?)",  # per-share/bps
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_schema(items: list[dict], schema: dict) -> list[str]:
    """Validate items against JSON Schema. Rejects duplicate IDs."""
    errors: list[str] = []

    try:
        from jsonschema import Draft202012Validator
        validator = Draft202012Validator(schema)
        for i, item in enumerate(items):
            for error in validator.iter_errors(item):
                item_id = item.get("id", f"index-{i}")
                errors.append(f"[{item_id}] schema: {error.message}")
    except ImportError:
        # Fallback: manual validation of required fields
        required = set(schema.get("required", []))
        for i, item in enumerate(items):
            item_id = item.get("id", f"index-{i}")
            for field in required:
                if field not in item:
                    errors.append(f"[{item_id}] missing required field: {field}")

    # Check duplicate IDs
    seen_ids: set[str] = set()
    for item in items:
        iid = item.get("id", "")
        if iid in seen_ids:
            errors.append(f"[{iid}] duplicate ID")
        seen_ids.add(iid)

    return errors


# ---------------------------------------------------------------------------
# Reference validation
# ---------------------------------------------------------------------------

def validate_references(items: list[dict], corpus_by_id: dict[str, dict]) -> list[str]:
    """Check every referenced chunk exists and metadata matches."""
    errors: list[str] = []

    for item in items:
        iid = item["id"]
        ticker = item["ticker"]
        gold_acc = item.get("gold_accession", "")
        gold_sec = item.get("gold_section", "")

        for cid in item.get("gold_chunk_ids", []):
            if cid not in corpus_by_id:
                errors.append(f"[{iid}] unknown chunk_id: {cid}")
                continue

            chunk = corpus_by_id[cid]

            # Ticker must match
            if chunk["ticker"] != ticker:
                errors.append(
                    f"[{iid}] chunk {cid[:12]}.. ticker mismatch: "
                    f"chunk={chunk['ticker']}, item={ticker}"
                )

        # For non-unanswerable items with gold_accession, check primary chunk
        if item.get("answerable", True) and gold_acc and item.get("gold_chunk_ids"):
            primary_cid = item["gold_chunk_ids"][0]
            if primary_cid in corpus_by_id:
                chunk = corpus_by_id[primary_cid]
                # For cross-filing comparisons, notes.rationale explains multiple loci
                if item["question_type"] != "cross_filing_comparison":
                    if chunk["accession_number"] != gold_acc:
                        errors.append(
                            f"[{iid}] primary chunk accession mismatch: "
                            f"chunk={chunk['accession_number']}, item={gold_acc}"
                        )
                    if gold_sec and chunk["filing_section"] != gold_sec:
                        errors.append(
                            f"[{iid}] primary chunk section mismatch: "
                            f"chunk={chunk['filing_section']}, item={gold_sec}"
                        )

    return errors


# ---------------------------------------------------------------------------
# Point-in-time validation
# ---------------------------------------------------------------------------

def validate_point_in_time(items: list[dict], corpus_by_id: dict[str, dict]) -> list[str]:
    """Validate point-in-time constraints for all items."""
    errors: list[str] = []

    for item in items:
        iid = item["id"]
        try:
            as_of_dt = parse_utc(item["as_of"])
        except ValueError as exc:
            errors.append(f"[{iid}] bad as_of: {exc}")
            continue

        as_of_epoch = int(as_of_dt.timestamp())
        answerable = item.get("answerable", True)
        trap_info = item.get("notes", {}).get("trap")

        if trap_info is None:
            # Ordinary answerable item: every gold chunk must be <= as_of
            if answerable:
                for cid in item.get("gold_chunk_ids", []):
                    if cid not in corpus_by_id:
                        continue
                    chunk = corpus_by_id[cid]
                    accepted = chunk.get("accepted_epoch")
                    if accepted is None:
                        errors.append(f"[{iid}] chunk {cid[:12]}.. missing accepted_epoch")
                        continue
                    if accepted > as_of_epoch:
                        errors.append(
                            f"[{iid}] chunk {cid[:12]}.. accepted_epoch={accepted} "
                            f"> as_of={as_of_epoch}"
                        )
        else:
            # PIT trap
            expected = trap_info.get("expected_behavior")
            future_cids = trap_info.get("future_chunk_ids", [])

            if expected == "abstain":
                # Future chunks must be > as_of
                for cid in future_cids:
                    if cid not in corpus_by_id:
                        errors.append(f"[{iid}] trap future chunk not found: {cid[:12]}..")
                        continue
                    chunk = corpus_by_id[cid]
                    accepted = chunk.get("accepted_epoch")
                    if accepted is None:
                        errors.append(f"[{iid}] trap future chunk missing epoch: {cid[:12]}..")
                        continue
                    if accepted <= as_of_epoch:
                        errors.append(
                            f"[{iid}] trap future chunk {cid[:12]}.. "
                            f"accepted_epoch={accepted} <= as_of={as_of_epoch}"
                        )

            elif expected == "older_filing_answer":
                # Allowed gold chunks must be <= as_of
                for cid in item.get("gold_chunk_ids", []):
                    if cid not in corpus_by_id:
                        continue
                    chunk = corpus_by_id[cid]
                    accepted = chunk.get("accepted_epoch")
                    if accepted is None:
                        errors.append(f"[{iid}] gold chunk missing epoch: {cid[:12]}..")
                        continue
                    if accepted > as_of_epoch:
                        errors.append(
                            f"[{iid}] gold chunk {cid[:12]}.. "
                            f"accepted_epoch={accepted} > as_of={as_of_epoch}"
                        )
                # Future chunks must be > as_of
                for cid in future_cids:
                    if cid not in corpus_by_id:
                        errors.append(f"[{iid}] trap future chunk not found: {cid[:12]}..")
                        continue
                    chunk = corpus_by_id[cid]
                    accepted = chunk.get("accepted_epoch")
                    if accepted is None:
                        continue
                    if accepted <= as_of_epoch:
                        errors.append(
                            f"[{iid}] trap future chunk {cid[:12]}.. "
                            f"accepted_epoch={accepted} <= as_of={as_of_epoch}"
                        )

    return errors


# ---------------------------------------------------------------------------
# Coverage validation
# ---------------------------------------------------------------------------

def validate_coverage(items: list[dict], corpus_by_id: dict[str, dict]) -> list[str]:
    """Validate type quota, per-ticker count, section/difficulty coverage, etc."""
    errors: list[str] = []

    # Total count
    if len(items) != TOTAL_ITEMS:
        errors.append(f"Expected {TOTAL_ITEMS} items, got {len(items)}")

    # Type quota
    type_counts = Counter(item["question_type"] for item in items)
    for qtype, expected in TYPE_QUOTA.items():
        actual = type_counts.get(qtype, 0)
        if actual < expected:
            errors.append(
                f"Type '{qtype}': need >= {expected}, got {actual}"
            )

    # Per-ticker count
    ticker_counts = Counter(item["ticker"] for item in items)
    for ticker in TICKERS:
        actual = ticker_counts.get(ticker, 0)
        if actual != ITEMS_PER_TICKER:
            errors.append(
                f"Ticker '{ticker}': need {ITEMS_PER_TICKER}, got {actual}"
            )

    # All tickers present
    missing_tickers = TICKERS - set(ticker_counts)
    if missing_tickers:
        errors.append(f"Missing tickers: {sorted(missing_tickers)}")

    # Section coverage
    sections_seen = set()
    for item in items:
        sec = item.get("gold_section", "")
        if sec:
            sections_seen.add(sec)
    # full_document counts as a section too
    missing_sections = {"item7_mda", "item1_business", "item7a_quant_risk",
                        "item8_financial_statements", "item1a_risk_factors"} - sections_seen
    if missing_sections:
        errors.append(f"Missing sections: {sorted(missing_sections)}")

    # Difficulty coverage
    diffs_seen = set(item["difficulty"] for item in items)
    missing_diffs = DIFFICULTIES - diffs_seen
    if missing_diffs:
        errors.append(f"Missing difficulties: {sorted(missing_diffs)}")

    # 10-K / 10-Q spread
    form_10k = 0
    form_10q = 0
    for item in items:
        for cid in item.get("gold_chunk_ids", []):
            if cid in corpus_by_id:
                ft = corpus_by_id[cid].get("form_type", "")
                if ft == "10-K":
                    form_10k += 1
                elif ft == "10-Q":
                    form_10q += 1
                break  # Count item once based on first chunk

    if form_10k < MIN_10K:
        errors.append(f"10-K items: need >= {MIN_10K}, got {form_10k}")
    if form_10q < MIN_10Q:
        errors.append(f"10-Q items: need >= {MIN_10Q}, got {form_10q}")

    # Tricky numeric count
    tricky_count = 0
    for item in items:
        span = item.get("notes", {}).get("evidence_span", "")
        ans = item.get("gold_answer", "")
        if _has_tricky_numeric(span) or _has_tricky_numeric(ans):
            tricky_count += 1
    if tricky_count < TRICKY_NUMERIC_MIN:
        errors.append(f"Tricky numeric items: need >= {TRICKY_NUMERIC_MIN}, got {tricky_count}")

    # Duplicate question check
    seen_questions: dict[str, str] = {}
    for item in items:
        norm = normalize_question(item["question"])
        if norm in seen_questions:
            errors.append(
                f"[{item['id']}] duplicate question (same as {seen_questions[norm]}): "
                f"'{item['question'][:60]}...'"
            )
        seen_questions[norm] = item["id"]

    # Unanswerable items: check gold fields are empty
    for item in items:
        if item["question_type"] == "unanswerable":
            iid = item["id"]
            if item.get("gold_answer") != "ABSTAIN":
                errors.append(f"[{iid}] unanswerable item must have gold_answer=ABSTAIN")
            if item.get("gold_chunk_ids") != []:
                errors.append(f"[{iid}] unanswerable item must have empty gold_chunk_ids")
            if item.get("gold_accession") != "":
                errors.append(f"[{iid}] unanswerable item must have empty gold_accession")
            if item.get("gold_section") != "":
                errors.append(f"[{iid}] unanswerable item must have empty gold_section")
            if item.get("answerable") is not False:
                errors.append(f"[{iid}] unanswerable item must have answerable=false")
            evidence = item.get("notes", {}).get("evidence_span", "")
            if evidence != "":
                errors.append(f"[{iid}] unanswerable item must have empty evidence_span")

    # Answer support check
    for item in items:
        iid = item["id"]
        answer = item.get("gold_answer", "")
        evidence = item.get("notes", {}).get("evidence_span", "")

        if answer == "ABSTAIN" and item.get("answerable") is False:
            continue  # Exempt true abstention items

        if not evidence:
            if item.get("answerable", True):
                errors.append(f"[{iid}] answerable item missing evidence_span")
            continue

        if not answer_supported(answer, evidence):
            errors.append(
                f"[{iid}] answer not supported by evidence: "
                f"answer='{answer[:60]}', evidence='{evidence[:60]}'"
            )

    return errors


# ---------------------------------------------------------------------------
# Corpus hash validation
# ---------------------------------------------------------------------------

def compute_corpus_hash(path: Path) -> str:
    """Compute SHA-256 of the corpus file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------

def validate_golden(
    golden_path: Path,
    corpus_path: Path,
    schema_path: Path,
    *,
    allow_unverified: bool = False,
) -> list[str]:
    """Run all validations and return a list of error strings."""
    errors: list[str] = []

    # Load inputs
    try:
        items = load_jsonl(golden_path)
    except (ValueError, FileNotFoundError) as exc:
        return [f"Failed to load golden file: {exc}"]

    try:
        schema = load_schema(schema_path)
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        return [f"Failed to load schema: {exc}"]

    try:
        corpus_rows = load_jsonl(corpus_path)
    except (ValueError, FileNotFoundError) as exc:
        return [f"Failed to load corpus: {exc}"]

    corpus_by_id = {r["chunk_id"]: r for r in corpus_rows}

    # Compute and validate corpus hash
    corpus_hash = compute_corpus_hash(corpus_path)

    # Schema validation
    errors.extend(validate_schema(items, schema))

    # Provenance validation
    for item in items:
        iid = item.get("id", "???")
        prov = item.get("provenance", {})
        if not prov.get("drafted_by"):
            errors.append(f"[{iid}] provenance.drafted_by is empty")
        if not prov.get("drafted_at"):
            errors.append(f"[{iid}] provenance.drafted_at is empty")
        if not prov.get("corpus_sha256"):
            errors.append(f"[{iid}] provenance.corpus_sha256 is empty")
        elif prov["corpus_sha256"] != corpus_hash:
            errors.append(
                f"[{iid}] corpus_sha256 mismatch: "
                f"item={prov['corpus_sha256'][:16]}.., corpus={corpus_hash[:16]}.."
            )
        if not allow_unverified:
            if not prov.get("verified_by"):
                errors.append(f"[{iid}] provenance.verified_by is null (release-strict)")
            if not prov.get("verified_at"):
                errors.append(f"[{iid}] provenance.verified_at is null (release-strict)")

    # Reference validation
    errors.extend(validate_references(items, corpus_by_id))

    # Point-in-time validation
    errors.extend(validate_point_in_time(items, corpus_by_id))

    # Coverage validation
    errors.extend(validate_coverage(items, corpus_by_id))

    return errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate SEC RAG golden set v1.")
    parser.add_argument("--golden", type=Path, required=True, help="Path to golden_v1.jsonl")
    parser.add_argument("--schema", type=Path, required=True, help="Path to golden_v1.schema.json")
    parser.add_argument("--corpus", type=Path, required=True, help="Path to sec_corpus.jsonl")
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Allow null verifier provenance (for drafting loop only).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    errors = validate_golden(
        args.golden,
        args.corpus,
        args.schema,
        allow_unverified=args.allow_unverified,
    )

    if errors:
        print(f"VALIDATION FAILED — {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    print("VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())