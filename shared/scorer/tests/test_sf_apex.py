"""Tests for sf_apex helpers — focused on error surfacing, not subprocess invocation."""
from __future__ import annotations

from src.sf_apex import _format_api_error, _format_component_failures


def test_format_component_failures_extracts_problem():
    """Real failure payload from `sf project deploy start --json` — the actionable
    error lives in result.details.componentFailures[*].problem, not in the top-level
    message field."""
    payload = {
        "status": 1,
        "result": {
            "details": {
                "componentFailures": [
                    {
                        "fullName": "response_quality_with_professionalism",
                        "componentType": "AiAgentScorerDefinition",
                        "problem": "The Scorer name must be at most 35 characters. Found: 37",
                        "problemType": "Error",
                        "success": False,
                    }
                ],
                "componentSuccesses": [],
            }
        },
    }
    msg = _format_component_failures(payload)
    assert msg == (
        "response_quality_with_professionalism: "
        "The Scorer name must be at most 35 characters. Found: 37"
    )


def test_format_component_failures_concatenates_multiple():
    payload = {
        "result": {
            "details": {
                "componentFailures": [
                    {"fullName": "A", "problem": "missing field foo"},
                    {"fullName": "B", "problem": "duplicate name"},
                ]
            }
        }
    }
    msg = _format_component_failures(payload)
    assert msg == "A: missing field foo; B: duplicate name"


def test_format_component_failures_returns_none_when_no_failures():
    """Caller falls back to other error fields when there are no component failures."""
    assert _format_component_failures({}) is None
    assert _format_component_failures({"result": {}}) is None
    assert _format_component_failures({"result": {"details": {}}}) is None
    assert _format_component_failures(
        {"result": {"details": {"componentFailures": []}}}
    ) is None


def test_format_component_failures_falls_back_to_error_field():
    """Some payloads use `error` instead of `problem`."""
    payload = {
        "result": {
            "details": {
                "componentFailures": [{"fullName": "X", "error": "broken thing"}]
            }
        }
    }
    assert _format_component_failures(payload) == "X: broken thing"


# ---- _format_api_error: the beta `sf api request rest` writes API errors to STDOUT and
#      only banners to STDERR. Regression: we used to surface STDERR, hiding the real cause
#      behind the "@salesforce/cli update available" banner. ----

_BETA_BANNER = (
    " ›   Warning: @salesforce/cli update available from 2.140.6 to 2.144.6.\n"
    "Warning: This command is currently in beta. Any aspect of this command can change "
    "without advanced notice. Don't use beta commands in your scripts."
)


def test_format_api_error_parses_error_list_from_stdout():
    """The exact shape that masked the topicName bug: error JSON on stdout, banner on stderr."""
    stdout = (
        '[\n  {\n    "errorCode": "INVALID_INPUT",\n'
        '    "message": "$.runs[0].topicName: is missing but it is required"\n  }\n]'
    )
    msg = _format_api_error(stdout, _BETA_BANNER)
    assert msg == "INVALID_INPUT: $.runs[0].topicName: is missing but it is required"
    # The banner must NOT leak into the surfaced error.
    assert "update available" not in msg
    assert "beta" not in msg


def test_format_api_error_parses_bare_error_object():
    stdout = '{"errorCode": "NOT_FOUND", "message": "template does not exist"}'
    assert _format_api_error(stdout, "") == "NOT_FOUND: template does not exist"


def test_format_api_error_concatenates_multiple_errors():
    stdout = '[{"errorCode": "E1", "message": "first"}, {"errorCode": "E2", "message": "second"}]'
    assert _format_api_error(stdout, "") == "E1: first; E2: second"


def test_format_api_error_message_only():
    stdout = '[{"message": "just a message, no code"}]'
    assert _format_api_error(stdout, "") == "just a message, no code"


def test_format_api_error_falls_back_to_stderr_when_stdout_empty():
    """No stdout (e.g. auth failure before any HTTP response) → use stderr."""
    assert _format_api_error("", "ERROR: not authorized") == "ERROR: not authorized"


def test_format_api_error_non_json_stdout_surfaced_verbatim():
    assert _format_api_error("some plain text error", "") == "some plain text error"


def test_format_api_error_no_output_at_all():
    assert _format_api_error("", "") == "no output"
