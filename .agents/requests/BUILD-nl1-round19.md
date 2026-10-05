# BUILD nl1 round 19 (builder: MiMo)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/nl-contracts. Commit after each item, descriptive messages. NEVER delete or weaken tests.
Codex review: .agents/codex/VERDICT-nl1-review4.md (2 High, 3 Medium). RULE: never change production view semantics just to make a test pass; every
fix needs a test that FAILS on the old code — prove it in a copy made with `git archive HEAD | tar -x -C /tmp/<dir>` (edit the DOC/code there).

1 (High). analytics_nl/policy.py:267-271 evaluates coverage only when total_count > 0 — (0, 0) stats fail open (CHEAP/ACCEPTED_CHEAP). Zero-total or invalid
   stats → INSUFFICIENT_DATA; validate 0 <= sample_count <= total_count (invalid → reject with a clear code). Tests for IV trend/compare/rank/aggregate.
2 (High). Bronze fallback views (docs/NL1_PROPOSED_SERVING_VIEWS.md:114-115, :617-618) publish only the derived 16:30 timestamp though rows are selected
   by the later ingest_ts. Output availability = GREATEST(derived_timestamp, ingest_ts). DuckDB test on the extracted fallback views: a row dated Jan 2
   ingested Jan 5 → availability Jan 5. Mutation: drop ingest_ts from the GREATEST → FAILS.
3 (Medium). registry.py fail-closed: :180-223 reject unsupported metric/operation keys, unknown aggregation tokens, unknown required slots; :225-255 close
   output scalar types to a fixed set; :301-308 exact coverage (no extras) — also reject unused approved views, unknown parameter types, defaults outside
   bounds. Tests: each malformed registry variant raises RegistryValidationError.
4 (Medium). policy.py:88-110 loads bounds with .get(..., default) — missing/malformed limits must raise PolicyValidationError (types, positivity,
   ordering min<=max, policy version, exact key set). Tests per case.
5 (Medium). Removing `adj.information_available_ts` from the GREATEST at docs:172 survives — make the availability test require EVERY joined input that
   carries an availability column (not just window-derived ones) to contribute to the final GREATEST. Mutation: drop adj.information_available_ts → FAILS.
Acceptance: python3 -m pytest tests/analytics_nl -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps);
python3 -m analytics_nl.export_schemas --check. .agents/mimo/VERDICT-nl1-round19.md. Commit everything.
