"""evals/rag_eval/generation.py — Optional phase 2 generation judging.

Gate all calls behind CLI ``--generation``; additionally require
``--allow-paid-calls`` (or a local judge configuration) before any remote
request.  Tests inject fake hooks/judges; CI cannot access network or secrets.
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Protocol, Sequence

from evals.rag_eval.models import GoldenItem, ItemResult, RetrievalHit


# ── Agent hook ────────────────────────────────────────────────────────────────

class AgentResponse(Protocol):
    """Protocol for agent responses."""
    answer: str
    sources: list[dict[str, Any]]


AgentHook = Callable[[GoldenItem, list[RetrievalHit]], AgentResponse]


def unwired_agent_hook(item: GoldenItem, hits: list[RetrievalHit]) -> AgentResponse:
    """Default agent hook that raises NotImplementedError.

    To use generation mode, provide a real agent hook that calls your RAG
    pipeline and returns an AgentResponse.
    """
    raise NotImplementedError(
        "Generation mode requires a real agent hook.  "
        "Pass a callable that takes (GoldenItem, list[RetrievalHit]) and returns "
        "an AgentResponse with .answer and .sources attributes.  "
        "Example: your_rag_pipeline.ask(question=item.question, contexts=[h.text for h in hits])"
    )


# ── Judge protocol ────────────────────────────────────────────────────────────

class JudgeProtocol(Protocol):
    """Protocol for LLM judge functions."""

    def __call__(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        gold_answer: Optional[str] = None,
    ) -> dict[str, Any]:
        """Score an answer. Returns dict with metric scores."""
        ...


# ── RAGAS-equivalent judge functions ──────────────────────────────────────────

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


def create_ragas_judge(
    llm_call: Callable[[str, int], str],
) -> JudgeProtocol:
    """Create a RAGAS-equivalent judge from an LLM call function.

    The llm_call function takes (prompt, max_tokens) and returns text.
    """
    import json
    import re

    def _parse_score(text: str, key: str = "score") -> Optional[float]:
        try:
            data = json.loads(text)
            val = data.get(key)
            if val is not None:
                return float(val)
        except (json.JSONDecodeError, ValueError):
            pass
        m = re.search(rf'"{key}"\s*:\s*([\d.]+)', text)
        if m:
            return float(m.group(1))
        m = re.search(r'\b(0\.\d+|1\.0|0|1)\b', text)
        return float(m.group(1)) if m else None

    def judge(
        question: str,
        answer: str,
        contexts: list[str],
        gold_answer: Optional[str] = None,
    ) -> dict[str, Any]:
        scores: dict[str, Any] = {}

        # Faithfulness
        if answer and contexts:
            prompt = _FAITHFULNESS_PROMPT.format(
                contexts=_fmt_contexts(contexts), answer=answer[:1000]
            )
            try:
                raw = llm_call(prompt, 256)
                scores["faithfulness"] = _parse_score(raw, "score")
            except Exception as e:
                scores["faithfulness"] = None
                scores["faithfulness_error"] = str(e)

        # Answer relevancy
        if answer:
            prompt = _ANSWER_RELEVANCY_PROMPT.format(question=question, answer=answer[:1000])
            try:
                raw = llm_call(prompt, 256)
                scores["answer_relevancy"] = _parse_score(raw, "score")
            except Exception as e:
                scores["answer_relevancy"] = None
                scores["answer_relevancy_error"] = str(e)

        # Context precision
        if contexts:
            prompt = _CONTEXT_PRECISION_PROMPT.format(
                question=question, contexts=_fmt_contexts(contexts)
            )
            try:
                raw = llm_call(prompt, 512)
                scores["context_precision"] = _parse_score(raw, "precision")
            except Exception as e:
                scores["context_precision"] = None
                scores["context_precision_error"] = str(e)

        # Context recall
        if gold_answer and contexts:
            prompt = _CONTEXT_RECALL_PROMPT.format(
                ground_truth=gold_answer[:500], contexts=_fmt_contexts(contexts)
            )
            try:
                raw = llm_call(prompt, 256)
                scores["context_recall"] = _parse_score(raw, "score")
            except Exception as e:
                scores["context_recall"] = None
                scores["context_recall_error"] = str(e)

        return scores

    return judge


# ── Generation runner ─────────────────────────────────────────────────────────

def run_generation(
    items: Sequence[GoldenItem],
    retrieval_results: list[ItemResult],
    agent_hook: AgentHook,
    judge: Optional[JudgeProtocol] = None,
    allow_paid_calls: bool = False,
) -> dict[str, Any]:
    """Run generation and judging on retrieval results.

    Requires explicit --generation flag and --allow-paid-calls for remote calls.
    Returns dict with per-item generation results.
    """
    if not allow_paid_calls and judge is not None:
        raise RuntimeError(
            "Generation judging requires --allow-paid-calls or a local judge. "
            "Set --allow-paid-calls to enable remote LLM calls."
        )

    results: dict[str, Any] = {"items": [], "errors": []}

    for ir in retrieval_results:
        item_result: dict[str, Any] = {
            "item_id": ir.item.id,
            "config": ir.config.label(),
        }

        try:
            response = agent_hook(ir.item, ir.hits)
            item_result["answer"] = response.answer
            item_result["sources"] = response.sources

            if judge is not None:
                contexts = [h.text for h in ir.hits]
                judge_scores = judge(
                    question=ir.item.question,
                    answer=response.answer,
                    contexts=contexts,
                    gold_answer=ir.item.gold_answer,
                )
                item_result["judge_scores"] = judge_scores

        except NotImplementedError as e:
            item_result["error"] = str(e)
            results["errors"].append(str(e))
        except Exception as e:
            item_result["error"] = f"{type(e).__name__}: {e}"
            results["errors"].append(str(e))

        results["items"].append(item_result)

    return results