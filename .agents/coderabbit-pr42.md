### pipelines/ingest_sec_companyfacts.py:77
_🎯 Functional Correctness_ | _🟠 Major_ | _⚡ Quick win_

**Mark the schema tests as Spark tests, or make the schema helpers importable without PySpark.**

`_get_bronze_schema()` and `_get_manifest_schema()` import `pyspark.sql.types`. The CI command `pytest -m "not spark and not lakebase and not databricks"` runs without PySpark installed. The result is 27+ `ModuleNotFoundError` failures in `tests/bronze/test_sec_companyfacts.py`, so CI is blocked. The test module docstring also claims that the tests are "Spark-free," and that claim is wrong. Choose one fix:
- Add `pytestmark`/`@pytest.mark.spark` to the schema-contract, writer, and `ensure_table` test classes.
- Use `pytest.importorskip("pyspark")` in those classes.






Also applies to: 108-119



</details>



<!-- fingerprinting:phantom:medusa:pangolin -->

<!-- cr-indicator-types:potential_issue -->

<!-- cr-comment:v1:76ab43a658e8848c9a68b825 -->

_Source: Pipeline failures_

<!-- This is an auto-generated comment by CodeRabbit -->

### pipelines/ingest_sec_companyfacts.py:617
_🗄️ Data Integrity & Integration_ | _🟡 Minor_ | _⚡ Quick win_



**Reserve each `(cik, payload_hash)` through the Delta append.**

Two mapped ticker workers with the same CIK and payload hash can both pass the duplicate check before either worker marks the key seen. `SparkCompanyFactsWriter.append_rows` appends both batches. Reserve the key through the append, mark it seen only after success, and release the reservation on failure so another worker can retry.



<!-- fingerprinting:phantom:medusa:wombat -->

<!-- cr-indicator-types:potential_issue -->

<!-- cr-comment:v1:46120c88cc3ba8ee02c116c4 -->

<!-- This is an auto-generated comment by CodeRabbit -->

### pipelines/ingest_sec_companyfacts.py:788
_🗄️ Data Integrity & Integration_ | _🟡 Minor_ | _⚡ Quick win_



**Propagate manifest schema failures when required columns remain missing.**

If schema inspection or `ALTER TABLE` fails while manifest columns are still missing, `ensure_table` must not return as if the migration succeeded. The later manifest append can fail after the bronze rows have already been written. Continue only when a fresh schema read confirms that all manifest columns are present.



<!-- suggestion_start -->



<!-- suggestion_end -->



</details>



<!-- fingerprinting:phantom:medusa:wombat -->

<!-- cr-indicator-types:potential_issue -->

<!-- cr-comment:v1:7be61499893f8fe6bada7a80 -->

<!-- This is an auto-generated comment by CodeRabbit -->

### resources/jobs.yml:116
_🩺 Stability & Availability_ | _🟠 Major_ | _⚡ Quick win_



**Add PyYAML to this job’s serverless dependencies.**

The job omits `--cik-overrides-path`, so a normal run calls `load_cik_overrides(None)`. The checked-in default file exists, and the loader imports `yaml`. Serverless environment version 1 does not list PyYAML as a preinstalled library. The task can fail with `ModuleNotFoundError` before it ingests Company Facts.



<!-- suggestion_start -->



<!-- suggestion_end -->



<!-- fingerprinting:phantom:medusa:wombat -->

<!-- cr-indicator-types:potential_issue -->

<!-- cr-comment:v1:ce301879ed278733ddbdcbb8 -->

<!-- This is an auto-generated comment by CodeRabbit -->
