from databricks.connect import DatabricksSession
spark = DatabricksSession.builder.serverless(True).getOrCreate()
FQN = "bootcamp_students.evangoh_capstone"
def c(s): return spark.sql(s).collect()[0][0]

print("=== bronze_options_quotes nullability (61,882 rows) ===")
cols = ["bid","ask","midpoint","implied_volatility","delta","volume","open_interest","last_price","strike","expiry","right"]
for col in cols:
    nn = c(f"SELECT COUNT({col}) FROM {FQN}.bronze_options_quotes")
    print(f"  {col:20s} non-null: {nn}")

print("\n=== gold_options_features iv coverage ===")
print("iv_atm non-null:", c(f"SELECT COUNT(iv_atm) FROM {FQN}.gold_options_features"))
print("iv_25d_put non-null:", c(f"SELECT COUNT(iv_25d_put) FROM {FQN}.gold_options_features"))
print("iv_25d_call non-null:", c(f"SELECT COUNT(iv_25d_call) FROM {FQN}.gold_options_features"))
print("iv_skew non-null:", c(f"SELECT COUNT(iv_skew) FROM {FQN}.gold_options_features"))
print("avg_spread_pct non-null:", c(f"SELECT COUNT(avg_spread_pct) FROM {FQN}.gold_options_features"))

print("\n=== gold_options_features sample full row ===")
for r in spark.sql(f"SELECT * FROM {FQN}.gold_options_features WHERE symbol='NVDA'").collect():
    print("  ", r)
