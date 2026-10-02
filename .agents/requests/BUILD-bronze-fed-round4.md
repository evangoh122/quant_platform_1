# BUILD-REQUEST: bronze-fed — ROUND 4 (H.15 publication calendar)

**Builder:** MiMo · **Checkers:** Claude, then DeepSeek
Read `.agents/deepseek/VERDICT-bronze-fed-check2.md`.

## The round-3 spec was wrong (the coordinator's error, now verified on FRED)
Round 3 told you to subtract Columbus Day and Veterans Day because the SIFMA bond market is open.
But `market_rate` series come from the Fed's **H.15** release, and the **Fed is closed** on those days.
FRED proves it — no observation on the holiday itself:

```
DGS10: 2024-10-11 4.08 | 2024-10-14 (blank, Columbus) | 2024-10-15 4.03
DGS10: 2024-11-08 4.30 | 2024-11-11 (blank, Veterans) | 2024-11-12 4.43
DGS10: 2024-03-28 4.20 | 2024-03-29 (blank, Good Friday) | 2024-04-01 4.33
```

So `2024-10-11` is available on **2024-10-15**, not 10-14 — round 3 created a one-day look-ahead.

## Fix
The publication calendar for `market_rate` = **US federal holidays + Good Friday**. Remove the
Columbus/Veterans subtraction (`notebooks/refresh_bronze_fed.py:107-117`). Rename the calendar to say
what it is (e.g. `"h15"`), not `"bond_market"`/SIFMA.

## Tests — fix the ones that encode the wrong behaviour
`tests/bronze/test_refresh_bronze_fed.py:145-147,152-153,163-165,209-213` assert Columbus Day is a
business day. Replace them:
- `2024-10-11` → available `2024-10-15 16:30 NY`; `2024-11-08` → `2024-11-12 16:30 NY`.
- Good Friday cases unchanged (`2024-03-28` → `2024-04-01`).
- Add a test that derives expected gaps from FRED-shaped fixture data: for every date in a fixture
  where the series is blank, the previous observation must not be available on that date.
- Prove the Columbus test FAILS against round-3 code (scratch copy under /tmp only).

**Do not run `--write` or truncate.** The coordinator rebuilds the table.
Edit only `notebooks/refresh_bronze_fed.py` and `tests/bronze/test_refresh_bronze_fed.py`. LF endings.
**Commit your work.** Write `.agents/mimo/VERDICT-bronze-fed-round4.md`.
