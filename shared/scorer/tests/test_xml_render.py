"""Parity tests: rendered XML must match the platform's expected scorer template shape.

The reference XML at tests/fixtures/reference_template_with_data_provider.xml is a
UI-built scorer prompt template (CompetitorMentions, exported via the Test Suite UI).
It is the ground truth for what the platform's auto-sampling pipeline expects: a
GenAiPromptTemplate that declares getSession as a templateDataProviders block and
references the conversation transcript via {!$SalesforceDataAction:getSession.chatTranscript}
in the body.
"""
from __future__ import annotations

from pathlib import Path

from src.scorer_spec import load
from src.xml_render import render

REFERENCE_XML = (
    Path(__file__).resolve().parent / "fixtures" / "reference_template_with_data_provider.xml"
)


def test_renders_sentiment_analysis_without_active_version():
    spec = load("sentiment_analysis")
    rendered = render(spec)
    # No <activeVersionIdentifier> on first deploy.
    assert "<activeVersionIdentifier>" not in rendered
    assert "<developerName>sentiment_analysis</developerName>" in rendered
    assert "<masterLabel>sentiment_analysis</masterLabel>" in rendered
    assert "<primaryModel>sfdc_ai__DefaultOpenAIGPT4OmniMini</primaryModel>" in rendered
    assert "<type>agentforce_session_tracing__scorerMultilabel</type>" in rendered
    assert "lightningtype://propertyType/agentforce_session_tracing__stdmDetailViewType" in rendered
    assert "{!$SalesforceDataAction:getSession.chatTranscript}" in rendered
    assert "{!$Input:AllowedLabels}" in rendered
    assert "{!$Input:FallbackLabel}" in rendered
    assert "what&apos;s the customer sentiment" in rendered


def test_renders_with_active_version_identifier():
    spec = load("sentiment_analysis")
    rendered = render(spec, active_version_identifier="FakeVerId_1")
    assert "<activeVersionIdentifier>FakeVerId_1</activeVersionIdentifier>" in rendered


def test_renders_template_data_providers_block():
    """Every emitted template registers the getSession Data Action as a data provider.

    This is required for the platform's auto-sampling pipeline — without it, the
    runner has nothing to invoke when hydrating {!$SalesforceDataAction:getSession.chatTranscript}.
    """
    spec = load("response_quality")
    rendered = render(spec)
    assert rendered.count("<templateDataProviders>") == 1
    assert "<definition>invocable://getSession</definition>" in rendered
    assert "<referenceName>SalesforceDataAction:getSession</referenceName>" in rendered
    assert "<parameterName>sessionDataView</parameterName>" in rendered
    assert "<valueExpression>{!$Input:Session}</valueExpression>" in rendered


def test_renders_match_reference_structural_blocks():
    """The structural blocks the platform looks for must match the UI-emitted reference.

    We compare:
      - the three <inputs> blocks (Session, AllowedLabels, FallbackLabel)
      - the <templateDataProviders> block
      - the <type> and <visibility> elements

    Per-scorer fields (developerName, masterLabel, prompt body, allowed labels,
    fallback) legitimately differ and are not asserted here.
    """
    spec = load("response_quality")
    rendered = render(spec)
    reference = REFERENCE_XML.read_text()

    for snippet in (
        "<apiName>Session</apiName>",
        "<definition>lightningtype://propertyType/agentforce_session_tracing__stdmDetailViewType</definition>",
        "<referenceName>Input:Session</referenceName>",
        "<apiName>AllowedLabels</apiName>",
        "<apiName>FallbackLabel</apiName>",
        "<definition>invocable://getSession</definition>",
        "<parameterName>sessionDataView</parameterName>",
        "<valueExpression>{!$Input:Session}</valueExpression>",
        "<referenceName>SalesforceDataAction:getSession</referenceName>",
        "<type>agentforce_session_tracing__scorerMultilabel</type>",
        "<visibility>Global</visibility>",
    ):
        assert snippet in rendered, f"missing in rendered: {snippet}"
        assert snippet in reference, f"missing in reference fixture: {snippet}"


def test_user_frustration_renders_all_inputs():
    spec = load("user_frustration")
    rendered = render(spec)
    assert rendered.count("<inputs>") == 3
    assert "<apiName>Session</apiName>" in rendered
    assert "<apiName>AllowedLabels</apiName>" in rendered
    assert "<apiName>FallbackLabel</apiName>" in rendered
    assert rendered.count("<templateDataProviders>") == 1
