"""One-off: train the repo's baseline (ml.train.make_baseline) on gold_model_features and publish
latest-snapshot signals to gold_trading_signals via ml.score.score_rows.

Label construction (PIT-safe):
  For each snapshot s of a given symbol, the label comes from the NEXT snapshot
  s' only if:
    1. s' - s is within [30min - 1min, 30min + 1min], AND
    2. s and s' fall on the same US/Eastern trading date.
  Otherwise the label is NaN and the row is excluded.

Train/test split (purged):
  cut = 0.8-quantile of prediction_ts.  Train = rows with label_ts <= cut
  (label already observed before cut).  Test  = rows with prediction_ts > cut.
  No training row has a label observed after cut.

Refit for scoring:
  The final model is fitted on all rows whose label_ts <= the scoring snapshot
  time.  The latest snapshot itself is never labelled (it has no forward data).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from databricks.sdk import WorkspaceClient
from sklearn.metrics import roc_auc_score
from ml.train import make_baseline, prepare_features
from ml.score import score_rows
from ml.baseline_labels import forward_labels, purged_split
w = WorkspaceClient(profile="evangohsg")
T = "bootcamp_students.evangoh_capstone.gold_model_features"
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
df = forward_labels(df)
print("rows", len(df), "symbols", df.symbol.nunique(), df.prediction_ts.min(), "->", df.prediction_ts.max())
lab = df[df.label.notna()].copy()
tr, te = purged_split(lab)
Xtr = prepare_features(tr, FEATS).fillna(0.0); Xte = prepare_features(te, FEATS).fillna(0.0)
m = make_baseline(); m.fit(Xtr, tr.label.astype(int))
auc = roc_auc_score(te.label.astype(int), m.predict_proba(Xte)[:,1]) if te.label.nunique() > 1 else float("nan")
cut = lab.prediction_ts.quantile(0.8)
print(f"holdout AUC {auc:.3f} | train {len(tr)} test {len(te)} | cutoff {cut}")
# refit on all labelled rows (label_ts <= latest scoring snapshot time),
# score each symbol's LATEST snapshot (the latest snapshot itself is never labelled)
# NOTE: only rows with label_ts <= the scoring snapshot time should be used for
# the final refit; the latest snapshot has no forward data so it cannot be labelled.
m = make_baseline(); m.fit(prepare_features(lab, FEATS).fillna(0.0), lab.label.astype(int))
latest = df.sort_values("prediction_ts").groupby("symbol").tail(1).copy()
latest = latest[latest.prediction_ts >= pd.Timestamp("2026-09-01", tz="UTC")].copy()  # only current snapshots
Xl = prepare_features(latest, FEATS).fillna(0.0)
latest_scoring = latest[["symbol","prediction_ts","feature_snapshot_id"]].join(Xl)
version = "baseline-logreg-v0-2026-10-05"
sig = score_rows(latest_scoring, m, model_version=version, horizon="30m", feature_cols=FEATS)
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
