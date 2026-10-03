# CHECK: robustness round 8, performance (DeepSeek)

MiMo vectorised `compute_costs` (649× speed-up) and added parallel variants (ProcessPool) plus
checkpointing. 231 tests pass. Read-only; scratch work in /tmp. Write
`.agents/deepseek/VERDICT-strategy-robustness-perf.md` (===VERDICT START/END===, Status).

Verify:
1. **Numerical equivalence.**
   - The new `compute_costs` equals the OLD implementation (`git show 67a25f8:strategies/backtest.py`)
     to 1e-10 on random inputs: NaN ADV, flips, reductions, exits, zero ADV, borrow on shorts, and the
     2×/3× cost multipliers.
   - Run your own randomized comparison with ≥ 500 cases.
2. **Determinism.** `workers=1` == `workers=4` == `workers=8` results, byte-identical after sorting.
   No shared mutable state across processes; the seeds are per variant.
3. **Checkpointing.**
   - The fingerprint covers ALL inputs: config, data hash, code version. A changed input must not
     reuse a stale cache. Prove it by changing a cost param and showing the cached variant is NOT
     reused.
   - `--no-resume` works. The cache dir is gitignored.
4. **Trial counting** is unaffected by caching: cached variants still count once, never twice.
5. The property tests and earlier guarantees still hold.

Run `python3 -m pytest -q tests/strategies tests/ml`, and the same suite with pyspark hidden.
