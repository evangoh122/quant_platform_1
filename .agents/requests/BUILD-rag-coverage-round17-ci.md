# BUILD-rag-coverage round 17 — IMPLEMENT NOW (PR #28 CI red; tests only)

You are MiMo. Stay on branch `slice/rag-coverage` (do not create/switch branches). Commit, LF endings, do not touch `.agents/dispatch.sh`.
PR #28 CI "Python tests" (no pyspark installed): 5 failed, 2115 passed —
tests/rag/test_merge_metrics.py::TestSparkDataWriterMetrics::{test_empty_history_returns_none, test_missing_key_returns_none,
test_exception_returns_none, test_metrics_with_zero_returns_zero, test_metrics_with_seven_returns_seven}:
`ImportError: cannot import name 'IntegerType' from 'pyspark.sql.types' (unknown location)` at pipelines/sec_rag_ingest.py:~1700.
They pass only where real pyspark is installed (Claude's WSL). You saw the same 5 fail on Windows (no pyspark) in round 16 — that IS this bug,
not an environment quirk; reproduce it there.
Fix the TESTS so they run without pyspark: provide the pyspark.sql.types names the writer imports (IntegerType, StringType, TimestampType,
LongType, StructType, StructField, …) via a properly-restored fake module for these tests (monkeypatch.setitem(sys.modules, ...) — never a bare
namespace package), keeping the assertions (None + WARNING; "0"→0; "7"→7) intact. Do NOT skip them. Verify on Windows (no pyspark):
`python -m pytest tests/rag/test_merge_metrics.py -q` → all pass; and that the full `python -m pytest tests/rag tests/bronze -q` still passes.
Claude re-verifies in WSL (with pyspark) and CI. Verdict: .agents/mimo/VERDICT-rag-coverage-round17-ci.md.
