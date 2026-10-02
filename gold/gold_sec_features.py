"""gold/gold_sec_features.py — silver_sec_sections -> gold_sec_features (PySpark).

The round-2 build request requires gold_sec_features to be built in PySpark and
to reuse ``api/services/sentiment.py`` (the Loughran-McDonald scorer), because
the scoring is Python and cannot be expressed in SQL. The transform:

  1. reads ``silver_sec_sections`` for the MVP universe,
  2. groups section text into a single filing document per
     (ticker, accession_number) ordered by chunk_index,
  3. scores each filing with ``sentiment.count_sentiment`` (tokenize + LM
     dictionary, exactly the API-lane implementation — no re-implementation),
  4. computes filing_similarity and risk_factor_change against the prior filing
     of the same ticker (ordered by accepted_ts) using the same tokenizer,
  5. MERGEs into ``gold_sec_features`` on (ticker, accession_number), so it is
     idempotent.

``information_available_ts`` = ``accepted_ts`` — the PIT key for all SEC
features (filing_date is never used).

The section text is small (thousands of rows across ~128 filings), so it is
collected to the driver and scored in-process rather than shipped through a
Spark UDF (which would re-serialize the dictionary per task).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from pyspark.sql import functions as F

from api.services.sentiment import count_sentiment, tokenize

CATALOG = os.getenv("CATALOG", "bootcamp_students")
SCHEMA = os.getenv("SCHEMA", "evangoh_capstone")
FQN = f"{CATALOG}.{SCHEMA}"

RISK_SECTION = "item1a_risk_factors"


def build(spark, universe: list[str]) -> int:
    rows = (
        spark.table(f"{FQN}.silver_sec_sections")
        .filter(F.col("ticker").isin(universe))
        .filter(F.col("ticker").isNotNull())
        .filter(F.col("accession_number").isNotNull())
        .filter(F.col("accepted_ts").isNotNull())
        .select(
            "ticker", "accession_number", "form_type", "accepted_ts",
            "filing_section", "chunk_index", "chunk_text",
        )
        .orderBy("ticker", "accession_number", "chunk_index")
        .collect()
    )

    # Group into one document per filing.
    filings: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r.ticker, r.accession_number)
        f = filings.setdefault(key, {
            "ticker": r.ticker,
            "accession_number": r.accession_number,
            "form_type": r.form_type,
            "accepted_ts": r.accepted_ts,
            "parts": [],
            "risk_parts": [],
        })
        text = r.chunk_text or ""
        f["parts"].append(text)
        if r.filing_section == RISK_SECTION:
            f["risk_parts"].append(text)

    # Ordered list per ticker for prior-filing comparison.
    by_ticker: dict[str, list] = {}
    for f in filings.values():
        by_ticker.setdefault(f["ticker"], []).append(f)
    for tk in by_ticker:
        by_ticker[tk].sort(key=lambda x: x["accepted_ts"])

    out_rows = []
    for tk, flist in by_ticker.items():
        prior_tokens: set | None = None
        prior_risk_tokens: set | None = None
        for f in flist:
            full_text = "\n\n".join(f["parts"])
            risk_text = "\n\n".join(f["risk_parts"])

            counts = count_sentiment(full_text)
            total = max(counts.total_words, 1)

            sentiment_score = round((counts.positive - counts.negative) / total, 8)
            tone_positive = round(counts.positive / total, 8)
            tone_negative = round(counts.negative / total, 8)
            tone_uncertainty = round(counts.uncertainty / total, 8)

            tokens = set(tokenize(full_text))
            risk_tokens = set(tokenize(risk_text))

            filing_similarity = None
            if tokens and prior_tokens:
                filing_similarity = round(len(tokens & prior_tokens) / len(tokens), 8)

            risk_factor_change = None
            if risk_tokens and prior_risk_tokens:
                risk_factor_change = round(
                    1.0 - len(risk_tokens & prior_risk_tokens) / len(risk_tokens), 8
                )

            material_event_flag = f["form_type"] == "8-K"
            event_type = "material_event" if material_event_flag else None

            out_rows.append((
                f["ticker"], f["accession_number"], f["form_type"],
                f["accepted_ts"], sentiment_score, tone_positive,
                tone_negative, tone_uncertainty, risk_factor_change,
                filing_similarity, material_event_flag, event_type,
                datetime.now(timezone.utc).replace(tzinfo=None),
            ))

            prior_tokens = tokens
            prior_risk_tokens = risk_tokens

    schema = (
        "ticker string, accession_number string, form_type string, "
        "information_available_ts timestamp, sentiment_score double, "
        "tone_positive double, tone_negative double, tone_uncertainty double, "
        "risk_factor_change double, filing_similarity double, "
        "material_event_flag boolean, event_type string, processed_ts timestamp"
    )
    src = spark.createDataFrame(out_rows, schema=schema)
    src.createOrReplaceTempView("_gold_sec_src")

    spark.sql(f"""
        MERGE INTO {FQN}.gold_sec_features AS tgt
        USING _gold_sec_src AS src
        ON tgt.ticker = src.ticker AND tgt.accession_number = src.accession_number
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    n = spark.sql(f"SELECT COUNT(*) FROM {FQN}.gold_sec_features").collect()[0][0]
    return n


if __name__ == "__main__":
    from databricks.connect import DatabricksSession
    from config.universe import load_universe

    spark = DatabricksSession.builder.serverless(True).getOrCreate()
    uni = load_universe()
    print("gold_sec_features rows:", build(spark, uni))
