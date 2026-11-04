"""Tests for discover.py MCP action identity checks."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.discover as d

FIXTURE = Path(__file__).parent / "fixtures" / "mcp" / "miguelforce_slack.agent"
ROOT = Path(__file__).parent.parent

GAFDS = [
    ("a35a85c9f600c3162823b8430ba4d38be", "slack_read_channel - Slack"),
    ("ab153b6cf610537e19208585232f50935", "slack_read_thread - Slack"),
    ("a2c362836c99530c49bcebad230c713be", "slack_search_channels - Slack"),
    ("a29f2e52c6bf73532877ec5afebe4bbaf", "slack_search_public - Slack"),
    ("a92c6644f97f436968b1d06a2cf89aaae", "slack_search_public_and_private - Slack"),
    ("a69212c177ff13d45a1e9dbfb8b2e40b3", "slack_search_users - Slack"),
]
EXPECTED = {
    "search_slack": "a92c6644f97f436968b1d06a2cf89aaae",
    "read_slack_channel": "a35a85c9f600c3162823b8430ba4d38be",
    "read_slack_thread": "ab153b6cf610537e19208585232f50935",
    "search_slack_channels": "a2c362836c99530c49bcebad230c713be",
    "search_slack_users": "a69212c177ff13d45a1e9dbfb8b2e40b3",
}


def _records():
    rows = [
        {"Id": f"1XO00000000000{i}AAA", "DeveloperName": dev, "MasterLabel": label,
         "InvocationTarget": f"Slack{i}", "InvocationTargetType": "mcpTool"}
        for i, (dev, label) in enumerate(GAFDS, 1)
    ]
    rows.append({"Id": "1XO000000000099AAA", "DeveloperName": "Sales_Tool", "MasterLabel": "Sales Tool",
                 "InvocationTarget": "Sales_Tool", "InvocationTargetType": "platformMcpTool"})
    return rows


@pytest.fixture(autouse=True)
def mock_org(monkeypatch):
    monkeypatch.setattr(d, "_query_org", lambda query, org: _records())


def _agent(tmp_path, body):
    f = tmp_path / "t.agent"
    f.write_text("subagent s:\n    actions:\n" + body, encoding="utf-8")
    return f


def test_claude_written_actions_fail():
    rows = d.discover(FIXTURE, "org").targets
    assert len(rows) == 6
    for key in EXPECTED.values():
        row = next(r for r in rows if r.details.startswith(f"action key must be {key}"))
        assert row.found is False
        assert f"source must be {key}" in row.details
        assert "warning" not in row.details


def test_ui_correct_action_passes():
    report = d.discover(FIXTURE, "org")
    passed = [t for t in report.targets if t.found]
    assert len(passed) == 1
    assert "slackx5freadx5fchannel" in passed[0].target
    assert "warning" not in passed[0].details


def test_tool_without_gafd(tmp_path):
    f = _agent(tmp_path, '        foo:\n            target: "mcpTool://NC/mcptoolx5fx5fnopex5ftool"\n')
    row = d.discover(f, "org").targets[0]
    assert row.found is False
    assert "no GenAiFunction for this MCP tool; allowlist it with sf agent mcp asset replace" in row.details


def test_source_only_wrong(tmp_path):
    key = EXPECTED["read_slack_channel"]
    f = _agent(tmp_path, f'        {key}:\n            source: "x"\n'
                         '            target: "mcpTool://NC/mcptoolx5fx5fslackx5freadx5fchannel"\n')
    row = d.discover(f, "org").targets[0]
    assert row.found is False
    assert f"source must be {key}" in row.details
    assert "action key must be" not in row.details


def test_label_vs_computed_key_warning(monkeypatch, tmp_path):
    recs = _records()
    recs[0]["DeveloperName"] = "aBAD"
    monkeypatch.setattr(d, "_query_org", lambda q, o: recs)
    f = _agent(tmp_path, '        aBAD:\n            source: "aBAD"\n'
                         '            target: "mcpTool://NC/mcptoolx5fx5fslackx5freadx5fchannel"\n')
    row = d.discover(f, "org").targets[0]
    assert row.found is True
    assert "warning" in row.details


def test_platform_mcp_tool(tmp_path):
    f = _agent(tmp_path, '        Sales_Tool:\n            source: "Sales_Tool"\n'
                         '            target: "platformMcpTool://Sales_Tool"\n'
                         '        Other_Tool:\n            source: "Other_Tool"\n'
                         '            target: "platformMcpTool://Other_Tool"\n')
    rows = d.discover(f, "org").targets
    assert [r.found for r in rows] == [True, False]
    assert all("1P match rule not verified against a UI sample" in r.details for r in rows)
    assert rows[0].target_type == "platformMcpTool"


def test_extract_includes_mcp_targets():
    uris = [t[0] for t in d.extract_targets(FIXTURE)]
    assert len(uris) == 6 and all(u.startswith("mcpTool://") for u in uris)
    actions = d.extract_actions(FIXTURE)
    assert actions[-1]["name"] == actions[-1]["source"] == "a35a85c9f600c3162823b8430ba4d38be"


@pytest.mark.parametrize("name", ["discover.py", "mcp_action.py"])
def test_script_trees_identical(name):
    assert (ROOT / "scripts" / name).read_bytes() == (ROOT / "skills/agentforce-generate/scripts" / name).read_bytes()
