# BUILD corporate-actions round 10 (builder: MiMo)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/corporate-actions. Commit after each item, descriptive messages. LF.
DeepSeek verdict: .agents/deepseek/VERDICT-corporate-actions-round9.md (3 blocking).
RULE FOR THIS ROUND: NO source-text/grep tests. Every new test must IMPORT and EXECUTE real code. Source-grep tests you replace may be deleted
(list them in the verdict).

1. Refactor the notebook's per-batch loop (notebooks/refresh_bronze_corporate_actions.py ~:340-505) into an importable function, e.g.
   `run_batch(symbols, adapter, writer, checkpoint_store, run_id)`, with injectable writer/checkpoint store (the notebook calls it with the Spark
   implementations). FUNCTIONAL test with in-memory fakes: writer raises after fetch (simulated crash) → no SUCCESS recorded; second call with the same
   run_id → the symbol is NOT skipped and its rows are written; a symbol that truly succeeded is skipped on resume. Mutation (in /tmp copy, paste
   output): record SUCCESS before append → FAILS.
2. SUCCESS only if ALL of a symbol's batch keys are verified (:492-499 bug: setdefault makes ANY verified row mark the symbol). Use
   `all(key in verified_keys for key in keys_by_symbol[sym])`. Test: symbol with 2 rows, only 1 verified → NOT SUCCESS (FAILED or pending), and it
   is re-fetched on resume. Mutation: revert to ANY → FAILS.
3. Post-append verification must not splice values into SQL (:478-485). Use a DataFrame join: create a DataFrame of the batch keys and
   inner-join/semi-join to bronze_corporate_actions on (symbol, ex_date, source), then collect the verified keys. Test (fake Spark or the function
   with an injectable key-lookup) that a symbol containing a quote is handled without error and verified correctly.
Acceptance: python3 -m pytest -q tests/bronze tests/silver tests/test_security.py all pass; pyspark hidden
(PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps). .agents/mimo/VERDICT-corporate-actions-round10.md with
counts + mutation outputs. Commit everything.
