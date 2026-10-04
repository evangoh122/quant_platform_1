# BUILD rag-coverage round 9 (builder: MiMo) — concurrency + backoff before the unattended rollout

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-coverage. Commit after each item, descriptive messages.
NEVER delete or weaken tests. Reviewer verdict: .agents/reviewer/VERDICT-rag-coverage-r1.md (N1 P1, N2–N5 P2; 9/10 Codex findings verified).
Each fix needs a test that FAILS on the old code — prove it in a copy made with `git archive HEAD | tar -x -C /tmp/<dir>` and paste the output.

N1 (P1). pipelines/sec_rag_ingest.py ~1553: the bronze MERGE uses the fixed temp view `_merge_src` on one shared Spark session with no lock, under
  --max-workers 4. Use a unique view name per call (uuid), drop it after, and serialise MERGE + the inserted-row metrics read on the target with a
  process-wide lock (one writer at a time into the same Delta table). The inserted count must come from that MERGE's own metrics, read inside the lock.
  Test: two threads writing different accessions concurrently → distinct view names, both batches' rows written, each reports its own inserted count.
  Mutation: fixed view name / no lock → FAILS.
N2 (P2). A failed history-file fetch is only a warning → partial coverage reported as success. Record the ticker as failed (or partial with reason) in
  sec_ingest_log and surface it in the run summary. Test.
N3 (P2). On 429/503 add a GLOBAL cool-down in the shared limiter (all workers pause until the Retry-After deadline), and cap Retry-After (e.g. 120 s;
  above the cap → treat as a hard failure for that request and record it). Tests: one worker's 429 pauses the others; Retry-After 2.3e9 → capped/failure.
N4 (P2). pipelines/build_sec_embeddings.py reports the candidate count when 0 rows were inserted — report the MERGE metric even when it is 0. Test.
N5 (P2). resources/jobs.yml: make sure the job tasks can import repo modules (sys.path / python_file location consistent with other jobs) and the
  embeddings job environment declares loguru and python-dotenv (and everything imported). Add a test that imports each job's entrypoint module with only
  the declared dependencies' module names available (or at least that every top-level import of the entrypoint is listed in the job environment).
  Claude will do the live one-ticker run.
Acceptance: python3 -m pytest tests/rag tests/bronze -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-coverage-round9.md. Commit everything.
