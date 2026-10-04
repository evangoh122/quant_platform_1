# BUILD nl1 round 20 (builder: MiMo) — finish fail-closed validation

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/nl-contracts. Descriptive commits. NEVER delete or weaken tests.
Codex review: .agents/codex/VERDICT-nl1-review5.md (2 Medium). Each fix needs a test that FAILS on the old code (prove with a `git archive` copy).
1. analytics_nl/policy.py:88-159: EXACT key sets at every level (unknown nested keys such as hard_bounds.gold.rogue_bound → PolicyValidationError);
   malformed nested mappings → PolicyValidationError (never AttributeError — validate type before any .get); remove every default substitution
   (:119-125, :150-158): missing → PolicyValidationError. Tests per case.
2. analytics_nl/registry.py: validate semantic_registry_version AND policy_version (not only semantic_model_version) at :160-163; grouping tokens must
   come from a fixed allow-list (:236-238); never suppress TypeError (:294-309) — a default of the wrong type (e.g. "oops" for an integer bound) →
   RegistryValidationError. Tests: each mutated production registry from Codex's probes raises.
Acceptance: python3 -m pytest tests/analytics_nl -q all pass; python3 -m analytics_nl.export_schemas --check. .agents/mimo/VERDICT-nl1-round20.md. Commit.
