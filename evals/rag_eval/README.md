# RAG Eval Harness

Deterministic retrieval evaluation for the SEC RAG pipeline. No LLM calls in retrieval mode.

## Quick Start

### Offline smoke run (no network, no Spark, no Databricks)

```bash
python -m evals.rag_eval \
  --adapter jsonl \
  --golden tests/rag/fixtures/rag_eval/golden_smoke.jsonl \
  --corpus tests/rag/fixtures/rag_eval/corpus_smoke.jsonl \
  --embeddings tests/rag/fixtures/rag_eval/embeddings_smoke.npz \
  --smoke-ids smoke-001,smoke-002,smoke-003,smoke-004,smoke-005 \
  --output-dir /tmp/rag-eval-smoke
```

### Full offline run (requires local corpus and embeddings)

```bash
python -m evals.rag_eval \
  --adapter jsonl \
  --golden evals/golden/golden_v1.jsonl \
  --corpus evals/data/sec_corpus.jsonl \
  --embeddings evals/data/sec_embeddings_bge_small.npz \
  --mode all \
  --ticker-filter both
```

### Live run (requires Databricks connectivity)

```bash
python -m evals.rag_eval \
  --adapter delta \
  --golden evals/golden/golden_v1.jsonl \
  --corpus /dev/null \
  --mode all \
  --ticker-filter both
```

## Retrieval Modes

| Mode | Description |
|------|-------------|
| `bm25` | BM25 keyword search only |
| `dense` | Dense vector cosine similarity only |
| `hybrid_rrf` | BM25 + Dense with Reciprocal Rank Fusion (k=60) |
| `hybrid_rerank` | Hybrid RRF + cross-encoder reranking |

## Ticker Filter

| Setting | Description |
|---------|-------------|
| `on` | Filter results to the golden item's ticker |
| `off` | No ticker filter (all companies eligible) |
| `both` | Run both configurations |

Combined with 4 modes, this yields 8 ablation configurations.

## Metrics

### Primary (chunk-level)
- **recall@k**: Fraction of gold chunk IDs found in top-k results
- **MRR@10**: Reciprocal rank of first relevant chunk in top-10
- **nDCG@10**: Normalized discounted cumulative gain with binary relevance

### Secondary (accession+section-level)
- Same metrics applied to unique `(accession, section)` keys derived from gold chunks

### PIT Leakage
- Count of returned chunks with `accepted_ts > as_of`
- **Hard gate**: any nonzero leakage fails the run

### Abstention/Trap
- `allowed_top_hit`: True iff top-1 is temporally allowed
- `abstention_label`: Heuristic label for unanswerable items

## Embedding Sidecar

The `.npz` sidecar contains:
- `embeddings`: float32 array (N x dimension)
- `chunk_ids`: string array (N)
- `embedding_model`: model name string
- `dimension`: int
- `normalized`: bool
- `corpus_sha256`: SHA-256 of the corpus JSONL

### Creating a sidecar from Delta (one-time export)

```bash
python -c "
from evals.rag_eval.corpus import export_delta_embeddings
from pathlib import Path
export_delta_embeddings(Path('evals/data/sec_embeddings_bge_small.npz'))
"
```

### Creating a sidecar locally with bge-small

```bash
python -c "
from evals.rag_eval.corpus import build_local_embeddings
from pathlib import Path
build_local_embeddings(
    corpus_path=Path('evals/data/sec_corpus.jsonl'),
    output_path=Path('evals/data/sec_embeddings_bge_small.npz'),
    model_name='BAAI/bge-small-en-v1.5',
)
"
```

### Creating a sidecar from pre-computed arrays

If you have embeddings from another source (e.g., a different model, a batch job),
use the `build_sidecar` CLI:

```bash
python -m evals.rag_eval.build_sidecar \
  --npy embeddings.npy \
  --ids chunk_ids.txt \
  --corpus corpus.jsonl \
  --out sidecar.npz \
  --model "BAAI/bge-small-en-v1.5" \
  --normalized
```

Supported formats:
- `--npy`: `.npy` (NumPy array) or `.f32` (raw float32 binary, requires `--dim`)
- `--ids`: `.npy` (NumPy array) or `.txt` (one ID per line)

The tool validates embedding/ID count and computes the corpus SHA-256 hash.

**Do not commit the full corpus, full embeddings, or generated reports.**

## Generation Mode (Phase 2)

Generation judging is optional and disabled by default. To enable:

```bash
python -m evals.rag_eval \
  --adapter jsonl \
  --golden ... \
  --corpus ... \
  --generation \
  --allow-paid-calls
```

Requires a real agent hook. The default `unwired_agent_hook` raises `NotImplementedError`.

## PIT Gate

Point-in-time filtering is applied **before scoring** in every retrieval mode.
Future filings (accepted after `as_of`) must never influence ranking.

Any nonzero PIT leakage count fails the run immediately. This is a hard gate.

## CI Policy

- No model downloads in tests
- No network calls in tests
- No paid API calls without `--allow-paid-calls`
- No pyspark imports in offline mode
- Fixtures are synthetic and small enough to commit

## Tests

```bash
python -m pytest -q tests/rag/test_rag_eval_corpus.py tests/rag/test_rag_eval_metrics.py tests/rag/test_rag_eval_retrieval.py tests/rag/test_rag_eval_generation.py tests/rag/test_rag_eval_report.py -m "not spark and not lakebase and not databricks"
```