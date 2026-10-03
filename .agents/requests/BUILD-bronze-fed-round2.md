# BUILD-REQUEST: bronze-fed — ROUND 2 (market-rate availability)

**Branch:** `slice/bronze-fed` · **Builder:** MiMo · **Validators:** Claude, then Codex

## Round 1 verified — keep it
`bronze_fed_series` exists with 12 series (7 `market_rate`, 5 `revised_macro`), current to
2026-09-30/10-02; zero duplicate `(series_id, observation_date, vintage_date)` keys; no row is
available on or before its observation date; `revised_macro` availability = `ingest_ts` for all
5,079 rows (correct). Lane-exclusive files only. Good.

## The defect
The coordinator amendment requires `market_rate` rows to be available at the **next New York
business day after `observation_date`, 16:30 America/New_York (DST-aware)** — so the rates are
usable for the 2022–2026 backtest.

`notebooks/refresh_bronze_fed.py:218` computes that time, then does
`info_ts = max(ny_ts, ingest_ts)`. For every historical row `ingest_ts` (today) wins.
Measured: **91,907 of 91,913 `market_rate` rows have `information_available_ts = ingest_ts`.**
That defeats the amendment entirely.

Also `:77-79` hardcodes EST (UTC−5) "for conservatism", so summer rows land at 17:30 NY instead
of 16:30. Not a leak, but not DST-aware as specified.

## Fix
1. For `market_rate`: `information_available_ts` = next NY business day after
   `observation_date` at 16:30 **America/New_York via `zoneinfo`** (DST-aware), converted to UTC.
   **Remove the `max(..., ingest_ts)`.** Weekend/holiday observations roll to the next business
   day. (US Federal holidays: use a fixed list or `pandas.tseries.holiday.USFederalHolidayCalendar`.)
2. Keep `revised_macro` exactly as is (`ingest_ts`).
3. Unit tests: a Wednesday observation → Thursday 16:30 NY; a Friday → Monday; a summer date →
   20:30 UTC and a winter date → 21:30 UTC; a holiday rolls forward.

## One-time rebuild — this table only
Bronze is append-only because the streaming pipeline reads `bronze_ohlcv`. `bronze_fed_series`
was **created today and has no readers**, so for this table only you may drop and rebuild it
once (or `TRUNCATE` then re-run `--write`). Do **not** apply this to any other bronze table.

## Verify (paste live output)
- `market_rate` availability distribution by NY weekday/time: all 16:30 NY on business days.
- Count with `information_available_ts = ingest_ts` among `market_rate` → expect ~0.
- No row available on or before its observation date; zero duplicate keys; row counts per
  series match round 1.

Edit only `notebooks/refresh_bronze_fed.py` and `tests/bronze/test_refresh_bronze_fed.py`.
**Commit your work.** Write `.agents/mimo/VERDICT-bronze-fed-round2.md`.
