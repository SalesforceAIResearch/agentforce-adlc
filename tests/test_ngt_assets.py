"""Structural tests for NGT assets and references shipped with /testing-agentforce.

These run without an `sf` CLI or any org. They check that the canonical NGT
YAML fixture exists, has the expected shape, and exercises the scorer
catalog; that the rewritten batch-testing.md reference is NGT-focused; that
the legacy archaeology doc carries the deprecation banner; and that the
troubleshooting doc covers the canonical-probe failure modes.

If any of these fail, docs are out of sync with the impl plan.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
NGT_FIXTURE = REPO_ROOT / "skills" / "testing-agentforce" / "assets" / "ngt-test-spec.yaml"
BATCH_TESTING = REPO_ROOT / "skills" / "testing-agentforce" / "references" / "batch-testing.md"
LEGACY_DOC = REPO_ROOT / "skills" / "testing-agentforce" / "references" / "legacy-testing-center.md"
TROUBLESHOOTING = REPO_ROOT / "skills" / "testing-agentforce" / "references" / "troubleshooting.md"
ASSETS_DIR = REPO_ROOT / "skills" / "testing-agentforce" / "assets"


# --- Canonical NGT YAML fixture ---------------------------------------------

def test_ngt_fixture_exists():
    assert NGT_FIXTURE.exists(), f"missing canonical NGT fixture at {NGT_FIXTURE}"


def test_ngt_fixture_top_level_shape():
    spec = yaml.safe_load(NGT_FIXTURE.read_text())
    assert spec["subjectType"] == "AGENT"
    assert spec["subjectName"]
    assert spec["testCases"]
    assert all("inputs" in tc and "scorers" in tc for tc in spec["testCases"])


def test_ngt_fixture_covers_all_scorer_categories():
    """Sanity — the canonical fixture should exercise every scorer category."""
    spec = yaml.safe_load(NGT_FIXTURE.read_text())
    seen = {s["name"] for tc in spec["testCases"] for s in tc["scorers"]}
    assertion_scorers = {
        "topic_sequence_match",
        "action_sequence_match",
        "agent_handoff_match",
        "bot_response_rating",
        "response_match",
    }
    quality_scorers = {"coherence", "factuality", "completeness", "task_resolution"}
    numeric_scorers = {"output_latency_milliseconds"}
    assert seen & assertion_scorers, "fixture must include at least one assertion scorer"
    assert seen & quality_scorers, "fixture must include at least one quality scorer"
    assert seen & numeric_scorers, "fixture must include the numeric scorer"


def test_legacy_authoring_assets_removed():
    """Mode B is NGT-only; legacy authoring templates must not ship."""
    for legacy in ("basic-test-spec.yaml", "standard-test-spec.yaml", "guardrail-test-spec.yaml"):
        assert not (ASSETS_DIR / legacy).exists(), (
            f"{legacy} should be removed — Mode B is NGT-only as of v0.7.0"
        )


# --- batch-testing.md (rewritten as NGT-focused) ----------------------------

def test_batch_testing_doc_is_ngt_focused():
    md = BATCH_TESTING.read_text()
    required_sections = [
        "## When to use",
        "## YAML schema",
        "## Scorer catalog",
        "## CLI invocations",
        "## Org capability probe",
        "## Result parsing",
        "## Validator errors",
        "## Hand-edit escape hatch",
        "## Known gotchas",
    ]
    for section in required_sections:
        assert section in md, f"missing section: {section}"
    assert "AiTestingDefinition" in md
    assert "agentforce-studio" in md
    assert "legacy-testing-center.md" in md, "must cross-link to legacy archaeology doc"


def test_batch_testing_doc_documents_canonical_probe():
    md = BATCH_TESTING.read_text()
    assert "sf agent test list" in md
    assert "INVALID_TYPE" in md, "must document the canonical-probe negative signal"


# --- legacy-testing-center.md (archaeology) ---------------------------------

def test_legacy_doc_has_deprecation_banner():
    md = LEGACY_DOC.read_text()
    assert "DEPRECATION NOTICE" in md
    assert "0.6.x" in md, "must point users at the legacy-supporting version pin"
    assert "AiEvaluationDefinition" in md  # still describes the legacy schema


# --- troubleshooting.md (NGT-specific issues) -------------------------------

def test_troubleshooting_covers_ngt():
    md = TROUBLESHOOTING.read_text()
    assert "AmbiguousTestDefinition" in md
    assert "agentforce-studio" in md
    assert "aFStudioTestingCenter" in md
    assert "0.6.x" in md, "non-NGT-org users must be pointed at the legacy version pin"
    assert "INVALID_TYPE" in md, "must document the canonical-probe failure mode"
