"""Thin wrappers around the `sf` CLI for Apex execution and REST calls."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

STDM_RESULT_MARKER = "DEBUG|STDM_RESULT:"


class SfCliError(RuntimeError):
    def __init__(self, message: str, *, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


def _format_component_failures(payload: dict) -> str | None:
    """Extract a readable error from `sf project deploy start --json` failures.

    On deploy failures the top-level `message` is generic ("unknown error"); the
    actual error text lives in `result.details.componentFailures[*].problem`.
    Returns a concatenated message like
    "<fullName>: <problem>; <fullName>: <problem>" or None if no component
    failures are present (so the caller falls back to other fields).
    """
    if not isinstance(payload, dict):
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    details = result.get("details")
    if not isinstance(details, dict):
        return None
    failures = details.get("componentFailures")
    if not isinstance(failures, list) or not failures:
        return None
    parts: list[str] = []
    for f in failures:
        if not isinstance(f, dict):
            continue
        problem = f.get("problem") or f.get("error") or "unknown component failure"
        full_name = f.get("fullName") or f.get("componentType") or "?"
        parts.append(f"{full_name}: {problem}")
    return "; ".join(parts) if parts else None


def _run(cmd: list[str], *, input_text: str | None = None, cwd: str | None = None) -> dict:
    """Run an sf command that supports --json and return the parsed JSON payload.

    Raises SfCliError if the command exits non-zero or its JSON shows status != 0.
    """
    proc = subprocess.run(
        cmd, capture_output=True, text=True, input=input_text, check=False, cwd=cwd,
    )
    if proc.returncode != 0:
        # sf usually emits JSON even on error when --json is set.
        try:
            payload = json.loads(proc.stdout)
            msg = (
                _format_component_failures(payload)
                or payload.get("message")
                or payload.get("name")
                or proc.stderr.strip()
                or "unknown error"
            )
        except json.JSONDecodeError:
            msg = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
        raise SfCliError(f"sf CLI failed: {msg}", stdout=proc.stdout, stderr=proc.stderr)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise SfCliError(f"sf CLI returned non-JSON output: {e}",
                         stdout=proc.stdout, stderr=proc.stderr) from e


def run_apex(org_alias: str, apex_body: str) -> str:
    """Execute anonymous Apex and return the concatenated debug log."""
    with tempfile.NamedTemporaryFile("w", suffix=".apex", delete=False) as tf:
        tf.write(apex_body)
        tf.flush()
        path = tf.name
    try:
        payload = _run([
            "sf", "apex", "run",
            "--file", path,
            "-o", org_alias,
            "--json",
        ])
    finally:
        Path(path).unlink(missing_ok=True)

    result = payload.get("result") or {}
    logs = result.get("logs", "") or ""
    if not result.get("success", True):
        exception_msg = result.get("exceptionMessage") or "anonymous Apex failed"
        raise SfCliError(f"Apex execution failed: {exception_msg}",
                         stdout=json.dumps(payload))
    return logs


def extract_stdm_result(logs: str) -> str:
    """Parse the AgentforceOptimizeService debug-log payload (DEBUG|STDM_RESULT:<json>).

    The STDM_RESULT marker appears after USER_DEBUG log lines. We find the DEBUG|STDM_RESULT:
    prefix (not plain STDM_RESULT: which also appears in the source-echo portion of the log),
    take everything after it on that line.
    """
    idx = logs.find(STDM_RESULT_MARKER)
    if idx == -1:
        raise SfCliError(f"STDM_RESULT marker not found in Apex debug log", stdout=logs)
    tail = logs[idx + len(STDM_RESULT_MARKER):]
    # The payload continues until the next newline (it's a single-line JSON blob).
    return tail.split("\n", 1)[0].strip()


def api_request(
    org_alias: str,
    path: str,
    *,
    method: str = "GET",
    body: Any = None,
) -> dict | list:
    """POST/GET to a Salesforce REST endpoint via `sf api request rest`.

    Body is passed via a temp file (`--body @path`) because the beta `sf api request rest`
    treats bare `--body <text>` as literal inline content — only `@file` or `-` for stdin
    are supported. stdin (`-`) is problematic because the sf CLI's TTY detection prints a
    banner on stderr when a pipe is used; file path is more reliable.
    """
    cmd = ["sf", "api", "request", "rest", path, "--method", method, "-o", org_alias]
    body_file: str | None = None
    if body is not None:
        body_text = body if isinstance(body, str) else json.dumps(body)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write(body_text)
            body_file = tf.name
        cmd.extend(["--body", f"@{body_file}"])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    finally:
        if body_file:
            Path(body_file).unlink(missing_ok=True)

    if proc.returncode != 0:
        raise SfCliError(
            f"sf api request rest failed: {_format_api_error(proc.stdout, proc.stderr)}",
            stdout=proc.stdout, stderr=proc.stderr,
        )
    # `sf api request rest` is a beta command that doesn't accept --json; the response body
    # is written to stdout as-is. Extract the JSON payload (it may be preceded by warning
    # banners on older CLI versions).
    return _extract_json_payload(proc.stdout, proc.stderr)


def _format_api_error(stdout: str, stderr: str) -> str:
    """Build a human-readable failure detail from a non-zero `sf api request rest`.

    The beta command writes API errors (`errorCode`/`message`) to STDOUT while STDERR
    carries only CLI/beta warnings (update banner, beta notice). If we surfaced STDERR
    the real cause would be hidden behind the banner — so we parse STDOUT first and only
    fall back to STDERR when STDOUT has nothing useful.

    Recognizes both shapes the endpoint returns:
      - a list wrapping one error:  [{"errorCode": "...", "message": "..."}]
      - a bare error object:        {"errorCode": "...", "message": "..."}
    """
    stripped = (stdout or "").strip()
    if stripped:
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        errors = []
        if isinstance(payload, list):
            errors = [e for e in payload if isinstance(e, dict) and ("errorCode" in e or "message" in e)]
        elif isinstance(payload, dict) and ("errorCode" in payload or "message" in payload):
            errors = [payload]
        if errors:
            parts = []
            for e in errors:
                code = e.get("errorCode")
                message = e.get("message")
                parts.append(f"{code}: {message}" if code and message else (message or code or ""))
            return "; ".join(p for p in parts if p)
        # Non-error JSON or plain text on stdout — surface it verbatim (truncated).
        return stripped[:500]
    return (stderr or "").strip()[:500] or "no output"


def _extract_json_payload(stdout: str, stderr: str) -> dict | list:
    """Find the first valid JSON object or array in stdout. Tolerates leading banners."""
    stripped = stdout.strip()
    if not stripped:
        raise SfCliError("empty response", stdout=stdout, stderr=stderr)
    # Fast path: clean JSON.
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # Fall back: find the first `{` or `[` and try progressively.
    for opener in ("[", "{"):
        idx = stripped.find(opener)
        if idx >= 0:
            candidate = stripped[idx:]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    raise SfCliError(f"sf api returned non-JSON: {stripped[:200]!r}",
                     stdout=stdout, stderr=stderr)


def soql_query(org_alias: str, query: str, *, use_tooling_api: bool = False) -> list[dict]:
    """Run a SOQL query via `sf data query` and return records."""
    cmd = ["sf", "data", "query", "-q", query, "-o", org_alias, "--json"]
    if use_tooling_api:
        cmd.append("--use-tooling-api")
    payload = _run(cmd)
    return (payload.get("result") or {}).get("records", []) or []


def list_metadata(org_alias: str, metadata_type: str) -> list[dict]:
    """List metadata members of a given type via `sf org list metadata`.

    Used for entities that aren't SOQL-queryable (e.g. GenAiPromptTemplate).
    Returns a list of {fullName, ...} records; an empty list means "none deployed".
    """
    cmd = [
        "sf", "org", "list", "metadata",
        "--metadata-type", metadata_type,
        "-o", org_alias,
        "--json",
    ]
    payload = _run(cmd)
    result = payload.get("result")
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("records", []) or []
    return []


def project_deploy(org_alias: str, source_dir: str, *, wait: int = 10,
                   project_root: str | None = None) -> dict:
    """Deploy metadata from a source directory.

    `project_root` must point to a directory containing sfdx-project.json. `sf project deploy
    start` only works when invoked with cwd inside a DX project, so callers pass the project
    root explicitly.
    """
    cmd = [
        "sf", "project", "deploy", "start",
        "--source-dir", source_dir,
        "-o", org_alias,
        "--wait", str(wait),
        "--json",
    ]
    return _run(cmd, cwd=project_root)


def project_retrieve(org_alias: str, source_dir: str, *, project_root: str | None = None) -> dict:
    """Retrieve metadata into a source directory. See project_deploy for cwd rules."""
    cmd = [
        "sf", "project", "retrieve", "start",
        "--source-dir", source_dir,
        "-o", org_alias,
        "--json",
    ]
    return _run(cmd, cwd=project_root)
