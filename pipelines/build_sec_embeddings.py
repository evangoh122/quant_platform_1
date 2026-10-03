"""pipelines/build_sec_embeddings.py — Idempotent batch embedding builder.

Reads chunk text from silver_sec_sections, embeds with BAAI/bge-small-en-v1.5
(384-d), and MERGEs into gold_sec_chunk_embeddings. Uses a Spark left anti-join
to select only unembedded chunks — no collect-all pattern.

Run via databricks-connect serverless:
    python pipelines/build_sec_embeddings.py
    python pipelines/build_sec_embeddings.py --ticker AAPL --batch-size 256 --partitions 4

Expected: ~10,720 rows on first run, 0 on second run (idempotent).
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────

CATALOG = os.getenv("CATALOG", "bootcamp_students")
SCHEMA = os.getenv("SCHEMA", "evangoh_capstone")
FQN = f"{CATALOG}.{SCHEMA}"

CHUNKS_TABLE = f"{FQN}.silver_sec_sections"
EMBEDDINGS_TABLE = f"{FQN}.gold_sec_chunk_embeddings"

EMBEDDING_MODEL = os.getenv("ST_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))
DEFAULT_BATCH_SIZE = 256
DEFAULT_PARTITIONS = 4

EMBEDDINGS_SCHEMA = (
    "chunk_id STRING, accession_number STRING, ticker STRING, "
    "accepted_ts TIMESTAMP, embedding ARRAY<FLOAT>, "
    "embedding_model STRING, embedded_ts TIMESTAMP"
)


def _ensure_table(spark) -> None:
    """Create the embeddings table if it does not exist."""
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {EMBEDDINGS_TABLE} (
            chunk_id STRING,
            accession_number STRING,
            ticker STRING,
            accepted_ts TIMESTAMP,
            embedding ARRAY<FLOAT>,
            embedding_model STRING,
            embedded_ts TIMESTAMP
        )
        USING DELTA
    """)


def build(
    spark,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    partitions: int = DEFAULT_PARTITIONS,
    ticker: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict:
    """Build embeddings for chunks not yet embedded.

    Uses Spark left anti-join to select only unembedded chunks, then processes
    in bounded batches. No collect-all pattern.

    Returns dict with keys: rows_written, embedding_dim, rows_already_embedded.
    """
    from api.services.embeddings import get_embeddings

    embeddings = get_embeddings()

    t0 = time.monotonic()

    # 0. Ensure target table exists
    _ensure_table(spark)

    # 1. Anti-join: select only chunks NOT already embedded for this model
    from pyspark.sql import functions as F

    chunks_query = (
        spark.table(CHUNKS_TABLE)
        .alias("c")
        .join(
            spark.table(EMBEDDINGS_TABLE)
            .filter(F.col("embedding_model") == EMBEDDING_MODEL)
            .select("chunk_id")
            .alias("e"),
            on=F.col("c.chunk_id") == F.col("e.chunk_id"),
            how="left_anti",
        )
        .filter(
            (F.col("c.chunk_text").isNotNull())
            & (F.col("c.chunk_id").isNotNull())
        )
        .select(
            "c.chunk_id",
            "c.chunk_text",
            "c.accession_number",
            "c.ticker",
            F.unix_timestamp(F.col("c.accepted_ts")).alias("accepted_epoch"),
        )
    )

    if ticker:
        chunks_query = chunks_query.filter(F.col("c.ticker") == ticker)

    if limit:
        chunks_query = chunks_query.limit(limit)

    # Repartition for parallel processing
    chunks_query = chunks_query.repartition(partitions)

    # Collect only the unembedded chunks (bounded by anti-join + ticker/limit)
    new_rows = chunks_query.collect()

    if not new_rows:
        elapsed = time.monotonic() - t0
        return {
            "rows_written": 0,
            "embedding_dim": EMBEDDING_DIM,
            "rows_already_embedded": 0,
            "elapsed_seconds": round(elapsed, 1),
        }

    # 2. Embed in bounded batches
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    out_rows = []
    total = len(new_rows)

    for batch_start in range(0, total, batch_size):
        batch = new_rows[batch_start : batch_start + batch_size]
        texts = [r["chunk_text"] for r in batch]
        vecs = embeddings.embed_documents(texts)

        for r, vec in zip(batch, vecs):
            # Validate dimension
            if len(vec) != EMBEDDING_DIM:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {EMBEDDING_DIM}, got {len(vec)} "
                    f"for chunk_id={r['chunk_id']}"
                )

            # Convert epoch to UTC datetime for storage
            epoch = r["accepted_epoch"]
            accepted_ts = (
                datetime.fromtimestamp(int(epoch), tz=timezone.utc)
                if epoch is not None
                else None
            )
            out_rows.append((
                r["chunk_id"],
                r["accession_number"],
                r["ticker"],
                accepted_ts,
                vec,
                EMBEDDING_MODEL,
                now,
            ))

        done = min(batch_start + batch_size, total)
        if done % 500 == 0 or done == total:
            print(f"  Embedded {done}/{total}")

    # 3. Write to Delta via MERGE (batch the writes)
    write_batch_size = 10000
    total_written = 0

    for write_start in range(0, len(out_rows), write_batch_size):
        write_batch = out_rows[write_start : write_start + write_batch_size]
        src_df = spark.createDataFrame(write_batch, schema=EMBEDDINGS_SCHEMA)
        src_df.createOrReplaceTempView("_embed_src")

        spark.sql(f"""
            MERGE INTO {EMBEDDINGS_TABLE} AS tgt
            USING _embed_src AS src
            ON tgt.chunk_id = src.chunk_id AND tgt.embedding_model = src.embedding_model
            WHEN NOT MATCHED THEN INSERT *
        """)

        total_written += len(write_batch)

    elapsed = time.monotonic() - t0
    return {
        "rows_written": total_written,
        "embedding_dim": EMBEDDING_DIM,
        "rows_already_embedded": 0,
        "elapsed_seconds": round(elapsed, 1),
    }


def main():
    from databricks.connect import DatabricksSession

    parser = argparse.ArgumentParser(description="Build SEC chunk embeddings")
    parser.add_argument("--catalog", default=os.getenv("CATALOG", "bootcamp_students"))
    parser.add_argument("--schema", default=os.getenv("SCHEMA", "evangoh_capstone"))
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--partitions", type=int, default=DEFAULT_PARTITIONS)
    parser.add_argument("--ticker", default=None, help="Filter to specific ticker(s), comma-separated")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of chunks to embed")
    args = parser.parse_args()

    global CATALOG, SCHEMA, FQN, CHUNKS_TABLE, EMBEDDINGS_TABLE
    CATALOG = args.catalog
    SCHEMA = args.schema
    FQN = f"{CATALOG}.{SCHEMA}"
    CHUNKS_TABLE = f"{FQN}.silver_sec_sections"
    EMBEDDINGS_TABLE = f"{FQN}.gold_sec_chunk_embeddings"

    spark = DatabricksSession.builder.serverless(True).getOrCreate()

    print("=== Build SEC Chunk Embeddings ===")
    print(f"Model: {EMBEDDING_MODEL} ({EMBEDDING_DIM}-d)")
    print(f"Source: {CHUNKS_TABLE}")
    print(f"Target: {EMBEDDINGS_TABLE}")
    print(f"Batch size: {args.batch_size}, Partitions: {args.partitions}")
    if args.ticker:
        print(f"Ticker filter: {args.ticker}")
    print()

    tickers = None
    if args.ticker:
        tickers = [t.strip() for t in args.ticker.split(",")]

    if tickers:
        for t in tickers:
            print(f"\n--- Processing {t} ---")
            result = build(
                spark,
                batch_size=args.batch_size,
                partitions=args.partitions,
                ticker=t,
                limit=args.limit,
            )
            print(f"  {t}: {result['rows_written']} rows in {result['elapsed_seconds']}s")
    else:
        result = build(
            spark,
            batch_size=args.batch_size,
            partitions=args.partitions,
            limit=args.limit,
        )
        print(f"\nFirst run:  {result['rows_written']} rows written in {result['elapsed_seconds']}s")

        # Second run to verify idempotency
        result2 = build(spark, batch_size=args.batch_size, partitions=args.partitions)
        print(f"Second run: {result2['rows_written']} rows written (expect 0)")

    return result


if __name__ == "__main__":
    main()