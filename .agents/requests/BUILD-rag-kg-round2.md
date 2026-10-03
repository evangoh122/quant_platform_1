# BUILD: SEC knowledge graph round 2 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit after each fix. NEVER delete or weaken
> existing tests.

DeepSeek (`.agents/deepseek/VERDICT-rag-kg.md`, read it fully) found 2 blocking defects:

1. **Instant-period facts dropped** (`sec_kg/build.py:~364-372`). `str(None)` gives "None", then
   `iso_date` raises and the row is rejected. 11,579 of 43,722 xbrl_facts (Assets, Liabilities, …)
   are lost.
   - Treat a null `period_start` as an INSTANT fact: `period_type="instant"` with `period_end` as the
     instant date.
   - Keep the `period_type` in the node/ID, so instant and duration facts with the same metric never
     collide.
   - Never `str()` a None. Count every rejected row by reason, and FAIL the build if any row is
     rejected for a reason other than an explicit, documented skip.
   - Test: instant facts (`period_start: null`) build. On the real export, the XbrlFact count equals
     the number of valid xbrl_fact rows (expect about 43,722, net of genuine duplicates; explain any
     gap).
2. **Fact citations are dead references** (`sec_kg/build.py:~106-107`). 0 of 43,722 fact
   `source_chunk_id`s exist in `sec_corpus.jsonl`. The corpus chunks only 128 of 1,026 accessions.
   - Verify every `source_chunk_id` against the chunk corpus or chunk table.
   - Only create a `SOURCED_FROM` edge to a Chunk that EXISTS.
   - Otherwise cite at FILING level: `citation_level: "filing"` with accession, form, accepted_ts
     and `source_url` (the EDGAR filing URL; build it from cik + accession if needed).
   - Mark `citation_level: "chunk"` only when the chunk resolves. Never emit a dead chunk id as a
     citation, and keep the provenance flags consistent between the fact and the chunk nodes.
   - `query_sec_facts` returns `citation_level` + accession + `source_url` (+ `chunk_id` only when
     real).
   - Tests:
     - an unresolvable chunk id → filing-level citation, no Chunk edge;
     - a resolvable one → chunk-level;
     - on the real export, report the counts per `citation_level`.

Re-run the offline build on the real export and report the node/edge counts by type, plus
citation_level counts. Run `python3 -m pytest -q -p no:cacheprovider tests/rag`, and the full suite
with `--ignore=tests/lakebase`. LF line endings only. Don't touch `.agents/dispatch.sh`. Leave no
scratch files. Write `.agents/mimo/VERDICT-rag-kg-round2.md`.
