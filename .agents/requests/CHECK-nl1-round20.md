# CHECK: NL1 round 20 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`. Write .agents/deepseek/VERDICT-nl1-round20.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED". Codex review: .agents/codex/VERDICT-nl1-review5.md. Request: BUILD-nl1-round20.md.
Rerun Codex's probes: policy — unknown nested key (hard_bounds.gold.rogue_bound) → PolicyValidationError; malformed nested mapping → PolicyValidationError
(not AttributeError); missing key → error (no defaults). Registry — mismatched semantic_registry_version / policy_version → error; unknown grouping token
→ error; default "oops" against integer bounds → RegistryValidationError (no suppressed TypeError). Mutations reverting each → a test FAILS.
Run python3 -m pytest tests/analytics_nl -q; python3 -m analytics_nl.export_schemas --check.
