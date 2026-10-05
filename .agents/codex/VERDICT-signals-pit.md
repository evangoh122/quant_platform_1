# Codex gpt-5.6-sol review — signals PIT (saved by Claude from scratchpad/codex-review-signals.log)

===VERDICT START===
# VERDICT: signals-pit — Codex reviewer

Status: CHANGES_REQUESTED

- Blocking — `scripts/publish_baseline_signals.py:56`: the scoring refit uses all labeled rows. A symbol scored at an earlier timestamp can therefore use another symbol’s labels observed later, violating point-in-time safety and contradicting the docstring at lines 16–18.
- Required: restrict refit labels to a cutoff no later than every scored row, or train separately by scoring timestamp. Add a staggered-symbol-timestamp regression test.
- Tests: 50 passed.
- Mutation proofs: all three mutations failed as required (5, 1, and 1 failures).
- The Databricks script was not run. No repository files were edited.

===VERDICT END===
