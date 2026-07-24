"""Pytest entry points for the real AgentScript SDK validator."""

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = ROOT / "tests" / "validate_agent_assets.mjs"
ASSET_ROOT = ROOT / "skills" / "agentforce-generate" / "assets"


def _parser_path() -> str:
    parser = os.environ.get("AGENTSCRIPT_PARSER")
    if not parser:
        pytest.skip(
            "Set AGENTSCRIPT_PARSER to run the AgentScript SDK tests; "
            "CI validates the pinned source build separately."
        )
    return parser


def _run_validator(asset_root: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "AGENTSCRIPT_PARSER": _parser_path()}
    return subprocess.run(
        ["node", str(VALIDATOR), str(asset_root)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_shipped_agent_assets_compile():
    result = _run_validator(ASSET_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_agent_sdk_rejects_malformed_asset(tmp_path):
    (tmp_path / "invalid.agent").write_text(
        "this is not valid AgentScript\n",
        encoding="utf-8",
    )
    result = _run_validator(tmp_path)
    assert result.returncode != 0
    assert "invalid.agent" in result.stdout + result.stderr
