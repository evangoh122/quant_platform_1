from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


class ReviewDecisionIn(BaseModel):
    cik: str = Field(max_length=10)
    accession: str = Field(max_length=25)
    form_type: str = Field(max_length=10)
    route: Literal['SAMPLED_REVIEW', 'ESCALATE']
    confidence: float = Field(ge=0.0, le=1.0)
    triggers_fired: list[str] = Field(default_factory=list)


class ReviewDecisionOut(BaseModel):
    id: str
    cik: str
    accession: str
    form_type: str
    route: Literal['SAMPLED_REVIEW', 'ESCALATE']
    confidence: float
    triggers_fired: list[str]
    status: Literal['pending', 'reviewed']
    created_at: datetime


class VerdictIn(BaseModel):
    reviewer_agrees: bool
    notes: str | None = Field(default=None, max_length=2000)


class DriftStatusOut(BaseModel):
    agreement_rate: float
    agreement_floor: float
    agreement_alert: bool
    unrecognized_concept_count: int
    concept_spike_threshold: int
    concept_alert: bool
    window_size: int
    last_updated: datetime


class CalibrationResultOut(BaseModel):
    message: str
    verdicts_used: int
    high_threshold: float | None = None
    medium_threshold: float | None = None
    projected_agreement_rate: float | None = None
