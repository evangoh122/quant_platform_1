# VERDICT: nl1-contracts — MiMo
**Status:** APPROVED
**Round:** 7

## Blocking findings
None — all three blocking issues from round 6 are resolved.

## Changes made

### 1. `LLMEntityMention.text` allowlist (`contracts.py:320-345`)
- Replaced blacklist with allowlist pattern `^[A-Za-z0-9][A-Za-z0-9 .&'\-/_]{0,24}$`
- Added NFKC normalization before pattern check
- Pattern emitted in JSON schema via `Field(pattern=...)`
- Max length reduced from 100 to 25 (longest real alias is 22 chars: `consumer_discretionary`)
- Added `_` to character class for sector names (justified: `consumer_discretionary`, `communication_services`, `real_estate`)
- Defense-in-depth retained: control chars, SQL metacharacters (`;'"`, `--`, `/*`, `*/`), SQL keywords (`SELECT`, `DROP`, `UNION`, etc.), prompt injection patterns

### 2. `resolve_relative_date` timezone fix (`aliases.py:230-240`)
- Changed `current_date = c.now().date()` to `current_date = now.astimezone(tz).date()` where `tz = ZoneInfo("America/New_York")`
- Added validation: naive clocks (no tzinfo) are now rejected with `ValueError`
- All injected-clock tests pass: UTC clocks at DST boundaries (2026-03-08, 2026-11-01) and year boundary (2025-12-31)

### 3. Schema walking audit + hostile corpus (`test_contracts.py:730-1085`)
- `TestSchemaWalkingAudit`: enumerates every string leaf of `LLMIntentOutput` schema, asserts each is enum, const, or has allowlist pattern
- `TestHostileCorpus`: 89 hostile payloads (SQL, shell, template, JNDI, URL, control/zero-width/bidi, homoglyph, multilingual injection) — all rejected by `LLMEntityMention.text` and `LLMIntentOutput`
- `TestMutationProofs`: verifies loosening `text` back to free string fails hostile corpus; adding new free `str` field fails schema audit
- `TestTimezoneHandling`: UTC-clock tests at DST start (2026-03-08), DST end (2026-11-01), year boundary (2025-12-31), and naive clock rejection

### 4. `semantic_model_version` pattern (`contracts.py:289, 371`)
- Added `pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$"` to both `CanonicalIntent` and `LLMIntentOutput`
- Schema walking audit now passes — no unconstrained string leaves

### 5. Schemas regenerated
- `python3 -m analytics_nl.export_schemas --write` → all 6 schemas updated
- `python3 -m analytics_nl.export_schemas --check` → "All schemas match"

## Non-blocking notes
- `consumer_discretionary` (22 chars) is the longest real alias; pattern max 25 chars gives 3-char buffer
- SQL keyword regex catches `SELECT`, `DROP`, `UNION`, `INSERT`, `UPDATE`, `DELETE`, `ALTER`, `CREATE`, `EXEC`, `TRUNCATE`, `GRANT`, `REVOKE` as standalone words (case-insensitive)
- Prompt injection regex expanded to catch `disregard all/previous`, `system:`, `override safety/all`, `bypass safety/all/filters`, `ignore all/safety/constraints`, `forget all/safety/constraints`
- Hostile corpus includes 89 payloads (exceeds ≥ 60 requirement)

## Checks run
- `python3 -m pytest -q tests/analytics_nl` → 268 passed
- `python3 -m pytest -q --ignore=tests/lakebase` → 806 passed, 67 skipped
- `python3 -m analytics_nl.export_schemas --check` → "All schemas match"
- Spot-checked: all 33 real aliases from `aliases_v1.yaml` accepted; all verdict payloads rejected