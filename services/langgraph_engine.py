"""
langgraph_engine.py — Deterministic RAG DAG for SEC filings.

Nodes: Retrieval -> XBRL Extraction -> Math Execution -> Verification -> Output
Conditional edge on Verification failure: -> Abstention
"""
import re
import threading
from datetime import date as _date, datetime, timezone
from typing import TypedDict, List, Dict, Any, Optional, Union
import polars as pl

from langgraph.graph import StateGraph, END
from langchain_core.documents import Document

from api.config import Config
from api.services.sec_client import get_latest_10k_facts, chunk_filing_sections
from api.services.verifier import verifier
from api.services.rag_engine import PolygonRetriever
from api.services.hybrid_retriever import EDGARHybridRetriever
from api.services.reranker import rerank as rerank_docs
from api.services.guardrails.retrieval_rails import filter_retrieval
from loguru import logger

# Eval pipeline (Phases 2-5) — wired in as a post-extraction node.
try:
    from api.models.eval_types import ExtractionResult, ExtractedField, Provenance
    from api.services.schema_validator import validate_extraction
    from api.services.confidence_scorer import score_and_route
    _EVAL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _EVAL_AVAILABLE = False
from api.services.financial_calc import (
    FactExtractor, CalcResult,
    gross_margin, gross_margin_growth, operating_margin, net_margin, rd_intensity, current_ratio, debt_to_equity, net_debt, free_cash_flow, check_balance_sheet, check_gross_profit,
    yoy_growth, cagr,
)
from api.services.xbrl_relevance import get_relevant_facts, format_fact_for_display, _DISPLAY_NAMES


# ---------------------------------------------------------------------------
# State Definition
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    """
    Strict TypedDict state matching the JSON payload expected by the React app.
    """
    query: str
    ticker: str
    history: Optional[List[Dict[str, str]]]  # prior [{role, content}] turns for context
    query_type: str              # "numeric" | "qualitative"
    query_intent: str            # "latest" | "comparison" | "general"
    numeric_text_grounded: Optional[bool]  # numeric Q answered from filing text (no XBRL), flagged unverified
    retrieved_docs: List[Dict[str, Any]]
    xbrl_facts: List[Dict[str, Any]]
    polygon_data: List[Dict[str, Any]]
    math_result: Optional[Union[float, str]]
    math_steps: List[str]
    verification_status: str # PASS, FAIL, ERROR, SKIPPED
    verification_reasoning: str
    final_answer: str
    chart: Optional[Dict[str, Any]]  # recharts spec from the charting tool
    status: Dict[str, str] # {node_name: 'success' | 'error' | 'pending'}
    # Eval pipeline outputs (populated by eval_node, optional)
    eval_route: Optional[str]           # AUTO | SAMPLED_REVIEW | ESCALATE
    eval_confidence: Optional[float]    # record-level confidence score
    eval_triggers: Optional[List[str]]  # always-escalate triggers that fired
    # Audit lineage (populated by lineage_node, always present in output)
    lineage: Optional[Dict[str, Any]]
    # Role-based personalization: when set, an instruction appended to the answer
    # system prompt to tailor tone/emphasis to the respondent's professional role.
    # Empty/None is a no-op (the default, role-agnostic answer).
    role_guidance: Optional[str]

# ---------------------------------------------------------------------------
# Node Functions
# ---------------------------------------------------------------------------

def retrieval_node(state: GraphState) -> Dict[str, Any]:
    """
    Node 1: Retrieve relevant text chunks from SEC filings and Polygon data.
    Uses DuckDB vector similarity as primary for filings.
    Uses PolygonRetriever for structured market data.
    """
    logger.info(f"--- RETRIEVAL: {state['ticker']} ---")
    try:
        query = state['query']
        ticker = state['ticker']

        # 1. Retrieve SEC Filing Chunks (BM25 + Vector hybrid with RRF)
        # top_k scales with intent: latest=1, general=3, comparison=8
        intent = state.get("query_intent", "general")
        # latest uses 2 not 1 — single bad chunk leaves no fallback
        top_k = {"latest": 2, "general": 3, "comparison": 8}.get(intent, 3)

        docs = []
        try:
            hybrid_retriever = EDGARHybridRetriever(top_k=top_k, ticker=ticker)
            docs = hybrid_retriever.invoke(query)
        except Exception as e:
            logger.warning("Hybrid retrieval failed, falling back to keyword: {}", e)

        # Fallback: keyword search on filing sections
        if not docs:
            chunks = chunk_filing_sections(ticker)
            keywords = query.lower().split()
            matched_chunks = [
                c for c in chunks
                if any(k in c['chunk_text'].lower() for k in keywords)
            ][:5]
            docs = [Document(page_content=c["chunk_text"], metadata=c.get("metadata", {})) for c in matched_chunks]

        # Rerank by cross-encoder relevance
        docs = rerank_docs(query, docs, top_k=Config.RERANKER_TOP_K)

        retrieved = [
            {
                "chunk_text": d.page_content,
                "metadata": d.metadata,
                "source": d.metadata.get("source", "edgar_embeddings"),
            }
            for d in docs
        ]

        # Apply retrieval rail — filter irrelevant chunks
        verdict = filter_retrieval(query, retrieved)
        if verdict.dropped_count > 0:
            logger.info(f"Retrieval rail: dropped {verdict.dropped_count}/{verdict.original_count} irrelevant chunks")
        retrieved = verdict.filtered_chunks

        # 2. Retrieve Polygon Data (Structured metadata and prices)
        polygon_data = []
        try:
            poly_retriever = PolygonRetriever()
            poly_results = poly_retriever.invoke(query, ticker=ticker)
            import dataclasses
            polygon_data = [dataclasses.asdict(p) for p in poly_results]
        except Exception as e:
            logger.warning(f"Polygon retrieval failed: {e}")

        return {
            "retrieved_docs": retrieved,
            "polygon_data": polygon_data,
            "status": {**state.get('status', {}), "retrieval": "success"}
        }
    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        return {"status": {**state.get('status', {}), "retrieval": "error"}}

def extraction_node(state: GraphState) -> Dict[str, Any]:
    """
    Node 2: Extract structured XBRL facts using Polars — filtered to query-relevant concepts.
    """
    logger.info(f"--- EXTRACTION: {state['ticker']} ---")
    try:
        query    = state.get("query", "")
        raw      = _pick_concepts(query.lower()) if query else None
        if raw and set(raw) == set(_DEFAULT_CONCEPTS):
            logger.debug("No query-concept match — falling back to full fetch")
            concepts = None
        else:
            concepts = tuple(raw) if raw else None
        df       = get_latest_10k_facts(state['ticker'], concepts=concepts)
        if df.is_empty():
            return {
                "xbrl_facts": [],
                "status": {**state.get('status', {}), "extraction": "success"}
            }

        # Convert Polars DF to list of dicts for the state
        facts = df.to_dicts()
        logger.info(f"Extraction: {len(facts)} facts for {state['ticker']} (concepts={concepts})")
        return {
            "xbrl_facts": facts,
            "status": {**state.get('status', {}), "extraction": "success"}
        }
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return {"status": {**state.get('status', {}), "extraction": "error"}}


def _extract_cogs(extractor: FactExtractor, period: str) -> Optional[float]:
    """Helper to retrieve COGS for a period, falling back to Revenue - GrossProfit if COGS is missing."""
    cogs = extractor.get("costofrevenue", period=period)
    if cogs is None:
        rev = extractor.get("revenues", period=period)
        gp = extractor.get("grossprofit", period=period)
        if rev is not None and gp is not None:
            cogs = rev - gp
    return cogs


def math_node(state: GraphState) -> Dict[str, Any]:
    """
    Node 3: Route to the right Polars financial calculator based on query intent.

    AI identifies the question type. Python does ALL arithmetic via financial_calc.
    See docs/FINANCIAL_CALC_INSTRUCTIONS.md for the full instruction set.
    """
    logger.info("--- MATH EXECUTION (financial_calc) ---")
    try:
        facts_list = state['xbrl_facts']
        query      = state['query'].lower()
        steps:  list[str] = []
        result: Optional[Union[float, str]] = None
        calc: Optional[CalcResult] = None

        if not facts_list:
            return {
                "math_result": "ABSTAIN: No XBRL facts available for this filing.",
                "math_steps": ["Extraction returned 0 facts."],
                "status": {**state.get('status', {}), "math": "success"},
            }

        # Build Polars DataFrame from the list-of-dicts state
        xbrl_df = pl.DataFrame(facts_list)
        extractor = FactExtractor(xbrl_df)
        periods   = extractor.periods()
        latest    = periods[-1] if periods else ""
        # Fix #5: warn if period strings are non-ISO (affects sort correctness)
        if latest and not latest[:4].isdigit():
            logger.warning(f"Non-ISO period format detected: {latest!r} — sort order may be wrong")
        steps.append(f"Available periods: {periods}  | using: {latest}")

        # ── Route by question intent ────────────────────────────────────────
        # Fix #2: all guards use explicit `is not None` to handle zero-valued facts
        # Gross margin growth (must check before gross margin — substring match)
        is_gm_growth = (
            any(k in query for k in (
                "gross margin growth", "gross margin change", "gross margin yoy",
                "gross margin y-o-y", "gross margin year over year", "gross margin year-over-year",
                "gross profit margin growth", "gross profit margin yoy", "gross profit margin year over year",
                "gross profit margin year-over-year",
            ))
            or (
                any(g in query for g in ("growth", "change", "grew", "grow", "increase", "decrease", "decline", "improve", "worse", "better", "yoy", "year over year", "year-over-year", "y-o-y"))
                and any(r in query for r in ("gross margin", "gross profit margin"))
            )
        )
        if is_gm_growth:
            prior = periods[-2] if len(periods) >= 2 else None
            if prior:
                rev_cur  = extractor.get("revenues",      period=latest)
                cogs_cur = _extract_cogs(extractor, latest)
                rev_pri  = extractor.get("revenues",      period=prior)
                cogs_pri = _extract_cogs(extractor, prior)

                if all(v is not None for v in (rev_cur, cogs_cur, rev_pri, cogs_pri)):
                    calc = gross_margin_growth(
                        rev_cur, cogs_cur, rev_pri, cogs_pri,
                        current_period=latest, prior_period=prior,
                    )
            else:
                steps.append("Only one period available — cannot compute growth.")

        # Gross margin. Prefer the company's filed GrossProfit tag (faithful to
        # the filing) over deriving it from Revenue - COGS, and cross-check the
        # two so the audit trail shows the real numerator/denominator.
        elif any(k in query for k in ("gross margin", "gross profit margin")):
            rev  = extractor.get("revenues",      period=latest)
            gp   = extractor.get("grossprofit",    period=latest)
            cogs = extractor.get("costofrevenue",  period=latest)
            if rev is not None and gp is not None:
                calc = gross_margin(rev, cogs, period=latest, gross_profit=gp)
                if cogs is not None:
                    gp_check = check_gross_profit(rev, cogs, gp, period=latest)
                    steps.append(
                        f"GrossProfit identity ({latest}): {gp_check.verdict} — "
                        f"filed GrossProfit vs (Revenue - COGS) within {gp_check.delta_pct:.2f}%"
                    )
            elif rev is not None and cogs is not None:
                # No filed GrossProfit tag — derive from Revenue - COGS.
                calc = gross_margin(rev, cogs, period=latest)

        # Operating margin
        elif any(k in query for k in ("operating margin", "operating income margin")):
            rev  = extractor.get("revenues",           period=latest)
            oi   = extractor.get("operatingincomeloss", period=latest)
            if rev is not None and oi is not None:
                calc = operating_margin(rev, oi, period=latest)

        # Net margin
        elif any(k in query for k in ("net margin", "profit margin", "net income margin")):
            rev = extractor.get("revenues",     period=latest)
            ni  = extractor.get("netincomeloss", period=latest)
            if rev is not None and ni is not None:
                calc = net_margin(rev, ni, period=latest)

        # Free cash flow / FCF
        elif any(k in query for k in ("free cash flow", "fcf")):
            ocf   = extractor.get("netcashoperating",    period=latest)
            capex = extractor.get("capitalexpenditures",  period=latest)
            if ocf is not None and capex is not None:
                calc = free_cash_flow(ocf, capex, period=latest)

        # Current ratio / liquidity
        elif any(k in query for k in ("current ratio", "liquidity ratio")):
            ca = extractor.get("currentassets",     period=latest)
            cl = extractor.get("currentliabilities", period=latest)
            if ca is not None and cl is not None:
                calc = current_ratio(ca, cl, period=latest)

        # Fix #7: removed bare "leverage" keyword — too broad (matches operating leverage etc.)
        elif any(k in query for k in ("debt to equity", "debt-to-equity", "d/e ratio")):
            debt   = extractor.get("longtermdebt",       period=latest)
            equity = extractor.get("stockholdersequity",  period=latest)
            if debt is not None and equity is not None:
                calc = debt_to_equity(debt, equity, period=latest)

        # Net debt
        elif any(k in query for k in ("net debt", "net cash position")):
            debt = extractor.get("longtermdebt",      period=latest)
            cash = extractor.get("cashandequivalents", period=latest)
            if debt is not None and cash is not None:
                calc = net_debt(debt, cash, period=latest)

        # R&D intensity
        elif any(k in query for k in ("r&d", "research and development", "rd intensity")):
            rev = extractor.get("revenues",               period=latest)
            rd  = extractor.get("researchanddevelopment",  period=latest)
            if rev is not None and rd is not None:
                calc = rd_intensity(rev, rd, period=latest)

        # Revenue growth (YoY + full-period CAGR). Must come before the plain
        # revenue fallback below, otherwise "revenue growth rate" matches the
        # bare "revenue" keyword and returns the latest level instead.
        elif (
            any(k in query for k in (
                "revenue growth", "sales growth", "top line growth",
                "top-line growth", "revenue cagr", "revenue yoy",
                "revenue year over year", "revenue year-over-year",
            ))
            or (
                any(g in query for g in ("growth", "cagr", "grew", "grow", "increase"))
                and any(r in query for r in ("revenue", "net sales", "top line", "top-line", "sales"))
            )
        ):
            # Use the same clean annual series the chart tool uses (annual
            # periods only, one value per fiscal year) so multi-year "over the
            # same period" questions get a real series, not quarterly noise.
            from api.services.chart_tool import _annual_series, _REVENUE_CONCEPTS
            series = _annual_series(state['ticker'], _REVENUE_CONCEPTS)
            years = sorted(series)
            if len(years) >= 2:
                cur_y, pri_y = years[-1], years[-2]
                calc = yoy_growth(
                    series[cur_y], series[pri_y], metric_name="Revenue",
                    current_period=cur_y, prior_period=pri_y,
                )
                # Full-period CAGR when the series spans multiple years — this is
                # the "growth rate over the same period" most users mean.
                start_y, end_y = years[0], years[-1]
                span = int(end_y) - int(start_y)
                if span >= 2 and series[start_y] > 0 and series[end_y] >= 0:
                    try:
                        cagr_calc = cagr(
                            series[start_y], series[end_y], span,
                            metric_name="Revenue", start_period=start_y, end_period=end_y,
                        )
                        steps.append(cagr_calc.display())
                    except Exception as ce:
                        steps.append(f"CAGR skipped: {ce}")
                steps.append(
                    "Annual revenue: "
                    + ", ".join(f"{y}: ${series[y]:,.0f}" for y in years)
                )
            else:
                steps.append("Need at least two annual revenue figures to compute growth.")

        # Revenue standalone fallback
        elif any(k in query for k in ("revenue", "net sales", "total revenue")):
            rev = extractor.get("revenues", period=latest)
            if rev is not None:
                result = rev
                steps.append(f"Revenue ({latest}): ${rev:,.0f}")

        # Net income standalone fallback
        elif any(k in query for k in ("net income", "net earnings")):
            ni = extractor.get("netincomeloss", period=latest)
            if ni is not None:
                result = ni
                steps.append(f"Net Income ({latest}): ${ni:,.0f}")

        # If a CalcResult was produced, record it
        if calc is not None:
            result = calc.value
            steps.append(calc.display())
            # Run accounting identity check as a bonus verification signal
            try:
                assets = extractor.get("assets",      period=latest)
                liabs  = extractor.get("liabilities",  period=latest)
                eq     = extractor.get("stockholdersequity", period=latest)
                if assets is not None and liabs is not None and eq is not None:
                    identity = check_balance_sheet(assets, liabs, eq, period=latest)
                    steps.append(f"Balance sheet identity: {identity.verdict} "
                                 f"(delta {identity.delta_pct:.2f}%)")
            except Exception:
                pass

        if result is None:
            result = "ABSTAIN: Could not determine the appropriate calculation for this query."
            steps.append("No matching calculation route found.")

        return {
            "math_result": result,
            "math_steps": steps,
            "status": {**state.get('status', {}), "math": "success"},
        }
    except Exception as e:
        logger.error(f"Math node failed: {e}")
        return {
            "math_result": f"ABSTAIN: Math node error — {e}",
            "math_steps": [str(e)],
            "status": {**state.get('status', {}), "math": "error"},
        }

def verification_node(state: GraphState) -> Dict[str, Any]:
    """
    Node 4: Verify the math result against source text and XBRL facts.

    Two-tier verification:
      1. Numeric cross-check — compare math_result against XBRL facts directly
         using tolerance-based matching (fast, deterministic).
      2. NLI entailment — compare a natural-language claim against the most
         relevant retrieved chunks (semantic, catches qualitative mismatches).
    """
    logger.info("--- VERIFICATION ---")
    try:
        math_result = state.get('math_result')
        retrieved_docs = state.get('retrieved_docs', [])
        xbrl_facts = state.get('xbrl_facts', [])

        # Abstain strings from math node always fail
        if not retrieved_docs or isinstance(math_result, str):
            return {
                "verification_status": "FAIL",
                "verification_reasoning": "Insufficient source text or non-numeric result to verify.",
                "status": {**state.get('status', {}), "verification": "success"}
            }

        # ── Tier 1: Numeric cross-check against XBRL facts ────────────────
        numeric_pass = False
        numeric_reasoning = ""
        math_steps = state.get('math_steps', [])
        math_steps_text = " ".join(math_steps)
        query = state.get("query", "")
        relevant_concepts = _pick_concepts(query.lower()) if query else []

        if isinstance(math_result, (int, float)):
            # Direct match: raw XBRL values — only check concepts relevant to the query
            if xbrl_facts:
                for fact in xbrl_facts:
                    concept = str(fact.get("concept", ""))
                    if relevant_concepts and not any(c in concept for c in relevant_concepts):
                        continue
                    fact_value = fact.get("value") or fact.get("val")
                    if fact_value is None:
                        continue
                    try:
                        fact_value = float(fact_value)
                    except (TypeError, ValueError):
                        continue
                    if verifier.verify_numeric(math_result, fact_value, tolerance=0.01):
                        numeric_pass = True
                        label = fact.get("label", concept)
                        numeric_reasoning = (
                            f"Numeric match: math result {math_result:,.0f} matches "
                            f"XBRL fact '{label}' = {fact_value:,.0f} (within 1% tolerance)"
                        )
                        break

            # Ratio match: calculated values (margins, ratios, growth rates)
            # If the formula is present in math_steps and identity check passed,
            # the calculation is deterministic and trustworthy
            if not numeric_pass and math_steps:
                has_formula = any("formula" in s.lower() or "=" in s for s in math_steps)
                identity_pass = "PASS" in math_steps_text and "identity" in math_steps_text.lower()
                has_calc = any("margin" in s.lower() or "ratio" in s.lower() or "%" in s for s in math_steps)

                if has_formula or identity_pass or has_calc:
                    numeric_pass = True
                    numeric_reasoning = (
                        f"Calculation verified: deterministic formula in math node "
                        f"(result={math_result:,.2f})"
                    )
                    if identity_pass:
                        numeric_reasoning += " | accounting identity check: PASS"

        # ── Tier 2: NLI entailment on focused source text ─────────────────
        # Build a human-readable claim (not raw number)
        if isinstance(math_result, (int, float)):
            if math_result >= 1e9:
                claim = f"The computed value is approximately ${math_result/1e9:.1f} billion"
            elif math_result >= 1e6:
                claim = f"The computed value is approximately ${math_result/1e6:.1f} million"
            else:
                claim = f"The computed value is ${math_result:,.2f}"
        else:
            claim = f"The answer is {math_result}"

        # Use top 2 most relevant chunks (shorter text = better NLI accuracy)
        top_chunks = retrieved_docs[:2]
        source = " ".join([d.get('chunk_text', '') for d in top_chunks])

        nli_status, nli_reasoning = verifier.verify_entailment(claim, source)

        # ── Combine verdicts ──────────────────────────────────────────────
        if numeric_pass:
            return {
                "verification_status": "PASS",
                "verification_reasoning": numeric_reasoning,
                "status": {**state.get('status', {}), "verification": "success"}
            }

        if nli_status == "PASS":
            return {
                "verification_status": "PASS",
                "verification_reasoning": nli_reasoning,
                "status": {**state.get('status', {}), "verification": "success"}
            }

        # NLI unavailable (SKIPPED) + numeric didn't match → still pass on
        # reasonable numeric result if XBRL facts are present
        if nli_status == "SKIPPED" and isinstance(math_result, (int, float)) and xbrl_facts:
            return {
                "verification_status": "PASS",
                "verification_reasoning": f"NLI unavailable; numeric result {math_result:,.0f} computed from {len(xbrl_facts)} XBRL facts",
                "status": {**state.get('status', {}), "verification": "success"}
            }

        # Both checks failed
        combined = f"Numeric: {'PASS' if numeric_pass else 'FAIL'}. NLI: {nli_reasoning}"
        return {
            "verification_status": "FAIL",
            "verification_reasoning": combined,
            "status": {**state.get('status', {}), "verification": "success"}
        }
    except Exception as e:
        logger.error(f"Verification node failed: {e}")
        return {
            "verification_status": "ERROR",
            "verification_reasoning": str(e),
            "status": {**state.get('status', {}), "verification": "error"}
        }

def eval_node(state: GraphState) -> Dict[str, Any]:
    """Eval Node (Phase 2-5): Run schema + confidence scoring over extracted XBRL facts.

    Converts the raw xbrl_facts list into an ExtractionResult and passes it
    through the eval pipeline.  The routing decision and confidence score are
    stored in the state for the audit trail but do NOT block the pipeline —
    escalation is surfaced to the caller, not used as a hard gate here so that
    the existing abstention logic is preserved.
    """
    logger.info("--- EVAL ---")
    if not _EVAL_AVAILABLE:
        return {"status": {**state.get('status', {}), "eval": "skipped"}}

    try:
        ticker = state.get("ticker", "")
        facts  = state.get("xbrl_facts", [])

        # Build a minimal ExtractionResult from the XBRL facts in state.
        # We use CIK=ticker as a placeholder when the real CIK is not in state.
        fields: List[ExtractedField] = []
        for fact in facts:
            name  = str(fact.get("concept", fact.get("label", "")))
            value = fact.get("value") or fact.get("val")
            if name and value is not None:
                try:
                    fields.append(ExtractedField(
                        name=name,
                        value=float(value),
                        provenance=Provenance.XBRL,
                        concept=name,
                    ))
                except (TypeError, ValueError):
                    pass

        if not fields:
            logger.info("Eval: no XBRL fields extracted — skipping scorer (no_data)")
            return {
                "eval_route":      None,
                "eval_confidence": None,
                "eval_triggers":   ["no_data"],
                "status": {**state.get('status', {}), "eval": "no_data"},
            }

        extraction = ExtractionResult(
            cik=ticker,
            accession="0000000000-00-000000",  # placeholder — real accession not in state
            form_type="10-K",
            period=None,
            fields=fields,
        )

        schema_result = validate_extraction(extraction)
        decision      = score_and_route(extraction, ticker=ticker)

        logger.info(
            "Eval: route={} conf={:.2f} triggers={} schema_valid={}",
            decision.route.value, decision.confidence,
            decision.triggers_fired, schema_result.is_valid,
        )

        return {
            "eval_route":      decision.route.value,
            "eval_confidence": round(decision.confidence, 4),
            "eval_triggers":   decision.triggers_fired,
            "status": {**state.get('status', {}), "eval": "success"},
        }
    except Exception as exc:
        logger.warning("Eval node error (non-fatal): {}", exc)
        return {"status": {**state.get('status', {}), "eval": "error"}}


def _safe_numeric(value) -> float | None:
    """Return float(value) or None — never raises on non-numeric XBRL values.
    nan/inf are excluded because they produce unreadable display strings.
    """
    import math
    try:
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


# Maps query keywords → XBRL concept substrings to surface in comparisons.
# Each entry is a list so multiple query signals map to the same concept set.
# NOTE: Keywords containing regex metacharacters (e.g. "long[- ]?term debt") are
# intentional and used with re.search(). Do NOT add unescaped (, ), *, +, etc.
_CONCEPT_MAP: list[tuple[tuple[str, ...], list[str]]] = [
    (("gross margin", "gross profit"),             ["GrossProfit", "Revenues", "RevenueFromContractWithCustomer", "CostOfGoodsAndServicesSold", "CostOfRevenue"]),
    (("revenue", "sales", "net sales"),            ["Revenues", "RevenueFromContractWithCustomer"]),
    (("operating income", "operating margin"),     ["OperatingIncomeLoss"]),
    (("net income", "earnings", "net earnings"),   ["NetIncomeLoss"]),
    (("r&d", "research and development"),          ["ResearchAndDevelopmentExpense"]),
    # FCF = operating cash flow − CapEx; surface both so caller can derive it
    (("free cash", "fcf"),                         ["NetCashProvidedByUsedInOperatingActivities",
                                                    "PaymentsToAcquirePropertyPlantAndEquipment"]),
    # This entry uses a regex character class [- ]? intentionally — do not escape
    (("long[- ]?term debt", "debt"),               ["LongTermDebt"]),
    (("assets",),                                  ["Assets"]),
]

_DEFAULT_CONCEPTS = ["Revenues", "NetIncomeLoss", "OperatingIncomeLoss"]


def _pick_concepts(query_lower: str) -> list[str]:
    """Return the XBRL concept substrings most relevant to the query.

    All matching keyword groups contribute (not just the first), so
    'operating revenue and net income' returns concepts for both.
    Falls back to a default set instead of an empty list.
    """
    matched: list[str] = []
    for keywords, concepts in _CONCEPT_MAP:
        if any(re.search(r"\b(?:" + kw + r")\b", query_lower) for kw in keywords):
            for c in concepts:
                if c not in matched:
                    matched.append(c)
    return matched if matched else _DEFAULT_CONCEPTS


def _period_sort_key(period: str) -> tuple:
    """Stable sort key for XBRL period strings.

    ISO dates (YYYY-MM-DD) sort correctly as strings but quarter labels like
    FY2023-Q10 sort before FY2023-Q2 lexicographically — normalize them.
    """
    try:
        return (0, _date.fromisoformat(period).isoformat())
    except (ValueError, TypeError):
        m = re.match(r"(\d{4})[^0-9]?Q(\d+)", period, re.IGNORECASE)
        if m:
            return (0, f"{m.group(1)}-Q{int(m.group(2)):02d}")
        return (1, period)


def _fmt_num(num: float) -> str:
    """Format a number for human display, preserving meaningful decimals."""
    if abs(num) < 10:
        return f"{num:,.4f}"
    if abs(num) < 1_000:
        return f"{num:,.2f}"
    return f"{num:,.0f}"


def _humanize_concept(concept: str) -> str:
    """Turn a raw XBRL concept (e.g. 'OperatingIncomeLoss') into a readable
    label. Prefers the shared display-name map, then falls back to splitting
    the PascalCase/camelCase token into spaced words."""
    if not concept:
        return concept
    mapped = _DISPLAY_NAMES.get(concept)
    if mapped:
        return mapped
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", concept)


def _fmt_compact(num: float) -> str:
    """Compact currency-style formatting for scannable table cells: abbreviate
    to B/M with thousand separators, keep small values (EPS, ratios) precise."""
    a = abs(num)
    if a >= 1_000_000_000:
        return f"{num / 1_000_000_000:,.2f}B"
    if a >= 1_000_000:
        return f"{num / 1_000_000:,.2f}M"
    if a >= 1_000:
        return f"{num:,.0f}"
    return f"{num:,.2f}"


def _fmt_result(value) -> str:
    """Human-format a single scalar answer: thousand separators when numeric
    (e.g. 215938000000.0 -> '215,938,000,000'), otherwise the raw string."""
    num = _safe_numeric(value)
    return _fmt_num(num) if num is not None else str(value)


def _fact_category(concept: str) -> Optional[str]:
    """Map a raw XBRL concept to a gross-margin-math category. Order matters:
    check COGS before revenue since 'CostOfRevenue' contains 'revenue'."""
    c = concept.lower()
    if "grossprofit" in c:
        return "gross_profit"
    if "costofrevenue" in c or "costofgoods" in c:
        return "cogs"
    if "revenue" in c or "sales" in c or c == "revenues":
        return "revenue"
    return None


def output_node(state: GraphState) -> Dict[str, Any]:
    """
    Final Node: Format the successful answer.
    For comparison intent, surfaces multi-period XBRL data instead of a single value.
    """
    logger.info("--- OUTPUT ---")

    # Constrain intent to safe literals (mirrors qualitative_output_node guard)
    intent = state.get("query_intent", "general")
    if intent not in ("latest", "comparison", "general"):
        intent = "general"

    ticker = state["ticker"]
    query_lower = state.get("query", "").lower()

    # Pre-build natural language YoY gross margin summary if applicable
    is_yoy_gm_ask = (
        any(k in query_lower for k in ("gross margin", "gross profit margin"))
        and any(k in query_lower for k in ("growth", "change", "grew", "grow", "increase", "decrease", "decline", "improve", "worse", "better", "yoy", "year over year", "year-over-year", "y-o-y"))
    )
    natural_yoy_summary = ""
    if is_yoy_gm_ask:
        try:
            facts = state.get("xbrl_facts", [])
            if isinstance(facts, list) and facts:
                xbrl_df = pl.DataFrame(facts)
                extractor = FactExtractor(xbrl_df)
                periods = extractor.periods()
                if len(periods) >= 2:
                    latest_p = periods[-1]
                    prior_p = periods[-2]
                    rev_cur = extractor.get("revenues", period=latest_p)
                    cogs_cur = _extract_cogs(extractor, latest_p)
                    rev_pri = extractor.get("revenues", period=prior_p)
                    cogs_pri = _extract_cogs(extractor, prior_p)

                    if all(v is not None for v in (rev_cur, cogs_cur, rev_pri, cogs_pri)):
                        current_gm = (rev_cur - cogs_cur) / rev_cur * 100
                        prior_gm = (rev_pri - cogs_pri) / rev_pri * 100
                        delta = current_gm - prior_gm
                        improved = "improved" if delta > 0 else "declined" if delta < 0 else "remained unchanged"
                        direction = "an increase" if delta > 0 else "a decrease" if delta < 0 else "no change"
                        natural_yoy_summary = (
                            f"Based on the SEC filings for {ticker}, "
                            f"gross margin {improved} year-over-year. "
                            f"The gross margin was {current_gm:.2f}% for the period ending {latest_p}, "
                            f"compared to {prior_gm:.2f}% for the period ending {prior_p}, "
                            f"representing {direction} of {abs(delta):.2f} percentage points."
                        )
        except Exception as ex:
            logger.warning(f"Failed to build natural YoY gross margin summary: {ex}")

    if intent == "comparison":
        facts = state.get("xbrl_facts", [])
        if isinstance(facts, list) and facts:
            concept_priority = _pick_concepts(query_lower)

            rows: list[tuple[str, str, float]] = []
            for f in facts:
                concept = f.get("concept", "")
                # Use word-boundary match to avoid false positives (e.g. "Gross" matching "GrossProfit")
                if not any(re.search(r"\b" + re.escape(c) + r"\b", concept, re.IGNORECASE) for c in concept_priority):
                    continue
                period = f.get("period_end", "")
                # fix: value=0 is valid — must not use `or` (falsy)
                raw = f.get("value") if f.get("value") is not None else f.get("val")
                num = _safe_numeric(raw)
                if period and num is not None:
                    rows.append((period, concept, num))

            rows.sort(key=lambda x: _period_sort_key(x[0]))

            # Duplicate XBRL facts (e.g. amended filings) can yield repeated
            # (period, concept) rows — collapse them BEFORE truncation so the
            # period cap counts distinct rows, not inflated duplicates.
            seen: set[tuple[str, str]] = set()
            deduped: list[tuple[str, str, float]] = []
            for period, concept, num in rows:
                key = (period, concept)
                if key in seen:
                    continue
                seen.add(key)
                deduped.append((period, concept, num))
            rows = deduped

            # Distinct periods in chronological order — the table is pivoted to
            # one row per period, so cap on PERIODS (not rows) to avoid dropping
            # a period just because it has several metrics.
            distinct_periods: list[str] = []
            for period, _c, _n in rows:
                if period not in distinct_periods:
                    distinct_periods.append(period)
            MAX_PERIODS = 6
            if len(distinct_periods) > MAX_PERIODS:
                logger.info(f"output_node: truncating {len(distinct_periods)} periods to last {MAX_PERIODS}")
                keep = set(distinct_periods[-MAX_PERIODS:])
                distinct_periods = distinct_periods[-MAX_PERIODS:]
                rows = [r for r in rows if r[0] in keep]

            if rows:
                lines = []
                if natural_yoy_summary:
                    lines.append(natural_yoy_summary)
                    lines.append("")
                lines.append(
                    f"**Multi-period comparison for {ticker}** (values in reported units)"
                )
                lines.append("")

                # GitHub-flavoured markdown table — renders as a real table in
                # the UI (remark-gfm). Pivoted to one row per period so periods
                # aren't repeated and metrics sit side by side.
                is_gm_ask = any(k in query_lower for k in ("gross margin", "gross profit margin"))
                if is_gm_ask:
                    # Purpose-built gross-margin view: Revenue, Gross Profit, and
                    # the derived Gross Margin %. Filers sometimes tag only a
                    # subset, so derive Revenue = Gross Profit + COGS and
                    # Gross Profit = Revenue − COGS where possible.
                    cats: dict[str, dict[str, float]] = {}
                    for period, concept, num in rows:
                        cat = _fact_category(concept)
                        if cat and cat not in cats.setdefault(period, {}):
                            cats[period][cat] = num
                    lines.append("| Period | Revenue | Gross Profit | Gross Margin |")
                    lines.append("| :-- | --: | --: | --: |")
                    for period in distinct_periods:
                        c = cats.get(period, {})
                        rev, gp, cogs = c.get("revenue"), c.get("gross_profit"), c.get("cogs")
                        if rev is None and gp is not None and cogs is not None:
                            rev = gp + cogs
                        if gp is None and rev is not None and cogs is not None:
                            gp = rev - cogs
                        gm = None
                        if gp is not None and rev is not None and rev != 0:
                            gm = gp / rev * 100
                        rev_c = _fmt_compact(rev) if rev is not None else "—"
                        gp_c = _fmt_compact(gp) if gp is not None else "—"
                        gm_c = f"{gm:.1f}%" if gm is not None else "—"
                        lines.append(f"| {period} | {rev_c} | {gp_c} | {gm_c} |")
                else:
                    # Generic wide pivot of whatever metrics were retrieved.
                    columns: list[str] = []
                    pivot: dict[str, dict[str, float]] = {}
                    for period, concept, num in rows:
                        label = _humanize_concept(concept)
                        if label not in columns:
                            columns.append(label)
                        pivot.setdefault(period, {})[label] = num
                    header = "| Period | " + " | ".join(col.replace("|", "\\|") for col in columns) + " |"
                    lines.append(header)
                    lines.append("| :-- | " + " | ".join("--:" for _ in columns) + " |")
                    for period in distinct_periods:
                        cells = [
                            _fmt_compact(pivot[period][col]) if col in pivot.get(period, {}) else "—"
                            for col in columns
                        ]
                        lines.append(f"| {period} | " + " | ".join(cells) + " |")

                math_result = state.get("math_result")
                if math_result is not None:
                    lines.append("")
                    lines.append(f"Latest calculated metric: {_fmt_result(math_result)}")
                answer = "\n".join(lines)
            else:
                math_result = state.get("math_result")
                if natural_yoy_summary:
                    answer = f"Comparison requested but no matching periods found. {natural_yoy_summary}"
                else:
                    answer = f"Comparison requested but no matching periods found. Latest: {_fmt_result(math_result)}"
        else:
            if natural_yoy_summary:
                answer = natural_yoy_summary
            else:
                answer = f"Based on the SEC filing for {ticker}, the answer is {_fmt_result(state.get('math_result'))}."
    else:
        if natural_yoy_summary:
            answer = natural_yoy_summary
        else:
            answer = f"Based on the SEC filing for {ticker}, the answer is {_fmt_result(state.get('math_result'))}."

    if state["verification_status"] == "PASS":
        answer += f"\n(Verified: {state['verification_reasoning']})"
    elif state["verification_status"] == "SKIPPED":
        answer += "\n(Note: NLI verification was skipped — model not available)"

    if state.get("eval_route") == "ESCALATE" and state.get("eval_triggers"):
        answer += f"\n[Eval: ESCALATE — triggers: {', '.join(state['eval_triggers'])}]"

    # Compute query-relevant XBRL facts for contextual display
    all_facts = state.get("xbrl_facts", [])
    try:
        relevance = get_relevant_facts(state.get("query", ""), all_facts)
        relevant_display = [format_fact_for_display(f) for f in relevance["relevant"]]
        badge = relevance["badge_text"]
        group = relevance["group"]
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"XBRL relevance filtering failed — falling back to empty ({e})")
        relevant_display = []
        badge = ""
        group = ""

    # Auto-attach a chart when the user asked for a trend/history of a metric
    # (numeric path doesn't use the LLM charting tool). Data is built from XBRL.
    chart_spec = None
    try:
        from api.services.chart_tool import detect_chart_request, build_chart_spec
        metric = detect_chart_request(state.get("query", ""))
        if metric:
            chart_spec = build_chart_spec(ticker, metric, "line")
    except Exception as e:
        logger.warning(f"output_node chart build failed (non-fatal): {e}")

    return {
        "final_answer": answer,
        "status": {**state.get('status', {}), "output": "success"},
        "relevant_xbrl": relevant_display,
        "xbrl_badge": badge,
        "xbrl_group": group,
        "chart": chart_spec,
    }

def abstention_node(state: GraphState) -> Dict[str, Any]:
    """
    Fallback Node: Handle verification failures or missing data.
    """
    logger.info("--- ABSTENTION ---")
    return {
        "final_answer": "I cannot answer this question with sufficient confidence based on the available SEC filing data.",
        "status": {**state.get('status', {}), "output": "success"}
    }


def _ensure_audit_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_runs (
            run_id            VARCHAR PRIMARY KEY,
            timestamp         VARCHAR NOT NULL,
            ticker            VARCHAR,
            question          TEXT,
            query_type        VARCHAR,
            answer            TEXT,
            eval_route        VARCHAR,
            confidence        DOUBLE,
            verification_status VARCHAR,
            model_used        VARCHAR,
            source_docs       JSON,
            chunk_ids         JSON,
            xbrl_facts_cited  JSON,
            math_result       VARCHAR,
            math_steps        JSON,
            eval_triggers     JSON,
            review_id         VARCHAR
        )
    """)


def lineage_node(state: GraphState) -> Dict[str, Any]:
    """
    Lineage Node: Build the audit lineage record for every response,
    and persist it to audit_runs in rag.duckdb for regulatory review.
    """
    logger.info("--- LINEAGE ---")
    import json
    import uuid
    from api.db.database import db_manager
    from api.db.review_queue import init_review_tables, insert_decision

    chunk_ids: List[str] = []
    source_docs: List[str] = []
    for doc in state.get("retrieved_docs", []):
        meta = doc.get("metadata", {})
        cid = meta.get("chunk_id") or meta.get("accession_number") or meta.get("chunk_index")
        if cid is not None:
            chunk_ids.append(str(cid))
        src = str(meta.get("accession_number") or meta.get("source", ""))
        if src and src not in source_docs:
            source_docs.append(src)

    cfg = Config.get_provider_config()
    eval_route = state.get("eval_route")
    review_id: Optional[str] = None

    if eval_route in ("SAMPLED_REVIEW", "ESCALATE"):
        try:
            review_conn = db_manager.get_review_connection()
            review_id = insert_decision(review_conn, {
                "cik": state.get("ticker", ""),
                "accession": source_docs[0] if source_docs else "unknown",
                "form_type": "10-K",
                "route": eval_route,
                "confidence": state.get("eval_confidence") if state.get("eval_confidence") is not None else 0.0,
                "triggers_fired": state.get("eval_triggers") if state.get("eval_triggers") is not None else [],
            })
            logger.info(f"Review queue entry created: {review_id} (route={eval_route})")
        except Exception as exc:
            logger.warning(f"Review queue insert failed (non-fatal): {exc}")

    ts = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())

    lineage: Dict[str, Any] = {
        "run_id": run_id,
        "source_docs": source_docs,
        "chunk_ids": chunk_ids,
        "model": cfg["model"],
        "confidence": state.get("eval_confidence"),
        "eval_route": eval_route,
        "timestamp": ts,
        "review_id": review_id,
    }

    # Persist full run to audit_runs for regulatory record-keeping
    try:
        xbrl_cited = [
            {"concept": f.get("concept"), "value": f.get("value"),
             "period_end": f.get("period_end"), "form_type": f.get("form_type")}
            for f in state.get("xbrl_facts", [])
            if isinstance(f, dict)
        ]
        math_result = state.get("math_result")
        def _dumps(v):
            return json.dumps(v, default=str)
        # Audit records are runtime output and MUST survive container restarts,
        # so they go to the persistent review/runtime DB (REVIEW_DB_PATH on the
        # persistent volume) — NOT the main DB, which is overwritten from the HF
        # dataset on every boot.
        conn = db_manager.get_review_connection()
        _ensure_audit_table(conn)
        conn.execute("""
            INSERT INTO audit_runs (
                run_id, timestamp, ticker, question, query_type, answer,
                eval_route, confidence, verification_status, model_used,
                source_docs, chunk_ids, xbrl_facts_cited, math_result,
                math_steps, eval_triggers, review_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            run_id, ts,
            state.get("ticker") or None,
            state.get("query") or None,
            state.get("query_type") or None,
            state.get("final_answer") or None,
            eval_route,
            state.get("eval_confidence"),
            state.get("verification_status") or None,
            cfg.get("model", "unknown"),
            _dumps(source_docs),
            _dumps(chunk_ids),
            _dumps(xbrl_cited),
            str(math_result) if math_result is not None else None,
            _dumps(state.get("math_steps", [])),
            _dumps(state.get("eval_triggers") or []),
            review_id,
        ])
        logger.info(f"Audit run saved: {run_id}")
    except Exception as exc:
        logger.warning(f"Audit run write failed (non-fatal): {exc}")

    return {
        "lineage": lineage,
        "status": {**state.get('status', {}), "lineage": "success"},
    }


# ---------------------------------------------------------------------------
# Query Classifier — numeric vs qualitative
# ---------------------------------------------------------------------------

_NUMERIC_KEYWORDS = [
    "gross margin", "gross profit margin", "gross margin growth",
    "operating margin", "operating income margin",
    "net margin", "profit margin", "net income margin",
    "free cash flow", "fcf",
    "current ratio", "liquidity ratio",
    "debt to equity", "debt-to-equity", "d/e ratio",
    "net debt", "net cash position",
    "r&d", "research and development", "rd intensity",
    "revenue", "net sales", "total revenue",
    "net income", "net earnings",
    "calculate", "compute",
    "percentage", "ratio", "growth rate", "yoy", "year over year",
]

# Strong qualitative signals — these override numeric classification.
# Only include terms that are clearly non-numeric and unlikely to appear
# in queries that actually want a computed metric.
_QUALITATIVE_SIGNALS = [
    "sentiment", "sentiment analysis", "tone", "management tone",
    "risk", "risks", "risk factor",
    "management discussion", "md&a", "highlighted by management",
    "strategy", "outlook", "competitive landscape", "threat", "challenge",
    "opportunities", "strengths", "weaknesses",
    "what are the risks", "what are the risk",
    "what is the strategy", "what is the outlook",
    "how does the company", "why did the company",
    "mentioned", "stated", "noted", "warned", "cautioned",
    "material weakness", "going concern", "contingency", "litigation",
    "regulation", "regulatory", "compliance",
    "acquisition", "merger", "divestiture",
    "business model", "market position", "competitive advantage",
    # Revenue/segment composition — these want a BREAKDOWN, which lives in the
    # filing narrative (segment footnote / MD&A), not in a single top-line XBRL
    # concept. Routing them numeric returns the total instead of the breakdown.
    "segment", "segments", "by segment", "reportable segment", "operating segment",
    "business segment", "product segment",
    "break down", "breakdown", "broken down",
    "by product", "by category", "by geography", "by region", "by end market",
    "by business", "by division", "by line of business",
    "composition", "split by", "split between", "product mix", "revenue mix",
    # "Where does the revenue come from" style — these want the segment/product
    # breakdown, not the top-line total.
    "sources of revenue", "source of revenue", "revenue sources", "revenue source",
    "main sources", "where does the revenue", "where did the revenue",
    "come from", "made up of", "driven by", "data center", "gaming",
    # Qualitative policy/structure questions that happen to contain metric words
    "policy", "recognition", "structure", "compensation", "plan",
    "definition", "accounting", "treatment", "standard", "guidance",
    "methodology", "approach", "technique", "method", "process",
    "capitalization", "amortization", "depreciation",
    "call", "transcript", "earnings call", "conference",
]


_COMPARISON_SIGNALS = [
    "compare", "comparison", "versus", " vs ", " vs.",
    "over the years", "year over year", "year-over-year", "y-o-y", "yoy", "trend", "historically",
    "history", "last 3 years", "last 5 years", "last two years", "last three years",
    "how has", "changed over", "change over", "growth over",
    "quarter over quarter", "quarter-over-quarter", "q-o-q", "qoq", "multi-year", "multiyear",
]

_LATEST_SIGNALS = [
    "latest", "most recent", "current", "most recently",
    "last quarter", "last fiscal", "this year", "this quarter",
]


def _detect_intent(query: str) -> str:
    """Classify query intent as 'comparison', 'latest', or 'general'.

    comparison → multiple sources needed, LLM should produce a comparison table.
    latest     → single most-recent source is sufficient.
    general    → balanced retrieval (2-3 sources).
    """
    q = query.lower()
    if any(s in q for s in _COMPARISON_SIGNALS):
        return "comparison"
    if any(s in q for s in _LATEST_SIGNALS):
        return "latest"
    return "general"


def _is_numeric_query(query: str) -> bool:
    """Check if the query requires numeric computation.

    Qualitative signals take priority — if the query contains strong
    qualitative indicators (risks, strategy, management discussion, etc.)
    it routes to the qualitative path even if numeric keywords are present.
    """
    q = query.lower()
    has_qualitative = any(kw in q for kw in _QUALITATIVE_SIGNALS)
    has_numeric = any(kw in q for kw in _NUMERIC_KEYWORDS)

    # Strong qualitative signals override numeric
    if has_qualitative:
        return False
    return has_numeric


_xbrl_ticker_cache: dict[str, bool] = {}


def _ticker_has_xbrl(ticker: str) -> bool:
    """True if this ticker has any structured XBRL facts in the DB.

    Tickers ingested only from an S-1/424B4 IPO prospectus (e.g. SPCX) carry
    rich filing text but no XBRL facts, so deterministic numeric verification
    can't run. Callers use this to allow text-grounded (clearly unverified)
    numeric answers for such tickers instead of abstaining outright. Cached
    per-ticker for the process lifetime. On any error, assumes XBRL is present
    so we fall back to the safe deterministic-verify path.
    """
    if not ticker:
        return True
    if ticker in _xbrl_ticker_cache:
        return _xbrl_ticker_cache[ticker]
    has = True
    try:
        from api.db.database import db_manager
        conn = db_manager.get_connection()
        row = conn.execute(
            "SELECT COUNT(*) FROM xbrl_facts WHERE ticker = ?", [ticker]
        ).fetchone()
        has = bool(row and row[0] > 0)
    except Exception as e:
        logger.warning("XBRL availability check failed for {}: {} — assuming present", ticker, e)
        has = True
    _xbrl_ticker_cache[ticker] = has
    return has


_REFUSAL_MARKERS = (
    "don't have", "do not have", "insufficient", "no information",
    "does not contain", "not contain", "cannot answer", "can't answer",
    "no financial", "no revenue", "no numerical", "would need",
)


def _text_grounded_decorations(state: GraphState, answer: str = "") -> dict:
    """Disclaimer note + badge for numeric answers grounded in filing text (no XBRL).

    Returns empty strings unless the classifier flagged this run as
    numeric_text_grounded, so it's a no-op on the normal qualitative path.

    The disclaimer is only attached when the answer actually presents a figure
    and isn't itself a refusal — otherwise "figures above are quoted from text"
    would contradict an "I don't have that data" answer when retrieval failed to
    surface a usable number.
    """
    if not state.get("numeric_text_grounded"):
        return {"note": "", "badge": "", "reasoning": ""}
    ticker = state.get("ticker", "")
    low = (answer or "").lower()
    has_figure = bool(re.search(r"[$\d]", answer or ""))
    is_refusal = any(m in low for m in _REFUSAL_MARKERS)
    if not has_figure or is_refusal:
        return {
            "note": "",
            "badge": "",
            "reasoning": (
                f"Text-grounded path for {ticker} (no XBRL filed); retrieval did "
                f"not surface a usable figure for this query."
            ),
        }
    return {
        "note": (
            f"\n\n_Figures above are quoted from {ticker}'s filing narrative "
            f"(IPO prospectus / S-1) and are **not XBRL-verified** like our "
            f"10-K-based numbers._"
        ),
        "badge": "From filing text • not XBRL-verified",
        "reasoning": (
            f"Text-grounded numeric answer for {ticker}: no XBRL facts were filed "
            f"(prospectus only), so figures are quoted from narrative text and not "
            f"deterministically verified."
        ),
    }


def _generate_educational_layers(query: str, answer: str, ticker: str) -> dict:
    """Produce the educational layers (sections 3–5 of the Standard Response
    Framework) for an already-finished answer: "What This Means", "How to
    Interpret This", and suggested follow-up questions.

    This is deliberately a SEPARATE, best-effort step that never touches the
    audited Layer-1 answer. It is given the finished answer and is forbidden
    from introducing any fact or number not already present — so it can only
    explain, never re-answer. Returns {} on any failure or when the layers
    don't apply (empty answer or an abstention/refusal), so callers can treat
    the result as purely additive display data.
    """
    import os

    if os.getenv("ANSWER_FRAMEWORK_ENABLED", "true").strip().lower() in ("0", "false", "no"):
        return {}

    answer = (answer or "").strip()
    if not answer:
        return {}
    # No point explaining an "I can't answer that" abstention.
    if any(m in answer.lower() for m in _REFUSAL_MARKERS):
        return {}

    try:
        import json
        from openai import OpenAI

        cfg = Config.get_provider_config()
        client = OpenAI(
            api_key=cfg["api_key"] or "local",
            base_url=cfg["base_url"],
            timeout=20.0,
        )
        system = (
            "You help people with NO accounting or finance background understand "
            "SEC filing answers. You are given a user question and a factual answer "
            "that has ALREADY been produced from the filings. Your job is to explain "
            "it — never to re-answer it. "
            "CRITICAL: do not introduce any number, statistic, or fact that is not "
            "already present in the answer. Do not contradict the answer. "
            "Respond with STRICT JSON only, no markdown, with exactly these keys: "
            '{"what_it_means": str, "how_to_interpret": str, "follow_ups": [str, ...]}. '
            '"what_it_means": translate the answer into plain English (2-3 sentences). '
            '"how_to_interpret": generic educational context about the metric/topic '
            "(what it measures, why it matters, a caveat) — assume zero finance "
            "background. "
            '"follow_ups": 3-4 concrete next questions the user could ask to go deeper.'
        )
        user = (
            f"Company ticker: {ticker or 'N/A'}\n"
            f"User question: {query}\n\n"
            f"Factual answer already produced:\n{answer}"
        )
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.15,
            max_tokens=600,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # Cap response size to prevent runaway LLM output
        if len(raw) > 10_000:
            logger.warning("Educational layers response exceeded 10KB — truncating")
            raw = raw[:10_000]
        # Tolerate a ```json fence if the model adds one despite instructions.
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw else raw
        data = json.loads(raw)
        follow_ups = data.get("follow_ups") or []
        if not isinstance(follow_ups, list):
            follow_ups = []
        return {
            "what_it_means": str(data.get("what_it_means", "")).strip(),
            "how_to_interpret": str(data.get("how_to_interpret", "")).strip(),
            "follow_ups": [str(f).strip() for f in follow_ups if str(f).strip()][:4],
        }
    except Exception as e:  # best-effort: never let this break the answer
        logger.warning(f"Educational layers generation failed (non-fatal): {e}")
        return {}


def classifier_node(state: GraphState) -> Dict[str, Any]:
    """Classify query as numeric/qualitative and detect comparison vs latest intent."""
    query = state["query"]
    qtype  = "numeric" if _is_numeric_query(query) else "qualitative"
    intent = _detect_intent(query)
    text_grounded = False
    # A numeric question about a ticker with no XBRL facts (e.g. an S-1
    # prospectus filer like SPCX) can't be deterministically verified. Rather
    # than abstain at the verification gate, route it through the LLM/text path
    # and flag the answer as quoted-from-text / not XBRL-verified.
    if qtype == "numeric" and not _ticker_has_xbrl(state.get("ticker", "")):
        logger.info(
            "--- CLASSIFIER: numeric query for {} but no XBRL facts — "
            "routing to text-grounded answer ---", state.get("ticker", ""))
        qtype = "qualitative"
        text_grounded = True
    logger.info(f"--- CLASSIFIER: {qtype} | intent={intent} ---")
    return {
        "query_type":   qtype,
        "query_intent": intent,
        "numeric_text_grounded": text_grounded,
        "status": {**state.get("status", {}), "classifier": "success"},
    }


def qualitative_output_node(state: GraphState) -> Dict[str, Any]:
    """Answer qualitative questions using LLM over retrieved SEC filing chunks.

    The LLM has access to financial calculation tools so it can compute
    metrics on-the-fly when the question involves numbers.
    """
    logger.info("--- QUALITATIVE OUTPUT ---")
    try:
        import json
        from openai import OpenAI

        docs = state.get("retrieved_docs", [])
        if not docs:
            return {
                "final_answer": "I don't have enough filing data to answer that question.",
                "verification_status": "SKIPPED",
                "verification_reasoning": "No retrieved documents for qualitative query.",
                "math_steps": [],
                "math_result": None,
                "status": {**state.get("status", {}), "output": "success"},
            }

        # Build context from top retrieved chunks
        context_parts = []
        for i, doc in enumerate(docs[:5]):
            text = doc.get("chunk_text", "")
            meta = doc.get("metadata", {})
            src = meta.get("source", "SEC filing")
            ticker = meta.get("ticker", state.get("ticker", ""))
            header = f"[Source {i+1}: {src}"
            if ticker:
                header += f" | {ticker}"
            header += "]"
            context_parts.append(f"{header}\n{text}")
        context = "\n\n---\n\n".join(context_parts)

        # Include XBRL facts for tool-calling context
        xbrl_facts = state.get("xbrl_facts", [])
        facts_text = ""
        if xbrl_facts:
            facts_lines = []
            for f in xbrl_facts[:20]:
                label = f.get("label", f.get("concept", ""))
                value = f.get("value") or f.get("val")
                unit = f.get("unit", "")
                period = f.get("period_end", "")
                if label and value is not None:
                    facts_lines.append(f"  {label}: {value} {unit} ({period})")
            if facts_lines:
                facts_text = "\n\nAvailable XBRL facts:\n" + "\n".join(facts_lines)

        ticker = state.get("ticker", "")
        # Retrieve computed Loughran-McDonald sentiment for context if available
        sentiment_context_text = ""
        try:
            from api.services.sentiment import get_filing_sentiment
            sentiment = get_filing_sentiment(ticker)
            if sentiment:
                totals = sentiment.get("totals", {})
                sentiment_context_text = (
                    f"\n\nLoughran-McDonald Sentiment analysis for {ticker} (Period: {sentiment.get('period_of_report')}):\n"
                    f"  - Positive words: {totals.get('positive', 0)}\n"
                    f"  - Negative words: {totals.get('negative', 0)}\n"
                    f"  - Uncertainty words: {totals.get('uncertainty', 0)}\n"
                    f"  - Net sentiment score: {sentiment.get('overall_net_sentiment', 0.0):.6f}\n"
                    f"  - Overall tone score: {sentiment.get('overall_tone_score', 0.0):.6f}\n"
                )
        except Exception as se:
            logger.debug("Failed to pull sentiment for qualitative context: {}", se)

        # Constrain to safe literals before interpolating into system prompt
        intent = state.get("query_intent", "general")
        if intent not in ("latest", "comparison", "general"):
            intent = "general"

        # Role-based personalization (conjoint). Appended to the system prompt to
        # tailor tone/emphasis to the respondent's role; never changes the numbers.
        _rg = (state.get("role_guidance") or "").strip()
        role_instruction = (
            " Reader-specific guidance — adapt the answer to this reader and satisfy "
            "any stated requirements. This changes only emphasis, structure, depth, "
            "and what you foreground; it must NEVER change the underlying numbers or "
            f"introduce facts not present in the context: {_rg[:1200]}"
            if _rg else ""
        )

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculate_financial_metric",
                    "description": "Calculate a financial metric (margin, ratio, growth rate) from XBRL data. Use when the question involves a specific number or calculation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "metric": {
                                "type": "string",
                                "enum": [
                                    "gross_margin", "operating_margin", "net_margin",
                                    "gross_margin_growth", "free_cash_flow",
                                    "current_ratio", "debt_to_equity", "rd_intensity",
                                    "revenue_yoy_growth", "revenue", "net_income",
                                ],
                                "description": "The financial metric to calculate",
                            },
                        },
                        "required": ["metric"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_financial_chart",
                    "description": (
                        "Render a chart of a financial metric's history across "
                        "fiscal years. Call this when the user asks for a trend, "
                        "history, 'over time', 'year over year', or 'historical' "
                        "view of a metric (e.g. 'historical revenue' -> a revenue "
                        "line chart). The chart's data is pulled from filed XBRL "
                        "facts automatically; you only choose the metric and type."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "metric": {
                                "type": "string",
                                "enum": [
                                    "revenue", "net_income", "gross_profit",
                                    "operating_income", "rd_expense",
                                    "gross_margin", "operating_margin", "net_margin",
                                ],
                                "description": "Which metric's history to chart.",
                            },
                            "chart_type": {
                                "type": "string",
                                "enum": ["line", "bar"],
                                "description": "line for trends over time, bar for discrete year-by-year comparison.",
                            },
                        },
                        "required": ["metric"],
                    },
                },
            },
        ]

        if intent == "comparison":
            intent_instruction = (
                "The user is asking for a COMPARISON across multiple periods or years. "
                "You MUST structure your answer as a comparison: present the values for each "
                "available period side-by-side (e.g. a table or year-by-year breakdown). "
                "Highlight the trend, direction of change, and percentage growth where possible. "
                "Do not summarise into a single figure — show each period explicitly."
            )
        elif intent == "latest":
            intent_instruction = (
                "The user wants the MOST RECENT figure only. "
                "Use the latest available period from the context. State the period date clearly."
            )
        else:
            intent_instruction = (
                "Answer using the most relevant data available in the context."
            )

        messages = [
            {
                "role": "system",
                "content": (
                    f"You are a financial analyst assistant specializing in SEC filings for {ticker}. "
                    "Answer questions using the provided context from SEC filings and XBRL facts. "
                    "Cite specific sections, risks, or statements from the filing. "
                    "If the question involves a financial metric or number, call the "
                    "calculate_financial_metric tool to compute it precisely. "
                    "Use Polars, never Pandas for any data operations. "
                    "Do not fabricate numbers, statistics, or claims not present in the context. "
                    "GROUNDING — strict dataset constraint: do not rely on outside information or general "
                    "knowledge. If the retrieved context or facts are insufficient to answer the question, or if "
                    "the information is not in the provided dataset, you MUST state politely and clearly that the "
                    "requested information is not available in the dataset or filings under review (do not guess "
                    "or extrapolate using outside knowledge). "
                    "Only name competitors, peers, customers, suppliers, or other companies if that name explicitly "
                    "appears in the provided filing context. If asked about competitors and the filings do not name them, "
                    "state politely that the filings under review do not enumerate specific competitors. "
                    f"If the context is insufficient, say so clearly and politely. {intent_instruction}{role_instruction}"
                ),
            },
        ]

        # Prior conversation turns so follow-ups ("what about its net income?",
        # "over the same period") resolve against earlier context. Only plain
        # user/assistant text is forwarded; the current turn's grounded context
        # is the final user message below.
        for turn in (state.get("history") or [])[-6:]:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content[:2000]})

        messages.append({
            "role": "user",
            "content": f"Context from SEC filings:\n\n{context}{facts_text}{sentiment_context_text}\n\nQuestion: {state['query']}",
        })

        cfg = Config.get_provider_config()
        client = OpenAI(
            api_key=cfg["api_key"] or "local",
            base_url=cfg["base_url"],
            timeout=30.0,
        )

        # First call — let LLM decide if it needs tools
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=cfg.get("temperature", 0.15),
            max_tokens=cfg.get("max_tokens", 4096),
        )

        msg = resp.choices[0].message

        # Handle tool calls
        if msg.tool_calls:
            messages.append(msg.model_dump())
            math_steps = []
            chart_spec: Optional[Dict[str, Any]] = None

            for tool_call in msg.tool_calls:
                fn_name = getattr(tool_call.function, "name", "") or ""
                try:
                    args = json.loads(tool_call.function.arguments)
                except (json.JSONDecodeError, KeyError):
                    args = {}

                if fn_name == "create_financial_chart":
                    from api.services.chart_tool import build_chart_spec
                    spec = build_chart_spec(
                        state.get("ticker", ""),
                        args.get("metric", ""),
                        args.get("chart_type", "line"),
                    )
                    if spec and chart_spec is None:
                        chart_spec = spec
                    tool_result = (
                        {"status": "chart created",
                         "title": spec["title"],
                         "points": len(spec["data"])}
                        if spec else
                        {"status": "no chart",
                         "reason": "not enough multi-period XBRL data for that metric"}
                    )
                else:
                    tool_result = _execute_tool(args.get("metric", ""), state)
                    math_steps.append(tool_result.get("display", str(tool_result)))

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result),
                })

            # Second call — LLM generates final answer with tool results
            resp2 = client.chat.completions.create(
                model=cfg["model"],
                messages=messages,
                temperature=cfg.get("temperature", 0.15),
                max_tokens=cfg.get("max_tokens", 4096),
            )
            answer = (resp2.choices[0].message.content or "").strip()

            deco = _text_grounded_decorations(state, answer)
            return {
                "final_answer": answer + deco["note"],
                "verification_status": "SKIPPED",
                "verification_reasoning": deco["reasoning"] or "Qualitative query with tool-assisted calculation.",
                "math_steps": math_steps,
                "math_result": None,
                "xbrl_badge": deco["badge"],
                "chart": chart_spec,
                "status": {**state.get("status", {}), "output": "success"},
            }

        # No tools needed — direct answer
        answer = (msg.content or "").strip()

        # Auto-attach chart for metric queries even when LLM didn't call the tool
        chart_spec = None
        try:
            from api.services.chart_tool import detect_chart_request, build_chart_spec
            metric = detect_chart_request(state.get("query", ""))
            if metric:
                chart_spec = build_chart_spec(state.get("ticker", ""), metric, "line")
        except Exception as e:
            logger.warning(f"qualitative_output_node auto-chart failed (non-fatal): {e}")

        deco = _text_grounded_decorations(state, answer)
        return {
            "final_answer": answer + deco["note"],
            "verification_status": "SKIPPED",
            "verification_reasoning": deco["reasoning"] or "Qualitative query — numeric verification not applicable.",
            "math_steps": ["Qualitative query — no computation needed."],
            "math_result": None,
            "xbrl_badge": deco["badge"],
            "chart": chart_spec,
            "status": {**state.get("status", {}), "output": "success"},
        }
    except Exception as e:
        logger.error(f"Qualitative output failed: {e}")
        return {
            "final_answer": "An error occurred while generating the answer. Please try again.",
            "verification_status": "SKIPPED",
            "verification_reasoning": "Qualitative output generation failed — internal error.",
            "math_steps": [],
            "math_result": None,
            "status": {**state.get("status", {}), "output": "error"},
        }


def _execute_tool(metric: str, state: GraphState) -> dict:
    """Execute a financial calculation tool and return the result as a dict."""
    import polars as pl
    from api.services.financial_calc import FactExtractor
    from api.services.metric_router import route_metric

    facts_list = state.get("xbrl_facts", [])
    if not facts_list:
        return {"error": "No XBRL facts available", "display": "No XBRL data"}

    xbrl_df = pl.DataFrame(facts_list)
    extractor = FactExtractor(xbrl_df)
    periods = extractor.periods()
    latest = periods[-1] if periods else ""
    prior = periods[-2] if len(periods) >= 2 else None

    result = route_metric(metric, extractor, latest, prior)
    if result:
        return {"value": result.value, "display": result.display(), "unit": result.unit}

    return {"error": f"Could not compute {metric} — missing data", "display": f"{metric}: data unavailable"}


# ---------------------------------------------------------------------------
# Graph Definition
# ---------------------------------------------------------------------------

def decide_next_step(state: GraphState) -> str:
    """
    Deterministic routing based on verification result.
    PASS or SKIPPED (NLI unavailable) -> output.
    FAIL or ERROR -> abstention.
    """
    if state['verification_status'] in ("PASS", "SKIPPED"):
        return "output"
    else:
        return "abstention"


def decide_pipeline(state: GraphState) -> str:
    """Route numeric queries through math/verification, qualitative to LLM output."""
    if state.get("query_type") == "qualitative":
        return "qualitative_output"
    return "extraction"


# Initialize graph
workflow = StateGraph(GraphState)

# Add nodes
workflow.add_node("retrieval", retrieval_node)
workflow.add_node("classifier", classifier_node)
workflow.add_node("extraction", extraction_node)
workflow.add_node("eval", eval_node)          # Phase 2-5 eval pipeline (BUG-8 fix)
workflow.add_node("math", math_node)
workflow.add_node("verification", verification_node)
workflow.add_node("output", output_node)
workflow.add_node("qualitative_output", qualitative_output_node)
workflow.add_node("abstention", abstention_node)
workflow.add_node("build_lineage", lineage_node)

# Set entry point
workflow.set_entry_point("retrieval")

# Retrieval -> Classifier (decides numeric vs qualitative)
workflow.add_edge("retrieval", "classifier")

# Classifier routes to either:
#   numeric path: Extraction -> Eval -> Math -> Verification -> Output/Abstention
#   qualitative path: Qualitative Output (LLM over retrieved docs)
workflow.add_conditional_edges(
    "classifier",
    decide_pipeline,
    {
        "extraction": "extraction",
        "qualitative_output": "qualitative_output",
    }
)

# Numeric pipeline
workflow.add_edge("extraction", "eval")
workflow.add_edge("eval", "math")
workflow.add_edge("math", "verification")

# Add conditional edge from verification
workflow.add_conditional_edges(
    "verification",
    decide_next_step,
    {
        "output": "output",
        "abstention": "abstention"
    }
)

# Both terminal nodes funnel through build_lineage before END
workflow.add_edge("output", "build_lineage")
workflow.add_edge("qualitative_output", "build_lineage")
workflow.add_edge("abstention", "build_lineage")
workflow.add_edge("build_lineage", END)

_app = None
_app_lock = __import__('threading').Lock()

def get_app():
    global _app
    if _app is None:
        with _app_lock:
            if _app is None:
                _app = workflow.compile()
    return _app

def _resolve_query_ticker(query: str, fallback: str) -> str:
    """Prefer the ticker the user actually named in the query over the caller's
    default. The UI ships a fixed default ticker, so without this a question
    about "NVDA" would be answered with the default company's (e.g. Micron's)
    XBRL data. Company name wins first, then an explicit ticker symbol; if the
    query names neither, the caller's ticker is kept.
    """
    if not query:
        return fallback
    # 1. Company name in the query ("NVIDIA" -> NVDA, "Micron" -> MU)
    try:
        from api.services.hybrid_retriever import resolve_ticker_from_query
        by_name = resolve_ticker_from_query(query, "")
        if by_name:
            return by_name
    except Exception:
        pass
    # 2. Explicit ticker symbol in the query ("NVDA", "AVGO"). Length >= 3 with a
    #    word boundary avoids prose false-matches on short/ambiguous symbols.
    try:
        from api.config import TICKER_TO_CIK
        for sym in TICKER_TO_CIK:
            if len(sym) >= 3 and re.search(r"\b" + re.escape(sym) + r"\b", query, re.IGNORECASE):
                logger.info(f"Resolved ticker {sym!r} from explicit symbol in query")
                return sym
    except Exception:
        pass
    return fallback


# Well-known companies we do NOT have SEC data for. If a user names one of
# these, abstain ("I don't know") instead of silently answering with the
# default ticker's data. Not exhaustive — the retrieval layer is the general
# backstop — but covers the common cases people test with.
_OUT_OF_UNIVERSE = {
    "tesla", "apple", "amazon", "alphabet", "google", "microsoft", "meta",
    "facebook", "netflix", "oracle", "salesforce", "adobe", "walmart", "costco",
    "jpmorgan", "goldman sachs", "berkshire", "coca cola", "pepsi", "disney",
    "boeing", "ford", "general motors", "exxon", "chevron", "pfizer", "moderna",
    "palantir", "uber", "airbnb", "spotify", "openai", "anthropic", "stripe",
    "blue origin", "rivian", "lucid", "snowflake",
}


def _named_uncovered_company(query: str) -> Optional[str]:
    """Return a well-known company named in the query that we do NOT cover, else None."""
    q = (query or "").lower()
    for name in _OUT_OF_UNIVERSE:
        if re.search(r"\b" + re.escape(name) + r"\b", q):
            return name
    return None


def _abstain_response(company: str) -> Dict[str, Any]:
    """A grounded 'I don't have data on that' answer (shaped like graph output)."""
    msg = (
        f"I don't have SEC filing data for **{company.title()}**, so I can't answer "
        f"that. I currently cover **SpaceX (SPCX)** and major semiconductor companies "
        f"(e.g. NVDA, AMD, MU, AVGO, QCOM, TXN, AMAT, LRCX, KLAC). "
        f"Ask about one of those and I'll pull it from their filings."
    )
    done = {k: "skipped" for k in (
        "input", "retrieval", "classifier", "extraction", "eval", "math", "verification", "output")}
    done["input"] = "success"
    done["output"] = "success"
    return {
        "final_answer": msg,
        "resolved_ticker": "",  # No ticker — company is out of coverage
        "xbrl_facts": [], "relevant_xbrl": [], "retrieved_docs": [], "polygon_data": [],
        "math_result": None, "math_steps": [],
        "verification_status": "ABSTAIN",
        "verification_reasoning": f"Out of coverage: no SEC data for {company}.",
        "status": done,
    }


_CONSENSUS_COLUMNS_ENSURED = False
_PERSONA_COLUMNS_ENSURED = False


def _ensure_consensus_columns(conn) -> None:
    """Idempotently add the consensus columns to audit_runs (DuckDB).

    Guarded by a process-level flag so the DDL (which takes a write lock) runs at
    most once per process rather than on every disagreement.
    """
    global _CONSENSUS_COLUMNS_ENSURED
    if _CONSENSUS_COLUMNS_ENSURED:
        return
    for col, typ in (
        ("consensus_status", "VARCHAR"),
        ("consensus_divergence", "DOUBLE"),
        ("consensus_secondary_model", "VARCHAR"),
    ):
        conn.execute(f"ALTER TABLE audit_runs ADD COLUMN IF NOT EXISTS {col} {typ}")
    _CONSENSUS_COLUMNS_ENSURED = True


def _consensus_worker(
    query: str,
    final_answer: str,
    context: str,
    run_id: Optional[str],
    prior_route: Optional[str],
    source_docs: List[str],
    resolved_ticker: str,
    eval_confidence: Optional[float],
) -> None:
    """Background worker for the dual-model consensus rail (Bias / Model-Risk).

    Runs OFF the request path (fire-and-forget) so it never adds latency to the
    user-facing answer. It receives a value snapshot — NOT the response dict — so
    there is no cross-thread mutation of an object the request has already
    returned. On material disagreement it escalates the audit/review tier
    (AUTO→SAMPLED_REVIEW), opens a review-queue entry, and persists `consensus_*`
    to `audit_runs`. The live response keeps its pre-consensus route; the audit
    row and review queue converge afterward (eventual consistency by design).
    Entirely non-fatal and fail-open.
    """
    try:
        from api.services.guardrails.consensus_rails import check_consensus

        verdict = check_consensus(query, context, final_answer)
        if verdict.skipped or verdict.agree:
            return

        # ── Material disagreement ────────────────────────────────────────────
        from api.db.database import db_manager
        from api.db.review_queue import insert_decision

        escalate = (prior_route or "").upper() not in ("SAMPLED_REVIEW", "ESCALATE")
        final_route = "SAMPLED_REVIEW" if escalate else prior_route
        review_id: Optional[str] = None

        # Concurrency (Codex r2 / MiMo): the request paths execute on the shared
        # singleton review connection WITHOUT a shared lock, so a background thread
        # must NOT use that same connection object. Open a DEDICATED, independent
        # connection for this thread (DuckDB connections are not safe to use
        # concurrently across threads; a separate connect() to the same file in the
        # same process attaches to the same DB instance and sees the same tables).
        conn = db_manager.get_new_review_connection()
        try:
            if escalate:
                try:
                    review_id = insert_decision(conn, {
                        "cik": resolved_ticker or "",
                        "accession": source_docs[0] if source_docs else "unknown",
                        "form_type": "10-K",
                        "route": "SAMPLED_REVIEW",
                        "confidence": eval_confidence if eval_confidence is not None else 0.0,
                        "triggers_fired": ["consensus_divergence"],
                    })
                except Exception as exc:
                    logger.warning(f"Consensus review-queue insert failed (non-fatal): {exc}")

            if run_id:
                try:
                    _ensure_consensus_columns(conn)
                    conn.execute(
                        """
                        UPDATE audit_runs
                           SET consensus_status = ?,
                               consensus_divergence = ?,
                               consensus_secondary_model = ?,
                               eval_route = ?,
                               review_id = COALESCE(?, review_id)
                         WHERE run_id = ?
                        """,
                        [
                            "DISAGREE",
                            verdict.divergence_score,
                            verdict.secondary_model,
                            final_route,
                            review_id,
                            run_id,
                        ],
                    )
                except Exception as exc:
                    logger.warning(f"Consensus audit update failed (non-fatal): {exc}")
        finally:
            # Always close this thread's dedicated connection.
            try:
                conn.close()
            except Exception:
                pass
    except Exception as exc:
        logger.warning(f"Consensus worker failed (non-fatal): {exc}")


def _spawn_consensus(query: str, result: Dict[str, Any]) -> None:
    """Risk-gate the question and, if warranted, fire the consensus worker in a
    background daemon thread. Snapshots everything the worker needs from `result`
    in THIS (request) thread, so the worker never touches the returned response.
    """
    try:
        from api.services.guardrails.consensus_rails import should_run_consensus

        if result.get("verification_status") == "ABSTAIN":
            return
        final_answer = result.get("final_answer") or ""
        docs = result.get("retrieved_docs") or []
        if not final_answer or not docs:
            return

        run, _reason = should_run_consensus(query, result.get("eval_route"))
        if not run:
            return

        context = "\n\n".join(d.get("chunk_text", "") for d in docs if d.get("chunk_text"))
        lineage = result.get("lineage") or {}
        threading.Thread(
            target=_consensus_worker,
            args=(
                query,
                final_answer,
                context,
                lineage.get("run_id"),
                result.get("eval_route"),
                lineage.get("source_docs") or [],
                result.get("resolved_ticker") or "",
                result.get("eval_confidence"),
            ),
            daemon=True,
            name="consensus-rail",
        ).start()
    except Exception as exc:
        logger.warning(f"Consensus spawn failed (non-fatal): {exc}")


def _ensure_persona_columns(conn) -> None:
    """Idempotently add the persona-fit columns to audit_runs (DuckDB).

    Guarded by a process-level flag so the DDL (which takes a write lock) runs at
    most once per process rather than on every miss.
    """
    global _PERSONA_COLUMNS_ENSURED
    if _PERSONA_COLUMNS_ENSURED:
        return
    for col, typ in (
        ("persona_role", "VARCHAR"),
        ("persona_fit_status", "VARCHAR"),
        ("persona_fit_score", "DOUBLE"),
        ("persona_fit_missing", "VARCHAR"),
    ):
        conn.execute(f"ALTER TABLE audit_runs ADD COLUMN IF NOT EXISTS {col} {typ}")
    _PERSONA_COLUMNS_ENSURED = True


def _persona_persist_worker(
    run_id: str, role: str, score: float, missing: List[str]
) -> None:
    """Background writer: persist a persona-fit MISS to the audit row.

    Only spawned on a miss (rare), so write-lock pressure stays low. Uses a
    dedicated connection (DuckDB connections aren't safe to share across threads),
    and is entirely non-fatal / fail-open.
    """
    try:
        from api.db.database import db_manager

        conn = db_manager.get_new_review_connection()
        try:
            _ensure_persona_columns(conn)
            conn.execute(
                """
                UPDATE audit_runs
                   SET persona_role = ?,
                       persona_fit_status = ?,
                       persona_fit_score = ?,
                       persona_fit_missing = ?
                 WHERE run_id = ?
                """,
                [role, "MISS", score, ", ".join(missing), run_id],
            )
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as exc:
        logger.warning(f"Persona-fit persist failed (non-fatal): {exc}")


def _apply_persona_rail(result: Dict[str, Any], role_key: Optional[str]) -> None:
    """Persona-fit rail: check the finished answer serves the active persona.

    Runs synchronously on the request path — the check is pure/deterministic
    (no LLM, no IO) so it adds negligible latency. It NEVER edits the answer or
    changes routing; it attaches a `persona_fit` summary to `result` for audit/UI
    and, only on a miss with a known run_id, fires a background thread to record
    the miss on the audit row. Fully fail-open.
    """
    try:
        if not role_key:
            return
        if result.get("verification_status") == "ABSTAIN":
            return
        answer = result.get("final_answer") or ""
        if not answer.strip():
            return

        from api.services.guardrails.persona_rails import check_persona_fit

        verdict = check_persona_fit(
            role_key, answer, verification_status=result.get("verification_status")
        )
        result["persona_fit"] = {
            "role": verdict.role,
            "fit": verdict.fit,
            "skipped": verdict.skipped,
            "score": verdict.score,
            "missing": verdict.missing,
            "reason": verdict.reason,
        }
        if verdict.skipped or verdict.fit:
            return

        logger.info(
            f"Persona-fit MISS (role={verdict.role}, score={verdict.score}): "
            f"{verdict.reason}"
        )
        run_id = (result.get("lineage") or {}).get("run_id")
        if run_id:
            threading.Thread(
                target=_persona_persist_worker,
                args=(run_id, verdict.role or "", verdict.score, verdict.missing),
                daemon=True,
                name="persona-fit-rail",
            ).start()
    except Exception as exc:
        logger.warning(f"Persona-fit rail spawn failed (non-fatal): {exc}")


def run_auditable_rag(query: str, ticker: str,
                      history: Optional[List[Dict[str, str]]] = None,
                      role_guidance: Optional[str] = None,
                      role_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Run the LangGraph DAG for a given query and ticker.

    `history` carries prior conversation turns ([{role, content}, ...]) so
    follow-up questions ("what about its net income?", "over the same period")
    are answered with the earlier context, not in isolation.

    `role_guidance` (optional) tailors the answer to a professional role
    (conjoint `role_based` personalization). It is appended to the answer system
    prompt only; when None/empty the answer is role-agnostic. It never alters
    retrieval, ticker resolution, or the audited numbers — purely emphasis,
    structure, and what the answer foregrounds.

    `role_key` (optional) is the same persona's key; it drives the persona-fit rail
    that checks, after the answer is generated, whether the answer satisfies that
    persona's hard requirements. Advisory only — never edits the answer.
    """
    # Ground on the company named in the question, not the UI's default ticker.
    # If the query names a company we DON'T cover, abstain rather than answering
    # with the default ticker's data ("SpaceX revenue" must not return Micron's).
    by_name = _resolve_query_ticker(query, "")  # covered ticker, or "" if none recognised
    if not by_name:
        uncovered = _named_uncovered_company(query)
        if uncovered:
            logger.info(f"Abstaining — query names uncovered company {uncovered!r}")
            return _abstain_response(uncovered)
        by_name = ticker  # no company named -> honour the UI's selected ticker
    if by_name != ticker:
        logger.info(f"Ticker override: query resolved to {by_name!r} (caller passed {ticker!r})")
    ticker = by_name

    # Multi-company comparison: the single-ticker DAG can't compare across
    # companies. Detect "vs competitors / industry" or 2+ named companies and
    # branch to the dedicated peer-comparison path (graph-derived peers + the
    # same financial_calc metrics), returning a comparison table.
    try:
        from api.services.peer_comparison import detect_comparison, run_peer_comparison
        decision = detect_comparison(query, ticker)
        if decision:
            logger.info(f"--- PEER COMPARISON: {decision} ---")
            result = run_peer_comparison(query, decision)
            result["resolved_ticker"] = decision["subject"]
            return result
    except Exception as e:
        logger.warning(f"Peer comparison path failed, falling back to single-company: {e}")

    app = get_app()
    inputs = {
        "query": query,
        "ticker": ticker,
        "history":              history or [],
        "query_type":           "numeric",
        "query_intent":         "general",
        "numeric_text_grounded": False,
        "retrieved_docs":      [],
        "xbrl_facts":          [],
        "polygon_data":        [],
        "math_result":         None,
        "math_steps":          [],
        "verification_status":  "",
        "verification_reasoning": "",
        "final_answer":        "",
        "eval_route":          None,
        "eval_confidence":     None,
        "eval_triggers":       None,
        "lineage":             None,
        "role_guidance":       role_guidance or None,
        "status": {
            "input":        "success",
            "retrieval":    "pending",
            "classifier":   "pending",
            "extraction":   "pending",
            "eval":         "pending",
            "math":         "pending",
            "verification": "pending",
            "output":       "pending",
        },
    }

    result = app.invoke(inputs)

    # Surface the ticker the query actually resolved to so the caller (and the
    # UI) can persist the active company across turns. Without this a follow-up
    # that names no company falls back to the UI's default ticker (e.g. a
    # follow-up to an NVDA question would be answered with Micron's data).
    result["resolved_ticker"] = ticker

    # Standard Response Framework sections 3–5: additive educational layers
    # generated from the finished answer (never alters the audited answer).
    layers = _generate_educational_layers(query, result.get("final_answer", ""), ticker)
    result["what_it_means"] = layers.get("what_it_means", "")
    result["how_to_interpret"] = layers.get("how_to_interpret", "")
    result["follow_ups"] = layers.get("follow_ups", [])

    # Sentiment / management tone analysis (Phase B) — best-effort, cached,
    # gated by SENTIMENT_LLM_ENABLED env var.  Returns {} on failure.
    # Skipped on abstentions (no filing data available).
    # Only generated for qualitative questions or when explicitly asking for risks, tone, or sentiment.
    try:
        query_lower = query.lower()
        is_qualitative_ask = (
            result.get("query_type") == "qualitative"
            or any(kw in query_lower for kw in ("risk", "sentiment", "tone", "discussion", "md&a", "outlook"))
        )
        if result.get("verification_status") != "ABSTAIN" and is_qualitative_ask:
            from api.services.sentiment import generate_tone_analysis, compute_tone_shift
            tone = generate_tone_analysis(ticker)
            if tone:
                # Enrich with embedding-based tone shift (Phase D) when available
                shift = compute_tone_shift(ticker)
                if shift:
                    tone["tone_shift_similarity"] = shift.get("similarity")
                    tone["tone_shift_interpretation"] = shift.get("interpretation", "")
                result["tone_analysis"] = tone
    except Exception as e:
        logger.debug("Tone analysis skipped (non-fatal): {}", e)

    # Dual-model consensus rail (Bias / Model-Risk) — risk-gated, fire-and-forget.
    # Spawns a background thread for high-stakes / hard multi-year / comparison
    # questions; never blocks the response. Audit + review queue converge after.
    _spawn_consensus(query, result)

    # Persona-fit rail — when the answer was personalized for a role, check it
    # actually serves that persona's requirements. Deterministic + advisory:
    # attaches `persona_fit` to result and records a miss on the audit row.
    _apply_persona_rail(result, role_key)

    return result
