# BUILD: strategy robustness round 9, fix the parallel and caching layer (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests, EXCEPT replacing the sequential "determinism" test with a real one (say so).

DeepSeek (`.agents/deepseek/VERDICT-strategy-robustness-perf.md`, read it fully). The vectorised
`compute_costs` is fine. Three blocking defects:

1. **The ProcessPool can't run.** `_worker_task` / `_worker_init` are nested in `main()`, so they're
   unpicklable, and every variant becomes `{"error": ...}`, swallowed into an all-ERROR report.
   - Move the workers to module level, in `strategies/robustness_worker.py`, taking only picklable
     args.
   - Pass shared data once, via the pool initializer: a module global set in the worker.
   - Do NOT swallow worker errors. Any variant error makes the run FAIL with the error listed.
   - **Real test:** run a tiny synthetic panel with `workers=1` and `workers=2` through the ACTUAL
     ProcessPool, with the `spawn` start method so it works on all platforms. The results must be
     identical. This test must fail on the current HEAD.
2. **The cache fingerprint is incomplete** (`strategies/robustness.py:~38-41`). Hash ALL of these:
   - the variant params;
   - the full resolved config (`cost_model`, `residual_reversion`, `robustness` blocks);
   - a data fingerprint: hash of the input panel's shape, date range, symbol list, and a checksum of
     the values;
   - a code version: hash of the source of `strategies/*.py`, or the git SHA plus a dirty flag.

   Test: changing `commission_bps` changes the fingerprint and forces a recompute.
3. **Resume misorders results** (`run_residual_reversion.py:~692-702`). Key the results by variant
   fingerprint/name, never by position. The final ordering follows the registry order by name.
   Test: a registry [A, B, C, D] with cached {A, C} must give A, B, C and D their OWN results.

Also: the run summary shows the computed vs cached variant counts and the wall time.

Run:
- `python3 -m pytest -q tests/strategies tests/ml`;
- the same suite with pyspark hidden.

LF line endings only. Don't touch `.agents/dispatch.sh`. Write
`.agents/mimo/VERDICT-strategy-robustness-round9.md`.
