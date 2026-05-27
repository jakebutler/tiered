from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from bright_research_agent.benchmark import BenchmarkQuestion, benchmark_questions
from bright_research_agent.evidence import (
    BrightDataEvidenceCollector,
    CachedEvidenceCollector,
    EvidenceCollector,
    EvidenceSubstrate,
    OfflineEvidenceCollector,
)
from bright_research_agent.policy import ClaimDomain, build_policy, policy_for_question
from bright_research_agent.scoring import score_comparison
from bright_research_agent.synthesis import synthesize_report


def build_collector(
    mode: str,
    cache_dir: Optional[Path] = None,
    retries: int = 2,
) -> EvidenceCollector:
    if mode == "live":
        collector: EvidenceCollector = BrightDataEvidenceCollector(retries=retries)
    elif mode == "live-serp":
        collector = BrightDataEvidenceCollector(retries=retries, fetch_pages=False)
    elif mode == "offline":
        collector = OfflineEvidenceCollector()
    else:
        raise ValueError("mode must be 'offline', 'live', or 'live-serp'")
    if cache_dir:
        return CachedEvidenceCollector(collector, cache_dir)
    return collector


async def compare_question(
    question: str,
    collector: EvidenceCollector,
    max_sources: int = 5,
) -> dict[str, Any]:
    policy = policy_for_question(question)
    baseline_substrate, tiered_substrate = await asyncio.gather(
        _safe_collect(collector, question, "baseline", policy, max_sources=max_sources),
        _safe_collect(collector, question, "tiered", policy, max_sources=max_sources),
    )
    comparison = {
        "question": question,
        "claim_domain": policy.claim_domain.value,
        "policy": policy.to_dict(),
        "baseline": synthesize_report(baseline_substrate, policy),
        "tiered": synthesize_report(tiered_substrate, policy),
    }
    comparison["scores"] = score_comparison(comparison)
    return comparison


async def run_benchmark(
    collector: EvidenceCollector,
    domains: list[ClaimDomain] | None = None,
    max_sources: int = 5,
    limit: int | None = None,
) -> dict[str, Any]:
    questions = benchmark_questions(domains)
    if limit is not None:
        questions = questions[:limit]
    cases = []
    for question in questions:
        cases.append(await _run_benchmark_case(question, collector, max_sources=max_sources))
    baseline_coverage = _avg(case["scores"]["baseline"]["authority_coverage"] for case in cases)
    tiered_coverage = _avg(case["scores"]["tiered"]["authority_coverage"] for case in cases)
    return {
        "benchmark": {
            "question_count": len(cases),
            "domains": sorted({case["claim_domain"] for case in cases}),
            "primary_metric": "Authority Coverage",
        },
        "summary": {
            "baseline_authority_coverage": baseline_coverage,
            "tiered_authority_coverage": tiered_coverage,
            "authority_coverage_delta": tiered_coverage - baseline_coverage,
            "tiered_improved_count": sum(1 for case in cases if case["scores"]["tiered_improved"]),
        },
        "cases": cases,
    }


async def _run_benchmark_case(
    question: BenchmarkQuestion,
    collector: EvidenceCollector,
    max_sources: int,
) -> dict[str, Any]:
    policy = build_policy(question.claim_domain)
    baseline_substrate, tiered_substrate = await asyncio.gather(
        _safe_collect(collector, question.question, "baseline", policy, max_sources=max_sources),
        _safe_collect(collector, question.question, "tiered", policy, max_sources=max_sources),
    )
    comparison = {
        "id": question.id,
        "question": question.question,
        "claim_domain": question.claim_domain.value,
        "expected_source_classes": list(question.expected_source_classes),
        "policy": policy.to_dict(),
        "baseline": synthesize_report(baseline_substrate, policy),
        "tiered": synthesize_report(tiered_substrate, policy),
    }
    comparison["scores"] = score_comparison(comparison)
    return comparison


def _avg(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


async def _safe_collect(
    collector: EvidenceCollector,
    question: str,
    run_type: str,
    policy,
    max_sources: int,
) -> EvidenceSubstrate:
    try:
        return await collector.collect(question, run_type, policy, max_sources=max_sources)
    except Exception as exc:  # noqa: BLE001 - benchmark output should preserve per-question failures
        return EvidenceSubstrate(
            question=question,
            run_type=run_type,
            claim_domain=policy.claim_domain.value,
            sources=[],
            queries=[],
            metadata={"collector": collector.__class__.__name__, "failed": True},
            errors=[f"{run_type} evidence collection failed: {exc}"],
        )
