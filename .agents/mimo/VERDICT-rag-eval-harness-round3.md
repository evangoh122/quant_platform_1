# VERDICT: rag-eval-harness-round3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings (all fixed)
- [corpus.py:83,491] `obj.get("accepted_ts", "")` ignored `accepted_epoch` → every record from exported corpus had empty timestamp, PIT filter vacuous → added `_resolve_accepted_ts()` parsing `accepted_epoch` → ISO UTC with fallback to `accepted_ts`, raises if neither present
- [metrics.py:170,190] `if _parse_ts(h.accepted_ts) and ...` silently skipped hits with missing timestamps → changed to `_parse_ts(...) is None or _parse_ts(...) > as_of` so missing/unparseable = PIT violation (fail-closed)
- [retrieve.py:111] `if not h.accepted_ts: continue` skipped empty timestamps → changed to count as leak (fail-closed)

## Non-blocking notes
- `build_sidecar.py` CLI added: `python -m evals.rag_eval.build_sidecar --npy ... --ids ... --corpus ... --out ...`
- Supports .npy/.f32 embeddings, .npy/.txt chunk IDs, corpus SHA validation
- README.md updated with build_sidecar documentation
- 4 existing tests updated to include required `accepted_ts` fields
- `_resolve_accepted_ts` uses `datetime.fromtimestamp(int(epoch), tz=timezone.utc)` — correct for POSIX seconds

## Checks run
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → 651 passed, 67 skipped, 0 failures
- `python3 -m pytest -q -p no:cacheprovider tests/rag/test_rag_eval_round3.py` → 12 passed
- `python3 -m pytest -q -p no:cacheprovider tests/rag/test_rag_eval_build_sidecar.py` → 4 passed
- `python3 -m evals.rag_eval.build_sidecar --help` → exits 0, shows usage
- `file evals/rag_eval/*.py tests/rag/test_rag_eval_round3.py` → all UTF-8 (LF)
- No secrets committed. No scratch files. No changes to `.agents/dispatch.sh`.