"""Test configuration for the ML lane.

Registers the ``spark`` and ``databricks`` markers so the shared ``pytest.ini``
(which we are not allowed to edit) can deselect them without emitting
``PytestUnknownMarkWarning``. The ML lane's fast tests need neither.
"""


def pytest_configure(config):
    config.addinivalue_line("markers", "spark: needs a local SparkSession")
    config.addinivalue_line("markers", "databricks: needs a live Databricks workspace/warehouse")
