"""One-off: train the repo's baseline (ml.train.make_baseline) on gold_model_features and publish
latest-snapshot signals to gold_trading_signals via ml.score.score_rows.

Label construction (1-trading-day horizon, PIT-safe):
  gold_model_features has ONE snapshot per symbol per day (~00:00–01:00 UTC,
  i.e. after the US close).  For each feature row (symbol, prediction_ts):
    D = the latest trade_date of that symbol with close_ts <= prediction_ts.
    N = the next trade_date after D for that symbol.
    label = 1.0 if close_N > close_D else 0.0; label_ts = close_ts_N.
    NaN label when D or N is missing or N - D > 5 calendar days.
  Daily closes are fetched from silver_ohlcv with ONE aggregated query:
    is_regular_session = true, timespan = 'minute', grouped by symbol and
    to_date(from_utc_timestamp(event_ts, 'America/New_York')), taking
    max_by(close, event_ts) as close and max(event_ts) as close_ts.

Train/test split (purged):
  cut = 0.8-quantile of prediction_ts.  Train = rows with label_ts <= cut
  (label already observed before cut).  Test  = rows with prediction_ts > cut.
  No training row has a label observed after cut.

Refit for scoring:
  The final model is fitted on labelled rows whose label_ts <= the earliest
  scoring snapshot time (refit_rows).  Scoring never uses a snapshot's own label;
  the latest snapshot is usually unlabelled, but may be labelled if a later close exists.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from databricks.sdk import WorkspaceClient
from sklearn.metrics import roc_auc_score
from ml.train import make_baseline, prepare_features
from ml.score import score_rows
from ml.baseline_labels import daily_close_labels, purged_split, refit_rows
w = WorkspaceClient(profile="evangohsg")
T = "bootcamp_students.evangoh_capstone.gold_model_features"
SILVER = "bootcamp_students.evangoh_capstone.silver_ohlcv"
def fetch(sql):
    st = w.statement_execution.execute_statement(warehouse_id="b15d3d6f837ba428", statement=sql, wait_timeout="50s")
    cols = [c.name for c in st.manifest.schema.columns]; rows = list(st.result.data_array or [])
    for ci in range(1, st.manifest.total_chunk_count or 0):
        rows += w.statement_execution.get_statement_result_chunk_n(st.statement_id, ci).data_array or []
    return pd.DataFrame(rows, columns=cols)
FEATS = ["return_1m","return_5m","return_15m","return_30m","rvol_5m","rvol_15m","rvol_30m","atr_14","rsi_14",
         "vwap_deviation","relative_volume","put_call_ratio","iv_atm","iv_skew","iv_term_slope","volume_anomaly_zscore",
         "sec_sentiment_score","sec_risk_factor_change","cot_lev_money_zscore","cot_crowding_score"]
df = fetch(f"SELECT symbol, prediction_ts, feature_snapshot_id, {', '.join(FEATS)} FROM {T}")
df["prediction_ts"] = pd.to_datetime(df["prediction_ts"])
for c in FEATS: df[c] = pd.to_numeric(df[c], errors="coerce")
df = df.sort_values(["symbol","prediction_ts"]).reset_index(drop=True)
# Fetch daily closes from silver_ohlcv: one row per (symbol, trade_date).
# Aggregated: max_by(close, event_ts) = close at the last regular-session
# minute bar; max(event_ts) = close_ts of that bar.
symbols_sql = ", ".join(f"'{s}'" for s in df.symbol.unique())
closes = fetch(f"""
    SELECT symbol,
           to_date(from_utc_timestamp(event_ts, 'America/New_York')) AS trade_date,
           max_by(close, event_ts) AS close,
           max(event_ts)           AS close_ts
    FROM {SILVER}
    WHERE is_regular_session = true
      AND timespan = 'minute'
      AND symbol IN ({symbols_sql})
    GROUP BY symbol, to_date(from_utc_timestamp(event_ts, 'America/New_York'))
    ORDER BY symbol, trade_date
""")
closes["close"] = pd.to_numeric(closes["close"], errors="coerce")
closes["close_ts"] = pd.to_datetime(closes["close_ts"])
closes["trade_date"] = pd.to_datetime(closes["trade_date"]).dt.date
df = daily_close_labels(df, closes)
print("rows", len(df), "symbols", df.symbol.nunique(), df.prediction_ts.min(), "->", df.prediction_ts.max())
lab = df[df.label.notna()].copy()
print("rows labelled", len(lab), "| label UP share", round(float(lab.label.mean()), 3))
tr, te = purged_split(lab)
Xtr = prepare_features(tr, FEATS).fillna(0.0); Xte = prepare_features(te, FEATS).fillna(0.0)
m = make_baseline(); m.fit(Xtr, tr.label.astype(int))
auc = roc_auc_score(te.label.astype(int), m.predict_proba(Xte)[:,1]) if te.label.nunique() > 1 else float("nan")
cut = lab.prediction_ts.quantile(0.8)
print(f"holdout AUC {auc:.3f} | train {len(tr)} test {len(te)} | cutoff {cut}")
# refit on labelled rows whose label_ts <= the earliest scoring snapshot,
# so no scored row sees a label observed after its own time.
latest = df.sort_values("prediction_ts").groupby("symbol").tail(1).copy()
latest = latest[latest.prediction_ts >= pd.Timestamp("2026-09-01", tz="UTC")].copy()  # only current snapshots
refit = refit_rows(lab, latest.prediction_ts)
print(f"refit cutoff {latest.prediction_ts.min()} | refit rows {len(refit)}")
m = make_baseline(); m.fit(prepare_features(refit, FEATS).fillna(0.0), refit.label.astype(int))
Xl = prepare_features(latest, FEATS).fillna(0.0)
latest_scoring = latest[["symbol","prediction_ts","feature_snapshot_id"]].join(Xl)
version = "baseline-logreg-v1-1d-2026-10-05"
sig = score_rows(latest_scoring, m, model_version=version, horizon="1d", feature_cols=FEATS)
print(sig[["symbol","prediction_ts","direction","probability"]].head(10).to_string(index=False))
print("signals", len(sig), "UP", (sig.direction=="UP").sum(), "DOWN", (sig.direction=="DOWN").sum())
if "--write" in sys.argv:
    from databricks.connect import DatabricksSession
    spark = DatabricksSession.builder.profile("evangohsg").serverless(True).getOrCreate()
    sdf = spark.createDataFrame(sig)
    sdf.createOrReplaceTempView("_sig")
    spark.sql("""MERGE INTO bootcamp_students.evangoh_capstone.gold_trading_signals t USING _sig s
                 ON t.signal_id = s.signal_id WHEN NOT MATCHED THEN INSERT *""")
    print("WRITTEN", spark.sql("select count(*) c from bootcamp_students.evangoh_capstone.gold_trading_signals").collect()[0]["c"])