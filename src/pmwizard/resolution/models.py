"""Explainable models for Entity Resolution V0."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResolutionOutcome(StrEnum):
    MATCHED = "matched"
    NEEDS_REVIEW = "needs_review"
    NO_MATCH = "no_match"


class ResolutionContext(BaseModel):
    """Optional structured hints extracted before resolution."""

    model_config = ConfigDict(extra="forbid")

    owner_id: UUID | None = None


class ScoreBreakdown(BaseModel):
    """Transparent components used to calculate a candidate score."""

    model_config = ConfigDict(extra="forbid")

    phrase_match: float = Field(ge=0.0, le=1.0)
    title_coverage: float = Field(ge=0.0, le=1.0)
    text_similarity: float = Field(ge=0.0, le=1.0)
    token_overlap: float = Field(ge=0.0, le=1.0)
    owner_match: float = Field(ge=0.0, le=1.0)
    temporal_proximity: float = Field(ge=0.0, le=1.0)


class ResolutionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str
    entity_id: UUID
    title: str
    score: float = Field(ge=0.0, le=1.0)
    breakdown: ScoreBreakdown
    reasons: list[str] = Field(default_factory=list)


class ResolutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: ResolutionOutcome
    query_text: str
    best_candidate: ResolutionCandidate | None = None
    candidates: list[ResolutionCandidate] = Field(default_factory=list)
    explanation: str
