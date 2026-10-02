from api.services.guardrails.persona_rails import check_persona_fit
from api.routes.conjoint import role_guidance_for, ROLES


# ── role_guidance_for: tone vs requirements are both present and labelled ──────

def test_role_guidance_splits_tone_and_requirements():
    g = role_guidance_for("compliance_officer")
    assert g is not None
    assert "Tone & emphasis:" in g
    assert "Requirements (the answer must satisfy these):" in g
    # The persona's JTBD context is still there.
    assert "Compliance Officer" in g


def test_role_guidance_omits_requirements_when_blank():
    # Relationship Manager has no hard requirements -> no Requirements clause.
    g = role_guidance_for("relationship_manager")
    assert g is not None
    assert "Tone & emphasis:" in g
    assert "Requirements (the answer must satisfy these):" not in g


def test_role_guidance_unknown_role_is_none():
    assert role_guidance_for(None) is None
    assert role_guidance_for("") is None
    assert role_guidance_for("not_a_role") is None


def test_every_role_has_requirements_field():
    for r in ROLES:
        assert "answer_requirements" in r


# ── Persona-fit rail: skip / fail-open behaviour ──────────────────────────────

def test_fit_unknown_role_skipped():
    v = check_persona_fit(None, "anything")
    assert v.skipped and v.fit
    v = check_persona_fit("not_a_role", "anything")
    assert v.skipped and v.fit


def test_fit_empty_answer_skipped():
    v = check_persona_fit("compliance_officer", "   ")
    assert v.skipped and v.fit


def test_relationship_manager_has_no_requirements_skipped():
    v = check_persona_fit("relationship_manager", "A clean client-ready summary.")
    assert v.skipped and v.fit


# ── Compliance Officer: needs citation + verification ─────────────────────────

def test_compliance_miss_when_no_citation_or_verification():
    v = check_persona_fit("compliance_officer", "Revenue was strong this year.")
    assert not v.fit
    assert "cite source filing / section" in v.missing
    assert "surface verification status" in v.missing


def test_compliance_fit_with_citation_and_verification_status():
    answer = "Per Item 7 (MD&A) of the 10-K, revenue rose."
    v = check_persona_fit("compliance_officer", answer, verification_status="PASS")
    assert v.fit
    assert v.score == 0.0


def test_compliance_fit_with_inline_verification_language():
    answer = "According to the 10-K filing, the figure was verified against the XBRL facts."
    v = check_persona_fit("compliance_officer", answer)
    assert v.fit


# ── Credit Analyst: figure-conditional requirements ───────────────────────────

def test_credit_no_numbers_no_applicable_requirements_skipped():
    # No figures in the answer -> the number-conditional requirements don't apply.
    v = check_persona_fit("credit_analyst", "The borrower's outlook is discussed qualitatively.")
    assert v.skipped and v.fit


def test_credit_qualitative_citation_not_treated_as_figure():
    # Regression (round 2): Item 1A / 10-K / fiscal 2024 are filing labels, a form
    # type, and a year — NOT reported financial figures. A correctly-cited
    # qualitative credit answer must not be flagged as a MISS.
    answer = "Per Item 1A of the 10-K, liquidity risk increased in fiscal 2024."
    v = check_persona_fit("credit_analyst", answer, verification_status="SKIPPED")
    assert v.skipped and v.fit, v


def test_has_financial_figure_distinguishes_amounts_from_labels():
    from api.services.guardrails.persona_rails import _has_financial_figure
    # Real figures:
    assert _has_financial_figure("$3.4 billion")
    assert _has_financial_figure("revenue rose 12.5%")
    assert _has_financial_figure("net income was 1,200 million")
    assert _has_financial_figure("$26 billion")
    assert _has_financial_figure("a 45 % gross margin")
    # Single-letter magnitude suffixes (round 3): real figures.
    assert _has_financial_figure("Net income was 3.4B.")
    assert _has_financial_figure("revenue of 2.1M")
    assert _has_financial_figure("market cap 1.2T")
    assert _has_financial_figure("500K units sold")
    assert _has_financial_figure("cut costs by 250K this year")
    # Not figures (filing labels / form types / years / section numbers):
    assert not _has_financial_figure("Item 1A of the 10-K in fiscal 2024")
    assert not _has_financial_figure("see Part II, Item 7")
    assert not _has_financial_figure("the 8-K filed in 2023")
    assert not _has_financial_figure("Section 1.01 of the agreement")
    # Bare 1-2 digit form numbers with a letter suffix must NOT count as magnitudes.
    assert not _has_financial_figure("the 10K filing")
    assert not _has_financial_figure("an 8K was filed")
    assert not _has_financial_figure("11K plan participants")


def test_credit_unverified_suffix_figure_without_caveat_misses():
    # Round-3 regression: an unverified single-letter-suffix figure must NOT slip
    # past the credit rail — it should require a caveat.
    v = check_persona_fit("credit_analyst", "Net income was 3.4B.", verification_status="FAIL")
    assert not v.fit
    assert "caveat any unverified number" in v.missing


def test_credit_unverified_number_without_caveat_misses():
    answer = "Net income was $1,200 million."
    v = check_persona_fit("credit_analyst", answer, verification_status="FAIL")
    assert not v.fit
    assert "caveat any unverified number" in v.missing


def test_credit_verified_number_fits():
    answer = "Per the 10-K, net income was $1,200 million."
    v = check_persona_fit("credit_analyst", answer, verification_status="PASS")
    assert v.fit


def test_credit_caveated_number_fits():
    answer = "Net income was approximately $1,200 million per the 10-K, though unverified."
    v = check_persona_fit("credit_analyst", answer, verification_status="FAIL")
    assert v.fit


# ── Equity Research Analyst: needs a citation ─────────────────────────────────

def test_equity_requires_citation():
    assert not check_persona_fit("equity_research_analyst", "Margins expanded.").fit
    assert check_persona_fit(
        "equity_research_analyst", "Per Item 1A of the 10-K, margins expanded."
    ).fit
