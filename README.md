# Tiered Research

Tiered Research is a demo workflow for showing that a web research agent should decide what source authority means before collecting evidence.

The defensible product claim is narrow: **Tiered improves source discipline by increasing Authority Coverage**. It does not guarantee truth, replace expert review, or treat Bright Data confidence as source authority.

The repo still includes the original Bright Data/OpenAI research agent, but the hackathon demo path is the `tiered-research` CLI:

- **Baseline Run**: ordinary SERP-style discovery.
- **Tiered Run**: creates a **Source Authority Policy**, generates **Tiered SERP Queries**, collects an **Evidence Substrate**, and labels citations as **Tier 1 Source**, **Tier 2 Source**, **Tier 3 Source**, or not accepted.
- **Authority Coverage**: the share of cited evidence supported by acceptable Tier 1 or Tier 2 sources.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Fill in `.env`:

```bash
OPENAI_API_KEY=...
BRIGHT_DATA_API_TOKEN=...
BRIGHT_DATA_SERP_ZONE=serp_api1
BRIGHT_DATA_UNLOCKER_ZONE=web_unlocker1
```

## Demo Commands

Run a single healthcare comparison fully offline:

```bash
tiered-research tiered \
  "Is Ozempic indicated for chronic weight management, and what safety warnings matter?" \
  --mode offline \
  --out artifacts/tiered-run.json
```

Compare a Baseline Run against a Tiered Run:

```bash
tiered-research compare \
  "Is Ozempic indicated for chronic weight management, and what safety warnings matter?" \
  --mode offline \
  --out artifacts/comparison.json \
  --report artifacts/comparison.md
```

Run the healthcare benchmark:

```bash
tiered-research benchmark \
  --mode offline \
  --domain healthcare \
  --out artifacts/healthcare-benchmark.json \
  --report artifacts/healthcare-benchmark.md
```

Run the full 100-question benchmark shape, 20 questions per **Claim Domain**:

```bash
tiered-research benchmark \
  --mode offline \
  --out artifacts/benchmark.json \
  --report artifacts/benchmark.md
```

Export cases for follow-up human evaluation:

```bash
tiered-research review-export \
  --benchmark-json artifacts/benchmark.json \
  --out artifacts/review.csv
```

Summarize reviewer adjudication after reviewers fill in `reviewer_tier`, `support_quality`, and `notes`:

```bash
tiered-research review-summary artifacts/review.csv
```

Human review is a follow-up calibration workflow, not a requirement for the demo score. Automated scoring owns `expected_source_classes`, source-tier labels, and Authority Coverage. Reviewers adjudicate `reviewer_tier`, `support_quality`, and `notes` so later benchmark reports can distinguish source-tier assignment errors from answer-support quality failures.

Optional live Bright Data smoke checks are environment-gated:

```bash
TIERED_LIVE_SMOKE=1 tiered-research live-smoke \
  "Is Wegovy approved for adults with obesity, and what are its major warnings?"
```

If Web Unlocker is unavailable, run the live demo with SERP-only evidence:

```bash
TIERED_LIVE_SMOKE=1 tiered-research live-smoke \
  "Is Wegovy approved for adults with obesity, and what are its major warnings?" \
  --serp-only
```

SERP-only mode uses Bright Data SERP title, snippet, URL, rank, and provider metadata as the **Evidence Substrate**. It is enough to demo source authority and **Authority Coverage**; use full `live` mode later when a Web Unlocker zone is available and page bodies should be fetched.

Use `--cache-dir artifacts/cache` on compare or benchmark runs to reuse prior fetched artifacts.

## Original Agent

```bash
python -m bright_research_agent.agent \
  "What is the market positioning of Perplexity's enterprise search product?"
```

Progress and tool-call logs are written to stderr so stdout remains valid JSON:

```bash
python -m bright_research_agent.agent \
  "What is the market positioning of Perplexity's enterprise search product?" \
  --log-level INFO
```

Set `--log-level WARNING` or `LOG_LEVEL=WARNING` for quieter output.

If the OpenAI request times out, give the model call more room and reduce turns:

```bash
python -m bright_research_agent.agent \
  "What is the current landscape of GTM engineering?" \
  --openai-timeout 300 \
  --max-turns 6
```

The final output is JSON matching the Pydantic schema in `src/bright_research_agent/schemas.py`.

## What This Demonstrates

- Source authority policy selection before discovery.
- Baseline vs Tiered comparison over comparable output shapes.
- Tier-labeled citations and explicit missing Tier 1 evidence gaps.
- Machine-readable benchmark artifacts and human-readable Markdown reports.
- SERP discovery through Bright Data SERP API.
- Page retrieval through Bright Data Unlocker API.
- OpenAI Agents SDK tool orchestration.
- Pydantic output validation for citation-backed research JSON.

## Demo Notes

Say:

- Tiered improves source discipline by increasing **Authority Coverage**.
- Healthcare questions should prefer regulator, label, manufacturer, and reputable medical sources.
- Provider confidence is optional ranking metadata; it is not source authority ground truth.

Avoid saying:

- Tiered guarantees truth.
- Tiered replaces expert review.
- Higher Bright Data confidence means a source is authoritative.

## Notes

- Treat scraped content as untrusted input. The agent instructions explicitly tell the model not to follow instructions found inside retrieved pages.
- Keep `max_sources` low during demos so the workflow stays fast and inexpensive.
- This API-first version is the clearest starting point for retries, concurrency, metrics, and cost controls.
