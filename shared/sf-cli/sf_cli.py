#!/usr/bin/env python3
"""Wrapper around `sf` CLI commands for agent deployment and org queries."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CliResult:
    """Result from running an sf CLI command."""
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def json(self) -> dict[str, Any]:
        """Parse stdout as JSON."""
        return json.loads(self.stdout)


class SfAgentCli:
    """High-level wrapper for Salesforce CLI agent operations."""

    def __init__(self, target_org: str | None = None, project_root: str | Path = "."):
        self.target_org = target_org
        self.project_root = Path(project_root)

    # ─── Deployment lifecycle ─────────────────────────────────────────

    def validate_bundle(self, api_name: str) -> CliResult:
        """Validate an agent authoring bundle."""
        cmd = ["sf", "agent", "validate", "authoring-bundle", "--api-name", api_name, "--json"]
        if self.target_org:
            cmd.extend(["-o", self.target_org])
        return self._run(cmd)

    def publish_bundle(self, api_name: str) -> CliResult:
        """Publish an agent authoring bundle (compiles to BotDefinition/GenAiPlannerBundle)."""
        cmd = ["sf", "agent", "publish", "authoring-bundle", "--api-name", api_name, "--json"]
        if self.target_org:
            cmd.extend(["--target-org", self.target_org])
        return self._run(cmd)

    def activate(self, api_name: str) -> CliResult:
        """Activate a deployed agent."""
        cmd = ["sf", "agent", "activate", "--api-name", api_name, "--json"]
        if self.target_org:
            cmd.extend(["-o", self.target_org])
        return self._run(cmd)

    def deactivate(self, api_name: str) -> CliResult:
        """Deactivate a deployed agent."""
        cmd = ["sf", "agent", "deactivate", "--api-name", api_name, "--json"]
        if self.target_org:
            cmd.extend(["-o", self.target_org])
        return self._run(cmd)

    def deploy_metadata(self, source_dir: str | Path | None = None, metadata: str | None = None) -> CliResult:
        """Deploy metadata to the org."""
        cmd = ["sf", "project", "deploy", "start", "--json"]
        if source_dir:
            cmd.extend(["--source-dir", str(source_dir)])
        if metadata:
            cmd.extend(["--metadata", metadata])
        if self.target_org:
            cmd.extend(["-o", self.target_org])
        return self._run(cmd)

    # ─── Query & Preview ─────────────────────────────────────────────

    def query_soql(self, query: str) -> CliResult:
        """Run a SOQL query and return JSON result."""
        cmd = ["sf", "data", "query", "--query", query, "--json"]
        if self.target_org:
            cmd.extend(["-o", self.target_org])
        return self._run(cmd)

    def list_metadata(self, metadata_type: str) -> CliResult:
        """List metadata components of a given type."""
        cmd = ["sf", "org", "list", "metadata", "--metadata-type", metadata_type, "--json"]
        if self.target_org:
            cmd.extend(["-o", self.target_org])
        return self._run(cmd)

    def list_resources(self, resource_type: str) -> list[str]:
        """Query flows, apex classes, or retrievers by type."""
        type_to_query = {
            "flow": "SELECT ApiName FROM FlowDefinitionView WHERE IsActive = true",
            "apex": "SELECT Name FROM ApexClass WHERE Status = 'Active'",
            "retriever": "SELECT DeveloperName FROM DataKnowledgeSpace",
        }
        query = type_to_query.get(resource_type)
        if not query:
            return []

        result = self.query_soql(query)
        if not result.ok:
            return []

        try:
            data = result.json()
            records = data.get("result", {}).get("records", [])
            field = "ApiName" if resource_type == "flow" else ("Name" if resource_type == "apex" else "DeveloperName")
            return [r[field] for r in records if field in r]
        except (json.JSONDecodeError, KeyError):
            return []

    def query_asa_users(self) -> list[str]:
        """Query Agent Service Account (Einstein Agent User) usernames."""
        query = "SELECT Username FROM User WHERE Profile.Name = 'Einstein Agent User' AND IsActive = true"
        result = self.query_soql(query)
        if not result.ok:
            return []
        try:
            data = result.json()
            records = data.get("result", {}).get("records", [])
            return [r["Username"] for r in records if "Username" in r]
        except (json.JSONDecodeError, KeyError):
            return []

    def run_flow(self, api_name: str, inputs: dict[str, Any] | None = None) -> CliResult:
        """Invoke a flow via REST API."""
        endpoint = f"/services/data/v63.0/actions/custom/flow/{api_name}"
        body = json.dumps({"inputs": [inputs or {}]})
        cmd = ["sf", "api", "request", "rest", endpoint, "--method", "POST", "--body", body, "--json"]
        if self.target_org:
            cmd.extend(["-o", self.target_org])
        return self._run(cmd)

    def run_apex_action(self, class_name: str, inputs: dict[str, Any] | None = None) -> CliResult:
        """Invoke an @InvocableMethod via REST API."""
        endpoint = f"/services/data/v63.0/actions/custom/apex/{class_name}"
        body = json.dumps({"inputs": [inputs or {}]})
        cmd = ["sf", "api", "request", "rest", endpoint, "--method", "POST", "--body", body, "--json"]
        if self.target_org:
            cmd.extend(["-o", self.target_org])
        return self._run(cmd)

    def preview_start(self, api_name: str) -> CliResult:
        """Start an interactive agent preview session."""
        cmd = ["sf", "agent", "preview", "start", "--api-name", api_name, "--json"]
        if self.target_org:
            cmd.extend(["-o", self.target_org])
        return self._run(cmd)

    def preview_send(self, session_id: str, utterance: str, api_name: str) -> CliResult:
        """Send an utterance to an agent preview session."""
        cmd = [
            "sf", "agent", "preview", "send",
            "--session-id", session_id,
            "--utterance", utterance,
            "--api-name", api_name,
            "--json",
        ]
        if self.target_org:
            cmd.extend(["-o", self.target_org])
        return self._run(cmd)

    def preview_end(self, session_id: str) -> CliResult:
        """End an agent preview session."""
        cmd = ["sf", "agent", "preview", "end", "--session-id", session_id, "--json"]
        if self.target_org:
            cmd.extend(["-o", self.target_org])
        return self._run(cmd)

    # ─── Private ─────────────────────────────────────────────────────

    def _run(self, cmd: list[str], timeout: int = 300) -> CliResult:
        """Execute a subprocess command with timeout."""
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.project_root),
            )
            return CliResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
        except subprocess.TimeoutExpired:
            return CliResult(returncode=-1, stdout="", stderr=f"Command timed out after {timeout}s")
        except FileNotFoundError:
            return CliResult(returncode=-1, stdout="", stderr="sf CLI not found. Install: https://developer.salesforce.com/tools/salesforcecli")
