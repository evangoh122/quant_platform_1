#!/usr/bin/env python3
"""Frontend mutation tests for decision-p0a round 4 (partial hint).

Tests r3 mutations M1-M4 and r4 mutations M1-M3 against the frontend
vitest suite. Each mutation runs in an isolated `git archive HEAD` copy.
"""
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_TEST = "frontend/src/screens/PaperPortfolio.test.tsx"
VITEST_BIN = "node_modules/.bin/vitest"

R3_MUTATIONS = [
    {
        "id": "r3-M1",
        "desc": "Restore combined-filter pricedPositions (remove independent summation)",
        "edits": [
            {
                "file": "frontend/src/screens/PaperPortfolio.tsx",
                "old": "  const positions = data?.positions.data ?? [];\n  const realized = positions.reduce((sum, p) => (p.realized_pnl != null ? sum + p.realized_pnl : sum), 0);\n  const unrealized = positions.reduce((sum, p) => (p.unrealized_pnl != null ? sum + p.unrealized_pnl : sum), 0);\n  const unpricedUnrealized = positions.filter((p) => p.unrealized_pnl == null).length;\n  const unpricedRealized = positions.filter((p) => p.realized_pnl == null).length;\n  const hasRealized = positions.some((p) => p.realized_pnl != null);\n  const hasUnrealized = positions.some((p) => p.unrealized_pnl != null);\n  const totalPnlKnown = hasRealized || hasUnrealized;\n  const totalPnl = realized + unrealized;",
                "new": "  const positions = data?.positions.data ?? [];\n  const pricedPositions = positions.filter((p) => p.realized_pnl != null && p.unrealized_pnl != null);\n  const realized = pricedPositions.reduce((sum, p) => sum + p.realized_pnl, 0);\n  const unrealized = pricedPositions.reduce((sum, p) => sum + p.unrealized_pnl, 0);\n  const unpricedUnrealized = positions.filter((p) => p.unrealized_pnl == null).length;\n  const unpricedRealized = positions.filter((p) => p.realized_pnl == null).length;\n  const totalPnlKnown = pricedPositions.length > 0;\n  const totalPnl = realized + unrealized;",
            },
        ],
        "tests": [
            "PaperPortfolio > shows em dash for Total P&L when all P&L values are null",
            "PaperPortfolio > counts unpriced realized independently of unpriced unrealized",
        ],
    },
    {
        "id": "r3-M2",
        "desc": "Coerce null to 0 (totalPnl always shows number)",
        "edits": [
            {
                "file": "frontend/src/screens/PaperPortfolio.tsx",
                "old": "value={totalPnlKnown ? totalPnl.toFixed(2) : '\\u2014'}",
                "new": "value={totalPnl.toFixed(2)}",
            },
        ],
        "tests": [
            "PaperPortfolio > shows em dash for Total P&L when all P&L values are null",
        ],
    },
    {
        "id": "r3-M3",
        "desc": "Drop unpriced note (remove hint entirely)",
        "edits": [
            {
                "file": "frontend/src/screens/PaperPortfolio.tsx",
                "old": "              hint={\n                !totalPnlKnown\n                  ? undefined\n                  : unpricedUnrealized > 0 || unpricedRealized > 0\n                    ? `partial \\u00b7 realized ${realized.toFixed(2)}${unpricedUnrealized > 0 ? ` \\u00b7 ${unpricedUnrealized} unrealized unpriced` : ''}${unpricedRealized > 0 ? ` \\u00b7 ${unpricedRealized} realized unpriced` : ''}`\n                    : undefined\n              }",
                "new": "              hint={undefined}",
            },
        ],
        "tests": [
            "PaperPortfolio > sums realized and unrealized independently; shows unpriced note",
            "PaperPortfolio > counts unpriced realized independently of unpriced unrealized",
        ],
    },
    {
        "id": "r3-M4",
        "desc": "Sum realized only with non-null unrealized",
        "edits": [
            {
                "file": "frontend/src/screens/PaperPortfolio.tsx",
                "old": "  const realized = positions.reduce((sum, p) => (p.realized_pnl != null ? sum + p.realized_pnl : sum), 0);",
                "new": "  const realized = positions.filter((p) => p.unrealized_pnl != null).reduce((sum, p) => (p.realized_pnl != null ? sum + p.realized_pnl : sum), 0);",
            },
        ],
        "tests": [
            "PaperPortfolio > counts unpriced realized independently of unpriced unrealized",
        ],
    },
]

R4_MUTATIONS = [
    {
        "id": "r4-M1",
        "desc": "Drop the unpricedRealized clause from the hint",
        "edits": [
            {
                "file": "frontend/src/screens/PaperPortfolio.tsx",
                "old": "${unpricedRealized > 0 ? ` \\u00b7 ${unpricedRealized} realized unpriced` : ''}`",
                "new": "``",
            },
        ],
        "tests": [
            "PaperPortfolio > shows partial hint with both counts when both kinds of null present",
            "PaperPortfolio > shows partial hint with realized unpriced when all unrealized present but one realized null",
        ],
    },
    {
        "id": "r4-M2",
        "desc": "Drop the word partial from the hint",
        "edits": [
            {
                "file": "frontend/src/screens/PaperPortfolio.tsx",
                "old": "partial \\u00b7 realized",
                "new": "realized",
            },
        ],
        "tests": [
            "PaperPortfolio > shows partial hint with realized unpriced when all unrealized present but one realized null",
            "PaperPortfolio > shows partial hint with unrealized unpriced when all realized present but two unrealized null",
            "PaperPortfolio > shows partial hint with both counts when both kinds of null present",
        ],
    },
    {
        "id": "r4-M3",
        "desc": "Only show hint when unpricedUnrealized > 0 (the current defect)",
        "edits": [
            {
                "file": "frontend/src/screens/PaperPortfolio.tsx",
                "old": "unpricedUnrealized > 0 || unpricedRealized > 0",
                "new": "unpricedUnrealized > 0",
            },
        ],
        "tests": [
            "PaperPortfolio > shows partial hint with realized unpriced when all unrealized present but one realized null",
            "PaperPortfolio > shows partial hint with both counts when both kinds of null present",
        ],
    },
]


def git_archive_copy(dest):
    os.makedirs(dest, exist_ok=True)
    archive = subprocess.run(
        ["git", "archive", "HEAD"], cwd=REPO, stdout=subprocess.PIPE, check=True
    )
    tar = subprocess.run(["tar", "-x", "-C", dest], input=archive.stdout, check=False)
    if tar.returncode != 0:
        raise RuntimeError("tar extraction failed")


def run_vitest(copy_dir, test_name):
    result = subprocess.run(
        [VITEST_BIN, "run", "--reporter=verbose", "-t", test_name, FRONTEND_TEST],
        capture_output=True, text=True, cwd=copy_dir,
    )
    return result.returncode != 0, result.stdout + result.stderr


def apply_edits(copy_dir, mutation):
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


def failure_excerpt(output):
    lines = [l for l in output.strip().splitlines() if "FAIL" in l or "AssertionError" in l or "Expected" in l or "Received" in l]
    if lines:
        return "\n  ".join(lines[-8:])
    return "\n  ".join(output.strip().splitlines()[-8:])


def run_mutation(m, label):
    print(f"\n{'=' * 60}")
    print(f"MUTATION {m['id']}: {m['desc']}")
    print(f"  tests: {m['tests']}")
    print(f"{'=' * 60}")

    workdir = tempfile.mkdtemp(prefix=f"mut_{m['id']}_")
    copy_dir = os.path.join(workdir, "repo")
    try:
        git_archive_copy(copy_dir)

        # Install deps (copy doesn't have node_modules)
        subprocess.run(["npm", "ci"], cwd=copy_dir, capture_output=True, timeout=120)

        # Baseline: all target tests must pass
        for test_name in m["tests"]:
            failed, output = run_vitest(copy_dir, test_name)
            if failed:
                print(f"  BASELINE FAILED on unmutated copy — cannot claim a kill:")
                print(f"  {failure_excerpt(output)}")
                return (m["id"], "ERROR", "baseline test failed")
        print("  baseline: all target tests PASS on unmutated copy")

        if not apply_edits(copy_dir, m):
            return (m["id"], "SKIP", "old text not found")

        # At least one test must fail
        any_failed = False
        for test_name in m["tests"]:
            failed, output = run_vitest(copy_dir, test_name)
            if failed:
                any_failed = True
                print(f"  test FAILED (expected): {test_name}")
                print(f"  {failure_excerpt(output)}")

        if not any_failed:
            print("  MUTANT SURVIVED — all tests PASSED on mutated code")
            return (m["id"], "FAIL", "test passed on mutated code")

        print(f"  KILLED — {sum(1 for _ in m['tests'])} test(s) expected to fail")
        return (m["id"], "PASS", str(m["tests"]))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main():
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO, capture_output=True, text=True,
    ).stdout.strip()
    if dirty:
        print("ABORT: tracked working tree is dirty; commit first.")
        return 2

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    print(f"Frontend mutation harness: isolated copies from `git archive {head}`\n")

    results = []

    print("=" * 60)
    print("R3 MUTATIONS (re-run)")
    print("=" * 60)
    for m in R3_MUTATIONS:
        r = run_mutation(m, "r3")
        results.append(r)

    print("\n" + "=" * 60)
    print("R4 MUTATIONS (new)")
    print("=" * 60)
    for m in R4_MUTATIONS:
        r = run_mutation(m, "r4")
        results.append(r)

    print(f"\n{'=' * 60}")
    print("FRONTEND MUTATION SUMMARY")
    print(f"{'=' * 60}")
    for mid, status, detail in results:
        print(f"  {mid}: {status} — {detail}")

    all_pass = all(s == "PASS" for _, s, _ in results)
    if all_pass:
        print(f"\nAll {len(results)} frontend mutation tests passed.")
        return 0
    print("\nSOME FRONTEND MUTATION TESTS FAILED!")
    return 1


if __name__ == "__main__":
    sys.exit(main())