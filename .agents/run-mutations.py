#!/usr/bin/env python3
"""Mutation tests for decision-p0a data-correctness fixes (round 2).

For every mutation this harness:
  1. extracts a fresh isolated copy of the tree with ``git archive HEAD``
     (never the live working tree, never a ``cp -r`` copy that would drag
     ``.git`` along),
  2. runs the mutation's target test on the UNMUTATED copy and requires it to
     PASS (baseline — a kill cannot be claimed against a red or erroring test),
  3. applies the mutation inside the copy and requires the target test to FAIL
     for the mutation's expected reason (``expect_fail_text`` must appear in
     the pytest output, so a fixture/collection error cannot masquerade as a
     kill).

The repo conftest is loaded (no ``--noconftest``): ``tests/api/conftest.py``
fixtures like ``fake_lakebase`` must resolve exactly as in a normal run.

Because copies come from ``git archive HEAD``, the tracked working tree must
match HEAD (commit first) — the harness aborts otherwise.
"""
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MUTATIONS = [
    {
        "id": "M1",
        "desc": "Remove orderBy in tools_retrieval (options read)",
        "edits": [
            {
                "file": "agent/tools_retrieval.py",
                "old": '.orderBy(F.col("feature_ts").desc())',
                "new": "",
            },
        ],
        "test": "tests/agent/test_tools_retrieval_ordering.py::test_orderBy_called_before_limit",
        "expect_fail_text": "is not in list",
    },
    {
        "id": "M2",
        "desc": "Replace trading-day helper call with timedelta in market.py",
        "edits": [
            {
                "file": "api/routes/market.py",
                "old": "from api.trading_days import start_for_trading_days",
                "new": "",
            },
            {
                "file": "api/routes/market.py",
                "old": "    from datetime import date\n    start_dt_date = start_for_trading_days(end_dt.date(), days)\n    start_dt = datetime.combine(start_dt_date, end_dt.time(), tzinfo=end_dt.tzinfo)",
                "new": "    start_dt = end_dt - timedelta(days=days)",
            },
            {
                "file": "api/routes/market.py",
                "old": "from datetime import datetime, timezone",
                "new": "from datetime import datetime, timedelta, timezone",
            },
        ],
        "test": "tests/api/test_trading_days.py::TestMarketRouteTradingDays::test_start_time_matches_helper_output",
        "expect_fail_text": "helper output",
    },
    {
        "id": "M3",
        "desc": "Change null P&L back to zero-coercion",
        "edits": [
            {
                "file": "api/routes/portfolio.py",
                "old": "realized_pnl=r.get(\"realized_pnl\"),\n                unrealized_pnl=r.get(\"unrealized_pnl\"),",
                "new": "realized_pnl=float(r.get(\"realized_pnl\") or 0),\n                unrealized_pnl=float(r.get(\"unrealized_pnl\") or 0),",
            },
        ],
        "test": "tests/api/test_portfolio_null_pnl.py::test_null_pnl_serializes_as_json_null",
        "expect_fail_text": "should be null",
    },
    {
        "id": "M4",
        "desc": "Remove count guard from SQL z-score",
        "edits": [
            {
                "file": "gold/02_gold_options_features.sql",
                "old": "    CASE WHEN vw.vol_count >= 20\n         THEN (day.total_volume - vw.avg_vol) / NULLIF(vw.std_vol, 0)\n    END AS volume_anomaly_zscore,",
                "new": "    (day.total_volume - vw.avg_vol) / NULLIF(vw.std_vol, 0) AS volume_anomaly_zscore,",
            },
        ],
        "test": "tests/gold/test_zscore_window_guard.py::test_gold_sql_count_guard_produces_null_for_small_windows",
        # Semantic kill: the guard-less expression must fail the NULL
        # assertion for small windows — not a SQL parse/extraction error.
        "expect_fail_text": "expected NULL",
    },
    {
        "id": "M5",
        "desc": "Make start_for_trading_days ignore weekends",
        "edits": [
            {
                "file": "api/trading_days.py",
                "old": "    # Walk backward from *end*, counting only weekdays.",
                "new": "    # Simple calendar subtraction (ignores weekends).\n    return end - timedelta(days=n)\n\n    # DEAD CODE below (unreachable)\n    # Walk backward from *end*, counting only weekdays.",
            },
        ],
        "test": "tests/api/test_trading_days.py::TestStartForTradingDays::test_wednesday_back_5_trading_days",
        "expect_fail_text": "2026, 9, 30",
    },
    {
        "id": "M6",
        "desc": "Remove the new orderBy from market_features_daily (r2)",
        "edits": [
            {
                "file": "db/delta_adapter.py",
                "old": "        ).select(*daily_cols)\n        return df.orderBy(F.col(\"event_date\").desc()).limit(limit)",
                "new": "        ).select(*daily_cols)\n        return df.limit(limit)",
            },
        ],
        "test": "tests/agent/test_delta_adapter_ordering.py::test_market_features_orders_event_date_desc_before_limit",
        "expect_fail_text": "never applied orderBy",
    },
    {
        "id": "M7",
        "desc": "Reverse order direction on read_analytics_table (r2)",
        "edits": [
            {
                "file": "db/delta_adapter.py",
                "old": "            rows = [r.asDict() for r in df.orderBy(F.col(\"event_date\").desc()).limit(limit).collect()]",
                "new": "            rows = [r.asDict() for r in df.orderBy(F.col(\"event_date\").asc()).limit(limit).collect()]",
            },
        ],
        "test": "tests/agent/test_delta_adapter_ordering.py::test_read_analytics_table_orders_event_date_desc_before_limit",
        "expect_fail_text": "must be descending",
    },
]


def git_archive_copy(dest: str) -> None:
    """Extract HEAD into dest via `git archive HEAD | tar -x` (no .git)."""
    os.makedirs(dest, exist_ok=True)
    archive = subprocess.run(
        ["git", "archive", "HEAD"], cwd=REPO, stdout=subprocess.PIPE, check=True
    )
    tar = subprocess.run(["tar", "-x", "-C", dest], input=archive.stdout, check=False)
    if tar.returncode != 0:
        raise RuntimeError("tar extraction of git archive failed")


def run_pytest(copy_dir: str, test_path: str) -> tuple:
    """Run one test in the copy. Returns (failed: bool, output: str)."""
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", test_path,
            "-x", "-q", "--timeout=30", "-p", "no:cacheprovider",
        ],
        capture_output=True, text=True, cwd=copy_dir,
    )
    return result.returncode != 0, result.stdout + result.stderr


def apply_edits(copy_dir: str, mutation: dict) -> bool:
    """Apply all edits of a mutation inside the copy. Returns success."""
    for edit in mutation["edits"]:
        filepath = os.path.join(copy_dir, edit["file"])
        with open(filepath, "r") as f:
            content = f.read()
        if edit["old"] not in content:
            print(f"  WARNING: old text not found in {edit['file']}")
            return False
        mutated = content.replace(edit["old"], edit["new"], 1)
        with open(filepath, "w") as f:
            f.write(mutated)
    return True


def failure_excerpt(output: str) -> str:
    """Assertion/error lines ('E ...') if any, else the tail of the output."""
    err_lines = [l for l in output.strip().splitlines() if l.strip().startswith("E ")]
    if err_lines:
        return "\n  ".join(err_lines[-8:])
    return "\n  ".join(output.strip().splitlines()[-8:])


def main() -> int:
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO, capture_output=True, text=True,
    ).stdout.strip()
    if dirty:
        print("ABORT: tracked working tree is dirty; commit first so")
        print("`git archive HEAD` copies the code under test:")
        print(dirty)
        return 2

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    print(f"mutation harness: isolated copies from `git archive {head}`")
    print("pytest runs with the repo conftest loaded (no --noconftest)\n")

    results = []

    for m in MUTATIONS:
        print(f"\n{'=' * 60}")
        print(f"MUTATION {m['id']}: {m['desc']}")
        print(f"  target: {m['test']}")
        print(f"  kill signature required: {m['expect_fail_text']!r}")
        print(f"{'=' * 60}")

        workdir = tempfile.mkdtemp(prefix=f"mut_{m['id']}_")
        copy_dir = os.path.join(workdir, "repo")
        try:
            git_archive_copy(copy_dir)

            # Baseline: the target test must pass on the unmutated copy.
            failed, output = run_pytest(copy_dir, m["test"])
            if failed:
                print("  BASELINE FAILED on unmutated copy — cannot claim a kill:")
                print("  " + failure_excerpt(output))
                results.append((m["id"], "ERROR", "baseline test failed on unmutated copy"))
                continue
            print("  baseline: test PASSES on unmutated copy")

            if not apply_edits(copy_dir, m):
                results.append((m["id"], "SKIP", "old text not found"))
                continue

            failed, output = run_pytest(copy_dir, m["test"])
            if not failed:
                print("  MUTANT SURVIVED — test PASSED on mutated code")
                results.append((m["id"], "FAIL", "test passed on mutated code"))
                continue

            if m["expect_fail_text"].lower() not in output.lower():
                print("  WRONG REASON — test failed but not via the expected kill signature:")
                print("  " + failure_excerpt(output))
                results.append((m["id"], "FAIL", "killed for the wrong reason"))
                continue

            print("  test FAILED (expected) via the expected kill signature")
            print("  pytest failure excerpt:")
            print("  " + failure_excerpt(output))
            results.append((m["id"], "PASS", m["test"]))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    print(f"\n{'=' * 60}")
    print("MUTATION TEST SUMMARY")
    print(f"{'=' * 60}")
    for mid, status, detail in results:
        print(f"  {mid}: {status} — {detail}")

    all_pass = all(s == "PASS" for _, s, _ in results)
    if all_pass:
        print(f"\nAll {len(results)} mutation tests passed (mutations detected by tests,"
              " for the expected reason, in isolated git-archive copies).")
        return 0
    print("\nSOME MUTATION TESTS FAILED!")
    return 1


if __name__ == "__main__":
    sys.exit(main())
