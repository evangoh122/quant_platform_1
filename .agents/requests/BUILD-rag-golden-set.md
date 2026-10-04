# BUILD: corpus-grounded SEC RAG golden set v1

## Goal and non-goals

Create a versioned, independently verifiable golden set under `evals/golden/` for the corpus actually searched by `agent/tools_retrieval.py::search_sec_filings(symbol, query, as_of, top_k)`. FinanceBench is not an input: its open questions cover filings through 2023, while this exported corpus covers 2024-09-11 through 2026-08-26. Every answerable question and every quoted evidence span must be drafted from `evals/data/sec_corpus.jsonl` only. Do not call the network or use outside facts.

The local export is gitignored and contains 10,720 chunks for ADI, AMAT, AMD, AVGO, INTC, KLAC, LRCX, MCHP, MPWR, MU, NVDA, QCOM, SNPS, SWKS, TER, and TXN. MiMo runs on Windows without Databricks; all authoring and validation must read that JSONL directly from the worktree. Do not require Spark, Databricks Connect, API credentials, or an LLM.

## Numbered changes

1. Add `evals/golden/golden_v1.schema.json` (new file) using JSON Schema draft 2020-12. Require exactly these fields (additional properties false):
   - `id`: unique string matching `^rag-v1-[0-9]{3}$`.
   - `ticker`: enum of the 16 uppercase corpus tickers.
   - `as_of`: RFC 3339/ISO UTC timestamp ending in `Z` (not a date-only value).
   - `question`: non-empty natural-language string.
   - `question_type`: enum `factual_lookup`, `risk_factor`, `business_description`, `quantitative_market_risk`, `cross_filing_comparison`, `point_in_time_trap`, `unanswerable`.
   - `gold_answer`: short string. Use the exact sentinel `ABSTAIN` for items whose correct answer is abstention; do not hide explanations in this field.
   - `gold_chunk_ids`: unique string array with at least one element for answerable ordinary items and traps whose later answering filing is known. Permit an empty array only for true `unanswerable` items.
   - `gold_accession`: SEC accession string for ordinary answerable items and known-future traps; empty string only for true unanswerable items.
   - `gold_section`: enum of `item7_mda`, `item1_business`, `item7a_quant_risk`, `item8_financial_statements`, `item1a_risk_factors`, `full_document`; empty string only for true unanswerable items.
   - `answerable`: boolean. It means answerable at `as_of`, not merely present somewhere in the corpus. It must be false for abstention traps and unanswerable items. A trap whose correct answer is supported by an older filing is true and cites that older filing; `notes` also identifies the disallowed newer chunk/accession.
   - `difficulty`: enum `easy`, `medium`, `hard`.
   - `notes`: object, not free text, requiring `evidence_span` (verbatim corpus substring, empty only for true unanswerable), `rationale`, and `trap` metadata. `trap` is either null or an object with `future_chunk_ids` (at least one), `future_accession`, `future_answer`, and `expected_behavior` enum `older_filing_answer`/`abstain`.
   - `provenance`: object requiring `drafted_by`, `drafted_at`, `verified_by`, `verified_at`, and `corpus_sha256`. Initial authoring may set verifier fields to null; final checked data may not.

2. Add `evals/golden/sample_candidates.py` (new file) as a deterministic authoring aid, not a question generator. Implement exact functions `load_corpus(path: Path) -> list[dict]`, `index_corpus(rows: Iterable[dict]) -> dict[str, dict]`, `sample_candidates(rows, *, seed: int, per_ticker: int, sections: set[str] | None = None) -> list[dict]`, and `write_candidate_packet(candidates, output: Path) -> None`. Stratify by ticker, filing section, and form, emit full chunk text plus metadata, never invent an answer, and default to a fixed seed. Add CLI options `--corpus`, `--output`, `--seed`, `--per-ticker`, and `--sections`. The script may write only the requested candidate packet; generated packets stay under gitignored `evals/data/` and are not committed.

3. Add `evals/golden/golden_v1.jsonl` (new file), approximately 80 items (target exactly 80 unless corpus evidence makes an item invalid). Draft every item manually from candidate chunk text. Requirements:
   - Exactly five items per ticker across all 16 tickers.
   - Across the set, minimum counts: 24 `factual_lookup`, 8 `risk_factor`, 8 `business_description`, 8 `quantitative_market_risk`, 10 `cross_filing_comparison`, 10 `point_in_time_trap`, and 8 `unanswerable`. Counts overlap only in subject matter, never in the `question_type` field; therefore adjust the proposed minimums into a documented exact 80-item quota in `validate.py` (recommended exact mix 24/8/8/8/10/12/10 = 80).
   - At least one 10-K-backed and one 10-Q-backed answerable item per ticker where the corpus permits it; globally at least 24 of each. Record form verification through referenced chunks even though form is not duplicated in the schema.
   - All six corpus sections represented, both easy/medium/hard represented, and at least 20 items using tricky numeric renderings such as `$`, commas, decimals, percentages, parentheses for negatives, basis points, millions/billions, or per-share units.
   - `factual_lookup` values come from MD&A or financial statements. Cross-filing items compare two or more chunks for the same ticker and list all supporting `gold_chunk_ids`; if the schema's single accession/section cannot describe them, set `gold_accession`/`gold_section` to the primary answer locus and explain every additional locus in `notes.rationale`.
   - Ordinary answerable items have `as_of >= accepted_epoch` for every gold chunk. Convert epochs to UTC exactly and choose a stable cutoff after acceptance, not filing date.
   - PIT traps set `as_of` before the answering filing's `accepted_epoch`. For `expected_behavior=abstain`, `gold_answer=ABSTAIN`, `answerable=false`, and the known future evidence lives in the normal gold fields plus `notes.trap`. For `older_filing_answer`, normal gold fields cite the allowed older chunk(s), `answerable=true`, while `notes.trap.future_chunk_ids` identifies the later, disallowed answer.
   - True unanswerable items must be answerable only by abstaining: `gold_answer=ABSTAIN`, `gold_chunk_ids=[]`, empty accession/section/evidence, `answerable=false`, and `notes.rationale` says how corpus-wide absence was checked. Questions must still concern the named company but must not depend on outside knowledge for a competing answer.
   - `gold_answer` must be literally supported by `notes.evidence_span`, or be numerically equivalent after conservative normalization. Quote the exact, contiguous evidence span in `notes.evidence_span`. Do not accept semantic-only paraphrases as numeric gold.
   - Questions must be unique after Unicode NFKC, lowercase, whitespace collapse, and terminal-punctuation removal. Do not encode accession, chunk ID, or answer text in the question as a retrieval shortcut.

4. Add `evals/golden/validate.py` (new file). Implement `load_jsonl(path: Path)`, `load_schema(path: Path)`, `validate_schema(items, schema)`, `normalize_question(text: str)`, `parse_utc(text: str)`, `normalize_numeric_values(text: str)`, `answer_supported(answer: str, evidence: str)`, `validate_references(items, corpus_by_id)`, `validate_point_in_time(items, corpus_by_id)`, `validate_coverage(items, corpus_by_id)`, and `validate_golden(golden_path: Path, corpus_path: Path, schema_path: Path) -> list[str]`. The CLI returns 0 only when the error list is empty and prints actionable item IDs otherwise.
   - Schema validation is per JSONL row and rejects duplicate IDs.
   - Every referenced chunk exists. Ordinary/older-answer gold chunks match item ticker, primary accession and primary section as applicable; every gold chunk is checked for ticker and its role is resolved from notes for multi-accession comparisons.
   - For answerable items, every allowed gold chunk has `accepted_epoch <= as_of`. Abstention traps require every future answering chunk to be `> as_of`; older-answer traps require allowed chunks `<= as_of` and future chunks `> as_of`. Treat missing/malformed timestamps as errors.
   - `answer_supported` first uses normalized literal substring matching, then conservative numeric equivalence over values extracted from the verbatim evidence. Normalize currency marks, thousands separators, parenthesized negatives, `%`, and explicit thousand/million/billion multipliers; do not equate different units or select any coincidental number. `ABSTAIN` is exempt only where the item contract permits it.
   - Enforce the exact 80-item type quota, five items per ticker, all ticker/type/section/difficulty rules above, 10-K/10-Q spread, tricky-number count, duplicate-question rule, and non-null independent verifier provenance for a release-ready run. Provide `--allow-unverified` only for the drafting loop; default validation is release-strict.
   - Hash the exact corpus file and require every item's `provenance.corpus_sha256` to match it.

5. Add `evals/golden/verify_report.md` (new file) with instructions and a table containing exactly one row per golden ID: `ID | Verdict (OK/FIX/DROP) | Evidence checked | PIT checked | Answer checked | Reason | Verifier`. Include totals by verdict and a statement that verification was independent and corpus-only. DeepSeek fills this file and the verifier fields in JSONL; MiMo must leave a complete 80-row template, ordered by ID.

6. Add `tests/rag/test_golden_set.py` (new file) with unit fixtures and release checks. Exact tests: `test_schema_rejects_missing_required_field`, `test_validator_rejects_unknown_chunk`, `test_validator_rejects_metadata_mismatch`, `test_validator_rejects_future_gold_for_answerable_item`, `test_validator_accepts_abstain_trap_with_future_evidence`, `test_validator_accepts_older_answer_trap`, `test_numeric_support_handles_financial_formats`, `test_numeric_support_rejects_wrong_unit`, `test_duplicate_questions_are_normalized`, `test_golden_v1_release_validates`, and `test_verify_report_has_one_row_per_item`. Small synthetic rows test edge cases; the release test skips with a clear message only when local `evals/data/sec_corpus.jsonl` is absent. It must not import pyspark.

7. Add `evals/golden/README.md` (new file) documenting schema semantics, exact frozen quotas, corpus hash, authoring command, strict validation command, trap examples (older answer versus abstain), and DeepSeek verification workflow. State that the golden file is versioned and immutable after acceptance; corrections create a documented v2 or a clearly reviewed v1 patch.

## Tests that must fail before this build

Before implementation, prove the requested surface does not exist:

```bash
python -m pytest -q tests/rag/test_golden_set.py
python evals/golden/validate.py --golden evals/golden/golden_v1.jsonl --schema evals/golden/golden_v1.schema.json --corpus evals/data/sec_corpus.jsonl
```

Capture the expected pre-build failures (`tests/rag/test_golden_set.py` and `evals/golden/validate.py` missing). After implementation, also demonstrate validator mutation failures using temporary copies outside the repo: change one chunk ID, move one answerable `as_of` before acceptance, change one answer/unit, duplicate a normalized question, and remove one ticker item; every mutation command must exit nonzero. Do not mutate the committed golden file.

## Acceptance commands

Run from repository root. Hide pyspark/Databricks-only tests and do not install or invoke Spark:

```bash
python -m pytest -q tests/rag/test_golden_set.py -m "not spark and not lakebase and not databricks"
python evals/golden/validate.py --golden evals/golden/golden_v1.jsonl --schema evals/golden/golden_v1.schema.json --corpus evals/data/sec_corpus.jsonl
python -m pytest -q tests/rag/test_eval_pipeline.py tests/rag/test_eval_types.py -m "not spark and not lakebase and not databricks"
git diff --check
```

## DeepSeek must check

- Independently open every referenced corpus chunk; do not trust MiMo's evidence extraction or self-verdict.
- For all 80 rows, confirm ticker/accession/section, exact quoted span, answer support, and natural wording; mark `OK`, `FIX`, or `DROP` with a concrete reason.
- Recompute UTC acceptance cutoffs and inspect both allowed and future chunks for every PIT trap.
- Search the corpus for plausible evidence before approving each unanswerable item.
- Check cross-filing comparisons use the same ticker, truly require multiple filings, and do not compare incompatible periods or units.
- Recompute type, ticker, form, section, difficulty, and numeric-format quotas; run strict validation and all mutation proofs.
- Reject leaked outside knowledge, questions that reveal the answer, unverifiable paraphrases, coincidental numeric matches, or duplicate templates.

## Delivery constraints

- LF line endings in every created or edited file.
- Do not touch `.agents/dispatch.sh`.
- Do not add `evals/data/sec_corpus.jsonl` or candidate packets to git; it remains a local worktree input.
- MiMo must commit the implementation and authored dataset.
- MiMo must write a self-verdict file at `.agents/mimo/VERDICT-rag-golden-set.md` containing changed files, commands and results, corpus SHA-256, quota totals, known limitations, and commit SHA.
- DeepSeek's later verdict is separate and must be written to `.agents/deepseek/VERDICT-rag-golden-set.md` as `APPROVED` or `CHANGES_REQUESTED` with file:line evidence.

## Offline data (exported by Claude, gitignored)
- `evals/data/sec_corpus.jsonl`: 10,720 chunks.
- `evals/data/sec_embeddings.npy` (10720×384 float32) + `evals/data/sec_embedding_ids.json`: the stored bge-small vectors in row order.
In a lane worktree these files are NOT present (gitignored). Read them from `/home/jianj/code/qp1-eval/evals/data/` via the env var `RAG_EVAL_DATA_DIR`, defaulting to `evals/data`.
