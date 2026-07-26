"""Tests for skills/agentforce-test/scripts/agent_profile.py

The profile is what makes a security test about the CUSTOMER's agent: it reads
the `.agent` file and reports the attack surface — actions, `available when`
authorization gates, LLM-filled action inputs, gate/identity variables, and the
agent's own stated guardrails. Every assertion below protects a grounding fact
the generator depends on; when the parser silently returns less, the generator
silently emits weaker tests, which is the failure mode this file exists to catch.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).parent.parent / "skills" / "agentforce-test" / "scripts"
)
AGENTS = (
    Path(__file__).parent.parent
    / "skills" / "agentforce-generate" / "assets" / "agents"
)


def _load():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "agent_profile", SCRIPTS / "agent_profile.py"
    )
    module = importlib.util.module_from_spec(spec)
    # @dataclass resolves type strings through sys.modules[cls.__module__]; a
    # module exec'd without being registered there raises AttributeError.
    sys.modules["agent_profile"] = module
    spec.loader.exec_module(module)
    return module


ap = _load()


@pytest.fixture(scope="module")
def order_service():
    return ap.parse_agent_file(AGENTS / "order-service.agent")


@pytest.fixture(scope="module")
def verification_gate():
    return ap.parse_agent_file(AGENTS / "verification-gate.agent")


class TestIdentity:
    def test_reads_name_label_and_description(self, order_service):
        assert order_service.developer_name
        assert order_service.description
        assert order_service.source_file.endswith("order-service.agent")

    def test_collects_subagents(self, order_service):
        names = [s.name for s in order_service.subagents]
        assert names
        assert len(set(names)) == len(names), "subagent names must be unique"


class TestActions:
    def test_parses_level1_definitions_with_targets(self, order_service):
        by_name = {a.name: a for a in order_service.actions}
        assert "lookup_order" in by_name
        lookup = by_name["lookup_order"]
        assert lookup.target.startswith(("flow://", "apex://", "retriever://"))
        assert lookup.target_name
        assert [i.name for i in lookup.inputs]
        assert [o.name for o in lookup.outputs]

    def test_is_displayable_marks_outputs_not_fields(self, order_service):
        """`is_displayable: True` is field metadata, not an output named
        `is_displayable`.

        Parsed as a field it both created a phantom output and left every real
        output non-displayable, which silently removed the grounding from the
        output-handling and misinformation generators.
        """
        for action in order_service.actions:
            names = [o.name for o in action.outputs] + [i.name for i in action.inputs]
            assert "is_displayable" not in names
            assert "description" not in names

        displayable = [
            o.name for a in order_service.actions for o in a.displayable_outputs
        ]
        assert displayable, "expected at least one is_displayable output"

    def test_write_detection_uses_verb_position(self, verification_gate):
        """`verify_email` is a READ that sets a gate, not a write.

        "email" is a write verb only when it LEADS the name (`email_receipt`).
        Misreading a verification action as a mutation would put it at the head
        of the write list and let a gate-bypass case target the very action that
        establishes the gate.
        """
        by_name = {a.name: a for a in verification_gate.actions}
        assert "verify_email" in by_name, "fixture changed; update this test"
        assert not by_name["verify_email"].is_write
        assert verification_gate.write_actions, "expected some write actions"
        assert "verify_email" not in [a.name for a in verification_gate.write_actions]

    def test_strong_write_verbs_count_in_any_position(self):
        assert ap.ActionDef(name="order_cancel").is_write        # cancel is strong
        assert ap.ActionDef(name="customer_refund").is_write     # refund is strong
        assert not ap.ActionDef(name="check_order_status").is_write
        assert ap.ActionDef(name="create_case").is_write         # leading verb

    def test_target_name_also_decides_write(self):
        # An innocuously-named action wired to a mutating target is still a write.
        action = ap.ActionDef(
            name="handle_request", target="flow://Delete_Account",
            target_type="flow", target_name="Delete_Account",
        )
        assert action.is_write


class TestGatesAndInvocations:
    def test_available_when_predicates_are_captured(self, order_service):
        assert order_service.gates, "expected `available when` guards"
        assert order_service.gated_invocations
        for guard in order_service.gates:
            assert guard.strip() == guard
            assert guard

    def test_gate_variables_are_boolean_verification_flags(self, verification_gate):
        gate_vars = {v.name for v in verification_gate.gate_variables}
        assert gate_vars
        for v in verification_gate.gate_variables:
            assert v.type == "boolean"

    def test_llm_filled_inputs_are_injection_sinks(self, order_service):
        sinks = order_service.llm_filled
        assert sinks, "expected `with x = ...` LLM-filled inputs"
        for invocation, param in sinks:
            assert invocation and param

    def test_definition_bound_inputs_are_not_injection_sinks(self):
        """`= @knowledge.citations_url` at the definition means the platform
        supplies the value, so it is not a place user text lands.

        Counting it as a sink produced an injection test against a parameter the
        user cannot influence — a guaranteed PASS that inflates the grade.
        """
        profile = ap.AgentProfile(
            actions=[ap.ActionDef(
                name="answer",
                inputs=[
                    ap.ActionInput(name="question"),
                    ap.ActionInput(name="citations_url",
                                   bound_default="@knowledge.citations_url"),
                ],
            )],
            invocations=[ap.Invocation(
                name="answer", target_ref="@actions.answer",
                llm_filled_inputs=["question", "citations_url"],
            )],
        )
        assert profile.llm_filled == [("answer", "question")]

    def test_writes_to_variables_are_captured(self, verification_gate):
        writes = [w for inv in verification_gate.invocations for w in inv.writes]
        assert writes, "expected `set @variables.x = ...` writes"


class TestVariables:
    def test_linked_variables_are_platform_session_context(self, order_service):
        for v in order_service.linked_variables:
            assert v.kind == "linked"

    def test_identity_variables_are_flagged(self, order_service):
        assert order_service.identity_variables, (
            "expected identity-ish variables to exfiltrate in LLM02 tests"
        )


class TestGuardrailRanking:
    def test_security_rules_outrank_loop_control_boilerplate(self, order_service):
        """Authoring templates open with "Perform only the current task".

        That is a rule but not a security rule — overriding it proves nothing, so
        the generator (which uses only the top few) must see the real policy
        first.
        """
        rules = order_service.guardrail_sentences()
        assert rules
        top = " ".join(rules[:2]).lower()
        assert "verify" in top or "fabricate" in top, rules[:3]
        assert "perform only the current" not in rules[0].lower()

    def test_multiline_block_rules_are_not_truncated(self):
        # `|` blocks wrap prose across lines; a soft newline is not a sentence
        # boundary, so splitting on it would cut a rule mid-clause.
        profile = ap.AgentProfile(system_instructions=(
            "Always verify the customer's identity\nbefore sharing any order "
            "details with them. Be friendly and concise."
        ))
        rules = profile.guardrail_sentences()
        assert rules
        assert "before sharing any order details" in rules[0]

    def test_short_fragments_are_not_treated_as_rules(self):
        profile = ap.AgentProfile(system_instructions="Do not. Be nice.")
        assert profile.guardrail_sentences() == []


class TestRobustness:
    def test_every_shipped_agent_parses_without_error(self):
        """The parser must never be the reason a security run fails.

        `.agent` is an indentation-sensitive DSL with constructs this profile
        does not model; unrecognized lines are skipped, never fatal.
        """
        files = sorted(AGENTS.glob("*.agent"))
        assert files
        for path in files:
            profile = ap.parse_agent_file(path)
            assert profile.source_file.endswith(path.name)

    def test_surfaceless_agent_yields_an_empty_surface_not_a_crash(self):
        profile = ap.parse_agent_file(AGENTS / "hello-world.agent")
        assert profile.actions == []
        assert profile.gates == []
        assert profile.write_actions == []

    def test_voice_and_knowledge_flags(self):
        voice = ap.parse_agent_file(AGENTS / "voice-service-agent.agent")
        assert voice.is_voice
        grounded = ap.parse_agent_file(AGENTS / "knowledge-grounded.agent")
        assert grounded.has_knowledge

    def test_to_dict_is_json_serializable(self, order_service):
        import json
        payload = json.dumps(order_service.to_dict())
        assert "derived" in payload
