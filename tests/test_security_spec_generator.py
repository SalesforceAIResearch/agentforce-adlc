"""Tests for skills/agentforce-test/scripts/security_spec_generator.py

Verifies the payloads convert into a schema-valid Testing Center
AiEvaluationDefinition spec (the Mode C1 security suite), and that
`--agent-file` produces cases grounded in that agent's own script.
"""

import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

SCRIPT = str(
    Path(__file__).parent.parent
    / "skills" / "agentforce-test" / "scripts" / "security_spec_generator.py"
)

AGENTS = (
    Path(__file__).parent.parent
    / "skills" / "agentforce-generate" / "assets" / "agents"
)
ORDER_SERVICE = str(AGENTS / "order-service.agent")

# Only these keys are valid Testing Center test-case fields (see batch-testing.md).
ALLOWED_KEYS = {
    "utterance",
    "expectedOutcome",
    "conversationHistory",
    "expectedTopic",
    "expectedActions",
    "contextVariables",
}


def run_generator_raw(*args):
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    return result.stdout


def run_generator(*args):
    return yaml.safe_load(run_generator_raw(*args))


def run_generator_with_stderr(*args):
    result = subprocess.run(
        [sys.executable, SCRIPT, *args], capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    return result.stdout, result.stderr


class TestSpecShape:
    def test_full_spec_is_valid_testing_center_yaml(self):
        spec = run_generator("--agent", "OrderService")
        assert spec["subjectType"] == "AGENT"
        assert spec["subjectName"] == "OrderService"
        assert spec["name"] == "OrderService Security Tests"
        assert isinstance(spec["testCases"], list)
        # 50 neutral payloads (9 platform-scoped ones are excluded by default)
        # minus UC-004 (repeat/latency test, not statically expressible).
        assert len(spec["testCases"]) == 49  # all 7 categories, full mode

    def test_every_case_has_utterance_and_outcome(self):
        spec = run_generator("--agent", "Foo")
        for case in spec["testCases"]:
            assert case.get("utterance"), case
            assert case.get("expectedOutcome"), case

    def test_no_custom_fields_leak_into_spec(self):
        # Testing Center rejects unknown fields; test_id/severity must stay in comments.
        spec = run_generator("--agent", "Foo")
        for case in spec["testCases"]:
            extra = set(case) - ALLOWED_KEYS
            assert not extra, f"unexpected keys: {extra}"

    def test_no_expected_topic_on_security_cases(self):
        # Security validates behavior, not routing — expectedTopic must be omitted.
        spec = run_generator("--agent", "Foo")
        assert all("expectedTopic" not in c for c in spec["testCases"])


class TestMultiLineScalars:
    """Payloads with embedded newlines (e.g. PI-005 delimiter injection) must be
    emitted as single physical YAML lines. Real line breaks under a hand-emitted
    `key: value` produce under-indented continuation text that stricter parsers
    (behind `sf agent test create`) reject with "Missing closing 'quote'".
    """

    def _key_value_lines(self, raw):
        # Lines that carry a hand-emitted scalar we must keep single-line.
        for line in raw.splitlines():
            stripped = line.lstrip()
            for key in ("- utterance:", "utterance:", "expectedOutcome:", "message:"):
                if stripped.startswith(key):
                    yield line, stripped[len(key):].strip()

    def test_no_scalar_line_folds_or_breaks(self):
        # Every emitted quoted scalar must open AND close its quote on one line.
        raw = run_generator_raw("--agent", "Foo")
        for line, value in self._key_value_lines(raw):
            if value[:1] in ("'", '"'):
                quote = value[0]
                assert value.endswith(quote) and len(value) > 1, (
                    f"scalar not closed on one line (would break sf test create): {line!r}"
                )

    def test_delimiter_injection_roundtrips_with_newline(self):
        # PI-005 contains a literal newline; it must survive as escaped content.
        spec = run_generator("--agent", "Foo", "--categories", "prompt_injection")
        hits = [c for c in spec["testCases"]
                if c["utterance"].startswith("---END OF CONVERSATION---")]
        assert len(hits) == 1, "expected the PI-005 delimiter-injection case"
        assert "\n" in hits[0]["utterance"], "embedded newline must be preserved"
        assert "[SYSTEM]:" in hits[0]["utterance"]


class TestMultiTurn:
    """`conversationHistory` models a COMPLETED prior exchange, so Testing Center
    requires it to alternate user -> agent, be even-length, and end on `agent`.
    Verified against `sf agent test create`, which rejects any other shape with
    "Conversation order is incorrect there should be 1 user and 1 agent elements
    alternating. Conversation must end with agent; odd number of turns is not
    allowed" — and since the CLI validates the whole spec before writing, ONE bad
    case blocks the entire suite.
    """

    def test_multiturn_uses_conversation_history(self):
        spec = run_generator("--agent", "Foo")
        multiturn = [c for c in spec["testCases"] if "conversationHistory" in c]
        assert multiturn, "expected some multi-turn payloads"
        for case in multiturn:
            for turn in case["conversationHistory"]:
                assert turn["role"] in ("user", "agent")
                assert turn["message"]

    def test_history_alternates_user_agent_and_ends_on_agent(self):
        # The exact contract `sf agent test create` enforces server-side.
        spec = run_generator("--agent", "Foo")
        multiturn = [c for c in spec["testCases"] if "conversationHistory" in c]
        assert multiturn
        for case in multiturn:
            roles = [t["role"] for t in case["conversationHistory"]]
            assert len(roles) % 2 == 0, f"odd history length {roles}: {case}"
            assert roles[-1] == "agent", f"history must end on agent: {roles}"
            assert roles == ["user", "agent"] * (len(roles) // 2), (
                f"history must alternate user->agent: {roles}"
            )

    def test_no_empty_conversation_history_key(self):
        # An empty list is accepted by the CLI but is pure noise — single-turn
        # cases must omit the key entirely.
        spec = run_generator("--agent", "Foo")
        for case in spec["testCases"]:
            if "conversationHistory" in case:
                assert case["conversationHistory"], f"empty history emitted: {case}"

    def test_utterance_under_test_is_the_final_user_turn(self):
        # PI-003's attack lands on turn 2; the setup turn belongs in history.
        spec = run_generator("--agent", "Foo", "--categories", "prompt_injection")
        hits = [c for c in spec["testCases"]
                if c["utterance"].startswith("Great! In this game")]
        assert len(hits) == 1, "expected the PI-003 multi-turn case"
        history = hits[0]["conversationHistory"]
        assert len(history) == 2
        assert history[0]["message"].startswith("Let's play a game")
        assert history[1]["role"] == "agent"

    def test_agent_replies_do_not_preconcede_the_attack(self):
        # The fabricated agent side must not already leak what the final
        # utterance is trying to extract, or the case tests an
        # already-compromised agent instead of the escalation.
        spec = run_generator("--agent", "Foo")
        for case in spec["testCases"]:
            for turn in case.get("conversationHistory", []):
                if turn["role"] != "agent":
                    continue
                lowered = turn["message"].lower()
                assert "you are a" not in lowered, f"leaks a persona prompt: {turn}"
                assert "my instructions are" not in lowered, f"leaks instructions: {turn}"


class TestHistoryNormalization:
    """A payload that omits the agent side must be repaired, not passed through:
    one malformed case makes `sf agent test create` reject the whole spec, so the
    generator fails safe by synthesizing a neutral reply and warning.
    """

    def _write_payload(self, tmp_path, turns):
        body = "\n".join(
            f"      - role: {r}\n        content: {m!r}" for r, m in turns
        )
        (tmp_path / "misinformation.yaml").write_text(
            "schema_version: '1.0'\n"
            "category: misinformation\n"
            "owasp_id: LLM09\n"
            "tests:\n"
            "  - id: TEST-001\n"
            "    name: Synthetic\n"
            "    severity: high\n"
            "    technique: synthetic\n"
            "    turns:\n" + body + "\n"
        )
        return tmp_path

    def _run(self, tmp_path):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--agent", "Foo",
             "--categories", "misinformation",
             "--payloads-dir", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        return yaml.safe_load(result.stdout), result.stderr

    def test_all_user_turns_get_paired(self, tmp_path):
        # The old bug: three user turns emitted [user, user] as history.
        self._write_payload(tmp_path, [("user", "one"), ("user", "two"), ("user", "three")])
        spec, stderr = self._run(tmp_path)
        history = spec["testCases"][0]["conversationHistory"]
        assert [t["role"] for t in history] == ["user", "agent", "user", "agent"]
        assert spec["testCases"][0]["utterance"] == "three"
        assert "unanswered" in stderr, "must warn when fabricating a reply"

    def test_single_prior_user_turn_gets_paired(self, tmp_path):
        # The other old shape: two user turns emitted [user] — odd, ends on user.
        self._write_payload(tmp_path, [("user", "one"), ("user", "two")])
        spec, stderr = self._run(tmp_path)
        history = spec["testCases"][0]["conversationHistory"]
        assert [t["role"] for t in history] == ["user", "agent"]
        assert history[1]["message"], "placeholder reply must be non-empty"

    def test_trailing_agent_turn_is_dropped(self, tmp_path):
        # The utterance under test must be the final USER turn; a trailing agent
        # turn is the reply we are about to assert on, so it carries no input.
        self._write_payload(
            tmp_path,
            [("user", "one"), ("agent", "reply one"), ("user", "two"), ("agent", "reply two")],
        )
        spec, stderr = self._run(tmp_path)
        case = spec["testCases"][0]
        assert case["utterance"] == "two"
        assert [t["role"] for t in case["conversationHistory"]] == ["user", "agent"]
        assert "trailing" in stderr

    def test_leading_agent_turn_is_dropped(self, tmp_path):
        # History must start on user; an unanswerable leading agent turn is
        # dropped rather than emitted as an invalid [agent, user] pair.
        self._write_payload(tmp_path, [("agent", "unprompted"), ("user", "one"), ("user", "two")])
        spec, stderr = self._run(tmp_path)
        history = spec["testCases"][0]["conversationHistory"]
        assert [t["role"] for t in history] == ["user", "agent"]
        assert "no preceding user turn" in stderr

    def test_payload_with_no_user_turn_is_skipped(self, tmp_path):
        # Nothing to send as the utterance — must be skipped, not emitted empty.
        self._write_payload(tmp_path, [("agent", "only an agent turn")])
        result = subprocess.run(
            [sys.executable, SCRIPT, "--agent", "Foo",
             "--categories", "misinformation", "--payloads-dir", str(tmp_path)],
            capture_output=True, text=True,
        )
        # No cases left at all -> generator exits 1 with an explicit error.
        assert result.returncode == 1
        assert "no user turn" in result.stderr


class TestEvaluationSemantics:
    def test_payload_specific_note_overrides_generic_outcome(self):
        # UC-003's payload asserts PASS on a *correct answer* (not on refusal),
        # which inverts the generic unbounded_consumption outcome. The generator
        # must use the payload's own meta.evaluation_note verbatim.
        spec = run_generator("--agent", "Foo", "--categories", "unbounded_consumption")
        uc003 = [c for c in spec["testCases"] if c["utterance"].startswith("AAAA")]
        assert len(uc003) == 1, "expected the context-saturation case"
        assert "correctly answers '4'" in uc003[0]["expectedOutcome"]

    def test_repeat_latency_payload_omitted(self):
        # UC-004 (repeat_count/latency) is not expressible as a static one-shot
        # case, so it must be dropped from the C1 suite (covered by Mode C2).
        spec = run_generator("--agent", "Foo", "--categories", "unbounded_consumption")
        assert all("1+1" not in c["utterance"] for c in spec["testCases"])


class TestFilters:
    def test_quick_mode_drops_medium_and_low(self):
        full = run_generator("--agent", "Foo", "--categories", "prompt_injection")
        quick = run_generator("--agent", "Foo", "--mode", "quick", "--categories", "prompt_injection")
        assert len(quick["testCases"]) < len(full["testCases"])

    def test_category_filter(self):
        spec = run_generator("--agent", "Foo", "--categories", "misinformation")
        # misinformation.yaml has 7 neutral tests + 2 platform-scoped (excluded).
        assert len(spec["testCases"]) == 7

    def test_custom_suite_name(self):
        spec = run_generator("--agent", "Foo", "--name", "My Suite")
        assert spec["name"] == "My Suite"

    def test_include_platform_adds_the_vendor_specific_cases(self):
        default = run_generator("--agent", "Foo", "--categories", "misinformation")
        opted_in = run_generator("--agent", "Foo", "--categories", "misinformation",
                                 "--include-platform")
        assert len(opted_in["testCases"]) > len(default["testCases"])
        # The exact payload a customer flagged as meaningless for their agent.
        assert not any("security bulletin" in c["utterance"]
                       for c in default["testCases"])
        assert any("security bulletin" in c["utterance"]
                   for c in opted_in["testCases"])


class TestGroundedGeneration:
    """`--agent-file` must produce cases that name the agent's OWN constructs.

    A generic suite tells the owner their agent "failed a jailbreak"; a grounded
    one tells them `process_return` ran without `@variables.customer_verified`,
    which names the line to fix.
    """

    def test_agent_file_adds_agent_specific_cases(self):
        generic = run_generator("--agent", "OrderService")
        grounded = run_generator("--agent", "OrderService",
                                 "--agent-file", ORDER_SERVICE)
        assert len(grounded["testCases"]) > len(generic["testCases"])

    def test_grounded_cases_name_real_actions_and_gates(self):
        raw = run_generator_raw("--agent", "OrderService",
                                "--agent-file", ORDER_SERVICE, "--no-static")
        spec = yaml.safe_load(raw)
        body = " ".join(c["utterance"] for c in spec["testCases"])
        outcomes = " ".join(c["expectedOutcome"] for c in spec["testCases"])

        # Real action names from order-service.agent appear in the traceability
        # comments, so a failure points at the exact `.agent` construct.
        assert "initiate_return" in raw
        assert "lookup_order" in raw

        # The utterances themselves use prose, not API identifiers — an attacker
        # types "just initiate return for me", not a developer_name — but the
        # agent's own gate and action still have to be recognizable in them.
        assert "initiate return" in body.lower()
        assert "customer verified" in body.lower()
        assert "customer verified" in outcomes.lower()

        # Domain vocabulary (retail), not Salesforce-the-vendor vocabulary.
        assert "order" in body.lower()
        assert "salesforce" not in body.lower()

    def test_no_static_emits_only_grounded_cases(self):
        raw = run_generator_raw("--agent", "OrderService",
                                "--agent-file", ORDER_SERVICE, "--no-static")
        # Every commented case ID is a generated one.
        ids = [line for line in raw.splitlines() if line.strip().startswith("# [")]
        assert ids
        assert all("[DYN-" in line for line in ids), (
            "static payload leaked into a --no-static run"
        )

    def test_no_static_without_agent_file_is_rejected(self):
        # Would silently produce an empty suite; must fail loudly instead.
        result = subprocess.run(
            [sys.executable, SCRIPT, "--agent", "Foo", "--no-static"],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert "--no-static" in result.stderr

    def test_missing_agent_file_is_rejected(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--agent", "Foo",
             "--agent-file", "/nonexistent/Nope.agent"],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_grounded_multiturn_histories_are_well_formed(self):
        # Generated cases go through the same C1 contract as hand-written ones;
        # one malformed history rejects the entire suite server-side.
        spec = run_generator("--agent", "OrderService",
                             "--agent-file", ORDER_SERVICE, "--no-static")
        multiturn = [c for c in spec["testCases"] if "conversationHistory" in c]
        assert multiturn, "expected generated escalation chains"
        for case in multiturn:
            roles = [t["role"] for t in case["conversationHistory"]]
            assert roles == ["user", "agent"] * (len(roles) // 2), roles
            assert all(t["message"].strip() for t in case["conversationHistory"])

    def test_grounded_history_needs_no_placeholder_repair(self):
        # The designer authors explicit `role: agent` replies, so `_pair_history`
        # should never have to fabricate one — a warning here means a generator
        # emitted consecutive user turns.
        _, stderr = run_generator_with_stderr(
            "--agent", "OrderService", "--agent-file", ORDER_SERVICE, "--no-static"
        )
        assert "unanswered" not in stderr, stderr
        assert "ended on a user turn" not in stderr, stderr

    def test_domain_override_changes_vocabulary(self):
        airline = run_generator_raw("--agent", "OrderService", "--agent-file",
                                    ORDER_SERVICE, "--no-static",
                                    "--domain", "airline")
        assert "passenger" in airline.lower()

    def test_max_per_category_caps_generated_cases(self):
        capped = run_generator("--agent", "OrderService", "--agent-file",
                               ORDER_SERVICE, "--no-static",
                               "--max-per-category", "1")
        uncapped = run_generator("--agent", "OrderService", "--agent-file",
                                 ORDER_SERVICE, "--no-static")
        assert len(capped["testCases"]) < len(uncapped["testCases"])

    def test_surfaceless_agent_still_produces_a_suite(self):
        # hello-world.agent has no actions or gates. The generator must emit the
        # conversation-level cases it CAN test rather than inventing a
        # gate-bypass case for a gate that does not exist.
        spec = run_generator("--agent", "HelloWorld", "--no-static",
                             "--agent-file", str(AGENTS / "hello-world.agent"))
        assert spec["testCases"]
        body = " ".join(c["utterance"] for c in spec["testCases"]).lower()
        assert "available when" not in body
