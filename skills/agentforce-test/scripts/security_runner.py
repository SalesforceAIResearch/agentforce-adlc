#!/usr/bin/env python3
"""Run OWASP security tests against an Agentforce agent via sf agent preview.

Usage:
    python3 security_runner.py --org <alias> --agent <AgentName> [options]

Options:
    --org           Target org alias (required)
    --agent         Agent bundle name (required)
    --mode          quick|full (default: full)
    --categories    Comma-separated category filter (default: all)
    --output        Output file path (default: stdout)
    --project-dir   Directory to run sf commands from (default: cwd)
    --delay         Seconds between tests (default: 1)
    --no-live       Disable live actions (use mocked actions instead)

This script is an EXECUTOR only — it sends adversarial payloads and collects
responses. It does NOT judge verdicts. All evaluation is done by Claude Code
as LLM-as-judge after the runner completes (reading the output JSON).

Loads test payloads from ../assets/payloads/*.yaml, executes them via
sf agent preview start/send/end, and outputs a JSON array of
{test_id, category, severity, name, utterances_sent, response} objects.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "shared" / "sf-cli"))
from sf_cli import SfAgentCli  # noqa: E402


PAYLOADS_DIR = Path(__file__).resolve().parent.parent / "assets" / "payloads"

CATEGORY_FILES = {
    "prompt_injection": "prompt-injection.yaml",
    "sensitive_info": "sensitive-info-disclosure.yaml",
    "output_handling": "output-handling.yaml",
    "excessive_agency": "excessive-agency.yaml",
    "system_prompt_leakage": "system-prompt-leakage.yaml",
    "misinformation": "misinformation.yaml",
    "unbounded_consumption": "unbounded-consumption.yaml",
}

ALL_CATEGORIES = list(CATEGORY_FILES.keys())


def parse_yaml_tests(filepath):
    """Parse test payloads from a YAML file."""
    tests = []
    if not filepath.exists():
        print(f"WARNING: Payload file not found: {filepath}", file=sys.stderr)
        return tests

    data = yaml.safe_load(filepath.read_text())
    if not data or "tests" not in data:
        print(f"WARNING: No tests found in {filepath}", file=sys.stderr)
        return tests

    category = data.get("category", "")

    for entry in data["tests"]:
        turns = []
        for turn in entry.get("turns", []):
            content = turn.get("content", "")
            if content:
                turns.append(content)

        if not turns:
            print(f"WARNING: Test '{entry.get('id', '?')}' has no turns, skipping", file=sys.stderr)
            continue

        tests.append({
            "id": entry.get("id", ""),
            "category": category,
            "severity": entry.get("severity", "medium"),
            "name": entry.get("name", entry.get("id", "")),
            "technique": entry.get("technique", ""),
            "turns": turns,
        })

    return tests


def load_tests(categories, mode):
    """Load tests from payload YAML files, filtered by category and mode."""
    all_tests = []
    for cat in categories:
        filename = CATEGORY_FILES.get(cat)
        if not filename:
            print(f"WARNING: Unknown category '{cat}', skipping", file=sys.stderr)
            continue
        filepath = PAYLOADS_DIR / filename
        tests = parse_yaml_tests(filepath)
        all_tests.extend(tests)

    if mode == "quick":
        all_tests = [t for t in all_tests if t["severity"] in ("critical", "high")]

    return all_tests


def run_tests(tests, cli, agent, delay):
    """Execute all tests and return results array."""
    results = []
    total = len(tests)
    current_category = None

    print(f"Starting OWASP Security Assessment: {total} tests", file=sys.stderr)
    print(f"Agent: {agent} | Org: {cli.target_org}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    for i, test in enumerate(tests):
        cat = test["category"]
        if cat != current_category:
            current_category = cat
            print(f"\n[{cat.upper()}]", file=sys.stderr)

        print(f"  [{i+1}/{total}] {test['id']}: {test['name']}...", file=sys.stderr, end=" ", flush=True)

        result = cli.preview_start(agent)
        if not result.ok:
            results.append({
                "test_id": test["id"],
                "category": cat,
                "severity": test["severity"],
                "name": test["name"],
                "response": "",
                "verdict": "INCONCLUSIVE",
                "error": "session_start_failed",
            })
            print("SKIP (no session)", file=sys.stderr)
            time.sleep(delay)
            continue

        session_id = result.json().get("result", {}).get("sessionId")
        if not session_id:
            results.append({
                "test_id": test["id"],
                "category": cat,
                "severity": test["severity"],
                "name": test["name"],
                "response": "",
                "verdict": "INCONCLUSIVE",
                "error": "no_session_id",
            })
            print("SKIP (no session ID)", file=sys.stderr)
            time.sleep(delay)
            continue

        response = ""
        for turn in test["turns"]:
            send_result = cli.preview_send(session_id, turn, agent)
            if send_result.ok:
                msgs = send_result.json().get("result", {}).get("messages", [])
                if msgs:
                    response = msgs[-1].get("message", msgs[-1].get("content", ""))
            if len(test["turns"]) > 1:
                time.sleep(0.5)

        cli.preview_end(session_id)

        results.append({
            "test_id": test["id"],
            "category": cat,
            "severity": test["severity"],
            "name": test["name"],
            "technique": test.get("technique", ""),
            "utterances_sent": test["turns"],
            "response": response,
            "turns_sent": len(test["turns"]),
        })

        print(f"OK ({len(response)} chars)", file=sys.stderr)
        time.sleep(delay)

    return results


def main():
    parser = argparse.ArgumentParser(description="Run OWASP security tests against an Agentforce agent")
    parser.add_argument("--org", required=True, help="Target org alias")
    parser.add_argument("--agent", required=True, help="Agent bundle name (DeveloperName)")
    parser.add_argument("--mode", choices=["quick", "full"], default="full", help="Test mode (default: full)")
    parser.add_argument("--categories", help="Comma-separated category filter (default: all)")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    parser.add_argument("--project-dir", default=os.getcwd(), help="SF project directory (default: cwd)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between tests (default: 1)")
    parser.add_argument("--no-live", action="store_true", help="Disable live actions (use mocked actions)")

    args = parser.parse_args()

    categories = ALL_CATEGORIES
    if args.categories:
        categories = [c.strip() for c in args.categories.split(",")]

    tests = load_tests(categories, args.mode)
    if not tests:
        print("ERROR: No tests loaded. Check payload files and category names.", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(tests)} tests ({args.mode} mode)", file=sys.stderr)
    if not args.no_live:
        print("Live actions enabled (use --no-live to disable)", file=sys.stderr)

    cli = SfAgentCli(target_org=args.org, project_root=args.project_dir)
    cli.live_actions = not args.no_live

    results = run_tests(tests, cli, args.agent, args.delay)

    output_json = json.dumps(results, indent=2)
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output_json)
        print(f"\nResults saved to {args.output}", file=sys.stderr)
    else:
        print(output_json)

    errored = sum(1 for r in results if r.get("error"))
    collected = len(results) - errored
    print(f"\nDone: {collected} responses collected, {errored} errors out of {len(results)} tests", file=sys.stderr)
    print("Verdicts will be assigned by LLM-as-judge (Claude Code) on the output.", file=sys.stderr)


if __name__ == "__main__":
    main()
