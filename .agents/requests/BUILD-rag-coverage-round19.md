# BUILD-rag-coverage round 19 — IMPLEMENT NOW (multi-CIK tickers + foreign filers; small)

You are MiMo. Stay on branch `slice/rag-coverage`. Commit per item, LF endings, never touch `.agents/dispatch.sh`, never weaken tests,
capture the red phase, paste mutation FAILED output into the verdict. Do NOT touch the live ingest that is running from this worktree's
current code — only edit files; Claude restarts runs.
Live finding (Claude, 2026-10-05): SEC company_tickers.json maps XOM → CIK 2115436 ("ExxonMobil Holdings Corp", new holding company, 1 filing),
while Exxon's 10-K/10-Q history is under CIK 34088. Discovery found 1 of 8 filings. Also ~20 universe tickers are foreign private issuers
(TSM, ASML, ARM, SAP, NVO, SHEL, BABA, AZN, PDD, NU, SE, STM, NOK, SPOT, NBIS…) that file 20-F / 6-K, not 10-K / 10-Q.
1. CIK overrides: `config/sec_cik_overrides.yaml` mapping a ticker to one or more CIKs (e.g. `XOM: ["0002115436", "0000034088"]`). Discovery
   unions filings from every CIK (dedupe by accession); stored `cik` is the filer CIK from the accession/submission. Tests with fixtures:
   XOM → 8 filings across two CIKs; duplicate accession across CIKs stored once. Mutation: ignore overrides → FAIL.
2. Foreign filers: when `--forms` includes 20-F / 40-F / 6-K, they are discovered and chunked like 10-K/10-Q (20-F section mapping: Item 3.D
   risk factors, Item 5 operating review; fall back to generic chunking when items are not detected). Do not change the default forms.
   Tests with a 20-F fixture. Document in the runbook: run `--forms 20-F,6-K --tickers <foreign list>` as a separate pass.
3. Runbook: add the override file + the foreign-filer pass.
Run: python3 -m pytest tests/rag tests/bronze -q --timeout 30. Verdict: .agents/mimo/VERDICT-rag-coverage-round19.md.
