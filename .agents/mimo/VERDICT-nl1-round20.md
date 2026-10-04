# VERDICT: nl1 round 20 — MiMo
**Status:** APPROVED
**Round:** 20

## Blocking findings
(none)

## Non-blocking notes
- Removed `description` keys from `policy_bounds_v1.yaml` (gold/silver hard_bounds) — these were undocumented extra keys that would now be rejected by strict key-set validation.
- Policy ordering validation now raises immediately on cheap > normal violations instead of deferring to the end.

## Checks run
- `python3 -m pytest tests/analytics_nl -q` → 437 passed (420 existing + 17 new)
- `python3 -m analytics_nl.export_schemas --check` → All schemas match
- Old-code mutation test: 13 of 17 new tests FAILED on git HEAD~ code (verified unknown keys, malformed mappings, version mismatches, grouping allow-list, TypeError suppression all fail-open on old code)
- New tests that passed on old code (4): missing-key tests that old validation loop already caught before construction defaults took effect

## Changes made

### analytics_nl/policy.py
- Added `_ALLOWED_*_KEYS` frozensets for exact key-set validation at every nesting level (top, hard_bounds, gold, silver, soft_thresholds, cheap, normal)
- Added unknown-key rejection before any field access
- Added `isinstance(layer_raw, dict)` check before `.get()` — malformed nested mappings now raise `PolicyValidationError`, not `AttributeError`
- Removed all default substitution (`.get("key", default)`) in construction section — uses direct `dict["key"]` access after validation guarantees keys exist
- Raises `PolicyValidationError` immediately on any validation error before construction

### analytics_nl/registry.py
- Added `semantic_registry_version` and `policy_version` validation alongside `semantic_model_version` at :160-170
- Added `_VALID_GROUPING_TOKENS` from `Grouping` enum — grouping values now checked against fixed allow-list at :245-248
- Changed `except TypeError: pass` to `except TypeError: errors.append(...)` at :305-320 — wrong-type defaults (e.g. `"oops"` for integer bound) now produce `RegistryValidationError`

### analytics_nl/data/policy_bounds_v1.yaml
- Removed `description` keys from `hard_bounds.gold` and `hard_bounds.silver` (would be rejected by strict key-set validation)

### tests/analytics_nl/test_policy.py
- Added `TestFailClosedKeySets` class (12 tests): unknown nested keys, malformed nested mappings, missing keys, unknown top-level keys

### tests/analytics_nl/test_registry.py
- Added 5 tests: `semantic_registry_version` mismatch, `policy_version` mismatch, unknown grouping token, TypeError not suppressed (min and max)