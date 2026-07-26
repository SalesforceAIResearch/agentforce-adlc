"""Tests for skills/agentforce-test/scripts/security_spec_generator.py

Verifies the OWASP payloads convert into a schema-valid Testing Center
AiEvaluationDefinition spec (the Mode C1 security suite).
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


class TestSpecShape:
    def test_full_spec_is_valid_testing_center_yaml(self):
        spec = run_generator("--agent", "OrderService")
        assert spec["subjectType"] == "AGENT"
        assert spec["subjectName"] == "OrderService"
        assert spec["name"] == "OrderService Security Tests"
        assert isinstance(spec["testCases"], list)
        # 57 payloads minus UC-004 (repeat/latency test, not statically expressible).
        assert len(spec["testCases"]) == 56  # all 7 categories, full mode

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
    def test_multiturn_uses_conversation_history(self):
        spec = run_generator("--agent", "Foo")
        multiturn = [c for c in spec["testCases"] if "conversationHistory" in c]
        assert multiturn, "expected some multi-turn payloads"
        for case in multiturn:
            for turn in case["conversationHistory"]:
                assert turn["role"] == "user"
                assert turn["message"]


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
        # misinformation.yaml has 7 tests
        assert len(spec["testCases"]) == 7

    def test_custom_suite_name(self):
        spec = run_generator("--agent", "Foo", "--name", "My Suite")
        assert spec["name"] == "My Suite"
