from typing import Any, Optional

from pydantic import BaseModel, Field


class Citation(BaseModel):
    url: str = Field(description="Source URL.")
    title: str = Field(description="Human-readable source title when available.")
    quote_or_evidence: str = Field(
        description="Short paraphrase or brief evidence snippet supporting a claim."
    )
    source_tier: Optional[str] = Field(
        default=None,
        description="Tier 1 Source, Tier 2 Source, Tier 3 Source, or not accepted.",
    )
    source_class: Optional[str] = Field(default=None)
    provider_metadata: Optional[dict[str, Any]] = Field(default=None)
    retrieval_error: Optional[str] = Field(default=None)


class ResearchClaim(BaseModel):
    claim: str
    confidence: str = Field(description="low, medium, or high")
    citations: list[Citation]
    supported: bool = True


class ResearchReport(BaseModel):
    question: str
    answer: str
    key_findings: list[ResearchClaim]
    open_questions: list[str] = Field(
        description="Important unknowns, contradictions, or areas needing paid/private data."
    )
    sources_consulted: list[Citation]
    evidence_gaps: list[str] = Field(default_factory=list)
