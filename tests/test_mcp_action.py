"""Tests for mcp_action.py — MCP action key, target, and UI-identical block rendering."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "mcp_action", Path(__file__).parent.parent / "skills" / "agentforce-generate" / "scripts" / "mcp_action.py"
)
mcp_action = importlib.util.module_from_spec(_SPEC)
sys.modules["mcp_action"] = mcp_action  # dataclasses look the module up
_SPEC.loader.exec_module(mcp_action)
action_key, target_uri = mcp_action.action_key, mcp_action.target_uri

FIX = Path(__file__).parent / "fixtures" / "mcp"
STATUS_KEY = "a62d42e97f7f53014a595742b49b2e574"


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


def test_eso_name_matches_esr_operations():
    # Values from the AdharshServerNew ESR metadata operations[].name (dev-org fixture).
    assert mcp_action.eso_name("hello_world") == "mcptoolx5fx5fhellox5fworld"
    assert mcp_action.eso_name("get_forecast") == "mcptoolx5fx5fgetx5fforecast"
    assert mcp_action.eso_name("revokeSession") == "mcptoolx5fx5frevokesession"


# --- org mocks ---------------------------------------------------------------


def _org(tools, gafds, esr="ComplexESTypeFinal", nc="ComplexESTypeFinal", ns=None, schema="tools", esr_error=None):
    """Fake `sf data query --use-tooling-api` for the ESR and GAFD queries."""

    def run(cmd, **kwargs):
        query = cmd[cmd.index("--query") + 1]
        if "FROM ExternalServiceRegistration" in query:
            if esr_error:
                out = json.dumps({"status": 1, "name": "INVALID_FIELD", "message": esr_error})
                return subprocess.CompletedProcess(cmd, 1, stdout=out, stderr="")
            body = json.dumps({"serverDescriptor": {}, "tools": tools}) if schema == "tools" else schema
            records = ([{"DeveloperName": esr, "NamedCredential": nc, "NamespacePrefix": ns, "Schema": body}]
                       if f"'{esr}'" in query else [])
        else:
            records = [g for g in gafds if f"'{g['DeveloperName']}'" in query]
        out = json.dumps({"status": 0, "result": {"records": records, "totalSize": len(records)}})
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    return run


def _gafd(esr, tool, ns=None):
    return {"DeveloperName": action_key(esr, tool["name"], ns), "MasterLabel": f"{tool['name']} - {esr}",
            "Description": tool["description"]}


@pytest.fixture
def status_tool():
    return json.loads((FIX / "esr_tool_set_status_light.json").read_text(encoding="utf-8"))


@pytest.fixture
def final_tools():
    return json.loads((FIX / "esr_tools_complexestypefinal.json").read_text(encoding="utf-8"))["tools"]


def _fetch(monkeypatch, tools, name, esr="ComplexESTypeFinal", gafds=None, nc=None, ns=None, **org_kw):
    gafds = [_gafd(esr, t, ns) for t in tools] if gafds is None else gafds
    monkeypatch.setattr(mcp_action.subprocess, "run", _org(tools, gafds, esr=esr, nc=nc or esr, ns=ns, **org_kw))
    return mcp_action.fetch_mcp_tool("org", esr, name)


# --- rendering -----------------------------------------------------------------


def test_render_matches_ui_fixture(monkeypatch, status_tool):
    ui = (FIX / "ui_block_set_status_light.agent.txt").read_text(encoding="utf-8")
    tool = _fetch(monkeypatch, [status_tool], "set_status_light")
    assert tool.key == STATUS_KEY
    assert tool.label == "set_status_light - ComplexESTypeFinal"
    block = mcp_action.render_action_block(tool)
    assert block == ui[ui.index(f"        {STATUS_KEY}:\n"):]
    ref = mcp_action.render_reasoning_ref(tool)
    assert ref == f"            {STATUS_KEY}: @actions.{STATUS_KEY}\n                with color = ...\n"
    assert ref in ui


def test_render_matches_more_ui_blocks(monkeypatch, final_tools):
    """date-time -> object + lightning__dateTimeStringType; string[] -> list[object] + lightning__textType."""
    ui = (FIX / "ui_blocks_complexestypefinal.agent.txt").read_text(encoding="utf-8")
    names = ["register_contact", "create_user_profile", "run_health_check"]
    rendered = "".join(mcp_action.render_action_block(_fetch(monkeypatch, final_tools, n)) for n in names)
    assert rendered == ui


def test_no_output_schema_omits_outputs(monkeypatch, status_tool):
    del status_tool["outputSchema"]
    block = mcp_action.render_action_block(_fetch(monkeypatch, [status_tool], "set_status_light"))
    assert "outputs:" not in block
    assert block.endswith("                    is_user_input: False\n")


def test_reasoning_ref_has_with_per_input(monkeypatch, final_tools):
    tool = _fetch(monkeypatch, final_tools, "register_contact")
    lines = mcp_action.render_reasoning_ref(tool).splitlines()
    assert lines[1:] == [f"                with {p} = ..." for p in ("email", "homepage", "signup_at")]


def test_missing_gafd_message(monkeypatch, status_tool):
    with pytest.raises(SystemExit) as exc:
        _fetch(monkeypatch, [status_tool], "set_status_light", gafds=[])
    assert "sf agent mcp asset replace" in str(exc.value)


def test_nested_tool_refused(monkeypatch, final_tools):
    with pytest.raises(SystemExit) as exc:
        _fetch(monkeypatch, final_tools, "place_order")
    msg = str(exc.value)
    assert "billing" in msg and "Builder UI" in msg


@pytest.mark.parametrize("prop", [
    {"type": "object", "properties": {"a": {"type": "string"}}},
    {"anyOf": [{"type": "string"}, {"type": "null"}]},
    {"type": "array", "items": {"type": "object"}},
    {"type": ["boolean", "null"]},
    {"type": "number"},
    {"type": "boolean"},
])
def test_complex_property_refused(monkeypatch, status_tool, prop):
    status_tool["inputSchema"]["properties"]["color"] = prop
    with pytest.raises(SystemExit, match="Builder UI"):
        _fetch(monkeypatch, [status_tool], "set_status_light")


def test_cli_json(monkeypatch, capsys, status_tool):
    calls = _org([status_tool], [_gafd("ComplexESTypeFinal", status_tool)])

    def run(cmd, **kwargs):
        if cmd[:2] == ["sf", "--version"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="@salesforce/cli/2.146.3 darwin-arm64 node-v22\n")
        return calls(cmd, **kwargs)

    monkeypatch.setattr(mcp_action.subprocess, "run", run)
    mcp_action.main(["-o", "org", "--server", "ComplexESTypeFinal", "--tool", "set_status_light", "--json"])
    out = json.loads(capsys.readouterr().out)
    (act,) = out["actions"]
    assert act["key"] == act["source"] == STATUS_KEY
    assert act["target"] == "mcpTool://ComplexESTypeFinal/mcptoolx5fx5fsetx5fstatusx5flight"
    assert act["actionBlock"].startswith(f"        {STATUS_KEY}:\n")
    assert act["reasoningReference"].endswith("with color = ...\n")


@pytest.mark.parametrize("stdout", ["@salesforce/cli/2.142.0 darwin-arm64 node-v22\n", None])
def test_cli_requires_sf(monkeypatch, stdout):
    def run(cmd, **kwargs):
        if stdout is None:
            raise FileNotFoundError("sf")
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout)

    monkeypatch.setattr(mcp_action.subprocess, "run", run)
    with pytest.raises(SystemExit, match=r"@salesforce/cli >= 2\.142\.1"):
        mcp_action.main(["-o", "org", "--server", "X", "--tool", "y"])


@pytest.mark.parametrize("name", ["get-alerts", "tools.get_alerts"])
def test_tool_name_outside_eso_rule_refused(monkeypatch, name):
    def run(cmd, **kwargs):
        raise AssertionError("no org query expected")

    monkeypatch.setattr(mcp_action.subprocess, "run", run)
    with pytest.raises(SystemExit, match="Builder UI"):
        mcp_action.fetch_mcp_tool("org", "ComplexESTypeFinal", name)


def test_esr_and_nc_names_differ(monkeypatch, status_tool):
    """The key uses the ESR name; the target uses the Named Credential name."""
    tool = _fetch(monkeypatch, [status_tool], "set_status_light", esr="P0Esr", nc="P0Nc")
    assert tool.key == action_key("P0Esr", "set_status_light")
    assert tool.key != action_key("P0Nc", "set_status_light")
    assert tool.target.startswith("mcpTool://P0Nc/")
    assert tool.target == "mcpTool://P0Nc/mcptoolx5fx5fsetx5fstatusx5flight"


def test_namespaced_esr_key(monkeypatch, status_tool):
    tool = _fetch(monkeypatch, [status_tool], "set_status_light", ns="ns1")
    assert tool.key == action_key("ComplexESTypeFinal", "set_status_light", "ns1")


def test_namespace_field_missing_refused(monkeypatch, status_tool):
    with pytest.raises(SystemExit) as exc:
        _fetch(monkeypatch, [status_tool], "set_status_light",
               esr_error="No such column 'NamespacePrefix' on entity 'ExternalServiceRegistration'.")
    msg = str(exc.value)
    assert "NamespacePrefix" in msg and "namespaced" in msg and "Builder UI" in msg


def test_other_esr_query_error_not_reported_as_namespace(monkeypatch, status_tool):
    with pytest.raises(SystemExit) as exc:
        _fetch(monkeypatch, [status_tool], "set_status_light", esr_error="INVALID_SESSION_ID")
    assert "namespaced" not in str(exc.value)
    assert "INVALID_SESSION_ID" in str(exc.value)


def test_null_schema_clear_message(monkeypatch, status_tool):
    with pytest.raises(SystemExit, match="has no Schema"):
        _fetch(monkeypatch, [status_tool], "set_status_light", schema=None)


def test_integer_list_matches_ui_param():
    """integer[] -> list[object] + lightning__integerType, pinned by a Builder UI output param."""
    prop = json.loads((FIX / "esr_prop_save_metadata_record_scores.json").read_text(encoding="utf-8"))
    ui = (FIX / "ui_param_save_metadata_record_scores.agent.txt").read_text(encoding="utf-8")
    p = mcp_action._param("save_metadata_record", "scores", prop, False)
    assert "\n".join(mcp_action._param_lines(p, 16, False)) + "\n" == ui
