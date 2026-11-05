#!/usr/bin/env python3
"""Compute MCP action identity and render UI-identical MCP action blocks for Agent Script `.agent` files.

The Builder UI writes each MCP action with a hashed key (also used as `source`)
and a `target` URI. This module reproduces both, and renders the action block
from the org's ExternalServiceRegistration schema and GenAiFunction row.

Usage:
    python3 scripts/mcp_action.py -o <org> --server <ESR> --tool <name> [--tool ...] [--json]

    from mcp_action import action_key, target_uri
    action_key("Slack", "slack_read_channel")
    target_uri("mcpTool", "MF_Slack_Mcp_User", "<ESO DeveloperName from the org>")
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from typing import Literal, Optional

MIN_SF = (2, 142, 1)
UI_ONLY = ("Add this tool with the Builder UI: "
           "the stored complex type name is not readable headless.")


def action_key(esr_name: str, tool: str, namespace: Optional[str] = None) -> str:
    """Return "a" + UUIDv3(MD5) of "[ns:]<ESR>:McpTool__<tool>" (Java UUID.nameUUIDFromBytes)."""
    name = f"{esr_name}:McpTool__{tool}"
    if namespace:
        name = f"{namespace}:{name}"
    return "a" + uuid.UUID(bytes=hashlib.md5(name.encode()).digest(), version=3).hex


def target_uri(kind: Literal["mcpTool", "platformMcpTool"], nc_name: Optional[str], eso_or_devname: str) -> str:
    """Build the action target. 3P needs the NC name; 1P takes the composite devName only."""
    if kind == "platformMcpTool":
        return f"platformMcpTool://{eso_or_devname}"
    if kind == "mcpTool":
        if not nc_name:
            raise ValueError("mcpTool target needs the Named Credential DeveloperName")
        return f"mcpTool://{nc_name}/{eso_or_devname}"
    raise ValueError(f"unknown kind: {kind}")


def eso_name(tool: str) -> str:
    """ExternalServiceOperation DeveloperName for a 3P MCP tool."""
    # shortcut: ESO name derived, not read from org (Tooling ExternalServiceOperation is not supported);
    # verify against ESR operations[].name if a tool name has characters other than [A-Za-z0-9_]
    return "mcptoolx5fx5f" + tool.lower().replace("_", "x5f")


@dataclass
class Param:
    name: str
    type: str
    label: str
    description: str
    required: bool = False
    complex_data_type_name: Optional[str] = None


@dataclass
class McpTool:
    key: str
    label: str
    description: str
    target: str
    inputs: list[Param] = field(default_factory=list)
    outputs: list[Param] = field(default_factory=list)


# Each item type is pinned by a Builder UI sample: string by tests/fixtures/mcp/ui_blocks_complexestypefinal.agent.txt,
# integer by tests/fixtures/mcp/ui_param_save_metadata_record_scores.agent.txt.
_LIST_TYPES = {"string": "lightning__textType", "integer": "lightning__integerType"}


def _param(tool: str, name: str, prop: dict, required: bool) -> Param:
    def refuse(why: str):
        raise SystemExit(f"{tool}: property '{name}' is {why}. {UI_ONLY}")

    if "$ref" in prop or any(k in prop for k in ("anyOf", "oneOf", "allOf")):
        refuse("a $ref/anyOf/oneOf/allOf type")
    ptype, fmt, cdt = prop.get("type"), prop.get("format"), None
    if ptype == "string":
        if fmt == "date-time":
            ptype, cdt = "object", "lightning__dateTimeStringType"
        elif fmt not in (None, "email", "uri"):
            refuse(f"a string with format '{fmt}' (no UI sample)")
    elif ptype == "array":
        items = prop.get("items") or {}
        if set(items) - {"type", "title", "description"} or items.get("type") not in _LIST_TYPES:
            refuse("an array of objects or of a type with no UI sample")
        ptype, cdt = "list[object]", _LIST_TYPES[items["type"]]
    # shortcut: number/boolean refused; enable once a Builder UI block for such a tool (e.g. get_forecast) is a fixture
    elif ptype != "integer":
        refuse(f"of type {json.dumps(ptype)}")
    # shortcut: label falls back to the property name when the schema has no title (no UI sample)
    return Param(name, ptype, prop.get("title", name), prop.get("description", ""), required, cdt)


def _params(tool: str, schema: Optional[dict]) -> list[Param]:
    schema = schema or {}
    req = set(schema.get("required", []))
    return [_param(tool, n, p, n in req) for n, p in schema.get("properties", {}).items()]


def _tooling_query(query: str, target_org: str) -> list[dict]:
    cmd = ["sf", "data", "query", "--use-tooling-api", "--query", query, "-o", target_org, "--json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        data = json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        raise SystemExit(f"query failed: {query}\n{e}")
    if proc.returncode != 0:
        raise SystemExit(f"query failed: {query}\n{data.get('message', proc.stderr)}")
    return data.get("result", {}).get("records", [])


def fetch_mcp_tool(target_org: str, esr_name: str, tool: str) -> McpTool:
    """Read the ESR schema and the GenAiFunction row for one 3P MCP tool."""
    if not re.fullmatch(r"\w+", esr_name):
        raise SystemExit(f"invalid server name: {esr_name}")
    if not re.fullmatch(r"[A-Za-z0-9_]+", tool):
        raise SystemExit(f"tool name {tool!r} has characters the ESO name rule is not proven for. {UI_ONLY}")
    try:
        esr = _tooling_query("SELECT DeveloperName, NamedCredential, NamespacePrefix, Schema "
                             f"FROM ExternalServiceRegistration WHERE DeveloperName='{esr_name}'", target_org)
    except SystemExit as e:
        error = str(e).split("\n", 1)[-1]
        if "NamespacePrefix" not in error:
            raise
        raise SystemExit(f"cannot read ExternalServiceRegistration.NamespacePrefix in {target_org} ({error}); "
                         f"the helper cannot tell if {esr_name} is namespaced, so it stops. {UI_ONLY}")
    if not esr:
        raise SystemExit(f"no ExternalServiceRegistration named {esr_name} in {target_org}")
    if not esr[0].get("Schema"):
        raise SystemExit(f"ExternalServiceRegistration {esr_name} has no Schema in {target_org}; "
                         f"check the server registration with sf agent mcp list")
    tools = {t["name"]: t for t in json.loads(esr[0]["Schema"]).get("tools", [])}
    if tool not in tools:
        raise SystemExit(f"{esr_name} has no tool {tool}; tools: {', '.join(tools)}")
    spec = tools[tool]
    inputs, outputs = _params(tool, spec.get("inputSchema")), _params(tool, spec.get("outputSchema"))
    key = action_key(esr_name, tool, esr[0].get("NamespacePrefix"))
    gafd = _tooling_query("SELECT DeveloperName, MasterLabel, Description FROM GenAiFunctionDefinition "
                          f"WHERE DeveloperName='{key}'", target_org)
    if not gafd:
        raise SystemExit(f"no GenAiFunction {key} for {tool} - {esr_name}; allowlist the tool first with "
                         f"sf agent mcp asset replace")
    target = target_uri("mcpTool", esr[0]["NamedCredential"], eso_name(tool))
    return McpTool(key, gafd[0]["MasterLabel"], gafd[0].get("Description") or "", target, inputs, outputs)


def _desc(text: str, key_indent: int, first: int) -> list[str]:
    """A `description: |` body the way the Builder UI writes it (whitespace-only lines are key indent + 18)."""
    lines = text.split("\n")
    out = [" " * first + lines[0]] + [" " * (key_indent + 2) + ln for ln in lines[1:]]
    return [ln if ln.strip() else " " * (key_indent + 18) for ln in out]


def _param_lines(p: Param, ind: int, is_input: bool) -> list[str]:
    d = ind + 4
    out = [" " * ind + f"{json.dumps(p.name)}: {p.type}", " " * d + "description: |"]
    out += _desc(p.description, d, d + 2)
    out.append(" " * d + f"label: {json.dumps(p.label, ensure_ascii=False)}")
    if is_input:
        out += [" " * d + f"is_required: {p.required}", " " * d + "is_user_input: False"]
    else:
        out += [" " * d + "is_displayable: False", " " * d + "filter_from_agent: False"]
    if p.complex_data_type_name:
        out.append(" " * d + f"complex_data_type_name: {json.dumps(p.complex_data_type_name)}")
    return out


def render_action_block(tool: McpTool, indent: int = 8) -> str:
    """Render the action definition for a subagent's `actions:` section."""
    d = indent + 4
    out = [" " * indent + f"{tool.key}:", " " * d + "description: |"]
    out += _desc(tool.description, d, d + 4)
    out += [" " * d + f"label: {json.dumps(tool.label, ensure_ascii=False)}",
            " " * d + "require_user_confirmation: False",
            " " * d + "include_in_progress_indicator: False",
            " " * d + f'source: "{tool.key}"',
            " " * d + f"target: {json.dumps(tool.target)}"]
    for section, params in (("inputs", tool.inputs), ("outputs", tool.outputs)):
        if params:
            out += [" " * (indent + 16), " " * d + f"{section}:"]
            for p in params:
                out += _param_lines(p, d + 4, section == "inputs")
    return "\n".join(out) + "\n"


def render_reasoning_ref(tool: McpTool, indent: int = 12) -> str:
    """Render the `reasoning.actions` reference with one `with <input> = ...` line per input."""
    out = [" " * indent + f"{tool.key}: @actions.{tool.key}"]
    out += [" " * (indent + 4) + f"with {p.name} = ..." for p in tool.inputs]
    return "\n".join(out) + "\n"


def _check_sf() -> None:
    need = "@salesforce/cli >= " + ".".join(map(str, MIN_SF))
    try:
        out = subprocess.run(["sf", "--version"], capture_output=True, text=True, timeout=30).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        raise SystemExit(f"sf CLI not found; install {need}")
    m = re.search(r"@salesforce/cli/(\d+)\.(\d+)\.(\d+)", out or "")
    if not m or tuple(map(int, m.groups())) < MIN_SF:
        raise SystemExit(f"need {need}; found: {(out or '').strip() or 'unknown'}")


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Render UI-identical MCP action blocks from org data")
    ap.add_argument("-o", "--target-org", required=True)
    ap.add_argument("--server", required=True, help="ExternalServiceRegistration DeveloperName")
    ap.add_argument("--tool", action="append", required=True, help="MCP tool name (repeatable)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    _check_sf()
    tools = [fetch_mcp_tool(args.target_org, args.server, t) for t in args.tool]
    if args.json:
        print(json.dumps({"actions": [
            {"key": t.key, "source": t.key, "target": t.target,
             "actionBlock": render_action_block(t), "reasoningReference": render_reasoning_ref(t)}
            for t in tools]}, indent=2))
        return
    print("# subagent actions:")
    print("".join(render_action_block(t) for t in tools))
    print("# reasoning actions:")
    print("".join(render_reasoning_ref(t) for t in tools), end="")


if __name__ == "__main__":
    main(sys.argv[1:])
