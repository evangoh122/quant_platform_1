# BUILD-rag-coverage round 19b — IMPLEMENT NOW (small; live finding)

You are MiMo. Stay on branch `slice/rag-coverage`. Commit per item, LF endings, never touch `.agents/dispatch.sh`, red phase + mutation proof.
Live (Claude, WSL): `--dry-run --tickers XOM --forms 10-K,10-Q` now raises
`AccessionOwnershipConflict: 0000034088-26-000093 already owned by CIK 0002115436 (ticker=XOM), but current request is CIK 0000034088 (ticker=XOM)`
(pipelines/sec_rag_ingest.py:~1535) — the earlier run stored that accession under the holding-company CIK.
1. Ownership: CIKs listed together in `config/sec_cik_overrides.yaml` for a ticker are ONE ownership group — no conflict between them. A genuine
   conflict (accession owned by an unrelated CIK/ticker) must be recorded per filing (failed audit row, run continues), never abort the whole run
   (dry-run included). Tests: XOM accession stored under 2115436, request from 34088 → no conflict; unrelated CIK → that filing fails, others succeed.
   Mutations: drop the group check → FAIL; re-raise instead of recording → FAIL.
2. Canonical stored CIK: for an override group, store the filer CIK actually present in the accession (prefix of the accession number) and add an
   idempotent fix-up the runbook can run (`--repair-cik-ownership --tickers XOM`) that rewrites existing rows for the group to that rule. Test.
Run: python3 -m pytest tests/rag tests/bronze -q --timeout 30. Claude re-runs the XOM dry run. Verdict: .agents/mimo/VERDICT-rag-coverage-round19b.md.
