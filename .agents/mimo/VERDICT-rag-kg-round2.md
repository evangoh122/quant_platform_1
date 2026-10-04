===VERDICT START===
# VERDICT: rag-kg-round2 — MiMo
**Status:** APPROVED
**Round:** 2

Both blocking defects from round 1 are fixed. Instant-period XBRL facts now
build correctly (11,579 recovered), and all fact citations resolve to real
chunks or fall back to filing-level with `source_url`. No dead chunk
references remain.

## Fixes applied

### Defect 1: Instant-period facts (`sec_kg/build.py:364-372`)
- `period_start_val = row.get("period_start")` — check None before str()
- `str(period_start_val) if period_start_val is not None else ""` — never
  produces `"None"`
- Same fix applied to `period_end_val` and to the second occurrence in the
  version processing loop (~line 395)
- Added `period_type: "instant" | "duration"` to every XbrlFact property
- Added `missing_period_end` rejection reason (FAIL the build if period_end
  is null)
- Instant facts now produce `period_start=""` in the series key, so they
  never collide with duration facts sharing the same metric/end date

### Defect 2: Dead chunk references (`sec_kg/build.py:106-107`)
- `resolve_source_chunk_id` now takes `corpus_chunk_ids: set` and returns
  3-tuple `(chunk_id, synthetic_source, citation_level)`
- If entity has a `source_chunk_id` that exists in corpus → `"chunk"` level
- If entity has a `source_chunk_id` NOT in corpus → falls through to
  accession-based lookup (still `"chunk"` if corpus has chunks for that
  accession)
- Only if no corpus chunks exist for the accession → `"filing"` level with
  `source_url` (EDGAR URL built from cik + accession)
- `SOURCED_FROM` edges are only created when `citation_level == "chunk"`
  (no dead references)
- Chunk nodes are only created when citation resolves to a real chunk
- Filing nodes are created on-demand for filing-level citations with
  `source_url` property
- `citation_level` and `source_url` added to XbrlFact, RiskFactor, Event
  properties
- `get_fact()` and `facts_timeseries()` return `citation_level`, `source_url`,
  and `period_type` in their response dicts

## Node/edge counts (real export)

| Type | Count |
|------|-------|
| XbrlFact | 43,722 (was 32,143 — recovered 11,579 instant facts) |
| instant period_type | 11,579 |
| duration period_type | 32,143 |
| Chunk | 10,720 |
| Filing | 2,754 |
| Company | 16 |
| Metric | 17 |
| Period | 2,624 |
| RiskFactor | 1,457 |
| Event | 1,741 |
| Section | 456 |
| **TOTAL nodes** | **63,507** |

| Edge type | Count |
|-----------|-------|
| REPORTED_FACT | 43,722 |
| INSTANCE_OF | 43,722 |
| FOR_PERIOD | 43,722 |
| SOURCED_FROM | 6,575 (was 35,341 — no dead refs) |
| SUPERSEDES | 965 |
| DISCLOSED_RISK | 1,457 |
| REPORTED_EVENT | 1,741 |
| **TOTAL edges** | **141,904** |

### Citation level counts (XbrlFacts)

| citation_level | Count |
|----------------|-------|
| chunk | 5,118 |
| filing | 38,604 |

All 6,575 SOURCED_FROM edges point to existing Chunk nodes.

## Tests

- 6 new tests added (TestInstantPeriodFacts: 3, TestCitationLevel: 3)
- Total rag suite: 370 passed, 19 skipped
- Full suite (ignoring lakebase): 649 passed, 67 skipped
- Build is byte-idempotent (SHA-256 identical across runs)
- LF line endings on all changed files

## Non-blocking notes

- `propose_xbrl_qa_candidates` correctly excludes filing-level facts
  (by design: "Only proposes … facts with real chunk provenance")
- The `rejected_row_count` in the manifest script is still approximate
  (non-blocking, same as round 1)
- No scratch files left, `.agents/dispatch.sh` untouched

## Checks run
- `python3 -m pytest -q -p no:cacheprovider tests/rag` → pass (370 passed, 19 skipped)
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → pass (649 passed, 67 skipped)
- `python3 scripts/build_sec_knowledge_graph.py --entities … --corpus … --output-dir /tmp/sec-kg-round2 --format jsonl` → pass (63,507 nodes / 141,904 edges)
- Second run byte-identical (SHA-256 match on nodes+edges)
- Instant-fact repro: `period_start: null` → XbrlFact node with `period_type: "instant"` → pass
- Citation level: unresolvable chunk + no accession chunks → `citation_level: "filing"`, no SOURCED_FROM edge → pass
- Citation level: resolvable chunk → `citation_level: "chunk"`, SOURCED_FROM edge present → pass
- No dead SOURCED_FROM references (all dst_id in node_ids) → pass
===VERDICT END===