"""Contract tests for the Agentforce Doctor skill."""

import json
from pathlib import Path

from tools import install


ROOT = Path(__file__).parent.parent
DOCTOR = ROOT / "skills" / "agentforce-doctor"


def test_doctor_skill_is_complete_and_registered():
    skill_text = (DOCTOR / "SKILL.md").read_text()
    assert "name: agentforce-doctor" in skill_text
    assert "[TODO" not in skill_text
    assert (DOCTOR / "agents" / "openai.yaml").exists()
    assert (DOCTOR / "references" / "diagnostic-catalog.md").exists()
    assert (DOCTOR / "references" / "evaluation-loop.md").exists()

    registry = json.loads(
        (ROOT / "shared" / "hooks" / "skills-registry.json").read_text()
    )
    assert registry["skills"]["agentforce-doctor"]["path"] == (
        "skills/agentforce-doctor"
    )


def test_doctor_skill_is_installed_by_file_copy_workflow(tmp_path):
    target = {"skills_dir": tmp_path / "skills"}
    installed = install.install_skills(ROOT, target)

    assert "agentforce-doctor" in installed
    assert (target["skills_dir"] / "agentforce-doctor" / "SKILL.md").exists()


def test_doctor_requires_actionable_findings_and_frozen_evaluation():
    skill_text = (DOCTOR / "SKILL.md").read_text()
    evaluation_text = (
        DOCTOR / "references" / "evaluation-loop.md"
    ).read_text()
    normalized_skill = " ".join(skill_text.split())
    normalized_evaluation = " ".join(evaluation_text.split())

    assert "No location, consequence, use case, and verification plan" in normalized_skill
    assert "same use cases and evaluators" in normalized_skill
    assert "Do not change the evaluator to make the candidate pass" in normalized_skill
    assert "must not silently encode the third category" in normalized_evaluation
    assert "Do not substitute a Python or regex approximation" in normalized_evaluation


def test_doctor_covers_prompt_indentation_and_action_leakage():
    catalog = (
        DOCTOR / "references" / "diagnostic-catalog.md"
    ).read_text()

    assert "indentation beneath `|` is treated as executable nesting" in catalog
    assert "action visually placed under one prompt branch" in catalog
    assert "available-action list" in catalog


def test_doctor_batches_large_agent_repairs():
    skill_text = " ".join((DOCTOR / "SKILL.md").read_text().split())
    evaluation_text = " ".join(
        (DOCTOR / "references" / "evaluation-loop.md").read_text().split()
    )

    assert "For an agent over 2,000 lines or 10 execution nodes" in skill_text
    assert "Repair at most three related causes in one batch" in skill_text
    assert "must never construct one monolithic patch" in skill_text
    assert "unaffected canary cases" in evaluation_text
