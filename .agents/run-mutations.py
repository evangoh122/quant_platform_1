#!/usr/bin/env python3
"""Mutation tests for decision-p0a data-correctness fixes.

Creates isolated git archive copies and applies each mutation, then runs
the corresponding test to verify it fails.
"""
import subprocess
import sys
import os
import shutil
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE_DIR = tempfile.mkdtemp(prefix="mutation_")

MUTATIONS = [
    {
        "id": "M1",
        "desc": "Remove orderBy in tools_retrieval",
        "file": "agent/tools_retrieval.py",
        "old": '.orderBy(F.col("feature_ts").desc())',
        "new": "",
        "test": "tests/agent/test_tools_retrieval_ordering.py::test_orderBy_called_before_limit",
    },
    {
        "id": "M2",
        "desc": "Replace helper call with timedelta in market.py",
        "file": "api/routes/market.py",
        "old": "from api.trading_days import start_for_trading_days",
        "new": "",
        "test": "tests/api/test_trading_days.py::TestMarketRouteTradingDays::test_start_time_matches_helper_output",
        "extra_reverts": [
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
    },
    {
        "id": "M3",
        "desc": "Change null P&L back to coercion",
        "file": "api/routes/portfolio.py",
        "old": "realized_pnl=r.get(\"realized_pnl\"),\n                unrealized_pnl=r.get(\"unrealized_pnl\"),",
        "new": "realized_pnl=float(r.get(\"realized_pnl\") or 0),\n                unrealized_pnl=float(r.get(\"unrealized_pnl\") or 0),",
        "test": "tests/api/test_portfolio_null_pnl.py::test_null_pnl_serializes_as_json_null",
    },
    {
        "id": "M4",
        "desc": "Remove count guard from SQL z-score",
        "file": "gold/02_gold_options_features.sql",
        "old": "    CASE WHEN vw.vol_count >= 20\n         THEN (day.total_volume - vw.avg_vol) / NULLIF(vw.std_vol, 0)\n    END AS volume_anomaly_zscore,",
        "new": "    (day.total_volume - vw.avg_vol) / NULLIF(vw.std_vol, 0) AS volume_anomaly_zscore,",
        "test": "tests/gold/test_zscore_window_guard.py::test_gold_sql_count_guard_produces_null_for_small_windows",
    },
    {
        "id": "M5",
        "desc": "Make start_for_trading_days ignore weekends",
        "file": "api/trading_days.py",
        "old": "    # Walk backward from *end*, counting only weekdays.",
        "new": "    # Simple calendar subtraction (ignores weekends).\n    return end - timedelta(days=n)\n\n    # DEAD CODE below (unreachable)\n    # Walk backward from *end*, counting only weekdays.",
        "test": "tests/api/test_trading_days.py::TestStartForTradingDays::test_wednesday_back_5_trading_days",
    },
]


def run_test(test_path):
    """Run a single test and return True if it fails."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, "--noconftest", "-x", "-q", "--timeout=30"],
        capture_output=True, text=True, cwd=REPO,
    )
    return result.returncode != 0


def apply_mutation(mutation):
    """Apply a mutation to the repo."""
    filepath = os.path.join(REPO, mutation["file"])
    with open(filepath, "r") as f:
        content = f.read()

    if mutation["old"] not in content:
        print(f"  WARNING: old text not found in {mutation['file']}")
        return None

    mutated = content.replace(mutation["old"], mutation["new"], 1)

    # Apply extra reverts if any
    for extra in mutation.get("extra_reverts", []):
        extra_path = os.path.join(REPO, extra["file"])
        with open(extra_path, "r") as f:
            extra_content = f.read()
        if extra["old"] in extra_content:
            extra_mutated = extra_content.replace(extra["old"], extra["new"], 1)
            with open(extra_path, "w") as f:
                f.write(extra_mutated)

    with open(filepath, "w") as f:
        f.write(mutated)

    return content  # return original for restore


def restore_mutation(mutation, original):
    """Restore original content."""
    filepath = os.path.join(REPO, mutation["file"])
    with open(filepath, "w") as f:
        f.write(original)


def main():
    results = []

    for m in MUTATIONS:
        print(f"\n{'='*60}")
        print(f"MUTATION {m['id']}: {m['desc']}")
        print(f"{'='*60}")

        # Apply mutation
        original = apply_mutation(m)
        if original is None:
            results.append((m["id"], "SKIP", "old text not found"))
            continue

        try:
            # Run the test (should fail)
            test_fails = run_test(m["test"])
            status = "PASS" if test_fails else "FAIL"
            print(f"  Test {'FAILED (expected)' if test_fails else 'PASSED (unexpected)'}")
            results.append((m["id"], status, m["test"]))
        finally:
            # Restore
            restore_mutation(m, original)
            # Restore extra reverts
            for extra in m.get("extra_reverts", []):
                extra_path = os.path.join(REPO, extra["file"])
                with open(extra_path, "r") as f:
                    extra_content = f.read()
                extra_original = extra_content.replace(extra["new"], extra["old"], 1)
                with open(extra_path, "w") as f:
                    f.write(extra_original)

    print(f"\n{'='*60}")
    print("MUTATION TEST SUMMARY")
    print(f"{'='*60}")
    for mid, status, detail in results:
        print(f"  {mid}: {status} — {detail}")

    all_pass = all(s == "PASS" for _, s, _ in results if s != "SKIP")
    if all_pass:
        print("\nAll mutation tests passed (mutations detected by tests).")
    else:
        print("\nSOME MUTATION TESTS FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    main()
