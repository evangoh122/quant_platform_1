# BUILD: rag-databricks round 7 (MiMo)

Round 6 is close. Claude found one blocking defect with a live check.

## Blocking: corpus `accepted_ts` is off by the client's local UTC offset
`_load_corpus` assumes a naive `row["accepted_ts"]` is UTC. It isn't. Through Databricks
Connect, Spark returns TIMESTAMPs as naive datetimes in the **client machine's local
timezone**, even though the session timezone is `Etc/UTC`. Live evidence (WSL client, UTC+8):

    session tz Etc/UTC
    accepted_ts -> datetime(2024, 12, 21, 6, 26, 46)   unix_timestamp(accepted_ts) = 1734733606
    naive-treated-as-UTC epoch = 1734762406            (+28800 s = 8 h wrong)

So every filing's time shifts by the host's UTC offset, and the size and direction of the
shift depend on where the code runs (WSL, Render, Databricks App).

Fix: do not rely on Python's conversion of TIMESTAMP values.
- In `_load_corpus` (and any other Spark read that feeds the PIT filter, e.g.
  `pipelines/build_sec_embeddings.py` if it stores `accepted_ts`), select
  `unix_timestamp(accepted_ts) AS accepted_epoch` (or `CAST(accepted_ts AS LONG)`).
- Build the stored timestamp from it: `datetime.fromtimestamp(epoch, tz=timezone.utc)`.
- Keep the ISO-UTC string format downstream.
- Keep the round-6 epoch comparison in the fallback (that one is correct, done in Spark).

## Tests
- A unit test where the mocked Spark row provides `accepted_epoch`, and the stored
  `accepted_ts` equals the correct UTC instant. It must not depend on `TZ`. Run it under
  `TZ=Asia/Singapore` and `TZ=America/New_York` (use monkeypatch + `time.tzset()`, or
  subprocess) and show it passes in both.
- Show that the old code (naive → UTC) fails that test under `TZ=Asia/Singapore`.

## Rules
LF line endings only. Don't touch `.agents/dispatch.sh`. `python3 -m pytest tests/rag -q`
must pass. Commit. Write `.agents/mimo/VERDICT-rag-databricks-round7.md`.
