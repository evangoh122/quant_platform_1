# VERDICT: vwap-compute — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
None.

## Non-blocking notes
- Session VWAP in gold uses trailing window (ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) — PIT-safe, no future leak.
- Daily VWAP from minute bars uses CONVERT_TIMEZONE('UTC','America/New_York',event_ts) for ET date — DST-correct.
- Symbols with no minute bars and no vendor vwap keep NULL vwap — never fabricated.
- vwap_source column tracks provenance: 'vendor' | 'minute_bars' | NULL.
- Idempotent ALTER TABLE ADD COLUMNS for vwap_source on existing tables.

## Checks run
```
python3 -m pytest tests/gold/test_gold_vwap_sql.py tests/silver/test_silver_vwap_sql.py -v --noconftest
```
→ 18 passed (8 gold + 10 silver)

```
python3 -m pytest tests/gold/ tests/silver/test_silver_vwap_sql.py tests/silver/test_silver_sql_semantics.py tests/silver/test_ohlcv_day_adjusted.py tests/analytics_nl/test_source_schema.py -q --noconftest
```
→ 151 passed

## Mutation tests (FAILED outputs)

### (a) Drop typical-price fallback
```
sed -i 's/COALESCE(vwap, (high + low + close) \/ 3.0)/vwap/g' gold/01_gold_ohlcv_features.sql
python3 -m pytest tests/gold/test_gold_vwap_sql.py::TestSessionVWAP -v --noconftest
```
→ 5 FAILED: bar1 session_vwap=None (COALESCE removed, all NULL vwap → NULL session_vwap)

### (b) Remove DATE(event_ts) from session partition
```
sed -i 's/PARTITION BY symbol, DATE(event_ts)/PARTITION BY symbol/g' gold/01_gold_ohlcv_features.sql
python3 -m pytest tests/gold/test_gold_vwap_sql.py::TestSessionVWAP::test_second_day_resets -v --noconftest
```
→ 1 FAILED: day2 bar1 session_vwap=11.78 (blended with day1, expected 20.0)

### (c) Use UTC date instead of ET in _minute_vwap
```
sed -i "s/DATE(CONVERT_TIMEZONE('UTC','America/New_York',event_ts))/DATE(event_ts)/g" silver/08_silver_ohlcv_day_adjusted.sql
python3 -m pytest tests/silver/test_silver_vwap_sql.py::TestMinuteVWAP::test_et_date_boundary -v --noconftest
```
→ 1 FAILED: trading_date=2026-03-10 (should be 2026-03-09 ET)

### (d) ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING (future leak)
```
sed -i '/session_vwap/{s/ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW/ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING/g}' gold/01_gold_ohlcv_features.sql
python3 -m pytest tests/gold/test_gold_vwap_sql.py::TestSessionVWAP::test_three_bars_null_vwap -v --noconftest
```
→ 1 FAILED: bar1 session_vwap=10.75 (sees future bar2, expected 10.0)

### (e) Fabricate proxy for symbols with no minute bars
```
# Remove LEFT JOIN _minute_vwap from _adjusted, replace COALESCE with dd.vwap
python3 -m pytest tests/silver/test_silver_vwap_sql.py::TestAdjustedVWAPSource::test_minute_bars_vwap_source -v --noconftest
```
→ 1 FAILED: resolved_vwap=None (minute bars ignored, expected 100.0)