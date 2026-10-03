# BUILD: SEC knowledge graph round 4 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests.

DeepSeek check3 (`.agents/deepseek/VERDICT-rag-kg-check3.md`): `SparkGraphStore`
(`api/services/sec_knowledge_graph.py:~177,201,223,260-263`) reads Spark TIMESTAMP columns straight
into `Provenance(accepted_ts=…)` and `KgEdge(valid_from=…, accepted_ts=…)`. PySpark returns
**tz-naive** datetimes, and `ensure_utc` raises, so EVERY production fact query crashes.

**Do NOT just `.replace(tzinfo=utc)`.** Claude verified in this project that Databricks Connect
returns naive datetimes in the CLIENT machine's local timezone (UTC+8 on the dev box), not UTC. The
same bug was fixed in `api/services/hybrid_retriever.py` by reading epoch seconds. Do the same here:
- In every Spark read in `SparkGraphStore`, select `unix_timestamp(col)` (or `CAST(col AS LONG)`) for
  every timestamp. That's the top-level `accepted_ts` and `valid_from`, and `accepted_ts` inside the
  `provenance` struct array (use `transform(provenance, p -> named_struct(..., 'accepted_epoch',
  unix_timestamp(p.accepted_ts)))`, or explode/aggregate).
- Then build aware UTC datetimes with `datetime.fromtimestamp(epoch, tz=timezone.utc)`.
- Apply this to all four `SparkGraphStore` methods.

Tests, each failing on the current HEAD:
- A fake Spark session whose rows return NAIVE datetimes expressed in a non-UTC local time (simulate
  UTC+8) for the raw columns, plus correct epoch values for the `unix_timestamp` columns.
  Instantiate the REAL `SparkGraphStore` and call `get_fact` / `facts_timeseries` / `neighbors`.
  They return results with the correct UTC `accepted_ts`, and the PIT filter works.
- Run under `TZ=Asia/Singapore` and `TZ=America/New_York`; both pass.
- The old round-trip test must actually instantiate `SparkGraphStore` and call `get_fact`, not just
  `hasattr`.

Run `python3 -m pytest -q -p no:cacheprovider tests/rag`, and the full suite with
`--ignore=tests/lakebase`, both with pyspark hidden too. LF line endings only. Don't touch
`.agents/dispatch.sh`. Write `.agents/mimo/VERDICT-rag-kg-round4.md`.
