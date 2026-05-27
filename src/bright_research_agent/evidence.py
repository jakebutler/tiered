from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from bright_research_agent.brightdata import serp_search_api, unlock_url_api
from bright_research_agent.policy import (
    SourceAuthorityPolicy,
    SourceTier,
    TIER_LABELS,
)


logger = logging.getLogger(__name__)


@dataclass
class ProviderMetadata:
    provider: str
    confidence: Optional[float] = None
    rank: Optional[int] = None
    raw: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass
class EvidenceItem:
    url: str
    title: str
    snippet: str
    content: str = ""
    source_tier: SourceTier = SourceTier.NOT_ACCEPTED
    source_tier_label: str = TIER_LABELS[SourceTier.NOT_ACCEPTED]
    source_class: str = "unclassified"
    provider_metadata: Optional[ProviderMetadata] = None
    retrieval_error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_tier"] = self.source_tier.value
        data["source_tier_label"] = TIER_LABELS[self.source_tier]
        if self.provider_metadata:
            data["provider_metadata"] = self.provider_metadata.to_dict()
        else:
            data.pop("provider_metadata", None)
        return {key: value for key, value in data.items() if value not in (None, "")}


@dataclass
class EvidenceSubstrate:
    question: str
    run_type: str
    claim_domain: str
    sources: list[EvidenceItem]
    queries: list[dict[str, Any]]
    metadata: dict[str, Any]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "run_type": self.run_type,
            "claim_domain": self.claim_domain,
            "sources": [source.to_dict() for source in self.sources],
            "queries": self.queries,
            "metadata": self.metadata,
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceSubstrate":
        sources = []
        for item in data.get("sources", []):
            tier = SourceTier(item.get("source_tier", SourceTier.NOT_ACCEPTED.value))
            provider_data = item.get("provider_metadata")
            provider_metadata = (
                ProviderMetadata(**provider_data) if isinstance(provider_data, dict) else None
            )
            sources.append(
                EvidenceItem(
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    snippet=item.get("snippet", ""),
                    content=item.get("content", ""),
                    source_tier=tier,
                    source_tier_label=TIER_LABELS[tier],
                    source_class=item.get("source_class", "unclassified"),
                    provider_metadata=provider_metadata,
                    retrieval_error=item.get("retrieval_error"),
                )
            )
        return cls(
            question=data["question"],
            run_type=data["run_type"],
            claim_domain=data["claim_domain"],
            sources=sources,
            queries=list(data.get("queries", [])),
            metadata=dict(data.get("metadata", {})),
            errors=list(data.get("errors", [])),
        )


class EvidenceCollector(Protocol):
    async def collect(
        self,
        question: str,
        run_type: str,
        policy: SourceAuthorityPolicy,
        max_sources: int = 5,
    ) -> EvidenceSubstrate:
        ...


class OfflineEvidenceCollector:
    """Deterministic fixture-backed collector for local demos and tests."""

    async def collect(
        self,
        question: str,
        run_type: str,
        policy: SourceAuthorityPolicy,
        max_sources: int = 5,
    ) -> EvidenceSubstrate:
        sources = _offline_sources(question, run_type, policy)[:max_sources]
        return EvidenceSubstrate(
            question=question,
            run_type=run_type,
            claim_domain=policy.claim_domain.value,
            sources=sources,
            queries=_queries_for_run(question, run_type, policy),
            metadata={
                "collector": "offline",
                "retries": 0,
                "latency_ms": 0,
                "cost_usd": None,
            },
            errors=[],
        )


class BrightDataEvidenceCollector:
    def __init__(
        self,
        retries: int = 2,
        country: Optional[str] = None,
        fetch_pages: bool = True,
    ) -> None:
        self.retries = max(0, retries)
        self.country = country
        self.fetch_pages = fetch_pages

    async def collect(
        self,
        question: str,
        run_type: str,
        policy: SourceAuthorityPolicy,
        max_sources: int = 5,
    ) -> EvidenceSubstrate:
        start = time.monotonic()
        errors: list[str] = []
        query_specs = _queries_for_run(question, run_type, policy)
        search_results: list[dict[str, Any]] = []
        for query_spec in query_specs[:3]:
            try:
                search = await _retry(
                    lambda: serp_search_api(
                        query_spec["query"],
                        country=self.country,
                        max_results=max_sources,
                    ),
                    retries=self.retries,
                )
                search_results.extend(search.get("results", []))
            except Exception as exc:  # noqa: BLE001 - user-facing per-question error
                errors.append(f"SERP failed for {query_spec['query']!r}: {exc}")

        deduped = _dedupe_results(search_results)[:max_sources]
        if not self.fetch_pages:
            return EvidenceSubstrate(
                question=question,
                run_type=run_type,
                claim_domain=policy.claim_domain.value,
                sources=_rank_sources(
                    [
                        _evidence_item_from_serp_result(
                            result,
                            policy.tier_for_url(result.get("url") or ""),
                        )
                        for result in deduped
                    ]
                ),
                queries=query_specs,
                metadata={
                    "collector": "bright_data_serp_only",
                    "retries": self.retries,
                    "latency_ms": round((time.monotonic() - start) * 1000),
                    "cost_usd": None,
                    "page_fetching": "disabled",
                },
                errors=errors,
            )

        pages = await asyncio.gather(
            *[
                _retry(lambda url=item["url"]: unlock_url_api(url, country=self.country), self.retries)
                for item in deduped
                if item.get("url")
            ],
            return_exceptions=True,
        )

        sources: list[EvidenceItem] = []
        for result, page in zip(deduped, pages):
            url = result.get("url") or ""
            tier = policy.tier_for_url(url) if run_type == "tiered" else SourceTier.NOT_ACCEPTED
            if run_type == "baseline":
                tier = policy.tier_for_url(url)
            provider_metadata = ProviderMetadata(
                provider="bright_data",
                confidence=_coerce_confidence(result.get("confidence")),
                rank=result.get("rank"),
                raw={
                    key: result[key]
                    for key in ("source", "description")
                    if key in result and result[key] is not None
                },
            )
            if isinstance(page, Exception):
                errors.append(f"Fetch failed for {url}: {page}")
                sources.append(
                    EvidenceItem(
                        url=url,
                        title=result.get("title") or url,
                        snippet=result.get("description") or "",
                        source_tier=tier,
                        source_tier_label=TIER_LABELS[tier],
                        source_class=_source_class_for_tier(tier),
                        provider_metadata=provider_metadata,
                        retrieval_error=str(page),
                    )
                )
            else:
                sources.append(
                    EvidenceItem(
                        url=url,
                        title=result.get("title") or url,
                        snippet=result.get("description") or "",
                        content=page.get("content", ""),
                        source_tier=tier,
                        source_tier_label=TIER_LABELS[tier],
                        source_class=_source_class_for_tier(tier),
                        provider_metadata=provider_metadata,
                    )
                )

        return EvidenceSubstrate(
            question=question,
            run_type=run_type,
            claim_domain=policy.claim_domain.value,
            sources=_rank_sources(sources),
            queries=query_specs,
            metadata={
                "collector": "bright_data",
                "retries": self.retries,
                "latency_ms": round((time.monotonic() - start) * 1000),
                "cost_usd": None,
            },
            errors=errors,
        )


class CachedEvidenceCollector:
    def __init__(self, inner: EvidenceCollector, cache_dir: Path) -> None:
        self.inner = inner
        self.cache_dir = cache_dir

    async def collect(
        self,
        question: str,
        run_type: str,
        policy: SourceAuthorityPolicy,
        max_sources: int = 5,
    ) -> EvidenceSubstrate:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        key = _cache_key(
            question,
            run_type,
            policy.claim_domain.value,
            max_sources,
            _collector_namespace(self.inner),
        )
        cache_path = self.cache_dir / f"{key}.json"
        if cache_path.exists():
            data = json.loads(cache_path.read_text())
            substrate = EvidenceSubstrate.from_dict(data)
            substrate.metadata["cache"] = "hit"
            return substrate
        substrate = await self.inner.collect(question, run_type, policy, max_sources)
        substrate.metadata["cache"] = "miss"
        cache_path.write_text(json.dumps(substrate.to_dict(), indent=2))
        return substrate


async def _retry(call, retries: int) -> Any:
    attempt = 0
    while True:
        try:
            return await call()
        except Exception:
            if attempt >= retries:
                raise
            attempt += 1
            await asyncio.sleep(min(0.25 * attempt, 1.0))


def _queries_for_run(
    question: str,
    run_type: str,
    policy: SourceAuthorityPolicy,
) -> list[dict[str, Any]]:
    if run_type == "baseline":
        return [
            {
                "tier": None,
                "tier_label": None,
                "query": question,
                "rationale": "Baseline Run uses ordinary SERP discovery without a Source Authority Policy.",
            }
        ]
    return [query.to_dict() for query in policy.generate_queries(question)]


def _offline_sources(
    question: str,
    run_type: str,
    policy: SourceAuthorityPolicy,
) -> list[EvidenceItem]:
    if run_type == "baseline":
        urls = [
            ("https://www.healthline.com/health/drugs/demo-drug", "Healthline drug overview", SourceTier.TIER_3, 0.91),
            ("https://www.goodrx.com/demo-drug/what-is", "GoodRx consumer summary", SourceTier.TIER_3, 0.87),
            ("https://medlineplus.gov/druginfo/meds/demo.html", "MedlinePlus drug information", SourceTier.TIER_2, 0.72),
        ]
    else:
        urls = [
            ("https://www.accessdata.fda.gov/drugsatfda_docs/label/demo-label.pdf", "FDA approved prescribing information", SourceTier.TIER_1, 0.82),
            ("https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=demo", "DailyMed official label", SourceTier.TIER_1, 0.78),
            ("https://medlineplus.gov/druginfo/meds/demo.html", "MedlinePlus clinical summary", SourceTier.TIER_2, 0.69),
            ("https://www.drugs.com/demo.html", "Drugs.com consumer summary", SourceTier.TIER_3, 0.88),
        ]

    items = []
    for rank, (url, title, tier, confidence) in enumerate(urls, start=1):
        policy_tier = policy.tier_for_url(url)
        tier = policy_tier if policy_tier is not SourceTier.NOT_ACCEPTED else tier
        items.append(
            EvidenceItem(
                url=url,
                title=title,
                snippet=f"Fixture evidence for: {question}",
                content=(
                    f"{title} discusses the indication and safety context for the "
                    f"research question: {question}."
                ),
                source_tier=tier,
                source_tier_label=TIER_LABELS[tier],
                source_class=_source_class_for_tier(tier),
                provider_metadata=ProviderMetadata(
                    provider="offline_fixture",
                    confidence=confidence,
                    rank=rank,
                ),
            )
        )
    return _rank_sources(items)


def _rank_sources(sources: list[EvidenceItem]) -> list[EvidenceItem]:
    authority_order = {
        SourceTier.TIER_1: 0,
        SourceTier.TIER_2: 1,
        SourceTier.TIER_3: 2,
        SourceTier.NOT_ACCEPTED: 3,
    }
    return sorted(
        sources,
        key=lambda source: (
            authority_order[source.source_tier],
            -(source.provider_metadata.confidence or 0.0) if source.provider_metadata else 0.0,
        ),
    )


def _source_class_for_tier(tier: SourceTier) -> str:
    if tier is SourceTier.TIER_1:
        return "regulator_or_approved_label"
    if tier is SourceTier.TIER_2:
        return "reputable_medical_reference"
    if tier is SourceTier.TIER_3:
        return "generic_health_explainer"
    return "not_accepted"


def _cache_key(
    question: str,
    run_type: str,
    claim_domain: str,
    max_sources: int,
    namespace: str,
) -> str:
    raw = json.dumps(
        {
            "namespace": namespace,
            "question": question,
            "run_type": run_type,
            "claim_domain": claim_domain,
            "max_sources": max_sources,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _collector_namespace(collector: EvidenceCollector) -> str:
    if isinstance(collector, BrightDataEvidenceCollector):
        return json.dumps(
            {
                "collector": collector.__class__.__name__,
                "country": collector.country,
                "fetch_pages": collector.fetch_pages,
                "retries": collector.retries,
                "serp_zone": os.getenv("BRIGHT_DATA_SERP_ZONE"),
                "unlocker_zone": os.getenv("BRIGHT_DATA_UNLOCKER_ZONE"),
            },
            sort_keys=True,
        )
    return collector.__class__.__name__


def _dedupe_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for result in results:
        url = result.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(result)
    return deduped


def _evidence_item_from_serp_result(
    result: dict[str, Any],
    tier: SourceTier,
) -> EvidenceItem:
    description = result.get("description") or ""
    return EvidenceItem(
        url=result.get("url") or "",
        title=result.get("title") or result.get("url") or "",
        snippet=description,
        content=description,
        source_tier=tier,
        source_tier_label=TIER_LABELS[tier],
        source_class=_source_class_for_tier(tier),
        provider_metadata=ProviderMetadata(
            provider="bright_data_serp",
            confidence=_coerce_confidence(result.get("confidence")),
            rank=result.get("rank"),
            raw={
                key: result[key]
                for key in ("source", "description")
                if key in result and result[key] is not None
            },
        ),
    )


def _coerce_confidence(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
