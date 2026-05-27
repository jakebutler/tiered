from __future__ import annotations

from pathlib import Path
from typing import Any


def write_json(path: Path, data: dict[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def comparison_markdown(comparison: dict[str, Any]) -> str:
    scores = comparison["scores"]
    baseline = scores["baseline"]
    tiered = scores["tiered"]
    lines = [
        f"# Tiered Research Comparison",
        "",
        f"**Research Question:** {comparison['question']}",
        "",
        f"**Claim Domain:** `{comparison['claim_domain']}`",
        "",
        "## Authority Coverage",
        "",
        "| Run | Authority Coverage | Tier 1 Found | Acceptable Citations |",
        "| --- | ---: | --- | ---: |",
        f"| Baseline Run | {_pct(baseline['authority_coverage'])} | {_yes(baseline['tier_1_found'])} | {baseline['acceptable_citation_count']} / {baseline['total_citation_count']} |",
        f"| Tiered Run | {_pct(tiered['authority_coverage'])} | {_yes(tiered['tier_1_found'])} | {tiered['acceptable_citation_count']} / {tiered['total_citation_count']} |",
        "",
        f"**Delta:** {_pct(scores['authority_coverage_delta'])}",
        "",
        "## Product Claim",
        "",
        "Tiered improves source discipline by increasing Authority Coverage. It does not guarantee truth or replace expert review.",
        "",
        "## Tiered Source Authority Policy",
        "",
        comparison["policy"]["rationale"],
        "",
        "## Baseline Sources",
        "",
        *_source_lines(comparison["baseline"]),
        "",
        "## Tiered Sources",
        "",
        *_source_lines(comparison["tiered"]),
        "",
        "## Evidence Gaps",
        "",
        *_gap_lines(comparison),
    ]
    return "\n".join(lines) + "\n"


def benchmark_markdown(results: dict[str, Any]) -> str:
    summary = results["summary"]
    lines = [
        "# Tiered Research Benchmark",
        "",
        f"**Questions:** {results['benchmark']['question_count']}",
        f"**Domains:** {', '.join(results['benchmark']['domains'])}",
        f"**Primary Metric:** {results['benchmark']['primary_metric']}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Baseline Authority Coverage | {_pct(summary['baseline_authority_coverage'])} |",
        f"| Tiered Authority Coverage | {_pct(summary['tiered_authority_coverage'])} |",
        f"| Authority Coverage Delta | {_pct(summary['authority_coverage_delta'])} |",
        f"| Tiered Improved Cases | {summary['tiered_improved_count']} |",
        "",
        "## Representative Cases",
        "",
    ]
    for case in results["cases"][:10]:
        lines.extend(
            [
                f"### {case['id']}",
                "",
                case["question"],
                "",
                f"- Baseline: {_pct(case['scores']['baseline']['authority_coverage'])}",
                f"- Tiered: {_pct(case['scores']['tiered']['authority_coverage'])}",
                f"- Delta: {_pct(case['scores']['authority_coverage_delta'])}",
                f"- Tier 1 found by Tiered: {_yes(case['scores']['tiered']['tier_1_found'])}",
                "",
            ]
        )
    lines.extend(
        [
            "## Demo Notes",
            "",
            "Say: Tiered improves source discipline by increasing Authority Coverage.",
            "",
            "Avoid saying: Tiered guarantees truth, replaces expert review, or treats provider confidence as source authority.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _source_lines(run_output: dict[str, Any]) -> list[str]:
    sources = run_output["evidence_substrate"]["sources"]
    if not sources:
        return ["- No sources collected."]
    return [
        f"- **{source.get('source_tier_label', 'Not accepted')}**: [{source.get('title')}]({source.get('url')})"
        for source in sources[:6]
    ]


def _gap_lines(comparison: dict[str, Any]) -> list[str]:
    gaps = []
    for run_type in ("baseline", "tiered"):
        for gap in comparison[run_type]["report"].get("evidence_gaps", []):
            gaps.append(f"- {run_type.title()}: {gap}")
    return gaps or ["- No evidence gaps reported."]


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _yes(value: bool) -> str:
    return "yes" if value else "no"

