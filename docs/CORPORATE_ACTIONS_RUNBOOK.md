# Corporate Actions Runbook

Copy/paste-ready commands for the corporate-actions lane.  Fill the result
block at the bottom after each run.

---

## 1. Deploy / check identity

```bash
# Confirm catalog/schema/profile
echo "CATALOG=$CATALOG SCHEMA=$SCHEMA DATABRICKS_PROFILE=${DATABRICKS_PROFILE:-evangohsg}"

# Current branch and commit
git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD

# Target table schemas (run in Databricks SQL or via CLI)
DESCRIBE TABLE bootcamp_students.evangoh_capstone.bronze_corporate_actions;
DESCRIBE TABLE bootcamp_students.evangoh_capstone.silver_ohlcv_day_adjusted;
DESCRIBE TABLE bootcamp_students.evangoh_capstone.data_quality_breaks;

# Live symbol universe query
SELECT COUNT(DISTINCT symbol) AS universe_count
FROM (
    SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol
    FROM bootcamp_students.evangoh_capstone.gold_tradable_universe
    WHERE symbol IS NOT NULL
    UNION SELECT 'SPY' UNION SELECT 'RSP' UNION SELECT 'QQQ'
);

# Pre-run Bronze row/key counts
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT (symbol, CAST(ex_date AS STRING), source)) AS distinct_keys
FROM bootcamp_students.evangoh_capstone.bronze_corporate_actions;
```

## 2. Dry-run

```bash
# Run the refresh with mode=dry-run, full lexical range, delay >= 0.5s
python notebooks/refresh_bronze_corporate_actions.py \
    --mode dry-run \
    --source massive \
    --delay-seconds 0.5

# Save JSON output.  Require:
#   - zero writes (mode=dry-run)
#   - no schema errors
#   - review failed/empty/conflict symbols
```

## 3. Fetch / write

**Mode:** The job defaults to `--mode dry-run` with no schedule.  Dry-run
fetches and deduplicates splits but writes nothing.  To actually persist
rows, pass `--mode write`.

**Conflict semantics:** The write path uses first-write-wins for the
natural key `(symbol, ex_date, source)`.  Rows already present in bronze
are never overwritten.  Incoming rows whose key matches an existing row
are counted as `conflict_rows` in the JSON report.  A `WARNING` log line
is emitted when `conflict_rows > 0` — investigate this because it means
the source returned data that is already in bronze (possible data change
or duplicate run).

```bash
# Dry-run (default — no writes, review JSON output)
python notebooks/refresh_bronze_corporate_actions.py \
    --source massive \
    --delay-seconds 0.5

# Write mode with a named run ID
python notebooks/refresh_bronze_corporate_actions.py \
    --mode write \
    --source massive \
    --run-id "manual-$(date +%Y%m%d)" \
    --delay-seconds 0.5

# Resume after interruption (same run ID)
python notebooks/refresh_bronze_corporate_actions.py \
    --mode write \
    --source massive \
    --run-id "manual-$(date +%Y%m%d)" \
    --delay-seconds 0.5

# Verify: post-count delta = new rows, zero duplicate natural keys
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT (symbol, CAST(ex_date AS STRING), source)) AS distinct_keys
FROM bootcamp_students.evangoh_capstone.bronze_corporate_actions;

# Rerun once — prove zero appended rows (conflict_rows should equal total)
python notebooks/refresh_bronze_corporate_actions.py \
    --mode write \
    --source massive \
    --run-id "manual-rerun-$(date +%Y%m%d)" \
    --delay-seconds 0.5
```

## 4. Build Silver

```bash
# Run only the adjusted daily step (or the full orchestrator)
python pipelines/run_silver_gold.py --only silver

# Run table checks
python pipelines/run_silver_gold.py --check

# Verify no duplicate keys
SELECT symbol, event_date, COUNT(*) AS cnt
FROM bootcamp_students.evangoh_capstone.silver_ohlcv_day_adjusted
GROUP BY symbol, event_date HAVING cnt > 1;

SELECT symbol, event_date, COUNT(*) AS cnt
FROM bootcamp_students.evangoh_capstone.data_quality_breaks
GROUP BY symbol, event_date HAVING cnt > 1;
```

## 5. AMZN verification

```sql
-- AMZN 2022-06-03 (prior bar) and 2022-06-06 (ex-date) raw data
SELECT symbol, event_date, close, previous_close, raw_overnight_return,
       cumulative_split_ratio, price_adjustment_factor,
       adj_close, return_1d, is_data_quality_break
FROM bootcamp_students.evangoh_capstone.silver_ohlcv_day_adjusted
WHERE symbol = 'AMZN' AND event_date BETWEEN '2022-06-03' AND '2022-06-06'
ORDER BY event_date;

-- Expected:
--   2022-06-03: adj_close ≈ 2447/20 = 122.35
--   2022-06-06: adj_close ≈ 124.79, return_1d ≈ +2% (NOT -95%)
--   is_data_quality_break = FALSE for both
```

## 6. Known examples

```sql
-- Forward splits (SPLIT_EXPLAINED, not masked)
SELECT symbol, event_date, classification, matched_split_ratio,
       split_error, is_masked
FROM bootcamp_students.evangoh_capstone.data_quality_breaks
WHERE classification = 'SPLIT_EXPLAINED'
ORDER BY symbol, event_date
LIMIT 20;

-- Reverse splits (SQQQ, SOXS, FNGU, etc.)
SELECT symbol, event_date, classification, matched_split_ratio,
       split_error, is_masked
FROM bootcamp_students.evangoh_capstone.data_quality_breaks
WHERE matched_split_ratio < 1.0
ORDER BY symbol, event_date;

-- META 2022-06-09 (ticker reuse, not a split)
SELECT symbol, event_date, classification, reason,
       is_masked, reviewed_by
FROM bootcamp_students.evangoh_capstone.data_quality_breaks
WHERE symbol = 'META' AND event_date = '2022-06-09';

-- Expected: classification = 'UNEXPLAINED_PENDING' or 'CONFIRMED_DATA_BREAK',
--           reason = 'no matching split event' or 'ticker_reuse',
--           is_masked = TRUE
```

## 7. Reconcile 237

```sql
-- Claude's exact scope: ever-in-Gold symbols, 2022 onward, including factors
WITH scope AS (
    SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol
    FROM bootcamp_students.evangoh_capstone.gold_tradable_universe
    WHERE symbol IS NOT NULL
    UNION SELECT 'SPY' UNION SELECT 'RSP' UNION SELECT 'QQQ'
),
candidates AS (
    SELECT db.*
    FROM bootcamp_students.evangoh_capstone.data_quality_breaks db
    JOIN scope s ON s.symbol = db.symbol
    WHERE db.event_date >= '2022-01-01'
)
SELECT
    classification,
    is_masked,
    COUNT(*) AS cnt
FROM candidates
GROUP BY classification, is_masked
ORDER BY classification, is_masked;

-- Verify total = 237
SELECT COUNT(*) AS total_candidates
FROM (
    SELECT db.*
    FROM bootcamp_students.evangoh_capstone.data_quality_breaks db
    JOIN (
        SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol
        FROM bootcamp_students.evangoh_capstone.gold_tradable_universe
        WHERE symbol IS NOT NULL
        UNION SELECT 'SPY' UNION SELECT 'RSP' UNION SELECT 'QQQ'
    ) s ON s.symbol = db.symbol
    WHERE db.event_date >= '2022-01-01'
);

-- If total != 237, report scope/date/source drift instead of changing the constant.
```

## 8. Review real moves

```sql
-- List unexplained/flagged breaks for human review
SELECT symbol, event_date, previous_close, close,
       raw_overnight_return, matched_split_ratio,
       post_split_gross_return, split_error, classification, reason
FROM bootcamp_students.evangoh_capstone.data_quality_breaks
WHERE classification IN ('UNEXPLAINED_PENDING', 'CONFIRMED_DATA_BREAK')
ORDER BY event_date, symbol;

-- After human review, update ALLOW_REAL_MOVE:
UPDATE bootcamp_students.evangoh_capstone.data_quality_breaks
SET classification = 'ALLOW_REAL_MOVE',
    reason = '<verified reason>',
    is_masked = FALSE,
    reviewed_by = '<analyst_email>',
    reviewed_ts = current_timestamp()
WHERE symbol = '<SYMBOL>' AND event_date = '<DATE>'
  AND reviewed_by IS NULL;

-- After human review, update CONFIRMED_DATA_BREAK:
UPDATE bootcamp_students.evangoh_capstone.data_quality_breaks
SET classification = 'CONFIRMED_DATA_BREAK',
    reason = '<e.g. ticker_reuse>',
    is_masked = TRUE,
    reviewed_by = '<analyst_email>',
    reviewed_ts = current_timestamp()
WHERE symbol = 'META' AND event_date = '2022-06-09'
  AND reviewed_by IS NULL;

-- Rebuild Silver to apply review decisions
python pipelines/run_silver_gold.py --only silver

-- Prove allowed returns are restored and confirmed/pending remain NULL
SELECT symbol, event_date, return_1d, is_data_quality_break
FROM bootcamp_students.evangoh_capstone.silver_ohlcv_day_adjusted
WHERE symbol IN ('META', '<ALLOWED_SYMBOL>')
  AND event_date IN ('2022-06-09', '<ALLOWED_DATE>');
```

## 9. Consumer gate

Do NOT run strategy r10 or deploy NL serving DDL until:
1. This lane is merged to main
2. The separate consumer changes (section 8 of the BUILD spec) pass their tests

---

## Result block

Fill after each live run:

```
Date:           ___________
Source/Run ID:  ___________
Branch/Commit:  ___________

Universe:       _____ symbols (raw), _____ final
Attempted:      _____ symbols
Succeeded:      _____
Empty:          _____
Failed:         _____
Resumed:        _____

Bronze new:     _____ rows
Bronze conflicts: _____
Pre-Bronze count: _____
Post-Bronze count: _____

Candidate total: _____
Split-explained: _____
Unexplained pending: _____
Confirmed data break: _____
Allow real move: _____
Masked total: _____

AMZN 2022-06-06:
  raw_close:      _____
  adj_close:      _____
  raw_return:     _____%
  adj_return:     _____%
  is_break:       _____

META 2022-06-09:
  classification: _____
  is_masked:      _____

Duplicate keys: _____
Query timestamp: ___________
```