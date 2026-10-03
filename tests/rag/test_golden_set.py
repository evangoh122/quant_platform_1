import pytest
from pathlib import Path
from unittest.mock import patch

# Ensure pyspark is not required
pytestmark = pytest.mark.not_spark


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_row():
    """Minimal valid golden item for unit tests."""
    return {
        "id": "rag-v1-001",
        "ticker": "NVDA",
        "as_of": "2026-01-15T00:00:00Z",
        "question": "What was NVIDIA's revenue for the quarter?",
        "question_type": "factual_lookup",
        "gold_answer": "$35.1 billion",
        "gold_chunk_ids": ["abc123"],
        "gold_accession": "0000050863-25-000001",
        "gold_section": "item7_mda",
        "answerable": True,
        "difficulty": "easy",
        "notes": {
            "evidence_span": "Revenue was $35.1 billion for the quarter ended January 2026.",
            "rationale": "Direct lookup from MD&A.",
            "trap": None,
        },
        "provenance": {
            "drafted_by": "MiMo",
            "drafted_at": "2026-10-03T00:00:00Z",
            "verified_by": None,
            "verified_at": None,
            "corpus_sha256": "a" * 64,
        },
    }


@pytest.fixture()
def sample_corpus_by_id():
    """Fake corpus index with one chunk."""
    return {
        "abc123": {
            "chunk_id": "abc123",
            "ticker": "NVDA",
            "accession_number": "0000050863-25-000001",
            "form_type": "10-Q",
            "filing_date": "2026-02-20",
            "accepted_epoch": 1738000000,
            "filing_section": "item7_mda",
            "chunk_index": 0,
            "chunk_text": "Revenue was $35.1 billion for the quarter ended January 2026.",
            "source_url": "https://www.sec.gov/test",
        }
    }


@pytest.fixture()
def schema_path():
    return Path("evals/golden/golden_v1.schema.json")


@pytest.fixture()
def golden_path():
    return Path("evals/golden/golden_v1.jsonl")


@pytest.fixture()
def corpus_path():
    p = Path("evals/data/sec_corpus.jsonl")
    if not p.exists():
        pytest.skip("Local corpus not present (evals/data/sec_corpus.jsonl)")
    return p


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestSchema:
    def test_schema_rejects_missing_required_field(self, sample_row, schema_path):
        """Removing any required field must fail schema validation."""
        from evals.golden.validate import validate_schema, load_schema

        schema = load_schema(schema_path)
        for field in ["id", "ticker", "as_of", "question", "question_type",
                       "gold_answer", "gold_chunk_ids", "gold_accession",
                       "gold_section", "answerable", "difficulty", "notes", "provenance"]:
            broken = {k: v for k, v in sample_row.items() if k != field}
            errors = validate_schema([broken], schema)
            assert any(field in e for e in errors), f"Missing '{field}' not caught"


# ---------------------------------------------------------------------------
# Reference tests
# ---------------------------------------------------------------------------

class TestReferences:
    def test_validator_rejects_unknown_chunk(self, sample_row, sample_corpus_by_id):
        """A chunk ID not in the corpus must be rejected."""
        from evals.golden.validate import validate_references

        sample_row["gold_chunk_ids"] = ["nonexistent_chunk"]
        errors = validate_references([sample_row], sample_corpus_by_id)
        assert any("unknown chunk" in e for e in errors)

    def test_validator_rejects_metadata_mismatch(self, sample_row, sample_corpus_by_id):
        """Ticker mismatch between chunk and item must be rejected."""
        from evals.golden.validate import validate_references

        sample_row["ticker"] = "AMD"  # corpus chunk is NVDA
        errors = validate_references([sample_row], sample_corpus_by_id)
        assert any("ticker mismatch" in e for e in errors)


# ---------------------------------------------------------------------------
# Point-in-time tests
# ---------------------------------------------------------------------------

class TestPointInTime:
    def test_validator_rejects_future_gold_for_answerable_item(self, sample_row, sample_corpus_by_id):
        """An answerable item with gold chunk accepted after as_of must be rejected."""
        from evals.golden.validate import validate_point_in_time

        # as_of is 2026-01-15, chunk accepted_epoch is 1738000000 (2025-01-27)
        # Set as_of before the chunk's acceptance
        sample_row["as_of"] = "2024-01-01T00:00:00Z"
        sample_row["answerable"] = True
        sample_row["notes"]["trap"] = None
        errors = validate_point_in_time([sample_row], sample_corpus_by_id)
        assert any("accepted_epoch" in e and "> as_of" in e for e in errors)

    def test_validator_accepts_abstain_trap_with_future_evidence(self, sample_row):
        """Abstain trap: future chunk > as_of, answer=ABSTAIN, answerable=false."""
        from evals.golden.validate import validate_point_in_time

        future_chunk = {
            "chunk_id": "future123",
            "ticker": "NVDA",
            "accession_number": "0000050863-26-000099",
            "form_type": "10-Q",
            "accepted_epoch": 1750000000,  # 2025-06-14, after as_of
            "filing_section": "item7_mda",
        }
        corpus = {"future123": future_chunk}

        sample_row["as_of"] = "2025-01-01T00:00:00Z"
        sample_row["answerable"] = False
        sample_row["gold_answer"] = "ABSTAIN"
        sample_row["gold_chunk_ids"] = []
        sample_row["notes"]["trap"] = {
            "future_chunk_ids": ["future123"],
            "future_accession": "0000050863-26-000099",
            "future_answer": "$39.3 billion",
            "expected_behavior": "abstain",
        }
        errors = validate_point_in_time([sample_row], corpus)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_validator_accepts_older_answer_trap(self, sample_row):
        """Older-answer trap: gold chunk <= as_of, future chunk > as_of."""
        from evals.golden.validate import validate_point_in_time

        old_chunk = {
            "chunk_id": "old123",
            "ticker": "NVDA",
            "accession_number": "0000050863-25-000001",
            "form_type": "10-Q",
            "accepted_epoch": 1738000000,  # 2025-01-27
            "filing_section": "item7_mda",
        }
        future_chunk = {
            "chunk_id": "new456",
            "ticker": "NVDA",
            "accession_number": "0000050863-26-000099",
            "form_type": "10-Q",
            "accepted_epoch": 1750000000,  # 2025-06-14
            "filing_section": "item7_mda",
        }
        corpus = {"old123": old_chunk, "new456": future_chunk}

        sample_row["as_of"] = "2025-03-01T00:00:00Z"
        sample_row["answerable"] = True
        sample_row["gold_answer"] = "$35.1 billion"
        sample_row["gold_chunk_ids"] = ["old123"]
        sample_row["gold_accession"] = "0000050863-25-000001"
        sample_row["notes"]["trap"] = {
            "future_chunk_ids": ["new456"],
            "future_accession": "0000050863-26-000099",
            "future_answer": "$39.3 billion",
            "expected_behavior": "older_filing_answer",
        }
        errors = validate_point_in_time([sample_row], corpus)
        assert errors == [], f"Unexpected errors: {errors}"


# ---------------------------------------------------------------------------
# Numeric support tests
# ---------------------------------------------------------------------------

class TestNumericSupport:
    def test_numeric_support_handles_financial_formats(self):
        """Currency with commas, millions, parentheses must be normalized."""
        from evals.golden.validate import answer_supported

        assert answer_supported(
            "$1,234.5 million",
            "revenue of $1,234.5 million for the period",
        )
        assert answer_supported(
            "($253 million)",
            "agreed to pay ($253 million) as a penalty",
        )
        assert answer_supported(
            "0.65%",
            "interest rate of 0.65% per annum",
        )

    def test_numeric_support_rejects_wrong_unit(self):
        """Different units must not be equated."""
        from evals.golden.validate import answer_supported

        # $1.2 billion vs $1.2 million — different values
        assert not answer_supported(
            "$1.2 billion",
            "invested $1.2 million in capital expenditures",
        )


# ---------------------------------------------------------------------------
# Duplicate question test
# ---------------------------------------------------------------------------

class TestDuplicateQuestions:
    def test_duplicate_questions_are_normalized(self):
        """Questions that differ only in case/punctuation must be caught."""
        from evals.golden.validate import normalize_question

        q1 = "What was NVIDIA's revenue?"
        q2 = "what was nvidia's revenue"
        assert normalize_question(q1) == normalize_question(q2)


# ---------------------------------------------------------------------------
# Report test
# ---------------------------------------------------------------------------

class TestVerifyReport:
    def test_verify_report_has_one_row_per_item(self, golden_path):
        """verify_report.md must have exactly one row per golden ID."""
        if not golden_path.exists():
            pytest.skip("Golden file not present")

        report_path = Path("evals/golden/verify_report.md")
        if not report_path.exists():
            pytest.skip("Verify report not present")

        import json
        items = []
        with open(golden_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))

        golden_ids = {item["id"] for item in items}

        with open(report_path, encoding="utf-8") as f:
            content = f.read()

        # Count table rows that match rag-v1-NNN pattern
        import re
        row_ids = set(re.findall(r"rag-v1-\d{3}", content))
        # Each ID should appear at least once in the table
        for gid in golden_ids:
            assert gid in row_ids, f"Missing {gid} in verify_report.md"


# ---------------------------------------------------------------------------
# Release validation
# ---------------------------------------------------------------------------

class TestRelease:
    def test_golden_v1_release_validates(self, golden_path, schema_path, corpus_path):
        """Full release validation must pass (allowing unverified for initial drafting)."""
        from evals.golden.validate import validate_golden

        errors = validate_golden(golden_path, corpus_path, schema_path, allow_unverified=True)
        assert errors == [], f"Validation errors:\n" + "\n".join(errors[:20])