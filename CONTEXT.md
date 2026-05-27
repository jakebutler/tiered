# Tiered Research Context

Tiered Research defines how a web research agent decides which sources are authoritative before collecting evidence for a user question.

## Language

**Tiered Research**:
A research workflow that creates a source authority policy before source discovery.
_Avoid_: Better search, smarter prompting

**Research Question**:
The user's natural-language request for an evidence-backed answer.
_Avoid_: Prompt, query

**Claim Domain**:
The subject area that determines what source authority means for a research question.
_Avoid_: Category, topic

**Source Authority Policy**:
A ranked definition of acceptable sources for a claim domain.
_Avoid_: Source list, SERP instructions

**Tier 1 Source**:
A primary or authoritative source for the claim domain.
_Avoid_: Best source, trusted source

**Tier 2 Source**:
A reputable secondary source that can support or contextualize a Tier 1 source.
_Avoid_: Backup source, okay source

**Tier 3 Source**:
A lower-authority source that may aid discovery but should not carry substantive claims by itself.
_Avoid_: Bad source, random source

**Tiered SERP Query**:
A search query generated from a source authority policy to target a specific source tier.
_Avoid_: Search query, Google query

**Evidence Substrate**:
The collected source material given to the synthesis agent.
_Avoid_: Context, scraped data

**Authority Coverage**:
The share of substantive claims supported by acceptable Tier 1 or Tier 2 sources.
_Avoid_: Accuracy, confidence

**Baseline Run**:
A research run that uses ordinary SERP discovery without a source authority policy.
_Avoid_: Control, untreated run

**Tiered Run**:
A research run that uses a source authority policy to guide discovery and citation evaluation.
_Avoid_: Treatment, improved run

## Relationships

- A **Research Question** has one or more **Claim Domains**.
- A **Claim Domain** determines a **Source Authority Policy**.
- A **Source Authority Policy** defines **Tier 1 Sources**, **Tier 2 Sources**, and **Tier 3 Sources**.
- A **Source Authority Policy** produces one or more **Tiered SERP Queries**.
- A **Baseline Run** and a **Tiered Run** produce comparable **Evidence Substrates**.
- **Authority Coverage** evaluates the **Evidence Substrate**, not just the final answer.

## Example Dialogue

> **Dev:** "For a question about a public company's revenue, should peer-reviewed articles count as Tier 1?"
> **Domain expert:** "No. The **Claim Domain** is public company financial performance, so **Tier 1 Sources** are SEC filings, audited annual reports, and company investor relations materials."

## Flagged Ambiguities

- "Confidence" can mean Bright Data's search-result confidence, model certainty, answer correctness, or source authority. Resolved: use **Authority Coverage** for the primary experiment metric and reserve "confidence" for provider-specific fields only.
- "Topic" can mean the broad subject, the exact claim being evaluated, or the search phrase. Resolved: use **Claim Domain** for the source-authority category and **Research Question** for the user's request.
