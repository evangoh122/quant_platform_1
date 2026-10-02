import sys
sys.path.insert(0, "/home/jianj/code/qp1-sg")
from datetime import datetime, timezone
from gold.pit_guard import LookaheadLeakError, validate_no_lookahead, find_lookahead_leaks

def t(s): return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)

PRED = t("2026-09-02T16:00:00+00:00")

clean = [
    {"name": "ohlcv_return_1m", "information_available_ts": t("2026-09-02T15:59:00+00:00")},
    {"name": "options_pcr", "information_available_ts": t("2026-09-02T08:36:24+00:00")},
    {"name": "sec_sentiment", "information_available_ts": t("2026-08-27T05:02:25+00:00")},
    {"name": "cot_positioning", "information_available_ts": t("2026-08-28T20:30:00+00:00")},
]

# 1. PASSING run — all features available at or before prediction_ts
print("=== PASSING run (no leak) ===")
validate_no_lookahead(clean, PRED)
print("validate_no_lookahead(...) -> no exception, OK")

# 2. FAILING run — inject a row available only after prediction_ts
print("\n=== FAILING run (injected leaking row) ===")
leaking = clean + [{"name": "future_quote", "information_available_ts": t("2026-09-02T16:05:00+00:00")}]
try:
    validate_no_lookahead(leaking, PRED)
    print("ERROR: guard did not fire (should have raised)")
except LookaheadLeakError as e:
    print(f"LookaheadLeakError raised as expected: {e}")

# 3. show the leaking row is precisely identified
leaks = find_lookahead_leaks(
    [{"information_available_ts": f["information_available_ts"], "prediction_ts": PRED} for f in leaking]
)
print("\nleaking rows found:", [l["information_available_ts"] for l in leaks])
