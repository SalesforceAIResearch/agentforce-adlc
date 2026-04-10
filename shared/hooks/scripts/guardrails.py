#!/usr/bin/env python3
"""PreToolUse Guardrails Hook for agentforce-adlc.

BLOCKING + AUTO-FIX guardrails that run BEFORE dangerous operations execute.

Severity levels:
- CRITICAL (BLOCK): DELETE/UPDATE without WHERE, hardcoded credentials, force push
- HIGH (AUTO-FIX): Reserved for future patterns
- MEDIUM (WARN): Hardcoded IDs, deprecated commands, old API versions

ADLC-specific patterns:
- Block sf agent publish without --json
- Block sf project deploy start on .agent files (must use sf agent publish)
- Block DELETE FROM / UPDATE SET without WHERE
"""

import json
import re
import sys
from pathlib import Path

try:
    from stdin_utils import read_stdin_safe
except ImportError:
    def read_stdin_safe(timeout_seconds=0.1):
        if sys.stdin.isatty():
            return {}
        try:
            return json.load(sys.stdin)
        except Exception:
            return {}


CRITICAL_PATTERNS = [
    {
        "pattern": r"DELETE\s+FROM\s+\w+\s*(;|$|--)",
        "message": "DELETE without WHERE clause — will delete ALL records",
        "suggestion": "Add WHERE clause: DELETE FROM Object WHERE Id = 'xxx'",
    },
    {
        "pattern": r"UPDATE\s+\w+\s+SET\s+(?!.*WHERE)",
        "message": "UPDATE without WHERE clause — will update ALL records",
        "suggestion": "Add WHERE clause: UPDATE Object SET Field = 'val' WHERE Id = 'xxx'",
    },
    {
        "pattern": r"(?:api[_-]?key|secret|password|token)\s*[=:]\s*['\"][a-zA-Z0-9]{16,}['\"]",
        "message": "Hardcoded credentials detected",
        "suggestion": "Use environment variables instead",
    },
    {
        "pattern": r"sf\s+(?:project\s+)?deploy\s+(?:start|preview)?.*--target-org\s+(?:prod|production)[^-]*$",
        "message": "Production deployment without --dry-run",
        "suggestion": "Add --dry-run flag for validation first",
    },
    {
        "pattern": r"git\s+push\s+(?:--force|-f)\s+(?:origin\s+)?(?:main|master)",
        "message": "Force push to main/master",
        "suggestion": "Use --force-with-lease or push to a branch",
    },
    {
        "pattern": r"DROP\s+(?:TABLE|DATABASE)\s+",
        "message": "DROP TABLE/DATABASE detected",
        "suggestion": "Use DELETE with backup instead",
    },
    # ADLC-specific: block sf agent publish without --json
    {
        "pattern": r"sf\s+agent\s+publish\s+(?!.*--json)",
        "message": "sf agent publish without --json — output may be unparseable",
        "suggestion": "Add --json flag: sf agent publish authoring-bundle --api-name X --json",
    },
    # ADLC-specific: block deploying .agent files via sf project deploy
    {
        "pattern": r"sf\s+project\s+deploy\s+start\s+.*\.agent\b",
        "message": "Cannot deploy .agent files with sf project deploy — use sf agent publish",
        "suggestion": "Use: sf agent publish authoring-bundle --api-name <Name> --target-org <org> --json",
    },
]

MEDIUM_PATTERNS = [
    {
        "pattern": r"['\"](?:001|003|005|006|00D|00e|500|a0[0-9A-Z])[a-zA-Z0-9]{12,15}['\"]",
        "message": "Hardcoded Salesforce ID detected — IDs vary between environments",
        "suggestion": "Use dynamic queries or Named Credentials",
    },
    {
        "pattern": r"\bsfdx\b",
        "message": "Deprecated SFDX command detected",
        "suggestion": "Use 'sf' commands instead of 'sfdx'",
    },
    {
        "pattern": r"--api-version\s+(?:[1-4]\d|5[0-5])\b",
        "message": "Old API version detected (< v56)",
        "suggestion": "Use API v66+ for latest features",
    },
    # Warn when deploying or publishing to production-named orgs
    {
        "pattern": r"sf\s+(?:agent\s+publish|project\s+deploy)\s+.*(?:--target-org|-o)\s+(?:prod|production|live)\b",
        "message": "Deploying to production-named org — verify this is intentional",
        "suggestion": "Use a sandbox or scratch org for development. If this is production, ensure safety review has been completed.",
    },
]


def is_output_only_command(command: str) -> bool:
    """Check if command is just outputting text (not executing DML)."""
    patterns = [r'^\s*echo\s+', r'^\s*printf\s+', r'^\s*cat\s*<<', r'^\s*print\s+']
    return any(re.search(p, command, re.IGNORECASE) for p in patterns)


def is_sf_context(command: str) -> bool:
    """Check if command is Salesforce-related."""
    indicators = [
        r'\bsf\b', r'\bsfdx\b', r'SELECT\s+', r'DELETE\s+FROM', r'UPDATE\s+\w+\s+SET',
        r'force-app', r'\.cls\b', r'\.agent\b', r'\.flow-meta',
        r'--target-org', r'apex\s+run', r'data\s+query',
    ]
    return any(re.search(p, command, re.IGNORECASE) for p in indicators)


def main():
    input_data = read_stdin_safe(timeout_seconds=0.1)
    if not input_data:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}))
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if tool_name != "Bash":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}))
        sys.exit(0)

    command = tool_input.get("command", "")
    if not command or not is_sf_context(command) or is_output_only_command(command):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}))
        sys.exit(0)

    # Check CRITICAL patterns (BLOCK)
    for rule in CRITICAL_PATTERNS:
        if re.search(rule["pattern"], command, re.IGNORECASE):
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": rule["message"],
                    "additionalContext": f"BLOCKED: {rule['message']}\nSuggestion: {rule['suggestion']}",
                }
            }
            print(json.dumps(output))
            sys.exit(0)

    # Check MEDIUM patterns (WARN)
    warnings = []
    for rule in MEDIUM_PATTERNS:
        if re.search(rule["pattern"], command, re.IGNORECASE):
            warnings.append(f"Warning: {rule['message']} — {rule['suggestion']}")

    if warnings:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "additionalContext": "\n".join(warnings),
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
