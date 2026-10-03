# BUILD: strategy robustness round 8, PERFORMANCE (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit after each step. NEVER delete or weaken
> existing tests. Results must be numerically IDENTICAL (to 1e-10) before and after.

Claude ran the full live suite:
`python -m strategies.run_residual_reversion --config strategies/config.yaml --robustness ...`
It timed out after **2h05m**, having completed the walk-forward but not the 72 variants. Profile and
fix:

1. **Profile first.** Use `cProfile` on ONE variant with a synthetic panel the size of the live run:
   about 940 days × 500 symbols. Report the top 10 hotspots in the verdict. Expect `compute_costs`
   (per-date, per-symbol Python loops), `cap_weight_changes_by_adv` (per-date loop),
   `_rolling_residuals_one_symbol`, PCA per date, and `screen_universe`.
2. **Vectorise.**
   - `compute_costs`: compute participation, bps and borrow with NumPy over the whole (dates ×
     symbols) array.
   - `cap_weight_changes_by_adv`: the recursion depends on prev, so keep the date loop, but
     vectorise across symbols, with no inner Python loop over symbols.
   - Any other hotspot found above.
3. **Equivalence tests** (mandatory): for random inputs, including NaN ADV, flips, reductions and
   exits, the new `compute_costs` and the cap function equal the OLD implementations (keep a private
   reference copy in the tests) to 1e-10. The 500-sequence property test must still pass.
4. **Parallel variants.** Run the 72 variants with `concurrent.futures.ProcessPoolExecutor`, with
   `--workers` defaulting to `min(8, cpu_count)`. The data is fetched ONCE in the parent and passed,
   or memory-mapped. Results are deterministic regardless of worker count; a test checks
   workers=1 == workers=4 on a small panel.
5. **Checkpointing.**
   - Write each finished variant to `strategies/results/.robustness_cache/<fingerprint>.json`
     (gitignored).
   - Skip completed fingerprints on rerun, with `--no-resume` to force.
   - Log progress and ETA after every variant.
6. **Target:** state the measured speed-up on the synthetic panel and the projected full-suite time.
   The goal is a full live run in under 30 minutes on this machine.

Run:
- `python3 -m pytest -q tests/strategies tests/ml`;
- the same suite with pyspark hidden.

LF line endings only. Don't touch `.agents/dispatch.sh`. Leave no scratch files. Write
`.agents/mimo/VERDICT-strategy-robustness-round8.md`.
