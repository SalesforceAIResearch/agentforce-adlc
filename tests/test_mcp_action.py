"""Tests for mcp_action.py — MCP action key and target helpers."""

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "mcp_action", Path(__file__).parent.parent / "skills" / "agentforce-generate" / "scripts" / "mcp_action.py"
)
mcp_action = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mcp_action)
action_key, target_uri = mcp_action.action_key, mcp_action.target_uri


def test_action_key_known_values():
    assert action_key("Slack", "slack_read_channel") == "a35a85c9f600c3162823b8430ba4d38be"
    assert action_key("Slack", "slack_send_message") == "a088dbc2f6de3312b9c1925ea188e6751"
    assert action_key("EstypeRound3", "create_team").startswith("a796bc2f")


def test_action_key_depends_on_esr():
    assert action_key("MF_Slack_Mcp_User", "slack_read_channel") != action_key("Slack", "slack_read_channel")


def test_action_key_namespace_changes_key():
    assert action_key("Slack", "slack_read_channel", "ns") != action_key("Slack", "slack_read_channel")


def test_target_uri_3p():
    eso = "mcptoolx5fx5fslackx5freadx5fchannel"
    assert target_uri("mcpTool", "MF_Slack_Mcp_User", eso) == f"mcpTool://MF_Slack_Mcp_User/{eso}"


def test_target_uri_1p_without_nc():
    assert target_uri("platformMcpTool", None, "dev_name") == "platformMcpTool://dev_name"


def test_target_uri_3p_requires_nc():
    with pytest.raises(ValueError):
        target_uri("mcpTool", None, "eso")
