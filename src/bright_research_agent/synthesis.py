from __future__ import annotations

from typing import Any

from bright_research_agent.evidence import EvidenceItem, EvidenceSubstrate
from bright_research_agent.policy import (
    SourceAuthorityPolicy,
    SourceTier,
    TIER_LABELS,
)
from bright_research_agent.schemas import Citation, ResearchClaim, ResearchReport


def synthesize_report(
    substrate: EvidenceSubstrate,
    policy: SourceAuthorityPolicy,
) -> dict[str, Any]:
    fetched_sources = [source for source in substrate.sources if not source.retrieval_error]
    tier1_sources = [source for source in fetched_sources if source.source_tier is SourceTier.TIER_1]
    tier2_sources = [source for source in fetched_sources if source.source_tier is SourceTier.TIER_2]
    acceptable_sources = tier1_sources + tier2_sources
    if substrate.run_type == "baseline":
        cited_sources = fetched_sources[:3]
    else:
        cited_sources = acceptable_sources[:3] or fetched_sources[:2]

    evidence_gaps = []
    if not tier1_sources:
        evidence_gaps.append(
            "Expected Tier 1 Source evidence was not found; do not treat lower-tier sources as a substitute for regulator, label, or official authority."
        )
    if substrate.sources and not fetched_sources:
        evidence_gaps.append(
            "Source URLs were discovered, but page retrieval failed; discovered URLs are not counted as cited evidence."
        )
    if substrate.errors:
        evidence_gaps.append("One or more evidence collection steps failed; inspect run metadata before making strong claims.")

    answer = _answer_text(substrate, tier1_sources, tier2_sources)
    claims = [
        ResearchClaim(
            claim=_claim_text(substrate, tier1_sources, tier2_sources),
            confidence="medium" if acceptable_sources else "low",
            supported=bool(acceptable_sources),
            citations=[_citation(source) for source in cited_sources],
        )
    ]
    if substrate.run_type == "tiered":
        claims.append(
            ResearchClaim(
                claim=(
                    "The Tiered Run deliberately prioritized sources according to the "
                    f"{policy.name} Source Authority Policy."
                ),
                confidence="high",
                supported=True,
                citations=[_citation(source) for source in cited_sources[:3]],
            )
        )

    report = ResearchReport(
        question=substrate.question,
        answer=answer,
        key_findings=claims,
        open_questions=evidence_gaps,
        evidence_gaps=evidence_gaps,
        sources_consulted=[_citation(source) for source in substrate.sources],
    )
    return {
        "question": substrate.question,
        "run_type": substrate.run_type,
        "claim_domain": substrate.claim_domain,
        "policy": policy.to_dict() if substrate.run_type == "tiered" else None,
        "tiered_serp_queries": substrate.queries,
        "evidence_substrate": substrate.to_dict(),
        "report": report.model_dump(mode="json"),
        "authority_summary": authority_summary(substrate.sources),
        "metadata": substrate.metadata,
        "errors": substrate.errors,
    }


def authority_summary(sources: list[EvidenceItem]) -> dict[str, Any]:
    counts = {tier.value: 0 for tier in SourceTier}
    fetched_counts = {tier.value: 0 for tier in SourceTier}
    for source in sources:
        counts[source.source_tier.value] += 1
        if not source.retrieval_error:
            fetched_counts[source.source_tier.value] += 1
    acceptable = fetched_counts[SourceTier.TIER_1.value] + fetched_counts[SourceTier.TIER_2.value]
    fetched_total = sum(fetched_counts.values())
    return {
        "source_counts": fetched_counts,
        "discovered_source_counts": counts,
        "acceptable_source_count": acceptable,
        "total_source_count": fetched_total,
        "tier_1_found": fetched_counts[SourceTier.TIER_1.value] > 0,
        "tier_2_found": fetched_counts[SourceTier.TIER_2.value] > 0,
        "authority_coverage": (acceptable / fetched_total) if fetched_total else 0.0,
    }


def _answer_text(
    substrate: EvidenceSubstrate,
    tier1_sources: list[EvidenceItem],
    tier2_sources: list[EvidenceItem],
) -> str:
    if tier1_sources:
        return (
            f"For '{substrate.question}', the strongest collected evidence includes "
            f"{len(tier1_sources)} Tier 1 Source(s) and {len(tier2_sources)} Tier 2 Source(s). "
            "Use these sources for the demo claim about source discipline; this does not guarantee truth or replace expert review."
        )
    if tier2_sources:
        return (
            f"For '{substrate.question}', the run found Tier 2 Source evidence but no Tier 1 Source evidence. "
            "The report should present the answer with explicit uncertainty about missing primary authority."
        )
    return (
        f"For '{substrate.question}', the run did not find acceptable Tier 1 or Tier 2 Source evidence. "
        "The answer should not make a strong substantive claim."
    )


def _claim_text(
    substrate: EvidenceSubstrate,
    tier1_sources: list[EvidenceItem],
    tier2_sources: list[EvidenceItem],
) -> str:
    if tier1_sources:
        return (
            f"Collected evidence for the Research Question includes Tier 1 Source material from {tier1_sources[0].title}."
        )
    if tier2_sources:
        return (
            f"Collected evidence for the Research Question includes Tier 2 Source material from {tier2_sources[0].title}, but no Tier 1 Source."
        )
    return "Collected evidence did not include acceptable Tier 1 or Tier 2 Source material."


def _citation(source: EvidenceItem) -> Citation:
    provider_metadata = source.provider_metadata.to_dict() if source.provider_metadata else None
    return Citation(
        url=source.url,
        title=source.title or source.url,
        quote_or_evidence=source.snippet or source.content[:240],
        source_tier=TIER_LABELS[source.source_tier],
        source_class=source.source_class,
        provider_metadata=provider_metadata,
        retrieval_error=source.retrieval_error,
    )
