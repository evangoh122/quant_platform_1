# VERDICT: rag-eval-harness-round12 — DeepSeek (checker)
===VERDICT START===
Status: CHANGES_REQUESTED
Round: 12

Checker: DeepSeek. Scope: commit a097865 (range 1c29a3b..HEAD, 1 commit). Read-only for source;
mutation proofs run in /tmp copies (/tmp/mut12). Python 3.12.3, pytest 9.1.1, HF_HUB_OFFLINE=1,
network guard active.

## Blocking findings

- [api/services/verifier.py:23-32] Lazy singleton init is not thread-safe (no lock). `_ensure_model()`
  sets `self._model_initialised = True` (line 26) *before* the slow `CrossEncoder(self.model_name)`
  construction completes (line 29). A second thread that calls `verify_entailment` concurrently sees
  `_model_initialised == True`, returns early, then hits `if not self.model:` (line 55) while `self.model`
  is still `None` → returns a spurious `"SKIPPED"` verdict for a claim the model is about to serve.
  Concrete reproduction (two threads racing on a slow model load):
  ```
  results: ['SKIPPED', 'PASS']
  ```
  This is exactly the "first concurrent request gets a wrong verification result" failure the check
  request item 3 asks about. There is a second, simpler race: two threads can both pass the
  `if self._model_initialised: return` check (both read False) before either writes True, causing
  double model construction. The shared singleton `verifier` is exercised by `verification_node`
  (api/services/langgraph_engine.py:506) via the sync FastAPI `chat` endpoint (api/routes/agent_chat.py:112),
  which runs in uvicorn's threadpool → concurrent first-calls are realistic. The rest of the codebase
  already follows the correct pattern (double-checked locking: `LocalSTEmbeddings._get_model`
  api/services/embeddings.py:48-51 and `get_embeddings` api/services/embeddings.py:168-170); `_ensure_model`
  should do the same (a `threading.Lock` + check inside the lock).

## Non-blocking notes

- The "no HF load" guard is delivered as a standalone test `test_fake_embedding_provider_active`
  (tests/rag/test_embedding_config.py:63) rather than as assertions *inside* the dense/hybrid harness
  tests as the build request literally asked. It still protects the offline regression: reverting the fake
  to `None` fails that guard (1 failed), and the dense/hybrid harness tests themselves do not load a model
  (they consume the offline npz embeddings). Deviation from the letter of the request, not a correctness gap.

## Item verification

### 1. Bootstrap zero-gold filter alignment — DONE
- `aggregate_results` builds `answerable_scored = [ir for ir in answerable if _has_gold(ir)]`
  (metrics.py:338) and reuses it for overall (`_avg_metrics`), bootstrap, per-type bootstrap and
  per-ticker bootstrap (metrics.py:360-392). ONE shared filter.
- Probe: one perfect row + one zero-gold row →
  `overall recall@5 = 1.0`, `bootstrap recall@5 mean = 1.0`, `n = 1`, `zero_gold_excluded = 1`. PASS.
- Mutation (bootstrap over all `answerable` rows again) → both `TestBootstrapExcludesZeroGold` tests FAIL:
  `Bootstrap mean 0.5 != 1.0 — bootstrap likely included zero-gold rows` (2 failed).

### 2. No Hugging Face model load — DONE
- Verifier singleton is lazy: `Verifier.__init__` constructs no model; `_ensure_model()` is deferred to
  first `verify_entailment` (api/services/verifier.py:52). No `CrossEncoder` at import.
- `_FakeCrossEncoder` (tests/rag/conftest.py:241) records instances, returns deterministic numpy arrays.
  `_no_cross_encoder_load` autouse fixture patches `sentence_transformers.CrossEncoder` and reloads the
  verifier module.
- Mutation 2a (eager `verifier._ensure_model()` at import) → guard `test_no_cross_encoder_constructed`
  FAILS (`Real CrossEncoder model loaded: <class 'tests.rag.conftest._FakeCrossEncoder'>`); 1 failed,
  and the eager path actually began a weight load (13.61s vs 3.68s). Guard works.
- Mutation 2b (`emb_mod._embeddings = None`) → `test_fake_embedding_provider_active` FAILS
  (`embeddings._embeddings is None — the conftest fake was not installed`); 1 failed.
- Timing `HF_HUB_OFFLINE=1 python3 -m pytest tests/rag -q --durations=5` → 439 passed, 19 skipped, 3.68s.
  Slowest 5: 0.13s / 0.10s / 0.09s / 0.09s / 0.07s (no model load).

### 3. Lazy verifier production behaviour — NOT THREAD-SAFE (see blocking finding)
- First-call latency: model load moved from import-time to first `verify_entailment` (intended).
- Thread safety: FAILS — no lock, flag-before-load race, double-load race. Demonstrated.

### 4. No tests deleted/weakened — DONE
- `git diff 1c29a3b..HEAD -- tests` touches only conftest.py (+47/-0), test_embedding_config.py (+15/-1),
  test_rag_eval_metrics.py (+66/-0), test_verifier.py (+66/-8). Removed lines in test_verifier.py are the
  old import and the old no-model branch, replaced by richer explicit fake-based tests
  (entailment/contradiction/SKIPPED + guard). No assertion weakened.
- pyspark hidden run: `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps
  HF_HUB_OFFLINE=1 python3 -m pytest tests/rag -q` → 439 passed, 19 skipped, 3.50s. PASS.

## Checks run
- `HF_HUB_OFFLINE=1 python3 -m pytest tests/rag -q --durations=5` → 439 passed, 19 skipped, 3.68s.
- pyspark hidden PYTHONPATH run → 439 passed, 19 skipped, 3.50s.
- Probe 1 (perfect + zero-gold) → overall 1.0 / bootstrap mean 1.0 / n 1 / excluded 1.
- Mutation 1 (bootstrap over all answerable) → 2 failed.
- Mutation 2a (eager CrossEncoder at import) → guard failed (1 failed).
- Mutation 2b (fake embedding → None) → guard failed (1 failed).
- Thread-race probe (2 concurrent verify_entailment on fresh Verifier) → `['SKIPPED', 'PASS']`.
- `git diff 1c29a3b..HEAD --numstat -- tests/` → only additions/rewrite of verifier tests.
- `git status` clean (no source modified; /tmp/mut12 copies only).
===VERDICT END===
