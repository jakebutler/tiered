from __future__ import annotations

from typing import Any


ACCEPTABLE_TIERS = {"tier_1", "tier_2"}


def score_run(run_output: dict[str, Any]) -> dict[str, Any]:
    sources = run_output.get("evidence_substrate", {}).get("sources", [])
    key_findings = run_output.get("report", {}).get("key_findings", [])
    citations = _report_citations(key_findings)
    valid_sources = _valid_sources(sources)
    acceptable = [
        citation
        for citation in citations
        if _is_acceptable_authority(citation)
    ]
    tier1_found = any(
        _tier_value(source.get("source_tier")) == "tier_1"
        or source.get("source_tier") == "Tier 1 Source"
        for source in valid_sources
    )
    evidence_gaps = run_output.get("report", {}).get("evidence_gaps", [])
    unsupported_claim_count = sum(
        1
        for claim in key_findings
        if claim.get("supported") is False
    )
    authority_coverage = _claim_authority_coverage(key_findings)
    if not key_findings:
        fallback_sources = [source for source in valid_sources if _is_acceptable_authority(source)]
        authority_coverage = (len(fallback_sources) / len(valid_sources)) if valid_sources else 0.0
        if not citations:
            acceptable = fallback_sources
            citations = valid_sources
    tier1_gap_disclosed = (not tier1_found) and any(
        "Tier 1" in gap or "tier 1" in gap for gap in evidence_gaps
    )
    return {
        "authority_coverage": authority_coverage,
        "acceptable_citation_count": len(acceptable),
        "total_citation_count": len(citations),
        "unsupported_claim_count": unsupported_claim_count,
        "tier_1_found": tier1_found,
        "tier_1_missing_honesty": tier1_gap_disclosed or tier1_found,
        "citation_appropriateness": "acceptable" if acceptable else "weak",
    }


def score_comparison(comparison: dict[str, Any]) -> dict[str, Any]:
    baseline = score_run(comparison["baseline"])
    tiered = score_run(comparison["tiered"])
    return {
        "baseline": baseline,
        "tiered": tiered,
        "authority_coverage_delta": tiered["authority_coverage"] - baseline["authority_coverage"],
        "tiered_improved": tiered["authority_coverage"] > baseline["authority_coverage"],
    }


def _report_citations(key_findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations = []
    for claim in key_findings:
        citations.extend(claim.get("citations", []))
    return citations


def _claim_authority_coverage(key_findings: list[dict[str, Any]]) -> float:
    if not key_findings:
        return 0.0
    covered = [
        claim
        for claim in key_findings
        if claim.get("supported") is not False
        and any(_is_acceptable_authority(citation) for citation in claim.get("citations", []))
    ]
    return len(covered) / len(key_findings)


def _is_acceptable_authority(source: dict[str, Any]) -> bool:
    return _tier_value(source.get("source_tier")) in ACCEPTABLE_TIERS


def _valid_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [source for source in sources if not source.get("retrieval_error")]


def _tier_value(value: Any) -> str:
    if value == "Tier 1 Source":
        return "tier_1"
    if value == "Tier 2 Source":
        return "tier_2"
    if value == "Tier 3 Source":
        return "tier_3"
    return str(value or "")
