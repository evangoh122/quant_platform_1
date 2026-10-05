===VERDICT START===
Status: CHANGES_REQUESTED

Findings:

1. Medium — Policy bounds validation still does not enforce the requested exact key sets. `analytics_nl/policy.py:88-159` accepts unknown nested keys; adding `hard_bounds.gold.rogue_bound` loaded successfully. Additionally, malformed nested mappings are detected at `analytics_nl/policy.py:93-97` but subsequently dereferenced with `.get()` at `:115-125`, producing `AttributeError` rather than `PolicyValidationError`. Default substitution also remains at `:119-125` and `:150-158`.

2. Medium — Registry validation remains partially fail-open. `analytics_nl/registry.py:160-163` validates only `semantic_model_version`, allowing mismatched `semantic_registry_version` and `policy_version`. `:236-238` accepts arbitrary identifier-shaped grouping tokens, and `:294-309` suppresses `TypeError`, allowing a wrongly typed default such as `"oops"` against integer bounds. Each mutated production registry loaded successfully with zero validation errors.

Verification:

- `python3 -m pytest tests/analytics_nl -q` — 420 passed.
- `python3 -m analytics_nl.export_schemas --check` — All schemas match.
- Adjusted-source DOC mutation in an archived `/tmp` copy — 1 failed, 418 passed, 1 skipped; the intended availability assertion failed.
- Sparse-IV probes for trend/compare/rank/aggregate with 12/19,390, absent, and `(0,0)` statistics all returned `REJECT / INSUFFICIENT_DATA`; invalid-count regression tests also pass.
- Trailing-newline ticker, index, and sector identifiers were rejected.
- PIT/relative-performance and validator regression subset — 43 passed.
- Bronze fallback availability and adjusted-source availability fixes are present.
- Repository working tree remained unchanged.
===VERDICT END===
