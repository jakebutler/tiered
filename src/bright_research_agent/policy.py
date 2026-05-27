from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Optional
from urllib.parse import urlparse


class ClaimDomain(str, Enum):
    HEALTHCARE = "healthcare_drug_indication_safety"
    FINANCIAL = "public_company_financial_performance"
    LEGAL = "legal_regulatory_status"
    POSITIONING = "product_company_positioning"
    SCIENTIFIC = "academic_scientific_claims"


class SourceTier(str, Enum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"
    NOT_ACCEPTED = "not_accepted"


TIER_LABELS = {
    SourceTier.TIER_1: "Tier 1 Source",
    SourceTier.TIER_2: "Tier 2 Source",
    SourceTier.TIER_3: "Tier 3 Source",
    SourceTier.NOT_ACCEPTED: "Not accepted by policy",
}


@dataclass(frozen=True)
class SourceTierRule:
    tier: SourceTier
    source_class: str
    description: str
    host_patterns: tuple[str, ...]
    query_modifiers: tuple[str, ...]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["tier"] = self.tier.value
        data["label"] = TIER_LABELS[self.tier]
        return data


@dataclass(frozen=True)
class TieredSERPQuery:
    tier: SourceTier
    query: str
    rationale: str

    def to_dict(self) -> dict:
        return {
            "tier": self.tier.value,
            "tier_label": TIER_LABELS[self.tier],
            "query": self.query,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class SourceAuthorityPolicy:
    claim_domain: ClaimDomain
    name: str
    rationale: str
    tier_rules: tuple[SourceTierRule, ...]
    expected_source_classes: tuple[str, ...]

    def tier_for_url(self, url: str) -> SourceTier:
        rule = self.rule_for_url(url)
        return rule.tier if rule else SourceTier.NOT_ACCEPTED

    def source_class_for_url(self, url: str) -> str:
        rule = self.rule_for_url(url)
        return rule.source_class if rule else "not_accepted"

    def rule_for_url(self, url: str) -> Optional[SourceTierRule]:
        host = normalized_host(url)
        for rule in self.tier_rules:
            if any(pattern in host for pattern in rule.host_patterns):
                return rule
        return None

    def generate_queries(self, question: str) -> list[TieredSERPQuery]:
        queries: list[TieredSERPQuery] = []
        for rule in self.tier_rules:
            for modifier in rule.query_modifiers[:2]:
                queries.append(
                    TieredSERPQuery(
                        tier=rule.tier,
                        query=f"{question} {modifier}",
                        rationale=rule.description,
                    )
                )
        return queries

    def to_dict(self) -> dict:
        return {
            "claim_domain": self.claim_domain.value,
            "name": self.name,
            "rationale": self.rationale,
            "tier_rules": [rule.to_dict() for rule in self.tier_rules],
            "expected_source_classes": list(self.expected_source_classes),
        }


def normalized_host(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path).lower()
    return host[4:] if host.startswith("www.") else host


def build_policy(domain: ClaimDomain) -> SourceAuthorityPolicy:
    if domain is ClaimDomain.HEALTHCARE:
        return SourceAuthorityPolicy(
            claim_domain=domain,
            name="Healthcare drug indication and safety",
            rationale=(
                "Drug indication and safety questions should prefer regulator, "
                "approved label, manufacturer, and reputable medical sources over "
                "generic health explainers."
            ),
            expected_source_classes=(
                "regulator_or_approved_label",
                "manufacturer_medical_information",
                "reputable_medical_reference",
                "generic_health_explainer",
            ),
            tier_rules=(
                SourceTierRule(
                    tier=SourceTier.TIER_1,
                    source_class="regulator_or_approved_label",
                    description="Regulator, approved label, or manufacturer material.",
                    host_patterns=(
                        "fda.gov",
                        "accessdata.fda.gov",
                        "labels.fda.gov",
                        "dailymed.nlm.nih.gov",
                    ),
                    query_modifiers=(
                        "FDA label prescribing information",
                        "DailyMed official label",
                    ),
                ),
                SourceTierRule(
                    tier=SourceTier.TIER_1,
                    source_class="manufacturer_medical_information",
                    description="Manufacturer medical information or prescribing material.",
                    host_patterns=(
                        "pfizer.com",
                        "lilly.com",
                        "merck.com",
                        "novonordisk",
                        "astrazeneca",
                        "jnj.com",
                        "bms.com",
                        "gilead.com",
                        "genentech",
                        "amgen.com",
                    ),
                    query_modifiers=(
                        "manufacturer prescribing information",
                    ),
                ),
                SourceTierRule(
                    tier=SourceTier.TIER_2,
                    source_class="reputable_medical_reference",
                    description="Reputable clinical or medical reference source.",
                    host_patterns=(
                        "nih.gov",
                        "ncbi.nlm.nih.gov",
                        "medlineplus.gov",
                        "mayoclinic.org",
                        "clevelandclinic.org",
                        "aafp.org",
                        "cochrane.org",
                        "msdmanuals.com",
                    ),
                    query_modifiers=(
                        "NIH clinical reference",
                        "medical reference safety indication",
                    ),
                ),
                SourceTierRule(
                    tier=SourceTier.TIER_3,
                    source_class="generic_health_explainer",
                    description="Generic health explainer useful for discovery only.",
                    host_patterns=(
                        "webmd.com",
                        "drugs.com",
                        "goodrx.com",
                        "healthline.com",
                        "verywellhealth.com",
                    ),
                    query_modifiers=("patient explainer",),
                ),
            ),
        )
    if domain is ClaimDomain.FINANCIAL:
        return _simple_policy(
            domain=domain,
            name="Public company financial performance",
            rationale="Financial performance claims should start from SEC filings, audited reports, and investor relations.",
            tier1=("sec.gov", "investor.", "annualreports.com"),
            tier2=("nasdaq.com", "nyse.com", "morningstar.com", "macrotrends.net"),
            tier3=("finance.yahoo.com", "marketwatch.com", "seekingalpha.com"),
            modifiers=("10-K annual report SEC filing", "investor relations quarterly results"),
            expected=("sec_filing", "audited_report", "investor_relations", "market_data_summary"),
        )
    if domain is ClaimDomain.LEGAL:
        return _simple_policy(
            domain=domain,
            name="Legal and regulatory status",
            rationale="Legal and regulatory claims should prefer primary law, regulator, docket, and official enforcement sources.",
            tier1=("justice.gov", "ftc.gov", "sec.gov", "ec.europa.eu", "federalregister.gov", "courtlistener.com"),
            tier2=("law.cornell.edu", "americanbar.org", "reuters.com/legal", "natlawreview.com"),
            tier3=("wikipedia.org", "findlaw.com", "jdsupra.com"),
            modifiers=("official regulator docket enforcement", "Federal Register court filing"),
            expected=("official_regulator", "court_or_docket", "primary_law", "legal_news_context"),
        )
    if domain is ClaimDomain.SCIENTIFIC:
        return _simple_policy(
            domain=domain,
            name="Academic and scientific claims",
            rationale="Scientific claims should prefer peer-reviewed papers, preprints, and institutional datasets before summaries.",
            tier1=("pubmed.ncbi.nlm.nih.gov", "nature.com", "science.org", "pnas.org", "nejm.org", "thelancet.com"),
            tier2=("arxiv.org", "biorxiv.org", "medrxiv.org", "scholar.google.com", "nih.gov"),
            tier3=("phys.org", "sciencedaily.com", "wikipedia.org"),
            modifiers=("peer reviewed study PubMed", "systematic review dataset"),
            expected=("peer_reviewed_paper", "preprint_or_dataset", "institutional_summary", "science_news_summary"),
        )
    return _simple_policy(
        domain=ClaimDomain.POSITIONING,
        name="Product and company positioning",
        rationale="Positioning claims should prefer company materials, product docs, pricing pages, and reputable market context.",
        tier1=("company", "docs.", "pricing", "blog.", "press."),
        tier2=("gartner.com", "forrester.com", "cbinsights.com", "crunchbase.com", "g2.com"),
        tier3=("medium.com", "substack.com", "reddit.com", "quora.com"),
        modifiers=("official product page pricing docs", "company press release positioning"),
        expected=("official_product_page", "company_docs_or_press", "market_research_context", "community_commentary"),
    )


def _simple_policy(
    domain: ClaimDomain,
    name: str,
    rationale: str,
    tier1: tuple[str, ...],
    tier2: tuple[str, ...],
    tier3: tuple[str, ...],
    modifiers: tuple[str, str],
    expected: tuple[str, ...],
) -> SourceAuthorityPolicy:
    return SourceAuthorityPolicy(
        claim_domain=domain,
        name=name,
        rationale=rationale,
        expected_source_classes=expected,
        tier_rules=(
            SourceTierRule(SourceTier.TIER_1, expected[0], "Primary or official authority.", tier1, (modifiers[0],)),
            SourceTierRule(SourceTier.TIER_2, expected[1], "Reputable secondary authority.", tier2, (modifiers[1],)),
            SourceTierRule(SourceTier.TIER_3, expected[-1], "Discovery or low-authority context.", tier3, ("summary explainer",)),
        ),
    )


def classify_claim_domain(question: str) -> ClaimDomain:
    text = question.lower()
    healthcare_terms = (
        "drug",
        "medication",
        "dose",
        "indication",
        "contraindication",
        "side effect",
        "safety",
        "fda",
        "label",
        "ozempic",
        "wegovy",
        "humira",
        "eliquis",
        "keytruda",
    )
    if any(term in text for term in healthcare_terms):
        return ClaimDomain.HEALTHCARE
    if any(term in text for term in ("revenue", "earnings", "10-k", "sec filing", "financial")):
        return ClaimDomain.FINANCIAL
    if any(term in text for term in ("lawsuit", "regulation", "court", "enforcement", "legal")):
        return ClaimDomain.LEGAL
    if any(term in text for term in ("study", "trial", "paper", "scientific", "researchers")):
        return ClaimDomain.SCIENTIFIC
    return ClaimDomain.POSITIONING


def policy_for_question(question: str) -> SourceAuthorityPolicy:
    return build_policy(classify_claim_domain(question))
