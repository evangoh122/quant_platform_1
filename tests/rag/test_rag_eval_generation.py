"""tests/rag/test_rag_eval_generation.py — Tests for generation module."""
from __future__ import annotations

import pytest

from evals.rag_eval.generation import (
    create_ragas_judge,
    run_generation,
    unwired_agent_hook,
)
from evals.rag_eval.models import GoldenItem, ItemResult, RetrievalConfig, RetrievalHit


def _hit(cid="c1") -> RetrievalHit:
    return RetrievalHit(
        chunk_id=cid, ticker="X", accession="A1", section="s1",
        form_type="10-K", accepted_ts="2024-01-01T00:00:00+00:00",
        text=f"text of {cid}", rank=1,
    )


def _item() -> GoldenItem:
    return GoldenItem(id="t1", ticker="X", question="What is X?")


def _item_result() -> ItemResult:
    return ItemResult(
        item=_item(),
        config=RetrievalConfig(mode="bm25", ticker_filter=True),
        hits=[_hit()],
    )


class TestGenerationDefaultIsDisabled:
    """test_generation_default_is_disabled"""

    def test_generation_requires_explicit_flag(self):
        """run_generation without allow_paid_calls raises."""
        with pytest.raises(RuntimeError, match="allow-paid-calls"):
            run_generation(
                [_item()],
                [_item_result()],
                unwired_agent_hook,
                judge=lambda q, a, c, g=None: {},
                allow_paid_calls=False,
            )


class TestUnwiredHookFailsClearly:
    """test_unwired_hook_fails_clearly"""

    def test_unwired_hook_raises(self):
        with pytest.raises(NotImplementedError, match="real agent hook"):
            unwired_agent_hook(_item(), [_hit()])


class TestPaidCallsNeedExplicitOptIn:
    """test_paid_calls_need_explicit_opt_in"""

    def test_allow_paid_calls_false_blocks(self):
        with pytest.raises(RuntimeError, match="allow-paid-calls"):
            run_generation(
                [_item()],
                [_item_result()],
                unwired_agent_hook,
                judge=lambda q, a, c, g=None: {"faithfulness": 0.5},
                allow_paid_calls=False,
            )

    def test_allow_paid_calls_true_allows(self):
        """With allow_paid_calls=True but unwired hook, errors are captured not raised."""
        results = run_generation(
            [_item()],
            [_item_result()],
            unwired_agent_hook,
            judge=None,
            allow_paid_calls=True,
        )
        # unwired hook raises NotImplementedError, but it's caught
        assert len(results["items"]) == 1
        assert "error" in results["items"][0]


class TestFakeGenerationMetrics:
    """test_fake_generation_metrics_accept_question_answer_contexts"""

    def test_fake_judge_receives_correct_args(self):
        """Fake judge receives question, answer, contexts, gold_answer."""
        received = {}

        def fake_judge(question, answer, contexts, gold_answer=None):
            received["question"] = question
            received["answer"] = answer
            received["contexts"] = contexts
            received["gold_answer"] = gold_answer
            return {"faithfulness": 0.9}

        def fake_hook(item, hits):
            class Resp:
                pass
            resp = Resp()
            resp.answer = "fake answer"
            resp.sources = []
            return resp

        results = run_generation(
            [_item()],
            [_item_result()],
            fake_hook,
            judge=fake_judge,
            allow_paid_calls=True,
        )

        assert received["question"] == "What is X?"
        assert received["answer"] == "fake answer"
        assert len(received["contexts"]) == 1
        assert received["contexts"][0] == "text of c1"