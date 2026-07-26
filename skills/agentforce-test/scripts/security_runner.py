#!/usr/bin/env python3
"""Run security tests against an Agentforce agent via sf agent preview (Mode C2).

Usage:
    python3 security_runner.py --org <alias> --agent <AgentName> \
        --agent-file path/to/My.agent [options]

Options:
    --org             Target org alias (required)
    --agent           Agent bundle name (required)
    --agent-file      Path to the .agent file to generate agent-specific probes
                      FROM (strongly recommended — see below)
    --domain          Force a business domain (default: inferred from the file)
    --mode            quick|full (default: full)
    --categories      Comma-separated category filter (default: all)
    --no-static       Probe only with agent-specific cases
    --include-platform Also send Salesforce-platform-specific payloads (org
                      admin, SOQL, vendor advisories) — only meaningful for
                      agents that administer Salesforce
    --max-per-category Cap agent-specific cases per category (0 = no cap)
    --payloads-dir    Static payloads directory (default: ../assets/payloads)
    --output          Output file path (default: stdout)
    --project-dir     Directory to run sf commands from (default: cwd)
    --delay           Seconds between tests (default: 1)
    --live-actions    Enable LIVE action execution (default: OFF / simulated).
                      Adversarial payloads include bulk delete/update, policy
                      changes, and data export — live execution can mutate CRM
                      data. Requires an explicit, separate opt-in.
    --allow-production Permit running against a production org. By default the
                      runner blocks non-sandbox orgs.

With `--agent-file`, probes are generated from the agent's own script — its
actions, its `available when` authorization gates, its LLM-filled inputs, its
stated guardrails — and phrased in its business domain. That is what makes a
finding actionable: "the agent ran `process_return` without
`@variables.customer_verified`" names a line to fix, where "the agent answered a
generic jailbreak" does not. Without the flag only the generic library is sent.

This script is an EXECUTOR only — it sends adversarial payloads and collects
responses. It does NOT judge verdicts. All evaluation is done by Claude Code
as LLM-as-judge after the runner completes (reading the output JSON).

SAFETY: security payloads are adversarial. The runner refuses to run against a
production org unless --allow-production is passed, and it runs with live
actions DISABLED unless --live-actions is passed. Prefer a sandbox.

Cases are loaded through security_payloads.py — the same loader Mode C1 uses —
so the suite deployed to Testing Center and the suite probed live match. Output
is a JSON array of {test_id, category, severity, name, utterances_sent,
response} objects.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "shared" / "sf-cli"))
from sf_cli import SfAgentCli  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from security_payloads import (  # noqa: E402
    ALL_CATEGORIES, PAYLOADS_DIR, load_tests,
)


def user_turns_only(test):
    """The utterances to actually send live.

    Multi-turn cases also carry `role: agent` reference replies, which exist so
    Mode C1 can render Testing Center's alternating `conversationHistory`. In C2
    the real agent supplies its own replies, so sending those as user utterances
    would corrupt the attack chain — the agent would be fed a script of what it
    "already said".
    """
    return [t["content"] for t in test["turns"] if t["role"] == "user"]


def check_org_is_sandbox(cli):
    """Return (is_sandbox, label) by querying Organization.IsSandbox.

    Returns (None, reason) when the org type cannot be determined, so the caller
    can decide how to treat an unknown org (fail closed).
    """
    result = cli.query_soql("SELECT IsSandbox, Name, OrganizationType FROM Organization LIMIT 1")
    if not result.ok:
        return None, "could not query Organization (permissions or connection)"
    try:
        records = result.json().get("result", {}).get("records", [])
        if not records:
            return None, "Organization query returned no rows"
        rec = records[0]
        is_sandbox = bool(rec.get("IsSandbox"))
        label = f"{rec.get('Name', '?')} ({rec.get('OrganizationType', '?')})"
        return is_sandbox, label
    except (ValueError, KeyError) as exc:
        return None, f"could not parse Organization query ({exc})"


def run_tests(tests, cli, agent, delay):
    """Execute all tests and return results array."""
    results = []
    # A case with no user turn cannot be probed. Drop it here (loudly) rather
    # than mid-run, so the printed total matches what actually gets sent.
    sendable = []
    for test in tests:
        turns = user_turns_only(test)
        if not turns:
            print(f"WARNING: {test['id']} has no user turn to send, skipping",
                  file=sys.stderr)
            continue
        sendable.append((test, turns))
    tests = sendable
    total = len(tests)
    current_category = None

    print(f"Starting OWASP Security Assessment: {total} tests", file=sys.stderr)
    print(f"Agent: {agent} | Org: {cli.target_org}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    for i, (test, utterances) in enumerate(tests):
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
        for turn in utterances:
            send_result = cli.preview_send(session_id, turn, agent)
            if send_result.ok:
                msgs = send_result.json().get("result", {}).get("messages", [])
                if msgs:
                    response = msgs[-1].get("message", msgs[-1].get("content", ""))
            if len(utterances) > 1:
                time.sleep(0.5)

        cli.preview_end(session_id)

        results.append({
            "test_id": test["id"],
            "category": cat,
            "severity": test["severity"],
            "name": test["name"],
            "technique": test.get("technique", ""),
            # Carried through for the judge: `source` says whether this probe was
            # generated from the agent's script, `surface` names the exact
            # construct it targets, and `remediation` is the fix to report.
            "source": test.get("source", "static"),
            "surface": (test.get("meta") or {}).get("surface", ""),
            "remediation": test.get("remediation", ""),
            "evaluation_note": (test.get("meta") or {}).get("evaluation_note", ""),
            "utterances_sent": utterances,
            "response": response,
            "turns_sent": len(utterances),
        })

        print(f"OK ({len(response)} chars)", file=sys.stderr)
        time.sleep(delay)

    return results


def main():
    parser = argparse.ArgumentParser(description="Run security tests against an Agentforce agent")
    parser.add_argument("--org", required=True, help="Target org alias")
    parser.add_argument("--agent", required=True, help="Agent bundle name (DeveloperName)")
    parser.add_argument("--agent-file",
                        help="Path to the .agent file to generate agent-specific probes FROM "
                             "(strongly recommended; without it only generic probes are sent)")
    parser.add_argument("--domain", default="",
                        help="Force a business domain (default: inferred from the .agent file)")
    parser.add_argument("--mode", choices=["quick", "full"], default="full", help="Test mode (default: full)")
    parser.add_argument("--categories", help="Comma-separated category filter (default: all)")
    parser.add_argument("--no-static", action="store_true",
                        help="Send only agent-specific probes (requires --agent-file)")
    parser.add_argument("--include-platform", action="store_true",
                        help="Also send Salesforce-platform-specific payloads (org admin, SOQL, "
                             "vendor advisories). Only meaningful for agents that administer Salesforce.")
    parser.add_argument("--max-per-category", type=int, default=0,
                        help="Cap agent-specific probes per category (0 = no cap)")
    parser.add_argument("--payloads-dir", default=str(PAYLOADS_DIR),
                        help="Static payloads directory (default: ../assets/payloads)")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    parser.add_argument("--project-dir", default=os.getcwd(), help="SF project directory (default: cwd)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between tests (default: 1)")
    parser.add_argument("--live-actions", action="store_true",
                        help="Enable LIVE action execution (default: OFF/simulated). Can mutate CRM data.")
    parser.add_argument("--allow-production", action="store_true",
                        help="Permit running against a non-sandbox (production) org. Blocked by default.")
    # Back-compat: --no-live was the old flag when live was the (unsafe) default.
    # Live is now off by default, so --no-live is a harmless no-op we still accept.
    parser.add_argument("--no-live", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    categories = ALL_CATEGORIES
    if args.categories:
        categories = [c.strip() for c in args.categories.split(",")]

    agent_file = Path(args.agent_file) if args.agent_file else None
    if agent_file and not agent_file.exists():
        print(f"ERROR: .agent file not found: {agent_file}", file=sys.stderr)
        sys.exit(1)
    if args.no_static and not agent_file:
        print("ERROR: --no-static removes the only source of tests when --agent-file "
              "is absent. Pass --agent-file or drop --no-static.", file=sys.stderr)
        sys.exit(1)

    tests = load_tests(
        categories=categories, mode=args.mode, agent_file=agent_file,
        domain=args.domain, include_platform=args.include_platform,
        include_static=not args.no_static, payloads_dir=Path(args.payloads_dir),
        max_per_category=args.max_per_category,
    )
    if not tests:
        print("ERROR: No tests loaded. Check payload files and category names.", file=sys.stderr)
        sys.exit(1)

    cli = SfAgentCli(target_org=args.org, project_root=args.project_dir)

    # ─── Safety gate: refuse production; default to simulated actions ─────────
    is_sandbox, org_label = check_org_is_sandbox(cli)
    if is_sandbox is None:
        print(f"ERROR: Cannot confirm org type ({org_label}). Refusing to send "
              f"adversarial payloads to an unverified org. Use --allow-production "
              f"to override once you have confirmed the target.", file=sys.stderr)
        if not args.allow_production:
            sys.exit(2)
        print("WARNING: --allow-production set — proceeding against an UNVERIFIED org.", file=sys.stderr)
    elif not is_sandbox:
        if not args.allow_production:
            print(f"ERROR: Target org {org_label} is NOT a sandbox. Security payloads "
                  f"are adversarial (bulk delete/update, policy changes, data export) "
                  f"and Salesforce advises running Testing Center only in sandboxes. "
                  f"Refusing to proceed. Re-run with --allow-production to override.",
                  file=sys.stderr)
            sys.exit(2)
        print(f"WARNING: --allow-production set — running against PRODUCTION org {org_label}.", file=sys.stderr)
    else:
        print(f"Org {org_label} is a sandbox — OK.", file=sys.stderr)

    cli.live_actions = args.live_actions
    grounded = sum(1 for t in tests if t["source"] == "grounded")
    print(f"Loaded {len(tests)} tests ({args.mode} mode) — "
          f"{grounded} agent-specific, {len(tests) - grounded} generic", file=sys.stderr)
    if args.live_actions:
        print("WARNING: LIVE actions ENABLED — adversarial payloads may mutate CRM data.", file=sys.stderr)
    else:
        print("Live actions DISABLED (simulated). Pass --live-actions to enable (sandbox only).", file=sys.stderr)

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
