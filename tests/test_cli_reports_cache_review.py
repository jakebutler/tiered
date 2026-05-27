import asyncio
import csv
import json
import os
import subprocess
import sys

from bright_research_agent.comparison import run_benchmark
from bright_research_agent.evidence import (
    BrightDataEvidenceCollector,
    CachedEvidenceCollector,
    OfflineEvidenceCollector,
)
from bright_research_agent.policy import ClaimDomain, build_policy
from bright_research_agent.reports import benchmark_markdown, comparison_markdown
from bright_research_agent.review import export_review_csv, summarize_review_csv


def test_cli_compare_writes_machine_and_human_readable_artifacts(tmp_path):
    json_path = tmp_path / "comparison.json"
    report_path = tmp_path / "comparison.md"
    env = {**os.environ, "PYTHONPATH": "src"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bright_research_agent.cli",
            "compare",
            "Is Wegovy approved for adults with obesity, and what are its major warnings?",
            "--mode",
            "offline",
            "--out",
            str(json_path),
            "--report",
            str(report_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    stdout = json.loads(result.stdout)
    data = json.loads(json_path.read_text())
    report = report_path.read_text()
    assert stdout["scores"]["tiered_improved"] is True
    assert data["baseline"]["run_type"] == "baseline"
    assert data["tiered"]["run_type"] == "tiered"
    assert "Authority Coverage" in report
    assert "Tiered improves source discipline" in report


def test_cli_tiered_outputs_policy_queries_and_tiered_evidence(tmp_path):
    json_path = tmp_path / "tiered.json"
    env = {**os.environ, "PYTHONPATH": "src"}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "bright_research_agent.cli",
            "tiered",
            "What is Humira approved to treat, and what serious infection warnings apply?",
            "--mode",
            "offline",
            "--out",
            str(json_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    data = json.loads(json_path.read_text())
    assert data["claim_domain"] == ClaimDomain.HEALTHCARE.value
    assert data["policy"]["tier_rules"]
    assert data["tiered_serp_queries"]
    assert any(
        source["source_tier_label"] == "Tier 1 Source"
        for source in data["evidence_substrate"]["sources"]
    )


def test_cached_collector_reuses_prior_artifact(tmp_path):
    class CountingCollector:
        def __init__(self):
            self.calls = 0

        async def collect(self, question, run_type, policy, max_sources=5):
            self.calls += 1
            return await OfflineEvidenceCollector().collect(question, run_type, policy, max_sources)

    inner = CountingCollector()
    collector = CachedEvidenceCollector(inner, tmp_path)
    policy = build_policy(ClaimDomain.HEALTHCARE)

    first = asyncio.run(collector.collect("Is Ozempic indicated?", "tiered", policy))
    second = asyncio.run(collector.collect("Is Ozempic indicated?", "tiered", policy))

    assert inner.calls == 1
    assert first.sources[0].url == second.sources[0].url
    assert second.metadata["cache"] == "hit"


def test_reports_preserve_provider_confidence_separately_from_authority():
    results = asyncio.run(
        run_benchmark(
            OfflineEvidenceCollector(),
            domains=[ClaimDomain.HEALTHCARE],
            limit=1,
        )
    )
    case = results["cases"][0]
    source = case["tiered"]["evidence_substrate"]["sources"][0]

    assert source["provider_metadata"]["confidence"] is not None
    assert "provider confidence" not in comparison_markdown(case).lower()
    assert "Authority Coverage" in benchmark_markdown(results)


def test_review_export_and_summary(tmp_path):
    results = asyncio.run(
        run_benchmark(
            OfflineEvidenceCollector(),
            domains=[ClaimDomain.HEALTHCARE],
            limit=1,
        )
    )
    csv_path = tmp_path / "review.csv"
    export_review_csv(results, csv_path)

    rows = list(csv.DictReader(csv_path.open()))
    rows[0]["reviewer_tier"] = "Tier 1 Source"
    rows[0]["support_quality"] = "partial"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    summary = summarize_review_csv(csv_path)

    assert summary["reviewed_rows"] == 1
    assert summary["tier_disagreement_count"] == 1
    assert summary["support_quality_counts"]["partial"] == 1
    assert "automated_tier" in summary["fields_for_human_review"]


def test_bright_data_serp_only_collector_does_not_require_unlocker(monkeypatch):
    async def fake_serp_search_api(query, country=None, max_results=5):
        return {
            "query": query,
            "country": country or "us",
            "results": [
                {
                    "title": "FDA approved prescribing information",
                    "url": "https://www.accessdata.fda.gov/drugsatfda_docs/label/demo.pdf",
                    "description": "FDA label snippet",
                    "rank": 1,
                    "confidence": 0.8,
                }
            ],
            "result_count": 1,
        }

    async def fail_unlock_url_api(*args, **kwargs):
        raise AssertionError("Unlocker should not be called in SERP-only mode")

    monkeypatch.setattr("bright_research_agent.evidence.serp_search_api", fake_serp_search_api)
    monkeypatch.setattr("bright_research_agent.evidence.unlock_url_api", fail_unlock_url_api)

    policy = build_policy(ClaimDomain.HEALTHCARE)
    substrate = asyncio.run(
        BrightDataEvidenceCollector(fetch_pages=False).collect(
            "Is Wegovy approved for adults with obesity?",
            "tiered",
            policy,
            max_sources=1,
        )
    )

    assert substrate.metadata["collector"] == "bright_data_serp_only"
    assert substrate.errors == []
    assert substrate.sources[0].source_tier_label == "Tier 1 Source"
    assert substrate.sources[0].content == "FDA label snippet"
