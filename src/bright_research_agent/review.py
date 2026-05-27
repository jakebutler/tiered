from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


REVIEW_FIELDS = (
    "case_id",
    "run_type",
    "question",
    "claim_domain",
    "source_url",
    "source_title",
    "automated_tier",
    "automated_source_class",
    "reviewer_tier",
    "support_quality",
    "notes",
)


def export_review_csv(benchmark_results: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        for case in benchmark_results.get("cases", []):
            for run_type in ("baseline", "tiered"):
                for source in case[run_type]["evidence_substrate"].get("sources", []):
                    writer.writerow(
                        {
                            "case_id": case["id"],
                            "run_type": run_type,
                            "question": case["question"],
                            "claim_domain": case["claim_domain"],
                            "source_url": source.get("url"),
                            "source_title": source.get("title"),
                            "automated_tier": source.get("source_tier_label"),
                            "automated_source_class": source.get("source_class"),
                            "reviewer_tier": "",
                            "support_quality": "",
                            "notes": "",
                        }
                    )


def summarize_review_csv(path: Path) -> dict[str, Any]:
    rows = list(csv.DictReader(path.open()))
    reviewed = [row for row in rows if row.get("reviewer_tier") or row.get("support_quality")]
    disagreements = [
        row
        for row in reviewed
        if row.get("reviewer_tier")
        and row.get("reviewer_tier") != row.get("automated_tier")
    ]
    support_counts: dict[str, int] = {}
    for row in reviewed:
        quality = row.get("support_quality") or "unlabeled"
        support_counts[quality] = support_counts.get(quality, 0) + 1
    return {
        "fields_for_human_review": [
            "automated_tier",
            "automated_source_class",
            "support_quality",
            "notes",
        ],
        "reviewed_rows": len(reviewed),
        "total_rows": len(rows),
        "tier_disagreement_count": len(disagreements),
        "support_quality_counts": support_counts,
        "confidence_note": (
            "Human adjudication increases confidence in automated benchmark labels by identifying tier-assignment disagreements and support-quality failures."
        ),
    }

