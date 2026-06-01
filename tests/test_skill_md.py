"""Structural tests for the testing-agentforce SKILL.md NGT cutover.

Asserts the v0.7.0 metadata + single-mode Mode B layout per the impl plan
at docs/spikes/2026-05-28-ngt-integration/07-impl-plan-skill-cutover.md.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = REPO_ROOT / "skills" / "testing-agentforce" / "SKILL.md"


def test_version_bumped():
    md = SKILL_MD.read_text()
    m = re.search(r'^\s*version:\s*"([^"]+)"', md, re.MULTILINE)
    assert m, "version field missing"
    assert m.group(1) >= "0.7.0", f"version must be ≥ 0.7.0 for NGT cutover (0.6.x ships legacy authoring); got {m.group(1)}"


def test_last_updated_bumped():
    md = SKILL_MD.read_text()
    m = re.search(r'^\s*last_updated:\s*"([^"]+)"', md, re.MULTILINE)
    assert m
    assert m.group(1) >= "2026-05-29"


def test_trigger_mentions_ngt_not_legacy_authoring():
    md = SKILL_MD.read_text()
    assert "AiTestingDefinition" in md, "TRIGGER block must mention AiTestingDefinition"
    assert "agentforce-studio" in md
    desc_match = re.search(r'description:\s*"((?:[^"\\]|\\.)*)"', md, re.DOTALL)
    assert desc_match, "description field not found"
    desc = desc_match.group(1)
    assert "AiEvaluationDefinition" not in desc or "legacy" in desc.lower(), (
        "TRIGGER should not invite legacy authoring; legacy reference is archaeology only"
    )


def test_single_mode_b():
    md = SKILL_MD.read_text()
    assert "## Mode B:" in md or "## Mode B " in md, "Mode B section missing"
    assert "Mode B1" not in md, "Mode B should not be split into B1/B2"
    assert "Mode B2" not in md
    assert "AiTestingDefinition" in md
    assert "--test-runner agentforce-studio" in md


def test_legacy_archaeology_referenced_not_active():
    md = SKILL_MD.read_text()
    assert "legacy-testing-center.md" in md
    assert "0.6.x" in md, "must point users at the legacy-supporting version pin"


def test_org_capability_probe_documented():
    md = SKILL_MD.read_text()
    assert "aFStudioTestingCenter" in md, "must mention the org-capability probe"
    assert "agent test list" in md, "must reference the canonical probe command"


def test_argument_hint_carries_mode_a():
    md = SKILL_MD.read_text()
    m = re.search(r'argument-hint:\s*"([^"]+)"', md)
    assert m, "argument-hint missing"
    # Mode A invocation shape (--authoring-bundle) must remain documented somewhere
    assert "--authoring-bundle" in m.group(1) or "--authoring-bundle" in md
