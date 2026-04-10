#!/usr/bin/env python3
"""SessionStart hook: preflight checks for agentforce-adlc.

Checks:
1. sf CLI is installed and accessible
2. Connected org exists (default or specified)
3. sfdx-project.json exists in current directory
"""

import json
import shutil
import subprocess
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


def check_sf_cli() -> tuple[bool, str]:
    """Check if sf CLI is installed."""
    if not shutil.which("sf"):
        return False, "sf CLI not found. Install: https://developer.salesforce.com/tools/salesforcecli"
    try:
        result = subprocess.run(["sf", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0]
            return True, f"sf CLI: {version}"
    except Exception:
        pass
    return False, "sf CLI found but version check failed"


def check_connected_org() -> tuple[bool, str]:
    """Check connected orgs and list them."""
    try:
        result = subprocess.run(
            ["sf", "org", "list", "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            orgs = data.get("result", {})
            # Collect all org types
            all_orgs = []
            for org_type in ("nonScratchOrgs", "scratchOrgs", "sandboxes", "devHubs", "other"):
                for org in orgs.get(org_type, []):
                    alias = org.get("alias", "")
                    username = org.get("username", "unknown")
                    is_default = org.get("isDefaultUsername", False)
                    org_label = f"{alias or username}"
                    if is_default:
                        org_label += " (default)"
                    all_orgs.append(org_label)
            if all_orgs:
                org_list = ", ".join(all_orgs[:5])
                if len(all_orgs) > 5:
                    org_list += f" (+{len(all_orgs) - 5} more)"
                return True, f"Connected orgs: {org_list}"
    except Exception:
        pass
    # Fallback to single org display
    try:
        result = subprocess.run(
            ["sf", "org", "display", "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            username = data.get("result", {}).get("username", "unknown")
            return True, f"Connected org: {username}"
    except Exception:
        pass
    return False, "No orgs connected. Run: sf org login web --alias <name>"


def check_project_json() -> tuple[bool, str]:
    """Check if sfdx-project.json exists."""
    if Path("sfdx-project.json").exists():
        return True, "sfdx-project.json found"
    return False, "sfdx-project.json not found in current directory"


def detect_adlc_project() -> tuple[bool, str]:
    """Detect if this is an ADLC project and hint at available skills."""
    indicators = []
    if Path("sfdx-project.json").exists():
        indicators.append("sfdx-project.json")
    bundles_dir = Path("force-app/main/default/aiAuthoringBundles")
    if bundles_dir.exists():
        agents = [d.name for d in bundles_dir.iterdir() if d.is_dir()]
        indicators.append(f"aiAuthoringBundles ({len(agents)} agent(s))")
    agent_files = list(Path(".").rglob("*.agent"))
    if agent_files and not bundles_dir.exists():
        indicators.append(f"{len(agent_files)} .agent file(s)")

    if indicators:
        hint = (
            f"ADLC project detected ({', '.join(indicators)}). "
            "Use /adlc-author to build agents, /adlc-test to test, "
            "/adlc-deploy to deploy. All agent requests should use ADLC skills."
        )
        return True, hint
    return False, ""


def main():
    """Run preflight checks and report status."""
    checks = [
        ("SF CLI", check_sf_cli()),
        ("Org Connection", check_connected_org()),
        ("Project Config", check_project_json()),
    ]

    messages = []
    all_ok = True
    for name, (ok, msg) in checks:
        status = "OK" if ok else "MISSING"
        messages.append(f"  [{status}] {name}: {msg}")
        if not ok:
            all_ok = False

    # Add ADLC project detection hint
    is_adlc, adlc_hint = detect_adlc_project()
    if is_adlc:
        messages.append(f"  [HINT] {adlc_hint}")

    context = "ADLC Preflight Checks:\n" + "\n".join(messages)
    if not all_ok:
        context += "\n\n  Some checks failed. Skills may not work correctly."

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
