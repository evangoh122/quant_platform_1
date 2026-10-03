===CODEX VERDICT START===
CHANGES_REQUESTED

Blocking finding:

- `api/services/embeddings.py:175` changes the Hugging Face default to `BAAI/bge-small-en-v1.5` (384 dimensions), but `api/config.py:178` still reports `Qwen/Qwen3-Embedding-8B`, and `api/config.py:210-211` still reports 4096 dimensions. Runtime configuration/telemetry therefore disagrees with the actual embedding implementation. Update both defaults and add coverage preventing future divergence.

Validation evidence:

- DeepSeek verdict: APPROVED.
- Reviewed `git diff origin/main -- . ':!.agents'`; `git diff --check` passed.
- Both requested full-suite commands were run but timed out after 300 seconds without completing. A diagnostic verbose run collected 605 tests and stalled at `tests/api/test_auth.py:6`.
- Changed-feature tests with both `databricks.connect` and PySpark hidden: 13 passed.
- All five mutation proofs failed targeted tests as required:
  - BM25 filter removal: 3 failures.
  - Corpus retry regression: 1 failure.
  - Dimension guard removal: 1 failure.
  - Blind exception restoration: 1 failure.
  - Schema FQN rebind removal: 1 failure.
- CI YAML policy passed: all `uses:` references are 40-hex SHAs, every checkout sets `persist-credentials: false`, and `.github/workflows/cd.yml:18` defaults `start_app` to false.
- Repository files were not modified.
===CODEX VERDICT END===
