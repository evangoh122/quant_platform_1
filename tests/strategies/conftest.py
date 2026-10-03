"""Test configuration for the strategies lane.

Registers the ``spark`` and ``databricks`` markers (mirroring tests/ml/conftest.py)
so the shared ``pytest.ini`` can deselect them without emitting
``PytestUnknownMarkWarning``. The strategies lane's offline tests need neither
Spark nor a live warehouse.
"""


def pytest_configure(config):
    config.addinivalue_line("markers", "spark: needs a local SparkSession")
    config.addinivalue_line("markers", "databricks: needs a live Databricks workspace/warehouse")
