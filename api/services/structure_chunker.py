"""
structure_chunker.py — Structure-aware chunking for SEC filings.

Treats tables, charts, and narrative sections differently:
- Tables: detected by pipe/grid patterns, kept intact as single chunks
- Narrative: semantic chunking — groups related sentences by topic similarity
- Metadata: tags each chunk with section_type (balance_sheet, income_statement, etc.)

Usage:
    from api.services.structure_chunker import StructureChunker
    chunker = StructureChunker()
    chunks = chunker.chunk(text, section_label="item_8", ticker="NVDA")
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger


@dataclass
class ChunkMetadata:
    """Metadata attached to every chunk."""
    ticker: str = ""
    section_label: str = ""        # e.g. "item_7", "item_1"
    section_type: str = "narrative" # balance_sheet, income_statement, md_and_a, etc.
    content_type: str = "narrative" # "table", "narrative", "list", "chart"
    period: str = ""
    form_type: str = ""
    chunk_index: int = 0
    total_chunks: int = 0
    char_count: int = 0


@dataclass
class Chunk:
    """A single chunk with text and metadata."""
    text: str
    metadata: ChunkMetadata


# ── Section-type classification ──────────────────────────────────────────────

# Split into 10-K and 20-F maps to avoid key collisions (item_7 means different things)
_10K_SECTION_TYPE_MAP: dict[str, str] = {
    "item_1":   "business_description",
    "item_1a":  "risk_factors",
    "item_7":   "md_and_a",
    "item_7a":  "quantitative_disclosures",
    "item_8":   "financial_statements",
}

_20F_SECTION_TYPE_MAP: dict[str, str] = {
    "item_3":   "key_information",
    "item_4":   "business_description",
    "item_5":   "operating_financial_review",
    "item_6":   "directors_compensation",
    "item_7":   "major_shareholders",
    "item_8":   "financial_statements",
    "item_10":  "additional_information",
    "item_11":  "quantitative_disclosures",
}

# Financial sub-section keywords (detected by content within Item 8)
_SECTION_TYPE_DEFAULTS: dict[str, str] = {
    "balance_sheet":    "balance_sheet",
    "income_statement": "income_statement",
    "cash_flow":        "cash_flow_statement",
    "equity_statement": "equity_statement",
    "notes":            "financial_notes",
    "full_text":        "narrative",
}

# Keywords that signal financial sub-sections within Item 8
_FINANCIAL_SUBSECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("balance_sheet",    re.compile(r"(?:consolidated\s+)?balance\s+sheets?", re.I)),
    ("income_statement", re.compile(r"(?:consolidated\s+)?(?:statements?\s+of\s+)?(?:operations|income|earnings|comprehensive\s+income)", re.I)),
    ("cash_flow",        re.compile(r"(?:consolidated\s+)?(?:statements?\s+of\s+)?cash\s+flows?", re.I)),
    ("equity_statement", re.compile(r"(?:consolidated\s+)?(?:statements?\s+of\s+)?(?:stockholders|shareholders|equity)", re.I)),
    ("notes",            re.compile(r"notes?\s+(?:to\s+)?(?:the\s+)?(?:consolidated\s+)?financial\s+statements?", re.I)),
]


# ── Table detection ──────────────────────────────────────────────────────────

# Pre-compiled patterns for table detection
_NUMERIC_TOKEN_RE = re.compile(r"^[\d,.$()%-]+$")

# Patterns that strongly indicate tabular data
_TABLE_PATTERNS: list[re.Pattern] = [
    # Pipe-delimited tables (markdown-style)
    re.compile(r"(?:^|\n)\s*\|.+\|(?:\s*\n\s*\|.+\|)+", re.MULTILINE),
    # Grid tables with multiple aligned columns (3+ spaces separating columns)
    re.compile(r"(?:^|\n)(?:\S+(?:\s{3,}\S+){2,}\s*\n){2,}", re.MULTILINE),
    # Financial table patterns: rows of numbers with labels
    # Uses [^\n]{3,60} instead of [\w\s&/.-]{3,60} to avoid ReDoS
    re.compile(
        r"(?:^|\n)(?:[^\n]{3,60})\s{2,}[\d,.$()%-]+\s{2,}[\d,.$()%-]+"
        r"(?:\s*\n(?:[^\n]{3,60})\s{2,}[\d,.$()%-]+\s{2,}[\d,.$()%-]+)+",
        re.MULTILINE,
    ),
    # Lines with consistent columnar number alignment (common in SEC filings)
    re.compile(
        r"(?:^|\n)(?:.*\$\s*[\d,]+.*\n){3,}",
        re.MULTILINE,
    ),
]

# Minimum lines to qualify as a table
_MIN_TABLE_LINES = 3


def _is_table_block(text: str) -> bool:
    """Check if a text block is tabular data."""
    lines = [l for l in text.strip().split("\n") if l.strip()]
    if len(lines) < _MIN_TABLE_LINES:
        return False

    # Check pipe-delimited
    pipe_lines = sum(1 for l in lines if "|" in l)
    if pipe_lines >= len(lines) * 0.6:
        return True

    # Check number density — tables have high ratio of numeric tokens
    all_tokens = re.findall(r"\S+", text)
    if not all_tokens:
        return False
    numeric_tokens = sum(1 for t in all_tokens if _NUMERIC_TOKEN_RE.match(t))
    numeric_ratio = numeric_tokens / len(all_tokens)
    if numeric_ratio > 0.25 and len(lines) >= _MIN_TABLE_LINES:
        return True

    # Check for consistent column alignment
    column_counts = [len(re.findall(r"\s{3,}", l)) for l in lines]
    if len(set(column_counts)) == 1 and column_counts[0] >= 2:
        return True

    return False


def _extract_tables(text: str) -> list[tuple[int, int, str]]:
    """
    Find table regions in text. Returns list of (start, end, table_text).
    Non-overlapping, ordered by position.
    """
    tables: list[tuple[int, int, str]] = []
    seen_spans: set[tuple[int, int]] = set()

    for pattern in _TABLE_PATTERNS:
        for m in pattern.finditer(text):
            start, end = m.start(), m.end()
            # Skip if overlapping with already-found table
            if any(s < end and e > start for s, e in seen_spans):
                continue
            table_text = m.group(0).strip()
            if len(table_text) > 100:  # Skip tiny matches
                tables.append((start, end, table_text))
                seen_spans.add((start, end))

    # Sort by position
    tables.sort(key=lambda t: t[0])
    return tables


def _split_around_tables(text: str) -> list[tuple[str, str]]:
    """
    Split text into alternating (content_type, text) segments.
    Returns: [("narrative", "..."), ("table", "..."), ("narrative", "..."), ...]
    """
    tables = _extract_tables(text)
    if not tables:
        return [("narrative", text)]

    segments: list[tuple[str, str]] = []
    cursor = 0

    for start, end, table_text in tables:
        # Narrative before this table
        if start > cursor:
            narrative = text[cursor:start].strip()
            if narrative:
                segments.append(("narrative", narrative))
        segments.append(("table", table_text))
        cursor = end

    # Trailing narrative
    if cursor < len(text):
        trailing = text[cursor:].strip()
        if trailing:
            segments.append(("narrative", trailing))

    return segments


# ── Semantic chunking for narrative ──────────────────────────────────────────

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "and", "but", "or",
    "nor", "not", "so", "yet", "both", "either", "neither", "each",
    "every", "all", "any", "few", "more", "most", "other", "some", "such",
    "no", "only", "own", "same", "than", "too", "very", "just", "because",
    "if", "when", "where", "how", "what", "which", "who", "whom", "this",
    "that", "these", "those", "i", "me", "my", "we", "our", "you", "your",
    "he", "him", "his", "she", "her", "it", "its", "they", "them", "their",
})

_WORD_RE = re.compile(r"[a-z]{3,}")


def _extract_content_tokens(s: str) -> set[str]:
    """Extract meaningful words from a sentence, excluding stopwords."""
    return {
        w for w in _WORD_RE.findall(s.lower())
        if w not in _STOPWORDS
    }


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences. Handles SEC filing conventions."""
    # Split on sentence boundaries, keeping the delimiter
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    # Also split on paragraph breaks
    sentences: list[str] = []
    for part in parts:
        sub_parts = re.split(r"\n{2,}", part)
        sentences.extend(s.strip() for s in sub_parts if s.strip())
    return sentences


def _sentence_similarity(a: str, b: str) -> float:
    """
    Lightweight topic similarity between two sentences.
    Uses word overlap (Jaccard) as a proxy for semantic similarity.
    No external model required — fast and deterministic.
    """
    tokens_a = _extract_content_tokens(a)
    tokens_b = _extract_content_tokens(b)
    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _semantic_chunk_narrative(
    text: str,
    max_chunk_size: int = 1500,
    min_chunk_size: int = 200,
    similarity_threshold: float = 0.15,
) -> list[str]:
    """
    Semantic chunking: groups related sentences by topic similarity.

    Algorithm:
    1. Split into sentences
    2. Start a new chunk when topic similarity with previous sentence drops
       below threshold, OR when accumulated size exceeds max_chunk_size
    3. Merge tiny chunks with neighbors

    This keeps related content together (e.g., all sentences about revenue
    growth stay in one chunk) instead of cutting at arbitrary character counts.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    if len(text) <= max_chunk_size:
        return [text]

    chunks: list[str] = []
    current_sentences: list[str] = [sentences[0]]
    current_size = len(sentences[0])

    for i in range(1, len(sentences)):
        sent = sentences[i]
        sent_len = len(sent)

        # Check topic continuity with the previous sentence
        similarity = _sentence_similarity(sentences[i - 1], sent)

        # Start new chunk if topic shifts or size limit reached
        topic_shift = similarity < similarity_threshold
        size_exceeded = current_size + sent_len > max_chunk_size

        if size_exceeded:
            # Force split even if under min_chunk_size — prevents oversized chunks
            chunks.append(" ".join(current_sentences))
            current_sentences = [sent]
            current_size = sent_len
        elif topic_shift and current_size >= min_chunk_size:
            chunks.append(" ".join(current_sentences))
            current_sentences = [sent]
            current_size = sent_len
        else:
            current_sentences.append(sent)
            current_size += sent_len

    # Flush remaining
    if current_sentences:
        remaining = " ".join(current_sentences)
        # Merge tiny tail into last chunk if possible
        if chunks and len(remaining) < min_chunk_size:
            chunks[-1] = chunks[-1] + " " + remaining
        else:
            chunks.append(remaining)

    return chunks


# ── Section-type detection ───────────────────────────────────────────────────

def _classify_section_type(section_label: str, section_text: str, form_type: str = "") -> str:
    """
    Determine the semantic type of a section.
    Uses form_type to disambiguate (10-K item_7 = MD&A, 20-F item_7 = major shareholders).
    For financial_statements, inspects content for sub-sections.
    """
    # Try form-specific map first
    form_upper = form_type.upper() if form_type else ""
    if "20-F" in form_upper:
        if section_label in _20F_SECTION_TYPE_MAP:
            base_type = _20F_SECTION_TYPE_MAP[section_label]
        elif section_label in _10K_SECTION_TYPE_MAP:
            base_type = _10K_SECTION_TYPE_MAP[section_label]
        else:
            base_type = _SECTION_TYPE_DEFAULTS.get(section_label, "narrative")
    else:
        if section_label in _10K_SECTION_TYPE_MAP:
            base_type = _10K_SECTION_TYPE_MAP[section_label]
        elif section_label in _20F_SECTION_TYPE_MAP:
            base_type = _20F_SECTION_TYPE_MAP[section_label]
        else:
            base_type = _SECTION_TYPE_DEFAULTS.get(section_label, "narrative")

    # For financial_statements, try to identify the specific sub-section
    if base_type == "financial_statements":
        for sub_type, pattern in _FINANCIAL_SUBSECTION_PATTERNS:
            # Check first 2000 chars for the sub-section header
            if pattern.search(section_text[:2000]):
                return sub_type
        return "financial_statements"

    return base_type


# ── Main chunker ─────────────────────────────────────────────────────────────

class StructureChunker:
    """
    Structure-aware chunker for SEC filings.

    - Tables: kept intact as single chunks (even if large)
    - Narrative: semantic chunking groups related sentences
    - Metadata: each chunk tagged with section_type, content_type, etc.
    """

    def __init__(
        self,
        max_chunk_size: int = 1500,
        min_chunk_size: int = 200,
        similarity_threshold: float = 0.15,
    ):
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.similarity_threshold = similarity_threshold

    def chunk(
        self,
        text: str,
        section_label: str = "full_text",
        ticker: str = "",
        period: str = "",
        form_type: str = "",
        provenance_header: str = "",
    ) -> list[Chunk]:
        """
        Chunk text with structure awareness.

        Returns a list of Chunk objects, each with text and ChunkMetadata.
        """
        if not text or not text.strip():
            return []

        section_type = _classify_section_type(section_label, text, form_type)

        # Split into table vs narrative segments
        segments = _split_around_tables(text)

        all_chunks: list[Chunk] = []
        chunk_idx = 0

        for content_type, segment_text in segments:
            if content_type == "table":
                # Tables: keep intact as single chunk, even if large
                all_chunks.append(Chunk(
                    text=segment_text,
                    metadata=ChunkMetadata(
                        ticker=ticker,
                        section_label=section_label,
                        section_type=section_type,
                        content_type="table",
                        period=period,
                        form_type=form_type,
                        chunk_index=chunk_idx,
                        char_count=len(segment_text),
                    ),
                ))
                chunk_idx += 1

            else:
                # Narrative: semantic chunking
                narrative_chunks = _semantic_chunk_narrative(
                    segment_text,
                    max_chunk_size=self.max_chunk_size,
                    min_chunk_size=self.min_chunk_size,
                    similarity_threshold=self.similarity_threshold,
                )
                for chunk_text in narrative_chunks:
                    all_chunks.append(Chunk(
                        text=chunk_text,
                        metadata=ChunkMetadata(
                            ticker=ticker,
                            section_label=section_label,
                            section_type=section_type,
                            content_type="narrative",
                            period=period,
                            form_type=form_type,
                            chunk_index=chunk_idx,
                            char_count=len(chunk_text),
                        ),
                    ))
                    chunk_idx += 1

        # Set total_chunks on all metadata
        for chunk in all_chunks:
            chunk.metadata.total_chunks = len(all_chunks)

        # Prepend provenance header to first chunk if provided
        if provenance_header and all_chunks:
            all_chunks[0].text = provenance_header + all_chunks[0].text
            # Update char_count to include the header
            all_chunks[0].metadata.char_count = len(all_chunks[0].text)

        logger.debug(
            f"Chunked {section_label} ({section_type}): "
            f"{len(all_chunks)} chunks "
            f"({sum(1 for c in all_chunks if c.metadata.content_type == 'table')} tables, "
            f"{sum(1 for c in all_chunks if c.metadata.content_type == 'narrative')} narrative)"
        )

        return all_chunks
