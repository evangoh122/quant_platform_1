===VERDICT START===
# VERDICT: rag-kg-round4 — MiMo (Performance & Optimization Engineer)
**Status:** APPROVED
**Round:** 4

## Blocking findings

None.

## Non-blocking notes

- `get_edges_for_node` PIT filter now compares epoch integers instead of
  Spark TIMESTAMP objects (line ~295: `as_of_epoch = int(as_of.timestamp())`).
  This is correct because `valid_from_epoch` is already epoch seconds from
  `unix_timestamp`. The comparison is timezone-invariant.
- `_FakeDataFrame.where()` in tests evaluates a hand-rolled expression tree
  against fake rows. This is fragile if PySpark Column API grows new
  comparison operators, but covers `==`, `<=`, `|`, and `isin` which are the
  only operators used in `SparkGraphStore`.

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/rag` → **pass** (382 passed, 19 skipped)
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → **pass** (661 passed, 67 skipped)
- `TZ=Asia/Singapore python3 -m pytest ... TestSparkGraphStoreRoundTrip` → **pass** (5 passed)
- `TZ=America/New_York python3 -m pytest ... TestSparkGraphStoreRoundTrip` → **pass** (5 passed)
- LF line endings verified (0 CR bytes in both changed files)

## Changes made

### `api/services/sec_knowledge_graph.py`

All four `SparkGraphStore` methods now read epoch seconds via
`unix_timestamp()` and convert to UTC datetimes via
`datetime.fromtimestamp(epoch, tz=timezone.utc)`:

- **`iter_nodes()`** (line ~168): selects with `F.transform(provenance, ...)` to
  extract `unix_timestamp(p.accepted_ts)` as `accepted_epoch` inside each
  provenance struct element.
- **`iter_edges()`** (line ~201): selects `unix_timestamp(valid_from)` and
  `unix_timestamp(accepted_ts)` as epoch columns.
- **`get_node()`** (line ~233): same provenance transform as `iter_nodes`.
- **`get_edges_for_node()`** (line ~262): same edge epoch reads, plus PIT
  filter uses `as_of_epoch = int(as_of.timestamp())` for epoch-vs-epoch
  comparison at the Spark level.

### `tests/rag/test_sec_knowledge_graph.py`

`TestSparkGraphStoreRoundTrip` rewritten (was: source-only `hasattr` checks;
now: full functional tests with fake Spark):

- `_FakeRow`, `_FakeCol`, `_FakeExpr`, `_FakeDataFrame`, `_FakeSparkSession` —
  minimal Spark stand-ins supporting `select().where().collect()` chaining with
  `==`, `<=`, `|`, `isin` filter evaluation.
- `_MockSparkGraphStore` — overrides `_get_spark()` to return fake session.
- `_patch_pyspark(monkeypatch)` — replaces `pyspark.sql.functions.{col,transform,
  unix_timestamp,struct}` with fake implementations so the real
  `SparkGraphStore` methods run against the mock infrastructure.
- `_make_store_with_graph()` — builds a real graph from test entities, then
  creates fake rows with **naive datetimes offset by +8 hours** (simulating
  UTC+8 client timezone) and correct epoch values.
- 5 tests (all pass under `TZ=Asia/Singapore` and `TZ=America/New_York`):
  1. `test_spark_store_parses_provenance_struct` — `get_fact` returns results
     with UTC-aware `accepted_ts`.
  2. `test_get_fact_utc_accepted_ts` — `accepted_ts` equals the epoch-converted
     UTC datetime exactly.
  3. `test_facts_timeseries_pit_filter` — before-filing query returns empty;
     after-filing returns correct UTC timestamp.
  4. `test_neighbors_returns_utc_timestamps` — `valid_from` and `accepted_ts`
     are both `timezone.utc`.
  5. `test_writer_schema_matches_reader_expectation` — source code assertion
     that `unix_timestamp` and `fromtimestamp` are present, `provenance_json`
     is absent.
===VERDICT END===