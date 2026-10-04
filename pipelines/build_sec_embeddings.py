"""
pipelines/build_sec_embeddings.py -- Idempotent batch embedding builder.

Reads chunk text from silver_sec_sections, embeds with BAAI/bge-small-en-v1.5
(384-d), and MERGEs into gold_sec_chunk_embeddings.  Only chunks whose
chunk_id is NOT already present for that embedding_model are embedded.

Uses Spark left anti-join for incremental processing -- never collects all
chunk IDs into the driver at once.

Embedding runs in parallel via a bounded ThreadPoolExecutor (max_workers =
partitions).  Each worker initialises its own model instance so there is no
contention on the shared model object.

Run via databricks-connect serverless:
    python pipelines/build_sec_embeddings.py
    python pipelines/build_sec_embeddings.py --ticker NVDA --batch-size 256

Expected: ~10,720 rows on first run, 0 on second run (idempotent).
"""
from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    all chunk IDs into the driver at once. Processes in bounded batches
    via toLocalIterator() to keep driver memory bounded.

    Embedding runs in parallel via a bounded ThreadPoolExecutor so that
    N batches can be embedded concurrently (N = partitions).

    Returns dict with keys: rows_written, embedding_dim, rows_already_embedded.
    """
    from api.services.embeddings import get_embeddings

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

    if partitions > 1:
        anti_join_df = anti_join_df.repartition(partitions)

    # Collect batches from the iterator
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    total_processed = 0
    rows_written = 0

    # get_embeddings() is a singleton — all workers share the same model
    # instance.  Bounded by max_workers=partitions.
    max_workers = max(1, partitions)

    def _embed_batch(batch):
        """Worker: embed a batch and write to Delta.  Returns row count."""
        from api.services.embeddings import get_embeddings as _get
        worker_embeddings = _get()
        return _embed_and_write_batch(spark, worker_embeddings, batch, now)

    # Submit batches to the pool as they come off the iterator.
    # At most max_workers futures are in-flight at any time (bounded memory).
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        pending = set()
        batch = []

        for row in anti_join_df.toLocalIterator():
            chunk_text_val = row["chunk_text"]
            if not chunk_text_val:
                continue

            batch.append({
                "chunk_id": row["chunk_id"],
                "chunk_text": chunk_text_val,
                "accession_number": row["accession_number"],
                "ticker": row["ticker"],
                "accepted_epoch": row["accepted_epoch"],
            })

            if len(batch) >= batch_size:
                # Wait for a slot if we've hit the concurrency limit
                if len(pending) >= max_workers:
                    done, pending = _drain_one(pending)
                    for f in done:
                        rows_written += f.result()
                pending.add(pool.submit(_embed_batch, batch))
                total_processed += len(batch)
                if total_processed % 500 == 0:
                    print(f"  Processed {total_processed} chunks")
                batch = []

        # Submit the last partial batch
        if batch:
            pending.add(pool.submit(_embed_batch, batch))
            total_processed += len(batch)

        # Wait for all remaining futures
        for f in as_completed(pending):
            rows_written += f.result()

    elapsed = time.monotonic() - t0
    return {
        "rows_written": rows_written,
        "embedding_dim": EMBEDDING_DIM,
        "rows_already_embedded": -1,  # unknown with anti-join
        "elapsed_seconds": round(elapsed, 1),
    }


def _drain_one(pending):
    """Wait for exactly one future to complete. Returns (done_set, remaining_set)."""
    from concurrent.futures import as_completed
    done = set()
    for f in as_completed(pending):
        done.add(f)
        break
    return done, pending - done


def _embed_and_write_batch(
    spark,
    embeddings,
    batch: list,
    now: datetime,
) -> int:
    """Embed a batch of chunks and MERGE into the embeddings table.

    Returns the number of rows written.
    """
    if not batch:
        return 0

    texts = [r["chunk_text"] for r in batch]
    vecs = embeddings.embed_documents(texts)

    out_rows = []
    for r, vec in zip(batch, vecs):
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

    src_df = spark.createDataFrame(out_rows, schema=EMBEDDINGS_SCHEMA)
    src_df.createOrReplaceTempView("_embed_src")

    spark.sql(f"""
        MERGE INTO {EMBEDDINGS_TABLE} AS tgt
        USING _embed_src AS src
        ON tgt.chunk_id = src.chunk_id AND tgt.embedding_model = src.embedding_model
        WHEN NOT MATCHED THEN INSERT *
    """)

    return len(out_rows)


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