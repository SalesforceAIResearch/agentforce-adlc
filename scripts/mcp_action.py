#!/usr/bin/env python3
"""Compute MCP action identity for Agent Script `.agent` files.

The Builder UI writes each MCP action with a hashed key (also used as `source`)
and a `target` URI. This module reproduces both.

Usage:
    from mcp_action import action_key, target_uri
    action_key("Slack", "slack_read_channel")
    target_uri("mcpTool", "MF_Slack_Mcp_User", "<ESO DeveloperName from the org>")
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Literal, Optional


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
