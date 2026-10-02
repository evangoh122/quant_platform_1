# BUILD-REQUEST: bronze-fed — ROUND 3 (bond-market calendar)

**Branch:** `slice/bronze-fed` · **Builder:** MiMo · **Checkers:** Claude, then DeepSeek
Read `.agents/deepseek/VERDICT-bronze-fed-check.md`. Everything else in round 2 is verified live
and correct — change only the business-day calendar.

## Defect (found by DeepSeek, verified against FRED)
`_next_ny_business_day` uses `pandas.tseries.holiday.USFederalHolidayCalendar`. Treasury/H.15
`market_rate` series follow the **bond market (SIFMA)** calendar:
- **Good Friday**: bond market closed, no H.15 publication (FRED `DGS10` has no 2024-03-29 or
  2025-04-18 observation) — but it is not a federal holiday, so a Thursday observation is marked
  available on Good Friday: **one business day early (look-ahead)**.
- **Columbus Day, Veterans Day**: federal holidays, but the bond market is open — availability
  is one day **late** (conservative, still wrong).

## Fix
Implement a SIFMA-style calendar for `market_rate` availability: federal holidays **plus Good
Friday**, **minus Columbus Day and Veterans Day**. Compute Good Friday from Easter
(`dateutil.easter` or the anonymous Gregorian algorithm). Keep it a pure function.
Do not use this calendar for anything else in the repo.

## Tests (must call production functions)
- `2024-03-28` (Thu before Good Friday) → available `2024-04-01` 16:30 NY.
- `2025-04-17` → `2025-04-21`.
- Columbus Day 2024 (`2024-10-14`) is a business day: `2024-10-11` (Fri) → `2024-10-14` 16:30 NY.
- Existing weekend / July 4 / DST tests still pass.
- Prove the Good Friday test fails against the old federal calendar (scratch copy in /tmp only).

**Do not run `--write` or truncate anything** — the coordinator will rebuild the table.
Edit only `notebooks/refresh_bronze_fed.py` and `tests/bronze/test_refresh_bronze_fed.py`.
LF line endings. **Commit your work.** Write `.agents/mimo/VERDICT-bronze-fed-round3.md`.
