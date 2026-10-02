from api.services.verifier import verifier, Verifier

def test_verify_numeric_exact():
    assert verifier.verify_numeric(100.0, 100.0)

def test_verify_numeric_within_tolerance():
    # 0.4% difference
    assert verifier.verify_numeric(100.4, 100.0)
    assert verifier.verify_numeric(99.6, 100.0)

def test_verify_numeric_outside_tolerance():
    # 0.6% difference
    assert not verifier.verify_numeric(100.6, 100.0)
    assert not verifier.verify_numeric(99.4, 100.0)

def test_verify_numeric_zero():
    assert verifier.verify_numeric(0.0, 0.0)
    assert not verifier.verify_numeric(0.1, 0.0)

def test_verify_entailment_no_model():
    # Should return ERROR if model not loaded (or SKIPPED if sentence-transformers is missing)
    v = Verifier(model_name="non-existent-model")
    res, reason = v.verify_entailment("claim", "source")
    from api.services.verifier import CrossEncoder
    if CrossEncoder is None:
        assert res == "SKIPPED"
    else:
        assert res == "ERROR"
