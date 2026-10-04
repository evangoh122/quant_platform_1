# BUILD: corporate actions round 4, Codex review (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests.

Codex (`.agents/codex/VERDICT-corporate-actions.md`), two blocking issues:

1. **The adjusted Silver MERGE uses `INSERT *`** (`silver/08_silver_ohlcv_day_adjusted.sql:~364`).
   Replace it with an explicit `INSERT (col, …) VALUES (src.col, …)` listing every target column
   once. Extend the MERGE-column test (`tests/silver/test_ohlcv_day_adjusted.py:~691`) to cover EVERY
   MERGE in the file. Prove that a missing column fails it.
2. **The notebook isn't usable as a Databricks NOTEBOOK or notebook JOB.**
   `refresh_bronze_corporate_actions.py:~143` runs strict `parse_args()` on kernel-injected argv
   (`-f kernel.json` → exit 2), and `:~152` does `import dbutils`, falling back to None, which
   discards the injected global.

   Fix:
   - `dbutils_obj = globals().get("dbutils")`.
   - If it exists (notebook or notebook-job context): IGNORE `sys.argv`, read all params from
     widgets, declaring the widgets with defaults first, and validate the values strictly (an
     unknown mode → error).
   - Otherwise (script / `spark_python_task` / CLI): strict `parse_args()` as now.
   - Keep parse-before-Spark in both paths.
   - Tests:
     - injected `-f kernel.json` together with an injected fake `dbutils` → runs from widgets;
     - an injected `dbutils` with widget `mode=write` → write; `mode=bogus` → error;
     - no `dbutils` + `--mdoe` → exit 2 (unchanged);
     - no `dbutils` + `--help` → exit 0, without Spark.
   - Also make `resources/jobs.yml` consistent: either a `spark_python_task` with CLI parameters
     (the CLI path), or a `notebook_task` with `base_parameters` (the widget path). State which, and
     why.

Run `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`, and the same with pyspark
hidden. LF line endings only. Don't touch `.agents/dispatch.sh`. Write
`.agents/mimo/VERDICT-corporate-actions-round4.md`.
