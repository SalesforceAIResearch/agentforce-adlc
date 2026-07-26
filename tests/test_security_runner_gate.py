"""Tests for the safety gate in skills/agentforce-test/scripts/security_runner.py

The runner must refuse to send adversarial payloads to a non-sandbox (or
unverifiable) org unless --allow-production is passed, and must default to
simulated (non-live) actions. These tests stub the `sf` CLI on PATH so the
Organization.IsSandbox query returns a controlled org type.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = str(
    Path(__file__).parent.parent
    / "skills" / "agentforce-test" / "scripts" / "security_runner.py"
)

# `sf` stub: emits the given IsSandbox JSON for the Organization query; for any
# other subcommand (preview start/send/end) it fails so the run stops cheaply
# after the gate. {status} controls the query's own success.
STUB_TEMPLATE = """#!/usr/bin/env bash
if printf '%s ' "$@" | grep -q "IsSandbox"; then
  echo '{query_json}'
  exit {query_exit}
fi
echo '{{"status":1,"result":{{}}}}'
exit 1
"""


def _write_stub(tmp_path, query_json, query_exit=0):
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "sf"
    stub.write_text(STUB_TEMPLATE.format(query_json=query_json, query_exit=query_exit))
    stub.chmod(0o755)
    return stub_dir


def _run(stub_dir, *args):
    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        [sys.executable, RUNNER, "--agent", "Foo", "--categories", "misinformation", *args],
        capture_output=True,
        text=True,
        env=env,
    )


PROD = '{"status":0,"result":{"records":[{"IsSandbox":false,"Name":"Prod","OrganizationType":"Enterprise Edition"}]}}'
SANDBOX = '{"status":0,"result":{"records":[{"IsSandbox":true,"Name":"Sbx","OrganizationType":"Developer Edition"}]}}'


class TestSandboxGate:
    def test_production_blocked_by_default(self, tmp_path):
        stub_dir = _write_stub(tmp_path, PROD)
        result = _run(stub_dir, "--org", "prod")
        assert result.returncode == 2
        assert "NOT a sandbox" in result.stderr

    def test_unknown_org_fails_closed(self, tmp_path):
        stub_dir = _write_stub(tmp_path, '{"status":1}', query_exit=1)
        result = _run(stub_dir, "--org", "mystery")
        assert result.returncode == 2
        assert "Cannot confirm org type" in result.stderr

    def test_allow_production_overrides(self, tmp_path):
        # With the override the gate passes; the run then fails later on preview
        # (stub returns failure), but that is not a gate rejection (exit != 2).
        stub_dir = _write_stub(tmp_path, PROD)
        result = _run(stub_dir, "--org", "prod", "--allow-production")
        assert result.returncode != 2
        assert "PRODUCTION" in result.stderr

    def test_sandbox_passes_gate_and_defaults_to_simulated(self, tmp_path):
        stub_dir = _write_stub(tmp_path, SANDBOX)
        result = _run(stub_dir, "--org", "sbx")
        assert "is a sandbox" in result.stderr
        assert "Live actions DISABLED" in result.stderr

    def test_live_actions_flag_warns(self, tmp_path):
        stub_dir = _write_stub(tmp_path, SANDBOX)
        result = _run(stub_dir, "--org", "sbx", "--live-actions")
        assert "LIVE actions ENABLED" in result.stderr

    def test_legacy_no_live_flag_accepted(self, tmp_path):
        # --no-live was the old flag; it must still parse (no-op now).
        stub_dir = _write_stub(tmp_path, SANDBOX)
        result = _run(stub_dir, "--org", "sbx", "--no-live")
        assert result.returncode != 2  # not a gate rejection
