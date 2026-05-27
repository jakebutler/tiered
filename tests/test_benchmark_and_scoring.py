import asyncio

from bright_research_agent.benchmark import benchmark_questions
from bright_research_agent.comparison import compare_question, run_benchmark
from bright_research_agent.evidence import OfflineEvidenceCollector
from bright_research_agent.policy import ClaimDomain
from bright_research_agent.scoring import score_run


def test_benchmark_contains_100_questions_with_20_per_domain():
    questions = benchmark_questions()

    assert len(questions) == 100
    for domain in ClaimDomain:
        assert sum(1 for question in questions if question.claim_domain is domain) == 20
    assert all(question.expected_source_classes for question in questions)


def test_offline_comparison_improves_authority_coverage():
    comparison = asyncio.run(
        compare_question(
            "Is Ozempic indicated for chronic weight management, and what safety warnings matter?",
            OfflineEvidenceCollector(),
        )
    )

    assert comparison["baseline"]["report"]["sources_consulted"]
    assert comparison["tiered"]["policy"]["claim_domain"] == ClaimDomain.HEALTHCARE.value
    assert comparison["scores"]["tiered_improved"] is True
    assert comparison["scores"]["tiered"]["tier_1_found"] is True


def test_score_run_discloses_missing_tier_1_gap():
    run_output = {
        "evidence_substrate": {
            "sources": [{"source_tier": "tier_2"}],
        },
        "report": {
            "key_findings": [{"supported": True, "citations": [{"source_tier": "Tier 2 Source"}]}],
            "evidence_gaps": ["Expected Tier 1 Source evidence was not found."],
        },
    }

    score = score_run(run_output)

    assert score["authority_coverage"] == 1.0
    assert score["tier_1_found"] is False
    assert score["tier_1_missing_honesty"] is True


def test_benchmark_preserves_per_question_collection_failures():
    class FailingCollector:
        async def collect(self, question, run_type, policy, max_sources=5):
            raise RuntimeError("provider unavailable")

    results = asyncio.run(
        run_benchmark(
            FailingCollector(),
            domains=[ClaimDomain.HEALTHCARE],
            limit=1,
        )
    )

    case = results["cases"][0]
    assert case["baseline"]["errors"] == ["baseline evidence collection failed: provider unavailable"]
    assert case["tiered"]["errors"] == ["tiered evidence collection failed: provider unavailable"]
    assert results["summary"]["baseline_authority_coverage"] == 0.0


def test_healthcare_benchmark_runs_with_fixture_collector():
    results = asyncio.run(
        run_benchmark(
            OfflineEvidenceCollector(),
            domains=[ClaimDomain.HEALTHCARE],
            limit=2,
        )
    )

    assert results["benchmark"]["question_count"] == 2
    assert results["summary"]["tiered_authority_coverage"] > results["summary"]["baseline_authority_coverage"]


def test_benchmark_limit_zero_runs_zero_cases():
    results = asyncio.run(
        run_benchmark(
            OfflineEvidenceCollector(),
            domains=[ClaimDomain.HEALTHCARE],
            limit=0,
        )
    )

    assert results["benchmark"]["question_count"] == 0
    assert results["cases"] == []


def test_score_run_uses_claim_count_not_citation_count():
    run_output = {
        "evidence_substrate": {"sources": []},
        "report": {
            "key_findings": [
                {
                    "supported": True,
                    "citations": [
                        {"source_tier": "Tier 1 Source"},
                        {"source_tier": "Tier 2 Source"},
                        {"source_tier": "Tier 3 Source"},
                    ],
                },
                {"supported": True, "citations": [{"source_tier": "Tier 3 Source"}]},
            ],
            "evidence_gaps": [],
        },
    }

    score = score_run(run_output)

    assert score["authority_coverage"] == 0.5
    assert score["acceptable_citation_count"] == 2
    assert score["total_citation_count"] == 4


def test_score_run_falls_back_to_valid_evidence_sources_without_report_claims():
    run_output = {
        "evidence_substrate": {
            "sources": [
                {"source_tier": "tier_1"},
                {"source_tier": "tier_3"},
                {"source_tier": "tier_1", "retrieval_error": "failed"},
            ],
        },
        "report": {"key_findings": [], "evidence_gaps": []},
    }

    score = score_run(run_output)

    assert score["authority_coverage"] == 0.5
    assert score["acceptable_citation_count"] == 1
    assert score["total_citation_count"] == 2
