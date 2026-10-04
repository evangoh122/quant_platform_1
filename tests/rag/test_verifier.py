import numpy as np
from unittest.mock import MagicMock

from tests.rag.conftest import _FakeCrossEncoder


def test_verify_numeric_exact():
    from api.services.verifier import verifier
    assert verifier.verify_numeric(100.0, 100.0)

def test_verify_numeric_within_tolerance():
    from api.services.verifier import verifier
    # 0.4% difference
    assert verifier.verify_numeric(100.4, 100.0)
    assert verifier.verify_numeric(99.6, 100.0)

def test_verify_numeric_outside_tolerance():
    from api.services.verifier import verifier
    # 0.6% difference
    assert not verifier.verify_numeric(100.6, 100.0)
    assert not verifier.verify_numeric(99.4, 100.0)

def test_verify_numeric_zero():
    from api.services.verifier import verifier
    assert verifier.verify_numeric(0.0, 0.0)
    assert not verifier.verify_numeric(0.1, 0.0)

def test_verify_entailment_no_model():
    """With fake CrossEncoder, model loads successfully → returns PASS (entailment)."""
    from api.services.verifier import Verifier, CrossEncoder
    v = Verifier(model_name="non-existent-model")
    if CrossEncoder is None:
        res, reason = v.verify_entailment("claim", "source")
        assert res == "ERROR"
    else:
        res, reason = v.verify_entailment("claim", "source")
        assert res == "PASS"

def test_verify_entailment_model_none():
    """Explicit model=None → SKIPPED."""
    from api.services.verifier import Verifier
    v = Verifier()
    v.model = None
    v._model_initialised = True
    v.failed_to_load = False
    res, reason = v.verify_entailment("claim", "source")
    assert res == "SKIPPED"

def test_verify_entailment_entailment():
    """Fake CrossEncoder returning entailment scores → PASS."""
    from api.services.verifier import Verifier
    v = Verifier()
    mock_model = MagicMock()
    mock_model.predict.return_value = np.array([[0.1, 0.2, 0.7]])
    v.model = mock_model
    v._model_initialised = True
    v.failed_to_load = False
    res, reason = v.verify_entailment("claim", "source")
    assert res == "PASS"
    assert "entails" in reason.lower()

def test_verify_entailment_contradiction():
    """Fake CrossEncoder returning contradiction scores → FAIL."""
    from api.services.verifier import Verifier
    v = Verifier()
    mock_model = MagicMock()
    mock_model.predict.return_value = np.array([[0.8, 0.15, 0.05]])
    v.model = mock_model
    v._model_initialised = True
    v.failed_to_load = False
    res, reason = v.verify_entailment("claim", "source")
    assert res == "FAIL"
    assert "contradicts" in reason.lower()

def test_no_cross_encoder_constructed():
    """Guard: CrossEncoder must be patched to fake; no real model may load."""
    from api.services.verifier import verifier, CrossEncoder
    assert CrossEncoder is _FakeCrossEncoder, "CrossEncoder patch not active"
    if verifier.model is not None:
        assert isinstance(verifier.model, MagicMock), (
            f"Real CrossEncoder model loaded: {type(verifier.model)}"
        )