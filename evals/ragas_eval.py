"""
evals/ragas_eval.py -- RAGAS-equivalent LLM-judge evaluation for RAG Workbench.

Implements the four canonical RAGAS metrics as direct LLM-judge calls,
using the same CHAT_PROVIDER / API keys already in .env.
No `ragas` package required -- works on Python 3.14.

Metrics:
  faithfulness      -- are answer claims grounded in retrieved context?
  answer_relevancy  -- does the answer address the question?
  context_precision -- fraction of retrieved chunks that are relevant?
  context_recall    -- does the context contain what's needed to answer?

Usage:
    python evals/ragas_eval.py
    python evals/ragas_eval.py --api-url http://localhost:8000
    python evals/ragas_eval.py --mode baseline
    python evals/ragas_eval.py --id 1,2,3
    python evals/ragas_eval.py --metrics faithfulness,answer_relevancy
    EVAL_API_URL=http://... python evals/ragas_eval.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from api.config import Config

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.csv"
RESULTS_DIR = Path(__file__).parent / "results"
PROJECT_ROOT = Path(__file__).parent.parent

sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# LLM client (uses centralized provider config)
# ---------------------------------------------------------------------------

_llm_cfg: dict | None = None


def _get_llm_cfg() -> dict:
    global _llm_cfg
    if _llm_cfg is None:
        _llm_cfg = Config.get_provider_config()
    return _llm_cfg


def _llm_call(prompt: str, max_tokens: int = 256) -> str:
    """
    Single-shot LLM call using the configured CHAT_PROVIDER.
    Returns the model's text response.
    """
    cfg = _get_llm_cfg()

    resp = requests.post(
        f"{cfg['base_url']}/chat/completions",
        headers={"Authorization": f"Bearer {cfg['api_key']}",
                 "Content-Type": "application/json"},
        json={
            "model": cfg["model"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _parse_json_score(text: str, key: str = "score") -> Optional[float]:
    """Extract a float score from an LLM JSON response."""
    try:
        # Try clean JSON first
        data = json.loads(text)
        val = data.get(key)
        if val is not None:
            return float(val)
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: regex hunt for the key
    m = re.search(rf'"{key}"\s*:\s*([\d.]+)', text)
    if m:
        return float(m.group(1))
    # Last resort: first float in the string
    m = re.search(r'\b(0\.\d+|1\.0|0|1)\b', text)
    return float(m.group(1)) if m else None

# ---------------------------------------------------------------------------
# RAGAS-equivalent metric implementations
# ---------------------------------------------------------------------------

_FAITHFULNESS_PROMPT = """\
You are evaluating a RAG (retrieval-augmented generation) system.

Given the retrieved contexts below and the generated answer, determine what
fraction of the answer's factual claims are explicitly supported by the contexts.

Retrieved contexts:
{contexts}

Generated answer:
{answer}

Score from 0.0 to 1.0:
  1.0 = every claim in the answer is directly supported by the contexts
  0.5 = roughly half the claims are supported
  0.0 = the answer makes claims not found in the contexts at all

Respond with ONLY valid JSON: {{"score": <float>, "reasoning": "<one sentence>"}}
"""

_ANSWER_RELEVANCY_PROMPT = """\
You are evaluating a RAG system.

Given the question and the generated answer, rate how directly and completely
the answer addresses what was asked.

Question: {question}

Generated answer: {answer}

Score from 0.0 to 1.0:
  1.0 = answer directly and completely addresses the question
  0.5 = answer is partially relevant or incomplete
  0.0 = answer is off-topic or refuses to answer a question that has an answer

Respond with ONLY valid JSON: {{"score": <float>, "reasoning": "<one sentence>"}}
"""

_CONTEXT_PRECISION_PROMPT = """\
You are evaluating a RAG system.

Given the question and the list of retrieved text chunks, determine what
fraction of the chunks are actually relevant to answering the question.

Question: {question}

Retrieved chunks:
{contexts}

For each chunk, assign 1 (relevant) or 0 (not relevant).
precision = relevant_chunks / total_chunks

Respond with ONLY valid JSON:
{{"chunk_scores": [<0 or 1>, ...], "precision": <float>, "reasoning": "<one sentence>"}}
"""

_CONTEXT_RECALL_PROMPT = """\
You are evaluating a RAG system.

Given the expected answer (ground truth) and the retrieved contexts, determine
what fraction of the information needed to produce the ground truth answer is
present in the contexts.

Expected answer (ground truth): {ground_truth}

Retrieved contexts:
{contexts}

Score from 0.0 to 1.0:
  1.0 = contexts contain all information needed to derive the ground truth answer
  0.5 = contexts contain some but not all needed information
  0.0 = contexts contain none of the needed information

Respond with ONLY valid JSON: {{"score": <float>, "reasoning": "<one sentence>"}}
"""


def _fmt_contexts(contexts: list[str]) -> str:
    return "\n\n".join(f"[{i+1}] {c[:600]}" for i, c in enumerate(contexts))


def score_faithfulness(answer: str, contexts: list[str]) -> tuple[Optional[float], str]:
    if not answer or not contexts:
        return None, "skipped -- no answer or no contexts"
    prompt = _FAITHFULNESS_PROMPT.format(
        contexts=_fmt_contexts(contexts), answer=answer[:1000]
    )
    try:
        raw = _llm_call(prompt)
        score = _parse_json_score(raw, "score")
        reason = json.loads(raw).get("reasoning", "") if score is not None else raw[:80]
        return score, reason or raw[:80]
    except Exception as e:
        return None, f"LLM error: {e}"


def score_answer_relevancy(question: str, answer: str) -> tuple[Optional[float], str]:
    if not answer:
        return None, "skipped -- no answer"
    prompt = _ANSWER_RELEVANCY_PROMPT.format(question=question, answer=answer[:1000])
    try:
        raw = _llm_call(prompt)
        score = _parse_json_score(raw, "score")
        reason = json.loads(raw).get("reasoning", "") if score is not None else raw[:80]
        return score, reason or raw[:80]
    except Exception as e:
        return None, f"LLM error: {e}"


def score_context_precision(question: str, contexts: list[str]) -> tuple[Optional[float], str]:
    if not contexts:
        return None, "skipped -- no contexts"
    prompt = _CONTEXT_PRECISION_PROMPT.format(
        question=question, contexts=_fmt_contexts(contexts)
    )
    try:
        raw = _llm_call(prompt, max_tokens=512)
        score = _parse_json_score(raw, "precision")
        reason = json.loads(raw).get("reasoning", "") if score is not None else raw[:80]
        return score, reason or raw[:80]
    except Exception as e:
        return None, f"LLM error: {e}"


def score_context_recall(ground_truth: str, contexts: list[str]) -> tuple[Optional[float], str]:
    if not ground_truth or not contexts:
        return None, "skipped -- no ground truth or no contexts"
    prompt = _CONTEXT_RECALL_PROMPT.format(
        ground_truth=ground_truth[:500], contexts=_fmt_contexts(contexts)
    )
    try:
        raw = _llm_call(prompt)
        score = _parse_json_score(raw, "score")
        reason = json.loads(raw).get("reasoning", "") if score is not None else raw[:80]
        return score, reason or raw[:80]
    except Exception as e:
        return None, f"LLM error: {e}"

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

SCORERS = {
    "faithfulness":      score_faithfulness,
    "answer_relevancy":  score_answer_relevancy,
    "context_precision": score_context_precision,
    "context_recall":    score_context_recall,
}


def load_golden_set(
    filter_ids: Optional[list[str]] = None,
    filter_mode: Optional[str] = None,
) -> list[dict]:
    rows = []
    with open(GOLDEN_SET_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if filter_ids and row["id"] not in filter_ids:
                continue
            if filter_mode and row["failure_mode"] != filter_mode:
                continue
            rows.append(row)
    return rows


def call_api(api_url: str, question: str, ticker: str, timeout: int = 60) -> dict:
    try:
        resp = requests.post(
            f"{api_url}/api/chat/auditable-rag",
            json={"message": question, "ticker": ticker},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"answer": "", "sources": [], "verification": {}, "error": str(e)}


def _extract_contexts(response: dict) -> list[str]:
    sources = response.get("sources") or []
    texts = []
    for s in sources:
        if isinstance(s, dict):
            t = s.get("text") or s.get("content") or s.get("chunk_text") or ""
            if t:
                texts.append(str(t)[:1500])
    return texts or []

# ---------------------------------------------------------------------------
# Main eval loop
# ---------------------------------------------------------------------------

def run(
    api_url: str,
    metric_names: list[str],
    delay: float = 2.0,
    filter_ids: Optional[list[str]] = None,
    filter_mode: Optional[str] = None,
) -> dict:
    unknown = [m for m in metric_names if m not in SCORERS]
    if unknown:
        print(f"[ERROR] Unknown metrics: {unknown}. Choose from: {list(SCORERS)}")
        sys.exit(1)

    questions = load_golden_set(filter_ids=filter_ids, filter_mode=filter_mode)
    if not questions:
        print("No questions matched the filter.")
        sys.exit(1)

    Config.validate_startup()
    provider = Config.CHAT_PROVIDER
    print(f"\n{'='*68}")
    print(f"  RAGAS-equivalent Eval  --  {len(questions)} question(s)")
    print(f"  Metrics : {', '.join(metric_names)}")
    print(f"  LLM     : {provider}  |  API: {api_url}")
    print(f"{'='*68}\n")

    results = []
    for q in questions:
        qid   = q["id"]
        ticker = q["ticker"]
        mode   = q.get("failure_mode", "unknown")
        diff   = q.get("difficulty", "?")

        print(f"  Q{qid:>2} [{mode:<22}] {ticker} -- fetching ...", end=" ", flush=True)
        response = call_api(api_url, q["question"], ticker)
        answer   = response.get("answer", "")
        contexts = _extract_contexts(response)
        err      = response.get("error", "")
        print(f"{'ERROR' if err else 'ok'} ({len(contexts)} ctx)", flush=True)
        time.sleep(delay * 0.3)   # small gap before LLM calls

        row: dict = {
            "id": qid, "ticker": ticker, "failure_mode": mode, "difficulty": diff,
            "question": q["question"], "answer_snippet": answer[:150],
            "n_contexts": len(contexts), "api_error": err,
        }

        for metric in metric_names:
            print(f"       scoring {metric} ...", end=" ", flush=True)
            scorer = SCORERS[metric]
            if metric == "faithfulness":
                score, reason = scorer(answer, contexts)
            elif metric == "answer_relevancy":
                score, reason = scorer(q["question"], answer)
            elif metric == "context_precision":
                score, reason = scorer(q["question"], contexts)
            elif metric == "context_recall":
                score, reason = scorer(q["expected_answer"], contexts)
            else:
                score, reason = None, "unknown metric"

            row[metric] = score
            row[f"{metric}_reason"] = reason
            disp = f"{score:.2f}" if score is not None else "N/A"
            print(disp, flush=True)
            time.sleep(delay)

        valid_scores = [v for k, v in row.items() if k in metric_names and v is not None]
        row["overall"] = round(sum(valid_scores) / len(valid_scores), 3) if valid_scores else None
        results.append(row)
        print()

    return _summarise(results, metric_names)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _safe_avg(values: list) -> Optional[float]:
    v = [x for x in values if x is not None]
    return round(sum(v) / len(v), 3) if v else None


def _summarise(results: list[dict], metric_names: list[str]) -> dict:
    n = len(results)
    print(f"\n{'='*68}")
    print(f"  Summary  ({n} questions)")
    print(f"{'='*68}")

    summary: dict[str, Optional[float]] = {}
    for m in metric_names + ["overall"]:
        vals = [r[m] for r in results if m in r]
        avg = _safe_avg(vals)
        summary[m] = avg
        if avg is not None:
            bar = "#" * int(avg * 30) + "-" * (30 - int(avg * 30))
            print(f"  {m:<22}  {bar}  {avg:.3f}")
        else:
            print(f"  {m:<22}  (no scores)")

    by_mode: dict[str, list] = {}
    for r in results:
        by_mode.setdefault(r["failure_mode"], []).append(r.get("overall"))

    print(f"\n  By failure mode:")
    for mode, scores in sorted(by_mode.items()):
        avg = _safe_avg(scores)
        disp = f"{avg:.3f}" if avg is not None else "N/A"
        print(f"    {mode:<24} {disp}  (n={len(scores)})")

    print(f"\n{'='*68}\n")

    return {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metric_names,
        "n": n,
        "summary": summary,
        "by_failure_mode": {k: _safe_avg(v) for k, v in by_mode.items()},
        "results": results,
    }

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_results(data: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"ragas_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    csv_path = out_dir / f"ragas_{ts}.csv"
    if data["results"]:
        cols = ["id", "ticker", "failure_mode", "difficulty"] + data["metrics"] + ["overall", "api_error", "answer_snippet"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(data["results"])
    return path

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="RAGAS-equivalent LLM-judge evaluation for RAG Workbench"
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("EVAL_API_URL", "http://localhost:8000"),
    )
    parser.add_argument(
        "--metrics",
        default="faithfulness,answer_relevancy,context_precision,context_recall",
        help="Comma-separated metrics to run",
    )
    parser.add_argument("--id",    dest="filter_id",   default=None,
                        help="Comma-separated question IDs, e.g. --id 1,2,5")
    parser.add_argument("--mode",  dest="filter_mode",  default=None,
                        help="Filter by failure_mode, e.g. --mode baseline")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds between LLM calls (default: 2.0)")
    parser.add_argument("--out",   default=str(RESULTS_DIR))
    args = parser.parse_args()

    metric_names = [m.strip() for m in args.metrics.split(",") if m.strip()]
    filter_ids   = [i.strip() for i in args.filter_id.split(",")] if args.filter_id else None

    data = run(
        api_url=args.api_url,
        metric_names=metric_names,
        delay=args.delay,
        filter_ids=filter_ids,
        filter_mode=args.filter_mode,
    )
    out_path = save_results(data, Path(args.out))
    print(f"  Results saved -> {out_path}")
