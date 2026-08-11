from pathlib import Path

import pytest

from src.scorer_spec import ScorerSpecError, load

BUNDLED = Path(__file__).resolve().parent.parent / "scorer_specs"


def test_loads_bundled_response_quality():
    spec = load("response_quality")
    assert spec.name == "response_quality"
    assert spec.data_type == "Text"
    assert spec.fallback_label == "Inconclusive"
    assert "Inconclusive" in spec.allowed_labels
    assert "Excellent" in spec.allowed_labels


def test_loads_by_path():
    path = BUNDLED / "user_frustration.yaml"
    spec = load(str(path))
    assert spec.name == "user_frustration"
    assert spec.fallback_label == "Unknown"


def test_rejects_missing_field(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("name: foo\n")
    with pytest.raises(ScorerSpecError, match="missing required fields"):
        load(str(f))


def test_rejects_fallback_not_in_allowed(tmp_path):
    """Text scorers are Predefined — their fallback MUST be one of `values`.

    OpenEnded scorers have a looser rule (see
    `test_openended_allows_fallback_outside_values`).
    """
    f = tmp_path / "bad.yaml"
    f.write_text(
        "name: foo\n"
        "description: x\n"
        "data_type: Text\n"
        "primary_model: m\n"
        "allowed_labels: [A, B]\n"
        "fallback_label: C\n"
        "prompt: |\n"
        "  {!$SalesforceDataAction:getSession.chatTranscript} {!$Input:AllowedLabels} {!$Input:FallbackLabel}\n"
    )
    with pytest.raises(ScorerSpecError, match="fallback_value"):
        load(str(f))


def test_openended_allows_fallback_outside_values(tmp_path):
    """OpenEnded scorers may declare a synthetic 'can't decide' fallback
    (e.g. NA, NOT_SET) that is NOT in `values` — the scorer-definition XML
    template materializes it as an extra <outputEnumValue> with
    <isFallback>true</isFallback> + <isSystemFallback>true</isSystemFallback>.
    Matches the reference tc07_number_measurement_pt scorer's use of NOT_SET.
    """
    f = tmp_path / "ok.yaml"
    f.write_text(
        "name: foo\n"
        "description: x\n"
        "data_type: OpenEnded\n"
        "lightning_type: lightning__multilineTextType\n"
        "primary_model: m\n"
        "values: [Delighted, Satisfied, Dissatisfied]\n"
        "fallback_value: NA\n"
        "prompt: |\n"
        "  {!$SalesforceDataAction:getSession.chatTranscript}\n"
    )
    spec = load(str(f))
    assert spec.fallback_label == "NA"
    assert "NA" not in spec.allowed_labels


def test_rejects_unknown_data_type(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(
        "name: foo\n"
        "description: x\n"
        "data_type: Date\n"
        "primary_model: m\n"
        "allowed_labels: [A]\n"
        "fallback_label: A\n"
        "prompt: |\n"
        "  {!$SalesforceDataAction:getSession.chatTranscript} {!$Input:AllowedLabels} {!$Input:FallbackLabel}\n"
    )
    with pytest.raises(ScorerSpecError, match="data_type"):
        load(str(f))


def test_rejects_missing_prompt_markers(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(
        "name: foo\n"
        "description: x\n"
        "data_type: Text\n"
        "primary_model: m\n"
        "allowed_labels: [A]\n"
        "fallback_label: A\n"
        "prompt: just a prompt, no markers\n"
    )
    with pytest.raises(ScorerSpecError, match="reference the session"):
        load(str(f))


def test_accepts_raw_input_session_marker(tmp_path):
    """A prompt that uses {!$Input:Session} (raw STDM JSON) instead of the
    Data Action reference is still valid — that path is supported for callers
    that want the full nested payload."""
    f = tmp_path / "raw.yaml"
    f.write_text(
        "name: raw_input_session\n"
        "description: x\n"
        "data_type: Text\n"
        "primary_model: m\n"
        "allowed_labels: [A]\n"
        "fallback_label: A\n"
        "prompt: |\n"
        "  {!$Input:Session} {!$Input:AllowedLabels} {!$Input:FallbackLabel}\n"
    )
    spec = load(str(f))
    assert spec.name == "raw_input_session"


def test_rejects_when_both_session_markers_missing(tmp_path):
    """Specifically: AllowedLabels + FallbackLabel are present but neither
    session marker is — the validator should still reject."""
    f = tmp_path / "bad.yaml"
    f.write_text(
        "name: foo\n"
        "description: x\n"
        "data_type: Text\n"
        "primary_model: m\n"
        "allowed_labels: [A]\n"
        "fallback_label: A\n"
        "prompt: |\n"
        "  {!$Input:AllowedLabels} {!$Input:FallbackLabel}\n"
    )
    with pytest.raises(ScorerSpecError, match="reference the session"):
        load(str(f))


def test_rejects_name_over_35_chars(tmp_path):
    """Salesforce caps AiAgentScorerDefinition names at 35 chars.

    Catching this client-side avoids the wasted round-trip through the
    template deploy/retrieve/activate flow only to fail at step 4."""
    f = tmp_path / "bad.yaml"
    long_name = "a" * 36
    f.write_text(
        f"name: {long_name}\n"
        "description: x\n"
        "data_type: Text\n"
        "primary_model: m\n"
        "allowed_labels: [A]\n"
        "fallback_label: A\n"
        "prompt: |\n"
        "  {!$Input:Session} {!$Input:AllowedLabels} {!$Input:FallbackLabel}\n"
    )
    with pytest.raises(ScorerSpecError, match="at most 35 characters"):
        load(str(f))


def test_accepts_name_at_35_chars(tmp_path):
    f = tmp_path / "ok.yaml"
    name = "a" * 35
    f.write_text(
        f"name: {name}\n"
        "description: x\n"
        "data_type: Text\n"
        "primary_model: m\n"
        "allowed_labels: [A]\n"
        "fallback_label: A\n"
        "prompt: |\n"
        "  {!$Input:Session} {!$Input:AllowedLabels} {!$Input:FallbackLabel}\n"
    )
    spec = load(str(f))
    assert len(spec.name) == 35


def test_rejects_invalid_name(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(
        "name: 1bad\n"
        "description: x\n"
        "data_type: Text\n"
        "primary_model: m\n"
        "allowed_labels: [A]\n"
        "fallback_label: A\n"
        "prompt: |\n"
        "  {!$SalesforceDataAction:getSession.chatTranscript} {!$Input:AllowedLabels} {!$Input:FallbackLabel}\n"
    )
    with pytest.raises(ScorerSpecError, match="name"):
        load(str(f))
