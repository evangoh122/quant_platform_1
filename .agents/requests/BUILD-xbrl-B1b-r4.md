# BUILD-xbrl-B1b round 4 (checker CHANGES_REQUESTED — tests rebuild the query instead of calling asof_facts)

You are MiMo. Branch `feat/xbrl-silver` (stay on it). Read `.agents/deepseek-fallback/VERDICT-xbrl-B1b-r3.md`. LF endings, never touch `.agents/dispatch.sh`, no
Databricks, no network. Shell rule as before (`.agentlogs/<name>.sh` + `wsl -d Ubuntu -- bash <path>`; no PowerShell, nothing in C:\temp). Stage only files you change.
COMMIT; verdict `.agents/mimo/VERDICT-xbrl-B1b-r4.md`.
THIS IS THE THIRD TIME a test re-implemented production logic. Rule for this repo: a test may only call production functions; it must never copy their logic.
Exact shape required in tests/db/test_xbrl_queries.py:
```python
class CapturingSpark:            # stands in for SparkSession
    def __init__(self): self.calls = []
    def sql(self, query, args=None):
        self.calls.append((query, args or {})); return _DuckFrame(query, args)  # or just record

spark = CapturingSpark()
asof_facts(spark, as_of=..., ticker="NVDA")          # call PRODUCTION code
query, args = spark.calls[-1]
rows = run_in_duckdb(query, args, fixture_tables)   # translate only {catalog}.{schema} names and named params (:name / $name) — no other rewriting
assert ...
```
Delete tests/db/test_xbrl_queries.py:170-186, 246-307 and 309-325 (the reconstructed queries). The four cases (no filter / ticker / concept / both) must run the SQL that
asof_facts() produced. Paste FAILED output with db/xbrl_queries.py changed back to `f.ticker` / `f.concept` (in a /tmp `git archive` copy).
