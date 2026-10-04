# BUILD: RAG eval harness round 5 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests.

DeepSeek (`.agents/deepseek/VERDICT-rag-eval-harness.md`, read it fully) disabled the production
`_pit_filter` and ran the fixture: the exit code was 1 (correct), BUT the saved report shows
`pit_leakage_total: 0` and "**Total leakage: 0** PASS", with no errors section. The audit report lies.

Causes:
- `evals/rag_eval/retrieve.py:~169` sets `ir.leakage_count = -1`, discarding the real count, and
  the CLI sums only `> 0` (`cli.py:~231`);
- the report is written before the gate is evaluated (`cli.py:~277` vs `~314-321`).

Fix:
1. Keep the REAL leaked-chunk count per item: count all returned chunks with `accepted > as_of`
   before raising. Store it, and never use a sentinel.
2. Compute the gate FIRST: PASS / FAIL / INCOMPLETE from the leakage total, the errors and the
   counts. Then write the report with that status, the per-config leakage, the leaked chunk ids
   (truncated) and an Errors section. The exit code matches the report status.
3. Remove the dead code path, and make sure no code path can render "PASS" with leakage > 0 or with
   errors.
4. Test: with a mutation that disables `_pit_filter` (monkeypatch it to identity), run the fixture
   end-to-end in-process. Assert the report JSON `pit_leakage_total` > 0, status FAIL, the Markdown
   contains "FAIL" and not "PASS", and the exit code is non-zero. This test must FAIL on the current
   HEAD.

Run:
- `python3 -m pytest -q -p no:cacheprovider tests/rag`;
- the full suite with `--ignore=tests/lakebase`;
- both with pyspark hidden.

LF line endings only. Don't touch `.agents/dispatch.sh`. Write
`.agents/mimo/VERDICT-rag-eval-harness-round5.md`.
