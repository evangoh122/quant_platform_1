# BUILD-xbrl-B1a round 10 (checker CHANGES_REQUESTED on r9 — Codex luna, DeepSeek out of balance)

You are MiMo. Branch `feat/xbrl-fundamentals` (stay on it). Read `.agents/deepseek-fallback/VERDICT-xbrl-B1a-r9.md`. LF endings, never touch
`.agents/dispatch.sh`, no Databricks, NO NETWORK in tests. Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you
change. COMMIT; verdict `.agents/mimo/VERDICT-xbrl-B1a-r10.md`.
1. pipelines/ingest_sec_companyfacts.py:807 — the ALTER path must derive missing columns AND types from the manifest/bronze StructType (no hard-coded
   `http_status INT`). Test: a fake existing table missing two StructType fields → one ALTER adding exactly those two with their StructType types.
2. pipelines/ingest_sec_companyfacts.py:176-219 — delete the unused hand-written BRONZE_FACT_COLUMNS / MANIFEST_COLUMNS (or derive them from the
   StructType if anything still imports them). grep must show no other hand-written column list.
3. `test_fallback_when_volumes_not_writable` reaches the network (DNS to SEC). Make it hermetic: fake HTTP / monkeypatch the fetch. Add a conftest guard
   that fails any test in tests/bronze that opens a socket (e.g. monkeypatch socket.socket.connect to raise) so this cannot regress.
