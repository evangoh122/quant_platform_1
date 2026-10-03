"""Tests for analytics_nl package initialization and imports."""

import importlib

import pytest


def test_package_imports():
    """analytics_nl package should import successfully."""
    import analytics_nl
    assert hasattr(analytics_nl, "SEMANTIC_MODEL_VERSION")
    assert hasattr(analytics_nl, "CanonicalIntent")
    assert hasattr(analytics_nl, "LLMIntentOutput")
    assert hasattr(analytics_nl, "PolicyOutcome")
    assert hasattr(analytics_nl, "ChartEnvelope")
    assert hasattr(analytics_nl, "ProvenanceEnvelope")


def test_version_constant():
    """SEMANTIC_MODEL_VERSION should be a nonempty string."""
    from analytics_nl.contracts import SEMANTIC_MODEL_VERSION
    assert isinstance(SEMANTIC_MODEL_VERSION, str)
    assert len(SEMANTIC_MODEL_VERSION) > 0
    assert SEMANTIC_MODEL_VERSION == "1.0.0"