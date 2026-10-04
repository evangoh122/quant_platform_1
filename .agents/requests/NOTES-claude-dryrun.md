# Claude live dry-run notes (2026-10-04), for round 3

`--mode dry-run --symbol-start A --symbol-end B`: 53 attempted, 28 with splits (128 rows), 25 empty,
0 failed, 37 s, 0 writes. Works. Two fixes are needed before a job run:

1. Running from `notebooks/` (as a Databricks job does) gives `ModuleNotFoundError: No module named
   'etl'`. Insert the repo root on `sys.path` at the top: `Path(__file__).resolve().parents[1]`.
2. `--help` / the arg parsing runs only AFTER `SparkSession.builder.getOrCreate()`. Parse the args
   first, so that `--help` and bad flags fail fast without Spark.

Minor: `datetime.utcnow()` is deprecated, so use `datetime.now(timezone.utc)`.
