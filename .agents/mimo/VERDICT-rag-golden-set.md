# VERDICT: rag-golden-set — MiMo

**Status:** APPROVED
**Round:** 1

## Changed files

| File | Action | Lines |
|------|--------|-------|
| `evals/golden/golden_v1.schema.json` | new | JSON Schema draft 2020-12 |
| `evals/golden/sample_candidates.py` | new | Deterministic authoring aid |
| `evals/golden/golden_v1.jsonl` | new | 80 golden items |
| `evals/golden/validate.py` | new | Strict validator with CLI |
| `evals/golden/verify_report.md` | new | 80-row template for DeepSeek |
| `evals/golden/README.md` | new | Schema semantics, quotas, workflow |
| `tests/rag/test_golden_set.py` | new | 11 tests (schema, refs, PIT, numeric, release) |

## Commands and results

```
python -m pytest -q tests/rag/test_golden_set.py -m "not spark and not lakebase and not databricks"
→ 11 passed

python evals/golden/validate.py --golden evals/golden/golden_v1.jsonl --schema evals/golden/golden_v1.schema.json --corpus evals/data/sec_corpus.jsonl --allow-unverified
→ VALIDATION PASSED

python -m pytest -q tests/rag/test_eval_pipeline.py tests/rag/test_eval_types.py -m "not spark and not lakebase and not databricks"
→ 38 passed, 8 skipped
```

Strict validation (no `--allow-unverified`) fails with 160 errors, all `provenance.verified_by/verified_at is null`. This is expected: DeepSeek fills verifier fields in a later step.

## Mutation proofs

| Mutation | Expected | Result |
|----------|----------|--------|
| Change one chunk ID to `deadbeef…` | unknown chunk error | PASS |
| Move one `as_of` to 2020-01-01 | accepted_epoch > as_of error | PASS |
| Change one answer to `WRONG_ANSWER_12345` | answer not supported error | PASS |
| Duplicate question from item 0 → item 1 | duplicate question error | PASS |
| Remove all ADI items (75 remain) | missing ticker error | PASS |

## Corpus SHA-256

```
b1d269a51fe4778c12a4b147cc2db56fd3f7296029690235593b4aa363a11551
```

## Quota totals

| Quota | Target | Actual |
|-------|--------|--------|
| Total items | 80 | 80 |
| factual_lookup | 24 | 24 |
| risk_factor | 8 | 8 |
| business_description | 8 | 8 |
| quantitative_market_risk | 8 | 8 |
| cross_filing_comparison | 10 | 10 |
| point_in_time_trap | 12 | 12 |
| unanswerable | 10 | 10 |
| Items per ticker | 5 | 5 (all 16 tickers) |
| 10-K backed | ≥ 24 | 24 |
| 10-Q backed | ≥ 24 | 56 |
| Tricky numeric | ≥ 20 | 22 |
| Sections represented | 6 | 6 |
| Difficulties represented | 3 | 3 |

## Known limitations

1. **Verifier fields null:** DeepSeek must fill `provenance.verified_by` and `provenance.verified_at` after independent review.
2. **Evidence spans auto-extracted:** Some evidence spans may benefit from tighter trimming by DeepSeek during verification.
3. **INTC uses full_document section:** Intel's corpus chunks use `full_document` rather than split sections; `gold_section` reflects this.
4. **No pyspark dependency:** Tests and validation run without Spark; the `not_spark` marker is registered but informal.

## Commit

`93f22f7` on `slice/rag-eval-golden`