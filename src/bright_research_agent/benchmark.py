from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from bright_research_agent.policy import ClaimDomain, build_policy


@dataclass(frozen=True)
class BenchmarkQuestion:
    id: str
    question: str
    claim_domain: ClaimDomain
    expected_source_classes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "claim_domain": self.claim_domain.value,
            "expected_source_classes": list(self.expected_source_classes),
        }


HEALTHCARE_QUESTIONS = (
    "Is Ozempic indicated for chronic weight management, and what safety warnings matter?",
    "Is Wegovy approved for adults with obesity, and what are its major warnings?",
    "What is Humira approved to treat, and what serious infection warnings apply?",
    "Is Eliquis approved to reduce stroke risk in atrial fibrillation, and what bleeding warnings apply?",
    "What is Keytruda indicated for, and what immune-mediated adverse reactions are warned?",
    "Is Mounjaro approved for type 2 diabetes, and what boxed warnings or precautions apply?",
    "What is Jardiance approved for, and what ketoacidosis warnings are listed?",
    "Is Dupixent indicated for atopic dermatitis, and what eye-related safety warnings apply?",
    "What is Xarelto approved to prevent or treat, and what bleeding risks are warned?",
    "Is Trulicity approved for type 2 diabetes, and what thyroid tumor warning appears?",
    "What is Cosentyx indicated for, and what infection or IBD warnings matter?",
    "Is Skyrizi approved for plaque psoriasis, and what infection warnings apply?",
    "What is Entresto approved for, and what pregnancy or angioedema warnings apply?",
    "Is Paxlovid authorized or approved for COVID-19 treatment, and what interaction warnings apply?",
    "What is Tamiflu indicated for, and what neuropsychiatric safety information is listed?",
    "Is Lantus indicated for diabetes, and what hypoglycemia safety warnings apply?",
    "What is Adderall approved to treat, and what boxed warnings apply?",
    "Is Zoloft indicated for depression, and what suicidality warnings apply?",
    "What is Botox approved to treat medically, and what distant spread warning applies?",
    "Is Narcan approved for opioid overdose reversal, and what withdrawal warnings apply?",
)


DOMAIN_QUESTION_STEMS = {
    ClaimDomain.FINANCIAL: (
        "What did {company} report for annual revenue, and which filing supports it?",
        ("Apple", "Microsoft", "Nvidia", "Tesla", "Amazon"),
    ),
    ClaimDomain.LEGAL: (
        "What is the current regulatory status of {company}'s antitrust matter?",
        ("Google", "Meta", "Amazon", "Apple", "Microsoft"),
    ),
    ClaimDomain.POSITIONING: (
        "How does {company} position its {product} product for enterprise buyers?",
        ("OpenAI|ChatGPT Enterprise", "Anthropic|Claude", "Databricks|Mosaic AI", "Snowflake|Cortex", "Atlassian|Rovo"),
    ),
    ClaimDomain.SCIENTIFIC: (
        "What peer-reviewed evidence supports the claim about {topic}?",
        ("GLP-1 cardiovascular outcomes", "CRISPR sickle cell therapy", "mRNA vaccine durability", "fusion ignition", "perovskite solar cell efficiency"),
    ),
}


def benchmark_questions(domains: Iterable[ClaimDomain] | None = None) -> list[BenchmarkQuestion]:
    selected = set(domains or list(ClaimDomain))
    questions: list[BenchmarkQuestion] = []
    if ClaimDomain.HEALTHCARE in selected:
        policy = build_policy(ClaimDomain.HEALTHCARE)
        for index, question in enumerate(HEALTHCARE_QUESTIONS, start=1):
            questions.append(
                BenchmarkQuestion(
                    id=f"healthcare-{index:02d}",
                    question=question,
                    claim_domain=ClaimDomain.HEALTHCARE,
                    expected_source_classes=policy.expected_source_classes,
                )
            )
    for domain, (template, values) in DOMAIN_QUESTION_STEMS.items():
        if domain not in selected:
            continue
        policy = build_policy(domain)
        expanded = _expand_to_twenty(template, values)
        for index, question in enumerate(expanded, start=1):
            questions.append(
                BenchmarkQuestion(
                    id=f"{domain.value}-{index:02d}",
                    question=question,
                    claim_domain=domain,
                    expected_source_classes=policy.expected_source_classes,
                )
            )
    return questions


def parse_domains(values: list[str] | None) -> list[ClaimDomain] | None:
    if not values:
        return None
    domains = []
    for value in values:
        normalized = value.strip().lower()
        aliases = {
            "healthcare": ClaimDomain.HEALTHCARE,
            "financial": ClaimDomain.FINANCIAL,
            "legal": ClaimDomain.LEGAL,
            "positioning": ClaimDomain.POSITIONING,
            "scientific": ClaimDomain.SCIENTIFIC,
        }
        domains.append(aliases[normalized] if normalized in aliases else ClaimDomain(normalized))
    return domains


def _expand_to_twenty(template: str, values: tuple[str, ...]) -> list[str]:
    suffixes = (
        "Use primary sources first.",
        "Separate official evidence from summaries.",
        "Identify whether Tier 1 evidence exists.",
        "Avoid relying on generic commentary alone.",
    )
    questions = []
    for value in values:
        for suffix in suffixes:
            if "|" in value:
                company, product = value.split("|", 1)
                question = template.format(company=company, product=product, topic=value)
            else:
                question = template.format(company=value, product=value, topic=value)
            questions.append(f"{question} {suffix}")
    return questions[:20]
