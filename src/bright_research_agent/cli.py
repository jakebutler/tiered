from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from bright_research_agent.benchmark import parse_domains
from bright_research_agent.comparison import build_collector, compare_question, run_benchmark
from bright_research_agent.policy import policy_for_question
from bright_research_agent.reports import (
    benchmark_markdown,
    comparison_markdown,
    write_json,
    write_markdown,
)
from bright_research_agent.review import export_review_csv, summarize_review_csv


logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    args = parse_args()
    configure_logging(args.log_level)
    if args.command == "policy":
        policy = policy_for_question(args.question)
        print(json.dumps(policy.to_dict(), indent=2))
        return
    if args.command == "compare":
        asyncio.run(_compare(args))
        return
    if args.command == "tiered":
        asyncio.run(_tiered(args))
        return
    if args.command == "benchmark":
        asyncio.run(_benchmark(args))
        return
    if args.command == "review-export":
        _review_export(args)
        return
    if args.command == "review-summary":
        print(json.dumps(summarize_review_csv(args.csv), indent=2))
        return
    if args.command == "live-smoke":
        asyncio.run(_live_smoke(args))
        return
    raise SystemExit(f"Unknown command: {args.command}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tiered Research demo CLI.")
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="Logging verbosity.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    policy = subparsers.add_parser("policy", help="Show selected Source Authority Policy.")
    policy.add_argument("question")

    compare = subparsers.add_parser("compare", help="Run Baseline and Tiered paths for one Research Question.")
    compare.add_argument("question")
    compare.add_argument("--mode", choices=("offline", "live", "live-serp"), default="offline")
    compare.add_argument("--max-sources", type=int, default=5)
    compare.add_argument("--cache-dir", type=Path)
    compare.add_argument("--out", type=Path, default=Path("artifacts/comparison.json"))
    compare.add_argument("--report", type=Path, default=Path("artifacts/comparison.md"))
    compare.add_argument("--retries", type=int, default=2)

    tiered = subparsers.add_parser("tiered", help="Run one Tiered Research path and emit policy, queries, and tier-labeled evidence.")
    tiered.add_argument("question")
    tiered.add_argument("--mode", choices=("offline", "live", "live-serp"), default="offline")
    tiered.add_argument("--max-sources", type=int, default=5)
    tiered.add_argument("--cache-dir", type=Path)
    tiered.add_argument("--out", type=Path, default=Path("artifacts/tiered-run.json"))
    tiered.add_argument("--retries", type=int, default=2)

    benchmark = subparsers.add_parser("benchmark", help="Run Baseline and Tiered benchmark.")
    benchmark.add_argument("--mode", choices=("offline", "live", "live-serp"), default="offline")
    benchmark.add_argument("--domain", action="append", help="Domain alias or full Claim Domain value. Repeat to include multiple domains.")
    benchmark.add_argument("--limit", type=int, help="Limit question count for smoke/demo runs.")
    benchmark.add_argument("--max-sources", type=int, default=5)
    benchmark.add_argument("--cache-dir", type=Path)
    benchmark.add_argument("--out", type=Path, default=Path("artifacts/benchmark.json"))
    benchmark.add_argument("--report", type=Path, default=Path("artifacts/benchmark.md"))
    benchmark.add_argument("--retries", type=int, default=2)

    review_export = subparsers.add_parser("review-export", help="Export benchmark cases for human adjudication.")
    review_export.add_argument("--benchmark-json", type=Path, default=Path("artifacts/benchmark.json"))
    review_export.add_argument("--out", type=Path, default=Path("artifacts/review.csv"))

    review_summary = subparsers.add_parser("review-summary", help="Summarize reviewer adjudication CSV.")
    review_summary.add_argument("csv", type=Path)

    live_smoke = subparsers.add_parser("live-smoke", help="Environment-gated live Bright Data smoke check.")
    live_smoke.add_argument("question")
    live_smoke.add_argument("--max-sources", type=int, default=2)
    live_smoke.add_argument("--cache-dir", type=Path, default=Path("artifacts/live-cache"))
    live_smoke.add_argument("--out", type=Path, default=Path("artifacts/live-smoke.json"))
    live_smoke.add_argument("--report", type=Path, default=Path("artifacts/live-smoke.md"))
    live_smoke.add_argument(
        "--serp-only",
        action="store_true",
        help="Use SERP title/snippet/URL evidence without Web Unlocker page fetching.",
    )
    return parser.parse_args()


async def _compare(args: argparse.Namespace) -> None:
    collector = build_collector(args.mode, cache_dir=args.cache_dir, retries=args.retries)
    comparison = await compare_question(args.question, collector, max_sources=args.max_sources)
    write_json(args.out, comparison)
    write_markdown(args.report, comparison_markdown(comparison))
    print(json.dumps(_comparison_summary(comparison, args.out, args.report), indent=2))


async def _tiered(args: argparse.Namespace) -> None:
    from bright_research_agent.synthesis import synthesize_report

    policy = policy_for_question(args.question)
    collector = build_collector(args.mode, cache_dir=args.cache_dir, retries=args.retries)
    substrate = await collector.collect(args.question, "tiered", policy, max_sources=args.max_sources)
    output = synthesize_report(substrate, policy)
    write_json(args.out, output)
    print(
        json.dumps(
            {
                "question": args.question,
                "claim_domain": output["claim_domain"],
                "tier_1_found": output["authority_summary"]["tier_1_found"],
                "json": str(args.out),
            },
            indent=2,
        )
    )


async def _benchmark(args: argparse.Namespace) -> None:
    collector = build_collector(args.mode, cache_dir=args.cache_dir, retries=args.retries)
    results = await run_benchmark(
        collector,
        domains=parse_domains(args.domain),
        max_sources=args.max_sources,
        limit=args.limit,
    )
    write_json(args.out, results)
    write_markdown(args.report, benchmark_markdown(results))
    print(json.dumps({"summary": results["summary"], "json": str(args.out), "report": str(args.report)}, indent=2))


async def _live_smoke(args: argparse.Namespace) -> None:
    if os.getenv("TIERED_LIVE_SMOKE") != "1":
        raise SystemExit("Set TIERED_LIVE_SMOKE=1 to run live Bright Data smoke checks.")
    required = ["BRIGHT_DATA_API_TOKEN", "BRIGHT_DATA_SERP_ZONE"]
    if not args.serp_only:
        required.append("BRIGHT_DATA_UNLOCKER_ZONE")
    for name in required:
        if not os.getenv(name):
            raise SystemExit(f"Missing required environment variable: {name}")
    collector = build_collector(
        "live-serp" if args.serp_only else "live",
        cache_dir=args.cache_dir,
        retries=1,
    )
    comparison = await compare_question(args.question, collector, max_sources=args.max_sources)
    write_json(args.out, comparison)
    write_markdown(args.report, comparison_markdown(comparison))
    print(json.dumps(_comparison_summary(comparison, args.out, args.report), indent=2))


def _review_export(args: argparse.Namespace) -> None:
    data = json.loads(args.benchmark_json.read_text())
    export_review_csv(data, args.out)
    print(json.dumps({"review_csv": str(args.out)}, indent=2))


def _comparison_summary(comparison: dict, out: Path, report: Path) -> dict:
    return {
        "question": comparison["question"],
        "claim_domain": comparison["claim_domain"],
        "scores": comparison["scores"],
        "json": str(out),
        "report": str(report),
    }


def configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), None)
    if not isinstance(level, int):
        raise SystemExit(f"Invalid log level {level_name!r}.")
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


if __name__ == "__main__":
    main()
