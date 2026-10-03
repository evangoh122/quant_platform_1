# SEC RAG Golden Set v1

## Overview

A versioned, independently verifiable golden set for evaluating the SEC RAG retrieval system (`agent/tools_retrieval.py::search_sec_filings`). Every question and evidence span is drafted from `evals/data/sec_corpus.jsonl` — no outside knowledge or network access used.

## Corpus

- **Source:** `evals/data/sec_corpus.jsonl` (10,720 chunks)
- **SHA-256:** `b1d269a51fe4778c12a4b147cc2db56fd3f7296029690235593b4aa363a11551`
- **Tickers:** ADI, AMAT, AMD, AVGO, INTC, KLAC, LRCX, MCHP, MPWR, MU, NVDA, QCOM, SNPS, SWKS, TER, TXN
- **Date range:** 2024-09-11 through 2026-08-26 (UTC)
- **Sections:** item1_business, item1a_risk_factors, item7_mda, item7a_quant_risk, item8_financial_statements, full_document

## Schema

See `golden_v1.schema.json` for the full JSON Schema (draft 2020-12). Key fields:

| Field | Description |
|-------|-------------|
| `id` | Unique ID: `rag-v1-NNN` |
| `ticker` | One of 16 corpus tickers |
| `as_of` | RFC 3339 UTC cutoff timestamp |
| `question` | Natural-language evaluation question |
| `question_type` | One of 7 types (see quotas below) |
| `gold_answer` | Short gold answer; `ABSTAIN` for abstention items |
| `gold_chunk_ids` | Supporting chunk IDs (empty for unanswerable) |
| `gold_accession` | Primary SEC accession number |
| `gold_section` | Primary filing section |
| `answerable` | Whether answerable at `as_of` |
| `difficulty` | easy / medium / hard |
| `notes.evidence_span` | Verbatim corpus substring |
| `notes.trap` | PIT trap metadata (null for non-traps) |
| `provenance` | Author/verifier timestamps and corpus hash |

## Frozen Quotas (80 items)

| Type | Count |
|------|-------|
| `factual_lookup` | 24 |
| `risk_factor` | 8 |
| `business_description` | 8 |
| `quantitative_market_risk` | 8 |
| `cross_filing_comparison` | 10 |
| `point_in_time_trap` | 12 |
| `unanswerable` | 10 |
| **Total** | **80** |

Additional constraints:
- 5 items per ticker × 16 tickers = 80
- At least 24 items backed by 10-K filings, at least 24 by 10-Q
- All6 corpus sections represented
- All3 difficulties represented
- At least 20 items with tricky numeric formats ($, commas, %, millions/billions)

## Question Types

### factual_lookup
Direct numeric or factual lookup from MD&A or financial statements.

### risk_factor
Identifies a specific risk factor from Item 1A.

### business_description
Describes the company's primary business from Item 1.

### quantitative_market_risk
Extracts percentages or amounts from Item 7A quantitative disclosures.

### cross_filing_comparison
Compares disclosures between two filings for the same ticker. Both chunk IDs are listed in `gold_chunk_ids`; primary accession/section describes the main locus.

### point_in_time_trap
Sets `as_of` before a newer filing. Two behaviors:
- **`abstain`:** `gold_answer=ABSTAIN`, `answerable=false`. The RAG should refuse because the answer changed.
- **`older_filing_answer`:** `answerable=true`, gold cites the older allowed chunk. `notes.trap.future_chunk_ids` identifies the disallowed newer chunk.

### unanswerable
`gold_answer=ABSTAIN`, `gold_chunk_ids=[]`, `answerable=false`. The metric is not disclosed anywhere in the corpus. The RAG should abstain.

## Authoring Command

```bash
# Generate candidate packet (deterministic, seed=42)
python evals/golden/sample_candidates.py --corpus evals/data/sec_corpus.jsonl --output evals/data/candidate_packet.jsonl --seed 42 --per-ticker 10

# Author golden items (uses corpus evidence directly)
python evals/golden/author_golden_final.py
```

## Validation Commands

```bash
# Strict validation (requires verifier provenance)
python evals/golden/validate.py --golden evals/golden/golden_v1.jsonl --schema evals/golden/golden_v1.schema.json --corpus evals/data/sec_corpus.jsonl

# Drafting-loop validation (allows unverified)
python evals/golden/validate.py --golden evals/golden/golden_v1.jsonl --schema evals/golden/golden_v1.schema.json --corpus evals/data/sec_corpus.jsonl --allow-unverified
```

## Trap Examples

### Abstention trap
```
Ticker: NVDA
as_of: 2025-06-01 (before Q2 filing)
gold_answer: ABSTAIN
answerable: false
trap.expected_behavior: abstain
trap.future_chunk_ids: [newer chunk from Q2]
```
The RAG should refuse because the answer exists only in a filing accepted after `as_of`.

### Older filing answer trap
```
Ticker: AMD
as_of: 2025-09-01 (after Q1, before Q3)
gold_answer: [answer from Q1]
answerable: true
trap.expected_behavior: older_filing_answer
trap.future_chunk_ids: [Q3 chunk with different answer]
```
The RAG should answer from Q1 and not cite Q3.

## DeepSeek Verification Workflow

1. Open every referenced corpus chunk independently.
2. Confirm ticker, accession, section, exact quoted span, answer support, and natural wording.
3. Mark each row `OK`, `FIX`, or `DROP` in `verify_report.md`.
4. Recompute UTC acceptance cutoffs and inspect PIT trap chunks.
5. Search corpus for plausible evidence before approving unanswerable items.
6. Run strict validation and mutation proofs.
7. Fill verifier fields in JSONL provenance.

## Versioning

This golden file is versioned and immutable after acceptance. Corrections create a documented v2 or a clearly reviewed v1 patch.