from bright_research_agent.policy import (
    ClaimDomain,
    SourceTier,
    build_policy,
    policy_for_question,
)


def test_healthcare_policy_selection_and_tier_assignment():
    policy = policy_for_question(
        "Is Ozempic indicated for chronic weight management, and what safety warnings matter?"
    )

    assert policy.claim_domain is ClaimDomain.HEALTHCARE
    assert "regulator" in policy.rationale.lower()
    assert policy.tier_for_url("https://www.accessdata.fda.gov/drugsatfda_docs/label/x.pdf") is SourceTier.TIER_1
    assert policy.tier_for_url("https://medlineplus.gov/druginfo/meds/demo.html") is SourceTier.TIER_2
    assert policy.tier_for_url("https://www.healthline.com/health/drugs/demo") is SourceTier.TIER_3


def test_all_domain_policy_scaffolds_generate_queries_and_expected_labels():
    for domain in ClaimDomain:
        policy = build_policy(domain)
        queries = policy.generate_queries("What source supports this claim?")

        assert policy.expected_source_classes
        assert {rule.tier.value for rule in policy.tier_rules} == {"tier_1", "tier_2", "tier_3"}
        assert queries
        assert all(query.query for query in queries)

