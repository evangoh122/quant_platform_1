"""
sentiment.py — Loughran-McDonald dictionary-based SEC filing sentiment analysis.

Provides deterministic, zero-LLM-cost sentiment scoring per filing section using
the financial-specific Loughran-McDonald dictionary (6 sentiment categories).

Usage:
    from api.services.sentiment import get_filing_sentiment, compare_filing_sentiment

    result = get_filing_sentiment("NVDA")
    delta  = compare_filing_sentiment("NVDA")
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from loguru import logger

from api.config import Config

# ── Dictionary loading ───────────────────────────────────────────────────────

_DICT_PATH = Path(__file__).parent.parent.parent / "data" / "sentiment_dict" / "lm_word_lists.json"

_SENTIMENT_CATEGORIES = (
    "positive", "negative", "uncertainty", "litigious",
    "constraining", "strong_modal", "weak_modal",
)


@dataclass(frozen=True)
class SentimentDictionary:
    """Immutable snapshot of the Loughran-McDonald word lists."""
    positive: frozenset[str]
    negative: frozenset[str]
    uncertainty: frozenset[str]
    litigious: frozenset[str]
    constraining: frozenset[str]
    strong_modal: frozenset[str]
    weak_modal: frozenset[str]

    def category_words(self, category: str) -> frozenset[str]:
        return getattr(self, category)


def load_lm_dictionary() -> SentimentDictionary:
    """Load the bundled Loughran-McDonald word lists (cached across calls)."""
    return _load_lm_dictionary_cached()


@lru_cache(maxsize=1)
def _load_lm_dictionary_cached() -> SentimentDictionary:
    if not _DICT_PATH.exists():
        logger.error("Loughran-McDonald dictionary not found at {}", _DICT_PATH)
        return SentimentDictionary(
            positive=frozenset(), negative=frozenset(), uncertainty=frozenset(),
            litigious=frozenset(), constraining=frozenset(),
            strong_modal=frozenset(), weak_modal=frozenset(),
        )
    with open(_DICT_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    return SentimentDictionary(
        positive=frozenset(w.lower() for w in raw.get("positive", [])),
        negative=frozenset(w.lower() for w in raw.get("negative", [])),
        uncertainty=frozenset(w.lower() for w in raw.get("uncertainty", [])),
        litigious=frozenset(w.lower() for w in raw.get("litigious", [])),
        constraining=frozenset(w.lower() for w in raw.get("constraining", [])),
        strong_modal=frozenset(w.lower() for w in raw.get("strong_modal", [])),
        weak_modal=frozenset(w.lower() for w in raw.get("weak_modal", [])),
    )


# ── Tokenizer ────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"[a-z][a-z\-']*[a-z]|[a-z]", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    """Lowercase tokenization matching Loughran-McDonald bag-of-words design.

    Strips numbers and punctuation.  Keeps hyphenated compounds like
    ``well-known`` and ``year-over-year``, and apostrophes (e.g. ``don't``).
    """
    return [t.lower() for t in _TOKEN_RE.findall(text)]


# ── Counting ─────────────────────────────────────────────────────────────────

@dataclass
class SentimentCounts:
    """Raw category counts + derived scores for a body of text."""
    positive: int = 0
    negative: int = 0
    uncertainty: int = 0
    litigious: int = 0
    constraining: int = 0
    strong_modal: int = 0
    weak_modal: int = 0
    total_words: int = 0

    @property
    def net_sentiment(self) -> float:
        """(positive - negative) / total_words  —  range roughly [-1, +1]."""
        return (self.positive - self.negative) / max(self.total_words, 1)

    @property
    def tone_score(self) -> float:
        """Composite management tone: (positive - negative - uncertainty) / total."""
        return (self.positive - self.negative - self.uncertainty) / max(self.total_words, 1)

    def to_dict(self) -> dict:
        return {
            "positive": self.positive,
            "negative": self.negative,
            "uncertainty": self.uncertainty,
            "litigious": self.litigious,
            "constraining": self.constraining,
            "strong_modal": self.strong_modal,
            "weak_modal": self.weak_modal,
            "total_words": self.total_words,
            "net_sentiment": round(self.net_sentiment, 6),
            "tone_score": round(self.tone_score, 6),
        }


def count_sentiment(text: str, dictionary: Optional[SentimentDictionary] = None) -> SentimentCounts:
    """Count Loughran-McDonald sentiment words in *text*.

    Parameters
    ----------
    text : str
        Raw section/filing text.
    dictionary : SentimentDictionary, optional
        Pre-loaded dictionary.  Loaded on first call when omitted.

    Returns
    -------
    SentimentCounts
        Category counts and derived scores.
    """
    if dictionary is None:
        dictionary = load_lm_dictionary()

    tokens = tokenize(text)
    total = len(tokens)
    if total == 0:
        return SentimentCounts(total_words=0)

    token_set = set(tokens)
    counts = {}
    for cat in _SENTIMENT_CATEGORIES:
        cat_words = dictionary.category_words(cat)
        counts[cat] = len(token_set & cat_words)

    return SentimentCounts(
        positive=counts["positive"],
        negative=counts["negative"],
        uncertainty=counts["uncertainty"],
        litigious=counts["litigious"],
        constraining=counts["constraining"],
        strong_modal=counts["strong_modal"],
        weak_modal=counts["weak_modal"],
        total_words=total,
    )


# ── Section-level analysis ───────────────────────────────────────────────────

def analyze_section(text: str, section_type: str = "unknown") -> dict:
    """Score a single filing section.

    Returns a dict with raw counts + derived scores + section metadata.
    """
    counts = count_sentiment(text)
    result = counts.to_dict()
    result["section_type"] = section_type
    return result


def analyze_filing_sections(sections: dict[str, str]) -> dict:
    """Score multiple named sections and aggregate.

    Parameters
    ----------
    sections : dict[str, str]
        Mapping of section label → raw text.
        Example: {"Item 7": "...", "Item 1A": "..."}

    Returns
    -------
    dict
        Keys: "sections" (per-section dicts), "totals" (aggregated counts),
        "overall_net_sentiment", "overall_tone_score".
    """
    section_results = {}
    totals = {cat: 0 for cat in _SENTIMENT_CATEGORIES}
    total_words = 0

    for section_label, text in sections.items():
        counts = count_sentiment(text)
        section_dict = counts.to_dict()
        section_dict["section_type"] = section_label
        section_results[section_label] = section_dict

        for cat in _SENTIMENT_CATEGORIES:
            totals[cat] += getattr(counts, cat)
        total_words += counts.total_words

    overall_net = (totals["positive"] - totals["negative"]) / max(total_words, 1)
    overall_tone = (totals["positive"] - totals["negative"] - totals["uncertainty"]) / max(total_words, 1)

    return {
        "sections": section_results,
        "totals": totals,
        "total_words": total_words,
        "overall_net_sentiment": round(overall_net, 6),
        "overall_tone_score": round(overall_tone, 6),
    }


# ── Filing-level analysis (queries DuckDB) ───────────────────────────────────

def get_filing_sentiment(
    ticker: str,
    accession: Optional[str] = None,
) -> Optional[dict]:
    """Compute sentiment for a filing's embedded chunks, grouped by section.

    Queries ``edgar_embeddings`` for the specified ticker and computes
    Loughran-McDonald scores per section and in aggregate.

    Parameters
    ----------
    ticker : str
        Stock ticker (e.g. "NVDA").
    accession : str, optional
        Specific accession number.  When *None*, uses the most recent filing.

    Returns
    -------
    dict or None
        Full sentiment result, or *None* when no data is found.
    """
    try:
        from api.db.database import db_manager
        conn = db_manager.get_connection()

        if accession:
            rows = conn.execute(
                """SELECT text, section_type, section_id, form_type, period_of_report, accession
                   FROM edgar_embeddings
                   WHERE ticker = ? AND accession = ?
                   ORDER BY chunk_index""",
                [ticker.upper(), accession],
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT text, section_type, section_id, form_type, period_of_report, accession
                   FROM edgar_embeddings
                   WHERE ticker = ?
                   AND accession = (
                       SELECT DISTINCT accession
                       FROM edgar_embeddings
                       WHERE ticker = ?
                       ORDER BY period_of_report DESC
                       LIMIT 1
                   )
                   ORDER BY chunk_index""",
                [ticker.upper(), ticker.upper()],
            ).fetchall()

        if not rows:
            logger.warning("No edgar_embeddings found for ticker={}", ticker)
            return None

        # Group by section_id (or section_type fallback)
        sections: dict[str, str] = {}
        metadata = {"ticker": ticker.upper()}
        for text, section_type, section_id, form_type, period, acc in rows:
            label = section_id or section_type or "unknown"
            sections[label] = sections.get(label, "") + "\n\n" + text
            if not metadata.get("form_type"):
                metadata["form_type"] = form_type
            if not metadata.get("period_of_report"):
                metadata["period_of_report"] = period
            if not metadata.get("accession"):
                metadata["accession"] = acc

        result = analyze_filing_sections(sections)
        result.update(metadata)
        return result

    except Exception as e:
        logger.error("get_filing_sentiment failed for {}: {}", ticker, e)
        return None


# ── Filing-to-filing comparison ───────────────────────────────────────────────

def compare_filing_sentiment(
    ticker: str,
    accession_a: Optional[str] = None,
    accession_b: Optional[str] = None,
) -> Optional[dict]:
    """Compare sentiment between two filings of the same company.

    When *accession_a* / *accession_b* are omitted the two most recent
    filings are used automatically.

    Returns a dict with per-category deltas and percentage changes.
    """
    try:
        from api.db.database import db_manager
        conn = db_manager.get_connection()

        # Fetch distinct filings ordered by period_of_report desc
        filings = conn.execute(
            """SELECT DISTINCT accession, period_of_report
               FROM edgar_embeddings
               WHERE ticker = ?
               ORDER BY period_of_report DESC""",
            [ticker.upper()],
        ).fetchall()

        if len(filings) < 2:
            logger.info("Need at least 2 filings for comparison, found {} for {}", len(filings), ticker)
            return None

        if accession_a and accession_b:
            acc_a, acc_b = accession_a, accession_b
        else:
            acc_b = filings[0][0]   # most recent
            acc_a = filings[1][0]   # prior

        sentiment_a = get_filing_sentiment(ticker, acc_a)
        sentiment_b = get_filing_sentiment(ticker, acc_b)

        if not sentiment_a or not sentiment_b:
            return None

        changes = {}
        for cat in _SENTIMENT_CATEGORIES:
            val_a = sentiment_a["totals"][cat]
            val_b = sentiment_b["totals"][cat]
            delta = val_b - val_a
            pct = (delta / max(val_a, 1)) * 100
            changes[cat] = {
                "previous": val_a,
                "current": val_b,
                "delta": delta,
                "pct_change": round(pct, 1),
            }

        tone_shift = round(
            sentiment_b["overall_tone_score"] - sentiment_a["overall_tone_score"], 6
        )

        return {
            "ticker": ticker.upper(),
            "filing_a": {
                "accession": acc_a,
                "period": sentiment_a.get("period_of_report", ""),
                "form_type": sentiment_a.get("form_type", ""),
            },
            "filing_b": {
                "accession": acc_b,
                "period": sentiment_b.get("period_of_report", ""),
                "form_type": sentiment_b.get("form_type", ""),
            },
            "changes": changes,
            "tone_shift": tone_shift,
        }

    except Exception as e:
        logger.error("compare_filing_sentiment failed for {}: {}", ticker, e)
        return None


# ── Convenience: sentiment history ────────────────────────────────────────────

def get_sentiment_history(ticker: str) -> list[dict]:
    """Return sentiment scores for all filings of *ticker*, most recent first."""
    try:
        from api.db.database import db_manager
        conn = db_manager.get_connection()

        filings = conn.execute(
            """SELECT DISTINCT accession, period_of_report
               FROM edgar_embeddings
               WHERE ticker = ?
               ORDER BY period_of_report DESC""",
            [ticker.upper()],
        ).fetchall()

        history = []
        for acc, period in filings:
            result = get_filing_sentiment(ticker, acc)
            if result:
                result["accession"] = acc
                result["period_of_report"] = period
                history.append(result)

        return history

    except Exception as e:
        logger.error("get_sentiment_history failed for {}: {}", ticker, e)
        return []


# ── LLM Tone Interpretation (Phase B) ────────────────────────────────────────

# Cache keyed by (ticker, accession) → avoids re-calling the LLM on repeated
# requests within the same process lifetime.  Capped at 64 entries to bound
# memory; oldest entries are evicted when the cap is reached.
_tone_cache: dict[tuple[str, str], dict] = {}
_TONE_CACHE_MAX = 64


def generate_tone_analysis(ticker: str) -> dict:
    """Best-effort LLM synthesis of sentiment data into a management tone summary.

    Follows the same pattern as ``_generate_educational_layers`` in
    ``langgraph_engine.py``: guarded by ``SENTIMENT_LLM_ENABLED`` env var,
    cached per ``(ticker, accession)``, returns ``{}`` on failure.
    """
    import os

    if os.getenv("SENTIMENT_LLM_ENABLED", "true").strip().lower() in ("0", "false", "no"):
        return {}

    ticker = (ticker or "").strip().upper()
    if not ticker:
        return {}

    try:
        sentiment = get_filing_sentiment(ticker)
        if not sentiment:
            return {}

        accession = sentiment.get("accession", "")
        cache_key = (ticker, accession)
        if cache_key in _tone_cache:
            return _tone_cache[cache_key]

        # Try to load prior filing for YoY comparison
        changes_pct = {}
        try:
            from api.db.database import db_manager
            conn = db_manager.get_connection()
            filings = conn.execute(
                """SELECT DISTINCT accession, period_of_report
                   FROM edgar_embeddings
                   WHERE ticker = ?
                   ORDER BY period_of_report DESC""",
                [ticker],
            ).fetchall()
            if len(filings) >= 2:
                prior_acc = filings[1][0]
                prior = get_filing_sentiment(ticker, prior_acc)
                if prior:
                    for cat in _SENTIMENT_CATEGORIES:
                        prev_val = prior["totals"].get(cat, 0)
                        curr_val = sentiment["totals"].get(cat, 0)
                        pct = ((curr_val - prev_val) / max(prev_val, 1)) * 100
                        changes_pct[cat] = round(pct, 1)
        except Exception as e:
            logger.debug("YoY comparison skipped for {}: {}", ticker, e)

        # Build section summary — sections is a dict[str, dict] from
        # analyze_filing_sections(), keyed by section label.
        section_lines = []
        sections_dict = sentiment.get("sections", {})
        for label, sec in sections_dict.items():
            if isinstance(sec, dict):
                stype = sec.get("section_type", label)
                ns = sec.get("net_sentiment", 0)
                direction = "positive" if ns > 0.01 else "negative" if ns < -0.01 else "neutral"
                section_lines.append(f"- {stype}: {direction} (net={ns:.4f})")
            else:
                section_lines.append(f"- {label}")
        section_text = "\n".join(section_lines) if section_lines else "No section data available."

        # Build YoY delta summary
        delta_lines = []
        for cat in ("positive", "negative", "uncertainty"):
            pct = changes_pct.get(cat)
            if pct is not None:
                sign = "+" if pct > 0 else ""
                delta_lines.append(f"{cat}: {sign}{pct}%")
        delta_text = ", ".join(delta_lines) if delta_lines else "No prior filing for comparison."

        import json
        from openai import OpenAI

        cfg = Config.get_provider_config()
        client = OpenAI(
            api_key=cfg["api_key"] or "local",
            base_url=cfg["base_url"],
            timeout=20.0,
        )

        system = (
            "You are a financial analyst reviewing management tone in SEC filings. "
            "You are given Loughran-McDonald sentiment scores for the current filing "
            "and year-over-year percentage changes. "
            "CRITICAL: Only reference the data provided. Do not invent numbers or facts. "
            "Respond with STRICT JSON only, no markdown, with exactly these keys: "
            '{"tone_label": str, "tone_direction": str, "tone_summary": str, '
            '"key_drivers": [str, ...]}. '
            '"tone_label": a short label like "More Cautious", "More Optimistic", or "Consistent". '
            '"tone_direction": "up" (more cautious/negative), "down" (more optimistic), or "flat". '
            '"tone_summary": 3-5 sentence analysis of management tone with evidence from the data. '
            '"key_drivers": 2-3 bullet points explaining what changed most.'
        )
        user = (
            f"Company: {ticker}\n"
            f"Period: {sentiment.get('period_of_report', 'N/A')}\n"
            f"Form: {sentiment.get('form_type', 'N/A')}\n\n"
            f"Section Sentiments:\n{section_text}\n\n"
            f"YoY Changes: {delta_text}\n\n"
            f"Overall net sentiment: {sentiment.get('overall_net_sentiment', 0):.4f}\n"
            f"Overall tone score: {sentiment.get('overall_tone_score', 0):.4f}"
        )

        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.15,
            max_tokens=512,
        )

        raw = (resp.choices[0].message.content or "").strip()
        if len(raw) > 10_000:
            raw = raw[:10_000]
        if raw.startswith("```"):
            raw = raw.strip("`")
        # Extract JSON object safely — guard against unmatched braces.
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            raw = raw[start:end + 1]

        data = json.loads(raw)
        key_drivers = data.get("key_drivers") or []
        if not isinstance(key_drivers, list):
            key_drivers = []

        result = {
            "tone_label": str(data.get("tone_label", "Unknown")).strip(),
            "tone_direction": str(data.get("tone_direction", "flat")).strip(),
            "tone_summary": str(data.get("tone_summary", "")).strip(),
            "key_drivers": [str(d).strip() for d in key_drivers if str(d).strip()][:5],
            "positive_terms": sentiment["totals"].get("positive", 0),
            "negative_terms": sentiment["totals"].get("negative", 0),
            "uncertainty_terms": sentiment["totals"].get("uncertainty", 0),
            "positive_change_pct": changes_pct.get("positive"),
            "negative_change_pct": changes_pct.get("negative"),
            "uncertainty_change_pct": changes_pct.get("uncertainty"),
            "section_scores": [
                {
                    "section_type": sec.get("section_type", label),
                    "net_sentiment": sec.get("net_sentiment", 0),
                    "tone_score": sec.get("tone_score", 0),
                }
                for label, sec in sentiment.get("sections", {}).items()
                if isinstance(sec, dict)
            ],
        }

        _tone_cache[cache_key] = result
        if len(_tone_cache) > _TONE_CACHE_MAX:
            # Evict oldest entry (first key inserted)
            _tone_cache.pop(next(iter(_tone_cache)))
        return result

    except Exception as e:
        logger.warning("Tone analysis generation failed (non-fatal): {}", e)
        return {}


# ── Embedding-Based Tone Shift (Phase D) ──────────────────────────────────────

def compute_tone_shift(ticker: str) -> Optional[dict]:
    """Measure cosine similarity between MD&A embeddings across consecutive filings.

    Low similarity may indicate strategic shift, new risks, or major business
    changes — orthogonal to word-count sentiment (which can stay neutral while
    topics shift).

    Returns a dict with similarity score and interpretation, or *None* when
    fewer than 2 filings exist or embeddings are unavailable.
    """
    try:
        import numpy as np
        from api.db.database import db_manager

        conn = db_manager.get_connection()
        ticker = (ticker or "").strip().upper()
        if not ticker:
            return None

        # Fetch distinct filings ordered by period desc
        filings = conn.execute(
            """SELECT DISTINCT accession, period_of_report
               FROM edgar_embeddings
               WHERE ticker = ?
               ORDER BY period_of_report DESC""",
            [ticker],
        ).fetchall()

        if len(filings) < 2:
            logger.info("Need >=2 filings for tone-shift, found {} for {}", len(filings), ticker)
            return None

        acc_b, period_b = filings[0]  # most recent
        acc_a, period_a = filings[1]  # prior

        def _fetch_mdna_embeddings(accession: str) -> list:
            """Fetch MD&A chunk embeddings for a filing.

            Filters to Item 7 (MD&A) but excludes Item 7A
            (Quantitative Market Risk Disclosures) which is not narrative MD&A.
            """
            rows = conn.execute(
                """SELECT embedding FROM edgar_embeddings
                   WHERE ticker = ? AND accession = ?
                   AND (section_id = 'Item 7' OR section_id LIKE 'Item 7 %')
                   AND section_id NOT LIKE 'Item 7A%'
                   AND embedding IS NOT NULL
                   ORDER BY chunk_index""",
                [ticker, accession],
            ).fetchall()
            return [row[0] for row in rows if row[0] is not None]

        emb_a = _fetch_mdna_embeddings(acc_a)
        emb_b = _fetch_mdna_embeddings(acc_b)

        if not emb_a or not emb_b:
            logger.info("No MD&A embeddings for tone-shift: {} (a={}) (b={})", ticker, len(emb_a), len(emb_b))
            return None

        # Validate consistent embedding dimensions within each filing
        dims_a = {len(e) for e in emb_a}
        dims_b = {len(e) for e in emb_b}
        if len(dims_a) != 1 or len(dims_b) != 1:
            logger.warning("Mixed embedding dims in tone-shift: {} (a={}) (b={})", ticker, dims_a, dims_b)
            return None
        if dims_a != dims_b:
            logger.warning("Cross-filing dimension mismatch: {} a={} b={}", ticker, dims_a, dims_b)
            return None

        # Mean-pool across chunks per filing
        mean_a = np.mean([np.array(e, dtype=np.float32) for e in emb_a], axis=0)
        mean_b = np.mean([np.array(e, dtype=np.float32) for e in emb_b], axis=0)

        # Cosine similarity (embeddings are typically L2-normalized, but be safe)
        norm_a = np.linalg.norm(mean_a)
        norm_b = np.linalg.norm(mean_b)
        if norm_a == 0 or norm_b == 0:
            return None
        similarity = float(np.dot(mean_a, mean_b) / (norm_a * norm_b))
        if not np.isfinite(similarity):
            return None

        # Interpretation
        if similarity > 0.95:
            interpretation = "High consistency — management narrative is stable"
        elif similarity > 0.85:
            interpretation = "Moderate consistency — minor topic shift detected"
        elif similarity > 0.70:
            interpretation = "Notable shift — meaningful change in strategic narrative"
        else:
            interpretation = "Significant shift — major strategic or risk changes detected"

        return {
            "ticker": ticker,
            "filing_a": {"accession": acc_a, "period": period_a},
            "filing_b": {"accession": acc_b, "period": period_b},
            "similarity": round(similarity, 4),
            "interpretation": interpretation,
            "chunk_counts": [len(emb_a), len(emb_b)],
            "thresholds": {
                "high": ">0.95 = consistent",
                "mid": "0.85-0.95 = moderate shift",
                "low": "<0.85 = significant shift",
            },
        }

    except Exception as e:
        logger.error("compute_tone_shift failed for {}: {}", ticker, e)
        return None
