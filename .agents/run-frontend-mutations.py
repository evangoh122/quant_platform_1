#!/usr/bin/env python3
"""Run frontend mutations manually: apply, test, revert.
Uses the working tree directly since node_modules is not in git archive.
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(REPO, "frontend")
PAPER = os.path.join(FRONTEND, "src/screens/PaperPortfolio.tsx")
TEST = "src/screens/PaperPortfolio.test.tsx"
VITEST = os.path.join(FRONTEND, "node_modules/.bin/vitest")
NODE = os.path.expanduser("~/.nvm/versions/node/v26.5.0/bin/node")

MIDDLE_DOT = "\u00b7"  # actual · character
EM_DASH = "\\u2014"    # literal \u2014 in the file

R3_MUTATIONS = [
    {
        "id": "r3-M1",
        "desc": "Restore combined-filter pricedPositions",
        "test": "PaperPortfolio > shows em dash for Total P&L when all P&L values are null",
        "old": (
            "  const positions = data?.positions.data ?? [];\n"
            "  const realized = positions.reduce((sum, p) => (p.realized_pnl != null ? sum + p.realized_pnl : sum), 0);\n"
            "  const unrealized = positions.reduce((sum, p) => (p.unrealized_pnl != null ? sum + p.unrealized_pnl : sum), 0);\n"
            "  const unpricedUnrealized = positions.filter((p) => p.unrealized_pnl == null).length;\n"
            "  const unpricedRealized = positions.filter((p) => p.realized_pnl == null).length;\n"
            "  const hasRealized = positions.some((p) => p.realized_pnl != null);\n"
            "  const hasUnrealized = positions.some((p) => p.unrealized_pnl != null);\n"
            "  const totalPnlKnown = hasRealized || hasUnrealized;\n"
            "  const totalPnl = realized + unrealized;"
        ),
        "new": (
            "  const positions = data?.positions.data ?? [];\n"
            "  const pricedPositions = positions.filter((p) => p.realized_pnl != null && p.unrealized_pnl != null);\n"
            "  const realized = pricedPositions.reduce((sum, p) => sum + p.realized_pnl, 0);\n"
            "  const unrealized = pricedPositions.reduce((sum, p) => sum + p.unrealized_pnl, 0);\n"
            "  const unpricedUnrealized = positions.filter((p) => p.unrealized_pnl == null).length;\n"
            "  const unpricedRealized = positions.filter((p) => p.realized_pnl == null).length;\n"
            "  const totalPnlKnown = pricedPositions.length > 0;\n"
            "  const totalPnl = realized + unrealized;"
        ),
    },
    {
        "id": "r3-M2",
        "desc": "Coerce null to 0",
        "test": "PaperPortfolio > shows em dash for Total P&L when all P&L values are null",
        "old": f"value={{totalPnlKnown ? totalPnl.toFixed(2) : '{EM_DASH}'}}",
        "new": "value={totalPnl.toFixed(2)}",
    },
    {
        "id": "r3-M3",
        "desc": "Drop unpriced note (remove hint)",
        "test": "PaperPortfolio > sums realized and unrealized independently; shows unpriced note",
        "old": (
            "              hint={\n"
            "                !totalPnlKnown\n"
            "                  ? undefined\n"
            "                  : unpricedUnrealized > 0 || unpricedRealized > 0\n"
            f"                    ? `partial {MIDDLE_DOT} realized ${{realized.toFixed(2)}}${{unpricedUnrealized > 0 ? ` {MIDDLE_DOT} ${{unpricedUnrealized}} unrealized unpriced` : ''}}${{unpricedRealized > 0 ? ` {MIDDLE_DOT} ${{unpricedRealized}} realized unpriced` : ''}}`\n"
            "                    : undefined\n"
            "              }"
        ),
        "new": "              hint={undefined}",
    },
    {
        "id": "r3-M4",
        "desc": "Sum realized only with non-null unrealized",
        "test": "PaperPortfolio > counts unpriced realized independently of unpriced unrealized",
        "old": "  const realized = positions.reduce((sum, p) => (p.realized_pnl != null ? sum + p.realized_pnl : sum), 0);",
        "new": "  const realized = positions.filter((p) => p.unrealized_pnl != null).reduce((sum, p) => (p.realized_pnl != null ? sum + p.realized_pnl : sum), 0);",
    },
]

R4_MUTATIONS = [
    {
        "id": "r4-M1",
        "desc": "Drop the unpricedRealized clause from the hint",
        "test": "PaperPortfolio > shows partial hint with both counts when both kinds of null present",
        "old": f"${{unpricedRealized > 0 ? ` {MIDDLE_DOT} ${{unpricedRealized}} realized unpriced` : ''}}`",
        "new": "``",
    },
    {
        "id": "r4-M2",
        "desc": "Drop the word partial from the hint",
        "test": "PaperPortfolio > shows partial hint with realized unpriced when all unrealized present but one realized null",
        "old": f"partial {MIDDLE_DOT} realized",
        "new": "realized",
    },
    {
        "id": "r4-M3",
        "desc": "Only show hint when unpricedUnrealized > 0",
        "test": "PaperPortfolio > shows partial hint with realized unpriced when all unrealized present but one realized null",
        "old": "unpricedUnrealized > 0 || unpricedRealized > 0",
        "new": "unpricedUnrealized > 0",
    },
]


def run_test(test_name):
    env = os.environ.copy()
    env["PATH"] = os.path.dirname(NODE) + ":" + env.get("PATH", "")
    result = subprocess.run(
        [NODE, VITEST, "run", "-t", test_name, TEST],
        capture_output=True, text=True, cwd=FRONTEND, timeout=60, env=env,
    )
    return result.returncode != 0, result.stdout + result.stderr


def apply_mutation(mutation):
    with open(PAPER, "r") as f:
        content = f.read()
    if mutation["old"] not in content:
        return False, f"old text not found (len={len(mutation['old'])})"
    mutated = content.replace(mutation["old"], mutation["new"], 1)
    with open(PAPER, "w") as f:
        f.write(mutated)
    return True, "ok"


def failure_excerpt(output):
    lines = [l for l in output.strip().splitlines()
             if "FAIL" in l or "Expected" in l or "Received" in l or "Error" in l]
    if lines:
        return "\n  ".join(lines[-5:])
    return "\n  ".join(output.strip().splitlines()[-5:])


def run_mutation(m):
    print(f"\n{'=' * 60}")
    print(f"MUTATION {m['id']}: {m['desc']}")
    print(f"  target: {m['test']}")
    print(f"{'=' * 60}")

    # Save original
    with open(PAPER, "r") as f:
        original = f.read()

    # Baseline check
    failed, output = run_test(m["test"])
    if failed:
        print("  BASELINE FAILED — cannot claim a kill")
        print(f"  {failure_excerpt(output)}")
        return (m["id"], "ERROR", "baseline failed")
    print("  baseline: PASS")

    # Apply mutation
    ok, msg = apply_mutation(m)
    if not ok:
        print(f"  SKIP: {msg}")
        return (m["id"], "SKIP", msg)

    # Run test on mutated code
    failed, output = run_test(m["test"])

    # Restore original
    with open(PAPER, "w") as f:
        f.write(original)

    if not failed:
        print("  MUTANT SURVIVED — test PASSED on mutated code")
        return (m["id"], "FAIL", "test passed on mutated code")

    print("  test FAILED (expected) — mutation KILLED")
    print(f"  {failure_excerpt(output)}")
    return (m["id"], "PASS", m["test"])


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
    print(f"Frontend mutation tests (manual patch-and-revert)")
    print(f"Base: {head}\n")

    results = []

    print("=== R3 MUTATIONS (re-run) ===")
    for m in R3_MUTATIONS:
        results.append(run_mutation(m))

    print("\n=== R4 MUTATIONS (new) ===")
    for m in R4_MUTATIONS:
        results.append(run_mutation(m))

    print(f"\n{'=' * 60}")
    print("FRONTEND MUTATION SUMMARY")
    print(f"{'=' * 60}")
    for mid, status, detail in results:
        print(f"  {mid}: {status} — {detail}")

    all_pass = all(s == "PASS" for _, s, _ in results)
    if all_pass:
        print(f"\nAll {len(results)} frontend mutation tests passed.")
        return 0
    print("\nSOME MUTANTS SURVIVED!")
    return 1


if __name__ == "__main__":
    sys.exit(main())