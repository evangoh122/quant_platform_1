"""
sec_analyzer.py — DeepSeek/MiMo-powered structured extraction from SEC filing chunks.

Extracts three signal types for bank analyst workflows:
  - named_entities   : executives, auditors, subsidiaries
  - risk_flags       : going concern, litigation, regulatory actions, restatement risk
  - forward_looking  : guidance statements with sentiment tag

Routes through Config.get_provider_config() so CHAT_PROVIDER=deepseek|mimo
controls the backend — no hardcoded model.
"""
from __future__ import annotations

import json
import re
from typing import Optional

import requests
from loguru import logger

from api.config import Config
from api.services.llm_health import get_llm_tracker
from api.services.polygon_verifier import run_checks as polygon_run_checks


# ---------------------------------------------------------------------------
# LLM client (same pattern as evals/ragas_eval.py)
# ---------------------------------------------------------------------------

def _llm_call(prompt: str, max_tokens: int = 1024) -> str:
    cfg = Config.get_provider_config()
    tracker = get_llm_tracker()
    import time as _time
    start = _time.monotonic()
    try:
        resp = requests.post(
            f"{cfg['base_url']}/chat/completions",
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": cfg["model"],
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": cfg.get("temperature", 0.1),
            },
            timeout=60,
        )
        elapsed = _time.monotonic() - start
        if elapsed > 30:
            logger.warning(f"Slow LLM call in sec_analyzer: {elapsed:.1f}s (max_tokens={max_tokens})")
        resp.raise_for_status()
        body = resp.json()
        choices = body.get("choices")
        if not choices:
            raise ValueError(f"Provider returned no choices: {body.get('error', body)}")
        result = choices[0]["message"]["content"].strip()
        tracker.record_success()
        return result
    except Exception as e:
        tracker.record_failure(str(e), context="sec_analyzer/llm")
        raise


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return {}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_ENTITY_PROMPT = """\
You are analyzing SEC filing text for a bank analyst.

Extract all named entities from the text below into three categories:
1. executives — C-suite officers, board members, named individuals
2. auditors — external audit firms explicitly named
3. subsidiaries — named subsidiary or affiliate entities

Text:
{text}

Respond with ONLY valid JSON:
{{"executives": ["name", ...], "auditors": ["name", ...], "subsidiaries": ["name", ...]}}
"""

_RISK_PROMPT = """\
You are a bank analyst reviewing an SEC filing for risk signals.

Identify any of the following risk flags present in the text:
- going_concern    : language about ability to continue as a going concern
- litigation       : pending lawsuits, legal proceedings, regulatory investigations
- restatement_risk : references to prior-period errors, restatements, or material weaknesses
- regulatory_action: SEC enforcement, CFTC, DOJ, or other named regulatory actions
- debt_covenant    : mentions of covenant breaches, waivers, or accelerated repayment

Text:
{text}

For each flag found, quote the key phrase. Respond with ONLY valid JSON:
{{"flags": [{{"type": "going_concern|litigation|restatement_risk|regulatory_action|debt_covenant", "excerpt": "quoted phrase", "severity": "high|medium|low"}}, ...]}}

Return an empty list if no flags are found: {{"flags": []}}
"""

_FORWARD_LOOKING_PROMPT = """\
You are analyzing an SEC filing for forward-looking statements relevant to a bank analyst.

Extract statements about future expectations, guidance, or projections.
Classify each as: positive (upbeat guidance), negative (cautionary), or neutral.

Text:
{text}

Respond with ONLY valid JSON:
{{"statements": [{{"text": "quoted statement", "sentiment": "positive|negative|neutral", "topic": "revenue|margins|capex|headcount|demand|other"}}, ...]}}

Limit to the 5 most significant statements. Return empty list if none found: {{"statements": []}}
"""


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------

def _fmt_chunks(chunks: list[str], max_chunks: int, max_chars: int = 800) -> str:
    return "\n\n".join(c[:max_chars] for c in chunks[:max_chunks])


def extract_named_entities(chunks: list[str]) -> dict:
    text = _fmt_chunks(chunks, max_chunks=4)
    try:
        raw = _llm_call(_ENTITY_PROMPT.format(text=text))
        result = _parse_json(raw)
        return {
            "executives": result.get("executives", []),
            "auditors": result.get("auditors", []),
            "subsidiaries": result.get("subsidiaries", []),
        }
    except Exception as e:
        logger.warning(f"Named entity extraction failed: {e}")
        return {"executives": [], "auditors": [], "subsidiaries": []}


def extract_risk_flags(chunks: list[str]) -> list[dict]:
    text = _fmt_chunks(chunks, max_chunks=6)
    try:
        raw = _llm_call(_RISK_PROMPT.format(text=text), max_tokens=1536)
        return _parse_json(raw).get("flags", [])
    except Exception as e:
        logger.warning(f"Risk flag extraction failed: {e}")
        return []


def extract_forward_looking(chunks: list[str]) -> list[dict]:
    text = _fmt_chunks(chunks, max_chunks=6)
    try:
        raw = _llm_call(_FORWARD_LOOKING_PROMPT.format(text=text), max_tokens=1536)
        return _parse_json(raw).get("statements", [])
    except Exception as e:
        logger.warning(f"Forward-looking extraction failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_filing(
    chunks: list[str],
    ticker: str,
    xbrl_facts: Optional[list[dict]] = None,
) -> dict:
    """Run extractors on filing chunks and cross-check against Polygon.io."""
    extraction_errors: list[str] = []

    named_entities = extract_named_entities(chunks)
    if not any(named_entities.values()):
        extraction_errors.append("named_entities: all extractors returned empty")

    risk_flags = extract_risk_flags(chunks)

    forward_looking = extract_forward_looking(chunks)

    result: dict = {
        "ticker": ticker,
        "named_entities": named_entities,
        "risk_flags": risk_flags,
        "forward_looking": forward_looking,
        "chunk_count": len(chunks),
        "model": Config.get_provider_config()["model"],
        "extraction_errors": extraction_errors,
        "polygon_verification": None,
    }

    api_key = Config.POLYGON_API_KEY
    if api_key:
        try:
            result["polygon_verification"] = polygon_run_checks(
                ticker=ticker,
                api_key=api_key,
                sec_analysis=result,
                xbrl_facts=xbrl_facts,
            )
        except Exception as e:
            logger.warning(f"Polygon verification failed (non-fatal): {e}")
            result["polygon_verification"] = {"errors": [str(e)]}
    else:
        logger.debug("POLYGON_API_KEY not set — skipping Polygon cross-checks")

    return result
