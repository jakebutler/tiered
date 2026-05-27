from __future__ import annotations

from typing import Any


ACCEPTABLE_TIERS = {"tier_1", "tier_2"}


def score_run(run_output: dict[str, Any]) -> dict[str, Any]:
    sources = run_output.get("evidence_substrate", {}).get("sources", [])
    citations = _report_citations(run_output)
    cited_or_sources = citations
    total = len(cited_or_sources)
    acceptable = [
        source
        for source in cited_or_sources
        if _tier_value(source.get("source_tier")) in ACCEPTABLE_TIERS
        or source.get("source_tier") in ("Tier 1 Source", "Tier 2 Source")
    ]
    fetched_sources = [source for source in sources if not source.get("retrieval_error")]
    tier1_found = any(
        _tier_value(source.get("source_tier")) == "tier_1"
        or source.get("source_tier") == "Tier 1 Source"
        for source in fetched_sources
    )
    evidence_gaps = run_output.get("report", {}).get("evidence_gaps", [])
    unsupported_claim_count = sum(
        1
        for claim in run_output.get("report", {}).get("key_findings", [])
        if claim.get("supported") is False
    )
    tier1_gap_disclosed = (not tier1_found) and any(
        "Tier 1" in gap or "tier 1" in gap for gap in evidence_gaps
    )
    return {
        "authority_coverage": (len(acceptable) / total) if total else 0.0,
        "acceptable_citation_count": len(acceptable),
        "total_citation_count": total,
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


def _report_citations(run_output: dict[str, Any]) -> list[dict[str, Any]]:
    citations = []
    for claim in run_output.get("report", {}).get("key_findings", []):
        citations.extend(claim.get("citations", []))
    return citations


def _tier_value(value: Any) -> str:
    if value == "Tier 1 Source":
        return "tier_1"
    if value == "Tier 2 Source":
        return "tier_2"
    if value == "Tier 3 Source":
        return "tier_3"
    return str(value or "")
