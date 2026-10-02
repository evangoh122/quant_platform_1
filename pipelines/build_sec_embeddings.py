"""
pipelines/build_sec_embeddings.py — Idempotent batch embedding builder.

Reads chunk text from silver_sec_sections, embeds with BAAI/bge-small-en-v1.5
(384-d), and MERGEs into gold_sec_chunk_embeddings.  Only chunks whose
chunk_id is NOT already present for that embedding_model are embedded.

Run via databricks-connect serverless:
    python pipelines/build_sec_embeddings.py

Expected: ~10,720 rows on first run, 0 on second run (idempotent).
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────

CATALOG = os.getenv("CATALOG", "bootcamp_students")
SCHEMA = os.getenv("SCHEMA", "evangoh_capstone")
FQN = f"{CATALOG}.{SCHEMA}"

CHUNKS_TABLE = f"{FQN}.silver_sec_sections"
EMBEDDINGS_TABLE = f"{FQN}.gold_sec_chunk_embeddings"

EMBEDDING_MODEL = os.getenv("ST_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))


def build(spark) -> dict:
    """Build embeddings for chunks not yet embedded.

    Returns dict with keys: rows_written, embedding_dim, second_run_rows.
    """
    from api.services.embeddings import get_embeddings

    embeddings = get_embeddings()
    if embeddings is None:
        raise RuntimeError("Embedding model not available")

    t0 = time.monotonic()

    # 1. Get chunk_ids already embedded for this model
    try:
        existing_df = spark.table(EMBEDDINGS_TABLE).filter(
            f"embedding_model = '{EMBEDDING_MODEL}'"
        ).select("chunk_id")
        existing_ids = set(r["chunk_id"] for r in existing_df.collect())
    except Exception:
        # Table may not exist yet
        existing_ids = set()

    # 2. Get all chunks
    chunks_df = spark.table(CHUNKS_TABLE).select(
        "chunk_id", "chunk_text",
    ).filter("chunk_text IS NOT NULL AND chunk_id IS NOT NULL")
    all_rows = chunks_df.collect()

    # 3. Filter to only unembedded chunks
    new_rows = [r for r in all_rows if r["chunk_id"] not in existing_ids]

    if not new_rows:
        elapsed = time.monotonic() - t0
        return {
            "rows_written": 0,
            "embedding_dim": EMBEDDING_DIM,
            "second_run_rows": 0,
            "elapsed_seconds": round(elapsed, 1),
        }

    # 4. Embed in batches
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    out_rows = []
    total = len(new_rows)

    for batch_start in range(0, total, EMBEDDING_BATCH_SIZE):
        batch = new_rows[batch_start : batch_start + EMBEDDING_BATCH_SIZE]
        texts = [r["chunk_text"] for r in batch]
        vecs = embeddings.embed_documents(texts)

        for r, vec in zip(batch, vecs):
            out_rows.append((
                r["chunk_id"],
                vec,
                EMBEDDING_MODEL,
                now,
            ))

        done = min(batch_start + EMBEDDING_BATCH_SIZE, total)
        if done % 500 == 0 or done == total:
            print(f"  Embedded {done}/{total}")

    # 5. Write to Delta via MERGE
    schema = (
        "chunk_id string, embedding array<float>, "
        "embedding_model string, embedded_ts timestamp"
    )
    src_df = spark.createDataFrame(out_rows, schema=schema)
    src_df.createOrReplaceTempView("_embed_src")

    spark.sql(f"""
        MERGE INTO {EMBEDDINGS_TABLE} AS tgt
        USING _embed_src AS src
        ON tgt.chunk_id = src.chunk_id AND tgt.embedding_model = src.embedding_model
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)

    elapsed = time.monotonic() - t0
    return {
        "rows_written": len(out_rows),
        "embedding_dim": EMBEDDING_DIM,
        "second_run_rows": 0,
        "elapsed_seconds": round(elapsed, 1),
    }


def main():
    from databricks.connect import DatabricksSession

    spark = DatabricksSession.builder.serverless(True).getOrCreate()

    print("=== Build SEC Chunk Embeddings ===")
    print(f"Model: {EMBEDDING_MODEL} ({EMBEDDING_DIM}-d)")
    print(f"Source: {CHUNKS_TABLE}")
    print(f"Target: {EMBEDDINGS_TABLE}")
    print()

    result = build(spark)
    print(f"\nFirst run:  {result['rows_written']} rows written in {result['elapsed_seconds']}s")

    # Second run to verify idempotency
    result2 = build(spark)
    print(f"Second run: {result2['rows_written']} rows written (expect 0)")

    return result


if __name__ == "__main__":
    main()