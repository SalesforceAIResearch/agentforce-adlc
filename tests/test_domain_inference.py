"""Tests for skills/agentforce-test/scripts/domain_inference.py

The domain supplies the VOCABULARY a payload is written in. Getting it wrong is
what produced the reported defect: an airline agent probed with Salesforce
security-bulletin questions. Two failure modes matter and both are pinned here:

  - claiming an industry on thin evidence (a hospitality payload sent to a bank
    agent reads as noise and the finding gets dismissed), and
  - dropping to `generic` when the evidence was actually there (the suite loses
    the domain-specific fabrication and exfiltration tests that make it useful).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "skills" / "agentforce-test" / "scripts"
AGENTS = (
    Path(__file__).parent.parent
    / "skills" / "agentforce-generate" / "assets" / "agents"
)


def _load(name):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec because @dataclass resolves annotations through
    # sys.modules[cls.__module__].
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


di = _load("domain_inference")
ap = _load("agent_profile")


def profile_with(description="", **kwargs):
    """A minimal profile carrying only the evidence under test."""
    return ap.AgentProfile(description=description, **kwargs)


class TestVocabularyCompleteness:
    """Every field the generators interpolate must be non-empty for every
    domain — a blank `record` renders "your  details" in a live payload."""

    @pytest.mark.parametrize("domain", di.DOMAINS + [di.GENERIC],
                             ids=lambda d: d.key)
    def test_domain_supplies_every_vocabulary_slot(self, domain):
        for field in ("key", "label", "actor", "actor_plural", "record",
                      "record_plural", "identifier", "authority", "regulation"):
            assert getattr(domain, field), f"{domain.key}.{field} is empty"
        # The generators index sensitive[0..2] and fabrication[0].
        assert len(domain.sensitive) >= 3, domain.key
        assert domain.fabrication, domain.key

    def test_domain_keys_are_unique(self):
        keys = [d.key for d in di.DOMAINS] + [di.GENERIC.key]
        assert len(set(keys)) == len(keys)

    @pytest.mark.parametrize("domain", di.DOMAINS, ids=lambda d: d.key)
    def test_anchors_are_a_subset_of_keywords(self, domain):
        """An anchor outside `keywords` would be scored from the system
        instructions but not from the business fields — silently invisible in
        the place the evidence is most reliable."""
        stray = set(domain.anchors) - set(domain.keywords)
        assert not stray, f"{domain.key} anchors not in keywords: {sorted(stray)}"

    @pytest.mark.parametrize("domain", di.DOMAINS, ids=lambda d: d.key)
    def test_anchors_are_not_ordinary_business_english(self, domain):
        """Anchors are scored from safety boilerplate, so a generic word here
        makes every agent look like this industry — exactly the bug that graded
        a Delta agent as HR off "manager approval"."""
        generic = {"account", "manager", "compensation", "performance",
                   "benefits", "leave", "payment", "card", "policy", "service",
                   "customer", "case", "order", "quote", "plan", "public"}
        overlap = set(domain.anchors) & generic
        assert not overlap, f"{domain.key} anchors too generic: {sorted(overlap)}"

    def test_generic_vocabulary_names_no_industry(self):
        """`generic` is rendered when we do not know the business, so its words
        must be true of any business."""
        blob = " ".join(
            [di.GENERIC.actor, di.GENERIC.record, di.GENERIC.identifier,
             di.GENERIC.authority, di.GENERIC.regulation]
            + di.GENERIC.sensitive + di.GENERIC.fabrication
        ).lower()
        for industry_word in ("flight", "patient", "policy", "hotel", "student",
                              "salesforce", "meter"):
            assert industry_word not in blob


class TestScoring:
    def test_keyword_matching_respects_word_boundaries(self):
        """Substring matching produced false industries: "similar" scored the
        telecom `sim` keyword, "carefully" scored healthcare `care`."""
        profile = profile_with(
            description="Handle requests carefully and use similar phrasing."
        )
        assert di.score_domains(profile) == []

    def test_action_names_alone_classify_the_agent(self):
        """Descriptions are often boilerplate; the nouns in action names are
        not. An agent that says nothing about itself must still classify."""
        profile = profile_with(actions=[
            ap.ActionDef(name="lookup_flight_status"),
            ap.ActionDef(name="rebook_passenger"),
            ap.ActionDef(name="check_baggage_allowance"),
        ])
        domain, why = di.infer_domain(profile)
        assert domain.key == "airline", why

    def test_variable_names_count_as_evidence(self):
        profile = profile_with(variables=[
            ap.Variable(name="patient_verified", type="boolean"),
            ap.Variable(name="prescription_id"),
            ap.Variable(name="appointment_date"),
        ])
        domain, _ = di.infer_domain(profile)
        assert domain.key == "healthcare"

    def test_ordinary_keywords_in_system_instructions_are_not_evidence(self):
        """Safety boilerplate mentions "account" and "card" generically; letting
        those score would make every agent look like a bank."""
        profile = ap.AgentProfile(system_instructions=(
            "Never share the customer's card, account, balance, transaction, "
            "or payment details. Verify identity before any transfer."
        ))
        assert di.score_domains(profile) == []

    def test_anchors_in_system_instructions_are_evidence(self):
        """Anchors are the exception: "passenger" and "baggage" do not appear in
        generic boilerplate, so wherever they show up they mean something."""
        profile = ap.AgentProfile(system_instructions=(
            "You help a passenger whose baggage was lost."
        ))
        domain, why = di.infer_domain(profile)
        assert domain.key == "airline", why

    def test_industry_in_the_instructions_outranks_generic_business_nouns(self):
        """The reported regression, reduced: a Delta Air Lines complaint agent
        scored hr=2 on "manager approval" and "compensation guardrails" while
        "Delta Air Lines", "flight delay", and "lost baggage" sat in the system
        instructions, which ordinary keywords do not read. It was graded as an
        employee-services agent and probed about payroll and performance
        reviews — the same defect the user reported, inverted."""
        profile = ap.AgentProfile(
            developer_name="CustomerResolutionAgent",
            description=(
                "Customer resolution assistant — analyzes complaints, assesses "
                "churn risk, generates guardrailed offers, drafts channel "
                "responses. Offers over $500 and any public social-media post "
                "require manager approval. Compensation guardrails apply."
            ),
            system_instructions=(
                "You are the Customer Resolution Agent, an AI assistant for "
                "Delta Air Lines. If a customer raises more than one complaint "
                "in a single message (for example a flight delay AND lost "
                "baggage), handle the first one and remind them you will also "
                "address the second."
            ),
        )
        domain, why = di.infer_domain(profile)
        assert domain.key == "airline", why


class TestGenericFallback:
    def test_single_keyword_hit_is_not_enough_to_claim_an_industry(self):
        """"account" alone appears in nearly every agent. One hit must not
        license a whole banking vocabulary."""
        profile = profile_with(description="Help the user with their account.")
        domain, why = di.infer_domain(profile)
        assert domain.key == "generic"
        assert "weak signal" in why

    def test_two_hits_do_claim_the_industry(self):
        # The threshold is exactly 2, so pin both sides of it.
        profile = profile_with(
            description="Help the user with their account balance."
        )
        domain, why = di.infer_domain(profile)
        assert domain.key == "financial", why

    def test_no_evidence_at_all_returns_generic(self):
        domain, why = di.infer_domain(ap.AgentProfile())
        assert domain.key == "generic"
        assert "no domain keywords" in why

    def test_rationale_names_the_runner_up(self):
        """The rationale is printed to the user, who is the only one who can
        catch a misclassification — it has to show the competition."""
        profile = ap.parse_agent_file(AGENTS / "order-service.agent")
        _, why = di.infer_domain(profile)
        assert "scored" in why and "next" in why

    def test_one_anchor_alone_clears_the_threshold(self):
        """An anchor is by definition a word no other industry uses, so a single
        one is stronger evidence than two ordinary business nouns."""
        profile = profile_with(description="Help with lost baggage.")
        domain, why = di.infer_domain(profile)
        assert domain.key == "airline", why


class TestOverride:
    def test_explicit_domain_wins_over_inference(self):
        profile = ap.parse_agent_file(AGENTS / "order-service.agent")
        inferred, _ = di.infer_domain(profile)
        forced, why = di.infer_domain(profile, "airline")
        assert forced.key == "airline"
        assert inferred.key != "airline", "fixture no longer proves the override"
        assert "forced" in why

    def test_override_accepts_generic(self):
        domain, _ = di.infer_domain(ap.AgentProfile(), "generic")
        assert domain.key == "generic"

    def test_override_is_case_and_space_insensitive(self):
        domain, _ = di.infer_domain(ap.AgentProfile(), "  Airline ")
        assert domain.key == "airline"

    def test_unknown_domain_fails_loudly_and_lists_the_choices(self):
        """Silently falling back would run a whole suite in the wrong
        vocabulary while the user believed they had selected one."""
        with pytest.raises(SystemExit) as exc:
            di.infer_domain(ap.AgentProfile(), "aviation")
        message = str(exc.value)
        assert "aviation" in message
        assert "airline" in message, "the error must list valid keys"


class TestShippedAgents:
    def test_every_shipped_agent_resolves_to_a_domain(self):
        files = sorted(AGENTS.glob("*.agent"))
        assert files
        for path in files:
            profile = ap.parse_agent_file(path)
            domain, why = di.infer_domain(profile)
            assert domain.key
            assert why

    def test_order_service_reads_as_retail(self):
        profile = ap.parse_agent_file(AGENTS / "order-service.agent")
        domain, why = di.infer_domain(profile)
        assert domain.key == "retail", why
        assert domain.actor == "customer"
        assert domain.record == "order"
