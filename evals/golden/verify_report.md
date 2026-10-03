# Verify Report: SEC RAG Golden Set v1

## Instructions

1. Open every referenced corpus chunk independently — do not trust the drafter's evidence extraction.
2. For each row, confirm: ticker, accession, section, exact quoted span, answer support, and natural question wording.
3. Mark each row `OK`, `FIX`, or `DROP` with a concrete reason.
4. Recompute UTC acceptance cutoffs and inspect both allowed and future chunks for PIT traps.
5. Search the corpus for plausible evidence before approving each unanswerable item.
6. Check cross-filing comparisons use the same ticker, require multiple filings, and do not compare incompatible periods or units.
7. Recompute type, ticker, form, section, difficulty, and numeric-format quotas.
8. Run strict validation and all mutation proofs.

## Verification Statement

Verification is independent and corpus-only. No outside knowledge or network access was used.

## Quota Summary

| Quota | Target | Actual |
|-------|--------|--------|
| Total items | 80 | _TBD_ |
| factual_lookup | >= 24 | _TBD_ |
| risk_factor | >= 8 | _TBD_ |
| business_description | >= 8 | _TBD_ |
| quantitative_market_risk | >= 8 | _TBD_ |
| cross_filing_comparison | >= 10 | _TBD_ |
| point_in_time_trap | >= 12 | _TBD_ |
| unanswerable | >= 10 | _TBD_ |
| 10-K backed items | >= 24 | _TBD_ |
| 10-Q backed items | >= 24 | _TBD_ |
| Tricky numeric items | >= 20 | _TBD_ |
| Items per ticker | 5 | _TBD_ |

## Item Verification Table

| ID | Verdict | Evidence checked | PIT checked | Answer checked | Reason | Verifier |
|----|---------|-----------------|-------------|----------------|--------|----------|
| rag-v1-001 | | | | | | |
| rag-v1-002 | | | | | | |
| rag-v1-003 | | | | | | |
| rag-v1-004 | | | | | | |
| rag-v1-005 | | | | | | |
| rag-v1-006 | | | | | | |
| rag-v1-007 | | | | | | |
| rag-v1-008 | | | | | | |
| rag-v1-009 | | | | | | |
| rag-v1-010 | | | | | | |
| rag-v1-011 | | | | | | |
| rag-v1-012 | | | | | | |
| rag-v1-013 | | | | | | |
| rag-v1-014 | | | | | | |
| rag-v1-015 | | | | | | |
| rag-v1-016 | | | | | | |
| rag-v1-017 | | | | | | |
| rag-v1-018 | | | | | | |
| rag-v1-019 | | | | | | |
| rag-v1-020 | | | | | | |
| rag-v1-021 | | | | | | |
| rag-v1-022 | | | | | | |
| rag-v1-023 | | | | | | |
| rag-v1-024 | | | | | | |
| rag-v1-025 | | | | | | |
| rag-v1-026 | | | | | | |
| rag-v1-027 | | | | | | |
| rag-v1-028 | | | | | | |
| rag-v1-029 | | | | | | |
| rag-v1-030 | | | | | | |
| rag-v1-031 | | | | | | |
| rag-v1-032 | | | | | | |
| rag-v1-033 | | | | | | |
| rag-v1-034 | | | | | | |
| rag-v1-035 | | | | | | |
| rag-v1-036 | | | | | | |
| rag-v1-037 | | | | | | |
| rag-v1-038 | | | | | | |
| rag-v1-039 | | | | | | |
| rag-v1-040 | | | | | | |
| rag-v1-041 | | | | | | |
| rag-v1-042 | | | | | | |
| rag-v1-043 | | | | | | |
| rag-v1-044 | | | | | | |
| rag-v1-045 | | | | | | |
| rag-v1-046 | | | | | | |
| rag-v1-047 | | | | | | |
| rag-v1-048 | | | | | | |
| rag-v1-049 | | | | | | |
| rag-v1-050 | | | | | | |
| rag-v1-051 | | | | | | |
| rag-v1-052 | | | | | | |
| rag-v1-053 | | | | | | |
| rag-v1-054 | | | | | | |
| rag-v1-055 | | | | | | |
| rag-v1-056 | | | | | | |
| rag-v1-057 | | | | | | |
| rag-v1-058 | | | | | | |
| rag-v1-059 | | | | | | |
| rag-v1-060 | | | | | | |
| rag-v1-061 | | | | | | |
| rag-v1-062 | | | | | | |
| rag-v1-063 | | | | | | |
| rag-v1-064 | | | | | | |
| rag-v1-065 | | | | | | |
| rag-v1-066 | | | | | | |
| rag-v1-067 | | | | | | |
| rag-v1-068 | | | | | | |
| rag-v1-069 | | | | | | |
| rag-v1-070 | | | | | | |
| rag-v1-071 | | | | | | |
| rag-v1-072 | | | | | | |
| rag-v1-073 | | | | | | |
| rag-v1-074 | | | | | | |
| rag-v1-075 | | | | | | |
| rag-v1-076 | | | | | | |
| rag-v1-077 | | | | | | |
| rag-v1-078 | | | | | | |
| rag-v1-079 | | | | | | |
| rag-v1-080 | | | | | | |

## Totals by Verdict

| Verdict | Count |
|---------|-------|
| OK | _TBD_ |
| FIX | _TBD_ |
| DROP | _TBD_ |

## Verification Statement

This verification was performed independently using only the corpus at `evals/data/sec_corpus.jsonl`. No external knowledge, network access, or LLM was used. Each chunk was opened and inspected directly.