"""
tests/bronze/test_refresh_runtime_exits.py
Exit-policy contract for the bronze refresh entry points (item 4).

Databricks ``spark_python_task`` runners report ``SystemExit(0)`` as a FAILED
task: after finishing its work a successful run under
``DATABRICKS_RUNTIME_VERSION`` must return normally. Real failures must still
exit non-zero and CLI exit codes are unchanged (0 on success, non-zero on
failure).

Covered scripts: notebooks/refresh_bronze_fed.py,
notebooks/refresh_bronze_options.py, notebooks/refresh_bronze_cot.py.
No Spark, no network: every live dependency is faked.
"""
import inspect
import sys

import pytest

from notebooks import refresh_bronze_cot as cot
from notebooks import refresh_bronze_fed as fed
from notebooks import refresh_bronze_options as opts


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def collect(self):
        return [self._row]


class _FakeSpark:
    def sql(self, query):
        if "COUNT(*)" in query:
            return _FakeResult({"n": 0})
        return _FakeResult({"m": None})


def _cot_report(status):
    return {
        "dataset": "com_fin",
        "table": "bootcamp_students.evangoh_capstone.bronze_cftc_com",
        "status": status,
        "pre_count": 0,
        "pre_max_date": None,
        "candidate_count": 0,
        "conflict_count": 0,
        "duplicate_count": 0,
        "new_count": 0,
        "post_count": 0,
        "post_max_date": None,
        "error": "",
        "source_file": "",
    }


def _daily_ok():
    return {
        "appended": 0,
        "candidate": 0,
        "new": 0,
        "entitlement_gap": False,
        "failed": 0,
    }


def _mock_fed(monkeypatch, rc):
    monkeypatch.setattr(fed, "run_refresh", lambda **kwargs: rc)


def _mock_cot(monkeypatch, status):
    monkeypatch.setattr(cot, "_ensure_spark_imports", lambda: None)
    monkeypatch.setattr(cot, "_get_spark", lambda: _FakeSpark())
    monkeypatch.setattr(cot, "get_target_stats", lambda spark, table: (None, None))
    monkeypatch.setattr(cot, "refresh_dataset", lambda **kwargs: _cot_report(status))
    monkeypatch.setattr(sys, "argv", ["refresh_bronze_cot.py", "--dry-run"])


def _mock_opts(monkeypatch, daily):
    monkeypatch.setattr(opts, "_get_spark", lambda: _FakeSpark())
    monkeypatch.setattr(opts, "_load_secrets", lambda: ("ak", "sk", "pk"))
    monkeypatch.setattr(
        opts,
        "_detect_s3",
        lambda *a, **kw: (None, None) if daily is None else (object(), "host"),
    )
    monkeypatch.setattr(opts, "_run_daily", lambda *a, **kw: daily)
    monkeypatch.setattr(
        opts,
        "_make_polygon_client",
        lambda key: (_ for _ in ()).throw(RuntimeError("probe")),
    )


# ---------------------------------------------------------------------------
# Success under the Databricks runtime: return normally (no SystemExit)
# ---------------------------------------------------------------------------

def test_fed_success_under_runtime_returns(monkeypatch):
    monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "15.4")
    monkeypatch.setattr(sys, "argv", ["refresh_bronze_fed.py", "--dry-run"])
    _mock_fed(monkeypatch, 0)
    assert fed.main() == 0


def test_options_success_under_runtime_returns(monkeypatch):
    monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "15.4")
    _mock_opts(monkeypatch, _daily_ok())
    assert opts.main(["--dry-run"]) == 0


def test_cot_success_under_runtime_returns(monkeypatch):
    monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "15.4")
    _mock_cot(monkeypatch, "OK")
    assert cot.main() == 0


# ---------------------------------------------------------------------------
# Real failure: exit non-zero everywhere
# ---------------------------------------------------------------------------

def test_fed_failure_under_runtime_exits_nonzero(monkeypatch):
    monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "15.4")
    monkeypatch.setattr(sys, "argv", ["refresh_bronze_fed.py", "--dry-run"])
    _mock_fed(monkeypatch, 1)
    with pytest.raises(SystemExit) as excinfo:
        fed.main()
    assert excinfo.value.code == 1


def test_options_failure_under_runtime_exits_nonzero(monkeypatch):
    monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "15.4")
    _mock_opts(monkeypatch, None)  # daily lane failed -> run fails
    with pytest.raises(SystemExit) as excinfo:
        opts.main(["--dry-run"])
    assert excinfo.value.code == 1


def test_cot_failure_under_runtime_exits_nonzero(monkeypatch):
    monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "15.4")
    _mock_cot(monkeypatch, "FAILED")
    with pytest.raises(SystemExit) as excinfo:
        cot.main()
    assert excinfo.value.code == 1


# ---------------------------------------------------------------------------
# CLI exit codes unchanged: 0 on success, non-zero on failure
# ---------------------------------------------------------------------------

def test_fed_cli_success_exits_zero(monkeypatch):
    monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)
    monkeypatch.setattr(sys, "argv", ["refresh_bronze_fed.py", "--dry-run"])
    _mock_fed(monkeypatch, 0)
    with pytest.raises(SystemExit) as excinfo:
        fed.main()
    assert excinfo.value.code in (0, None)


def test_options_cli_success_exits_zero(monkeypatch):
    monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)
    _mock_opts(monkeypatch, _daily_ok())
    with pytest.raises(SystemExit) as excinfo:
        opts.main(["--dry-run"])
    assert excinfo.value.code in (0, None)


def test_cot_cli_success_exits_zero(monkeypatch):
    monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)
    _mock_cot(monkeypatch, "OK")
    with pytest.raises(SystemExit) as excinfo:
        cot.main()
    assert excinfo.value.code in (0, None)


def test_fed_cli_failure_exits_nonzero(monkeypatch):
    monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)
    monkeypatch.setattr(sys, "argv", ["refresh_bronze_fed.py", "--dry-run"])
    _mock_fed(monkeypatch, 1)
    with pytest.raises(SystemExit) as excinfo:
        fed.main()
    assert excinfo.value.code == 1


# ---------------------------------------------------------------------------
# _finish helper semantics (identical in all three scripts)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mod", [fed, opts, cot], ids=["fed", "options", "cot"])
class TestFinishHelper:
    def test_runtime_success_returns(self, mod, monkeypatch):
        monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "15.4")
        assert mod._finish(0) == 0

    def test_runtime_failure_exits_nonzero(self, mod, monkeypatch):
        monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "15.4")
        with pytest.raises(SystemExit) as excinfo:
            mod._finish(1)
        assert excinfo.value.code == 1

    def test_cli_success_exits_zero(self, mod, monkeypatch):
        monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)
        with pytest.raises(SystemExit) as excinfo:
            mod._finish(0)
        assert excinfo.value.code in (0, None)

    def test_cli_failure_exits_nonzero(self, mod, monkeypatch):
        monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)
        with pytest.raises(SystemExit) as excinfo:
            mod._finish(1)
        assert excinfo.value.code == 1


# ---------------------------------------------------------------------------
# Entry-point wiring regression anchor (old code had no _finish at all)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mod", [fed, opts, cot], ids=["fed", "options", "cot"])
def test_main_routes_through_finish(mod):
    """main() must apply the shared exit policy, not raw sys.exit/main exit."""
    src = inspect.getsource(mod.main)
    assert "_finish(" in src, (
        f"{mod.__name__}.main must route its exit codes through _finish()"
    )
    assert "sys.exit(" not in src, (
        f"{mod.__name__}.main must not call sys.exit directly"
    )
