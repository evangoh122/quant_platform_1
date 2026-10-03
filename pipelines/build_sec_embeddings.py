"""
pipelines/build_sec_embeddings.py -- Idempotent batch embedding builder.

Reads chunk text from silver_sec_sections, embeds with BAAI/bge-small-en-v1.5
(384-d), and MERGEs into gold_sec_chunk_embeddings.  Only chunks whose
chunk_id is NOT already present for that embedding_model are embedded.

Uses Spark left anti-join for incremental processing -- never collects all
chunk IDs into the driver.

Run via databricks-connect serverless:
    python pipelines/build_sec_embeddings.py
    python pipelines/build_sec_embeddings.py --ticker NVDA --batch-size 256

Expected: ~10,720 rows on first run, 0 on second run (idempotent).
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone

# -- Config --

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
    ticker: str = "",
    limit: int = 0,
) -> dict:
    """Build embeddings for chunks not yet embedded.

    Uses Spark left anti-join to find unembedded chunks -- never collects
    all chunk IDs into the driver.

    Returns dict with keys: rows_written, embedding_dim, rows_already_embedded.
    """
    from api.services.embeddings import get_embeddings

    embeddings = get_embeddings()

    t0 = time.monotonic()

    _ensure_table(spark)

    from pyspark.sql import functions as F

    # Anti-join: chunks NOT already embedded for this model
    chunks_df = (
        spark.table(CHUNKS_TABLE)
        .filter("chunk_text IS NOT NULL AND chunk_id IS NOT NULL")
        .select(
            "chunk_id", "chunk_text", "accession_number", "ticker",
            F.unix_timestamp(F.col("accepted_ts")).alias("accepted_epoch"),
        )
    )

    if ticker:
        chunks_df = chunks_df.filter(F.col("ticker") == ticker.upper().strip())

    embedded_df = (
        spark.table(EMBEDDINGS_TABLE)
        .filter(F.col("embedding_model") == EMBEDDING_MODEL)
        .select(F.col("chunk_id").alias("emb_chunk_id"))
    )

    anti_join_df = (
        chunks_df
        .join(embedded_df, chunks_df.chunk_id == embedded_df.emb_chunk_id, "left_anti")
    )

    if limit > 0:
        anti_join_df = anti_join_df.limit(limit)

    new_rows = anti_join_df.collect()

    if not new_rows:
        elapsed = time.monotonic() - t0
        return {
            "rows_written": 0,
            "embedding_dim": EMBEDDING_DIM,
            "rows_already_embedded": -1,  # unknown with anti-join
            "elapsed_seconds": round(elapsed, 1),
        }

    # Embed in bounded batches
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
                    f"Embedding dimension mismatch: expected {EMBEDDING_DIM}, "
                    f"got {len(vec)} for chunk {r['chunk_id']}"
                )

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

    # Validate all vectors before write
    for row in out_rows:
        vec = row[4]
        if len(vec) != EMBEDDING_DIM:
            raise ValueError(
                f"Vector dimension {len(vec)} != expected {EMBEDDING_DIM} "
                f"for chunk {row[0]}"
            )

    # Write to Delta via MERGE (append-only: never WHEN MATCHED UPDATE)
    src_df = spark.createDataFrame(out_rows, schema=EMBEDDINGS_SCHEMA)
    src_df.createOrReplaceTempView("_embed_src")

    spark.sql(f"""
        MERGE INTO {EMBEDDINGS_TABLE} AS tgt
        USING _embed_src AS src
        ON tgt.chunk_id = src.chunk_id AND tgt.embedding_model = src.embedding_model
        WHEN NOT MATCHED THEN INSERT *
    """)

    elapsed = time.monotonic() - t0
    return {
        "rows_written": len(out_rows),
        "embedding_dim": EMBEDDING_DIM,
        "rows_already_embedded": -1,
        "elapsed_seconds": round(elapsed, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Build SEC chunk embeddings")
    parser.add_argument("--catalog", default=os.getenv("CATALOG", "bootcamp_students"))
    parser.add_argument("--schema", default=os.getenv("SCHEMA", "evangoh_capstone"))
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--partitions", type=int, default=DEFAULT_PARTITIONS)
    parser.add_argument("--ticker", default="", help="Filter to specific ticker")
    parser.add_argument("--limit", type=int, default=0, help="Limit chunks to process")
    args = parser.parse_args()

    global CATALOG, SCHEMA, FQN, CHUNKS_TABLE, EMBEDDINGS_TABLE
    CATALOG = args.catalog
    SCHEMA = args.schema
    FQN = f"{CATALOG}.{SCHEMA}"
    CHUNKS_TABLE = f"{FQN}.silver_sec_sections"
    EMBEDDINGS_TABLE = f"{FQN}.gold_sec_chunk_embeddings"

    from databricks.connect import DatabricksSession

    spark = DatabricksSession.builder.serverless(True).getOrCreate()

    print("=== Build SEC Chunk Embeddings ===")
    print(f"Model: {EMBEDDING_MODEL} ({EMBEDDING_DIM}-d)")
    print(f"Source: {CHUNKS_TABLE}")
    print(f"Target: {EMBEDDINGS_TABLE}")
    if args.ticker:
        print(f"Ticker filter: {args.ticker}")
    print()

    result = build(
        spark,
        batch_size=args.batch_size,
        partitions=args.partitions,
        ticker=args.ticker,
        limit=args.limit,
    )
    print(f"\n  {result['rows_written']} rows written in {result['elapsed_seconds']}s")


if __name__ == "__main__":
    main()