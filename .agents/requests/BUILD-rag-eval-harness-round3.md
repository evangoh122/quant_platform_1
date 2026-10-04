# BUILD: RAG eval harness round 3 (MiMo)

Claude ran the harness live-offline on the real exported corpus (10,720 chunks, real bge-small
sidecar, golden v1). It runs end to end: `PIT Leakage: 0 PASS`, recall@5 0.0625. **The PIT gate is
vacuous.**

1. **[Blocking] Timestamps never load.** `evals/rag_eval/corpus.py:~83,~491` read
   `obj.get("accepted_ts", "")`, but the exported corpus (and the golden spec) uses
   `accepted_epoch` (int seconds, UTC). Every record therefore has `accepted_ts == ""`.
   - Parse `accepted_epoch` → ISO UTC. Keep `accepted_ts` as a fallback if present.
   - If BOTH are missing, raise at load time with a count. Never silently empty.
2. **[Blocking] The leakage metric fails OPEN.** `evals/rag_eval/metrics.py:~170,~190` skip hits whose
   timestamp doesn't parse (`if _parse_ts(...) and ...`). A hit with a missing or unparseable
   timestamp must count as a PIT VIOLATION, or abort the run. It must never be skipped. Same for
   the trap scoring at `~185`.
3. Check that the retriever path the harness drives (via `retrieve_mode` / `HybridRetriever`) receives
   real `accepted_ts` in doc metadata. The production `_pit_filter` must actually exclude future
   chunks in eval runs.
4. **Tests, each failing on the current HEAD (prove it in /tmp):**
   - A JSONL record with only `accepted_epoch` loads with the correct ISO time.
   - A record with neither field → load error.
   - A retrieved hit with a missing timestamp → leakage counted / the run fails.
   - **End-to-end on the fixture:** an item whose `as_of` precedes some fixture chunk's `accepted_epoch`.
     The harness must never return that chunk, and leakage must be 0 for the RIGHT reason. A
     mutation that disables the production PIT filter must make the leakage gate FAIL.
5. Make the embeddings sidecar easy to build. Add `python -m evals.rag_eval.build_sidecar --npy ...
   --ids ... --corpus ... --out ...`, which writes the `.npz` with the manifest the loader expects,
   corpus hash included. Claude built one by hand. Document it in `evals/rag_eval/README.md`.

Run:
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`, with 0 failures;
- the same suite with pyspark and databricks.connect hidden.

LF line endings only. Don't touch `.agents/dispatch.sh`. Leave no scratch files. Commit with a
descriptive message. Write `.agents/mimo/VERDICT-rag-eval-harness-round3.md`.
