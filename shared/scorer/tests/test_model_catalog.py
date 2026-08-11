"""Tests for model_catalog — catalog filtering and per-org enablement parsing.

The parse_configured_models fixtures mirror the real Data 360 configured-models
Connect API response shape (verified against core-264-public test fixtures:
core/cdp-impl/test/func/connect/MlConfiguredModelApiTest/response/*.json). Each
record combines `namespace` + `name` into the `sfdc_ai__Default…` identifier.
"""
from __future__ import annotations

from src import model_catalog
from src.model_catalog import parse_configured_models


def _rec(name, *, namespace="sfdc_ai", capability="ChatCompletion",
         status="Enabled"):
    return {
        "namespace": namespace,
        "name": name,
        "capability": capability,
        "status": status,
        "artifact": {"namespace": "llmgateway", "name": name.replace("Default", "")},
    }


def test_parse_extracts_sfdc_ai_identifiers():
    payload = {
        "configuredModels": [
            _rec("DefaultOpenAIGPT4OmniMini"),
            _rec("DefaultGPT5"),
        ],
        "nextPageUrl": None,
    }
    idents, next_page = parse_configured_models(payload)
    assert idents == {
        "sfdc_ai__DefaultOpenAIGPT4OmniMini",
        "sfdc_ai__DefaultGPT5",
    }
    assert next_page is None


def test_parse_keeps_rerouted_drops_deprecated_and_disabled():
    """Enabled + Rerouted are usable; Deprecated/Disabled are not."""
    payload = {
        "configuredModels": [
            _rec("DefaultGPT5", status="Enabled"),
            _rec("DefaultOpenAIGPT4", status="Rerouted"),
            _rec("DefaultOldModel", status="Deprecated"),
            _rec("DefaultOffModel", status="Disabled"),
        ]
    }
    idents, _ = parse_configured_models(payload)
    assert idents == {"sfdc_ai__DefaultGPT5", "sfdc_ai__DefaultOpenAIGPT4"}


def test_parse_drops_non_chatcompletion_capabilities():
    """Embedding / classification models can't drive a scorer prompt template."""
    payload = {
        "configuredModels": [
            _rec("DefaultGPT5", capability="ChatCompletion"),
            _rec("DefaultAda", capability="Embedding"),
            _rec("DefaultClassifier", capability="BinaryClassification"),
        ]
    }
    idents, _ = parse_configured_models(payload)
    assert idents == {"sfdc_ai__DefaultGPT5"}


def test_parse_drops_non_sfdc_ai_namespace():
    """BYO / custom models live under other namespaces and aren't catalog aliases."""
    payload = {
        "configuredModels": [
            _rec("DefaultGPT5", namespace="sfdc_ai"),
            _rec("MyCustomLlm", namespace="c"),
            _rec("SomeArtifact", namespace="llmgateway"),
        ]
    }
    idents, _ = parse_configured_models(payload)
    assert idents == {"sfdc_ai__DefaultGPT5"}


def test_parse_surfaces_next_page_url():
    payload = {
        "configuredModels": [_rec("DefaultGPT5")],
        "nextPageUrl": "/services/data/v66.0/ssot/machine-learning/configured-models?page=2",
    }
    idents, next_page = parse_configured_models(payload)
    assert idents == {"sfdc_ai__DefaultGPT5"}
    assert next_page == payload["nextPageUrl"]


def test_parse_tolerates_malformed_payloads():
    """A partial/unexpected response must never crash the picker."""
    assert parse_configured_models(None) == (set(), None)
    assert parse_configured_models([]) == (set(), None)
    assert parse_configured_models({}) == (set(), None)
    assert parse_configured_models({"configuredModels": "nope"}) == (set(), None)
    # Records missing keys are skipped, not fatal.
    payload = {"configuredModels": [{}, {"name": "X"}, {"namespace": "sfdc_ai"}]}
    assert parse_configured_models(payload) == (set(), None)


def test_parsed_identifiers_intersect_the_catalog():
    """The identifiers the API yields are the exact form CATALOG stores — a direct
    intersection works with no alias/artifact mapping."""
    payload = {
        "configuredModels": [
            _rec("DefaultOpenAIGPT4OmniMini"),  # in catalog
            _rec("DefaultGPT5"),                # in catalog
            _rec("DefaultSomeUnknownModel"),    # not in catalog
        ]
    }
    idents, _ = parse_configured_models(payload)
    catalog_ids = {m.identifier for m in model_catalog.CATALOG}
    enabled_in_catalog = idents & catalog_ids
    assert "sfdc_ai__DefaultOpenAIGPT4OmniMini" in enabled_in_catalog
    assert "sfdc_ai__DefaultGPT5" in enabled_in_catalog
    assert "sfdc_ai__DefaultSomeUnknownModel" not in enabled_in_catalog


def test_default_pick_is_a_real_catalog_identifier():
    """The Step 4.5 default judge must exist in the catalog."""
    catalog_ids = {m.identifier for m in model_catalog.CATALOG}
    assert "sfdc_ai__DefaultOpenAIGPT4OmniMini" in catalog_ids
    assert model_catalog.DEFAULT_PICKS[0] == "sfdc_ai__DefaultOpenAIGPT4OmniMini"
