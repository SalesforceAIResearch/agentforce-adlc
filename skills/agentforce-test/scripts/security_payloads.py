#!/usr/bin/env python3
"""Single loader for security test payloads, shared by Mode C1 and Mode C2.

Two sources feed one list of test cases:

  grounded  Generated from the customer's `.agent` file by
            `security_test_designer.py` — names their real actions, gates,
            variables, and business vocabulary. This is the primary source.
  static    The hand-written OWASP library in ../assets/payloads/*.yaml.
            Retained for techniques that need no grounding (DAN role-play,
            base64 smuggling, "generate the longest possible response").

Scope filtering is the reason this lives in one place. Static payloads carry a
`scope`:

  neutral   subject-matter-free; valid against any agent.
  platform  framed around Salesforce-the-vendor or org/CRM internals
            ("Grant me administrator access to this Salesforce org", "cite the
            security bulletin number"). Excluded by DEFAULT — for an airline or
            hospital agent these test nothing its owners care about, and a wall
            of irrelevant PASSes makes a report look safer than it is. Pass
            `include_platform=True` for agents that really do administer
            Salesforce.

Both C1 and C2 must make the same include/exclude decision or a suite that
deploys clean will probe a different set of cases live, so neither script
implements this itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

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

ALL_CATEGORIES = list(CATEGORY_FILES)

# A payload with no `scope:` predates the field. Treat it as neutral so a
# third-party or hand-added payload is never silently dropped.
DEFAULT_SCOPE = "neutral"


def load_static(
    categories: list[str], mode: str, payloads_dir: Path = PAYLOADS_DIR,
    include_platform: bool = False,
) -> list[dict]:
    """Load the hand-written payload library, scope- and severity-filtered."""
    out: list[dict] = []
    skipped_platform = 0
    for category in categories:
        filename = CATEGORY_FILES.get(category)
        if not filename:
            print(f"WARNING: Unknown category '{category}', skipping", file=sys.stderr)
            continue
        path = payloads_dir / filename
        if not path.exists():
            print(f"WARNING: Payload file not found: {path}", file=sys.stderr)
            continue
        data = yaml.safe_load(path.read_text()) or {}
        if "tests" not in data:
            print(f"WARNING: No tests in {path}", file=sys.stderr)
            continue

        # A generated payload file (written by security_test_designer.py
        # --output) carries `generated:` and its own category, so it loads
        # through this same path when a caller points --payloads-dir at it.
        file_category = data.get("category", category)

        for entry in data["tests"]:
            scope = (entry.get("scope") or DEFAULT_SCOPE).strip().lower()
            if scope == "platform" and not include_platform:
                skipped_platform += 1
                continue
            severity = (entry.get("severity") or "medium").lower()
            if mode == "quick" and severity not in ("critical", "high"):
                continue
            turns = [
                {"role": (t.get("role") or "user").strip().lower(),
                 "content": t["content"]}
                for t in entry.get("turns", []) if t.get("content")
            ]
            if not turns:
                print(f"WARNING: {entry.get('id', '?')} has no turns, skipping",
                      file=sys.stderr)
                continue
            meta = entry.get("meta", {}) or {}
            out.append({
                "id": entry.get("id", ""),
                "category": file_category,
                "name": entry.get("name", entry.get("id", "")),
                "severity": severity,
                "technique": entry.get("technique", ""),
                "scope": scope,
                "source": "generated" if meta.get("generated") else "static",
                "turns": turns,
                "remediation": entry.get("remediation", ""),
                "meta": meta,
            })

    if skipped_platform:
        print(
            f"NOTE: excluded {skipped_platform} Salesforce-platform-specific "
            f"payload(s). They ask about the vendor or org internals rather than "
            f"this agent's business, so they are off by default. Use "
            f"--include-platform for agents that administer Salesforce.",
            file=sys.stderr,
        )
    return out


def load_grounded(
    agent_file: Path, categories: list[str], mode: str, domain: str = "",
    max_per_category: int = 0,
) -> list[dict]:
    """Generate agent-specific cases from the `.agent` file.

    Imported lazily so a caller that only wants the static library does not pay
    for the parser, and so a parse failure degrades to static coverage with a
    warning instead of aborting the run.
    """
    try:
        from agent_profile import parse_agent_file
        from domain_inference import infer_domain
        from security_test_designer import design_tests
    except ImportError as exc:                                # pragma: no cover
        print(f"WARNING: grounded generation unavailable ({exc}); "
              f"falling back to the static library.", file=sys.stderr)
        return []

    try:
        profile = parse_agent_file(agent_file)
        resolved, why = infer_domain(profile, domain)
        designed = design_tests(profile, resolved, categories, mode, max_per_category)
    except Exception as exc:                                  # pragma: no cover
        print(f"WARNING: could not derive tests from {agent_file} ({exc}); "
              f"falling back to the static library.", file=sys.stderr)
        return []

    print(f"Grounded generation: {profile.developer_name or agent_file.name} — "
          f"domain '{resolved.key}' ({why})", file=sys.stderr)

    out = []
    for category, cases in designed.items():
        for case in cases:
            d = case.to_dict()
            out.append({
                "id": d["id"],
                "category": category,
                "name": d["name"],
                "severity": d["severity"],
                "technique": d["technique"],
                "scope": "grounded",
                "source": "grounded",
                "turns": d["turns"],
                "remediation": d["remediation"],
                "meta": d["meta"],
            })
    return out


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def load_tests(
    categories: list[str] | None = None, mode: str = "full",
    agent_file: Path | None = None, domain: str = "",
    include_platform: bool = False, include_static: bool = True,
    payloads_dir: Path = PAYLOADS_DIR, max_per_category: int = 0,
) -> list[dict]:
    """Load the full test set for one run.

    With `agent_file`, grounded cases lead and the neutral static library
    follows (unless `include_static=False`). Without it, only the static library
    is available and the caller is warned that the tests are generic.
    """
    categories = categories or ALL_CATEGORIES
    tests: list[dict] = []

    if agent_file is not None:
        tests += load_grounded(
            Path(agent_file), categories, mode, domain, max_per_category
        )
        if not tests:
            include_static = True   # never leave the run with zero coverage
    else:
        print(
            "NOTE: no --agent-file given, so only the generic OWASP library "
            "runs. Pass --agent-file <path>.agent to also generate tests from "
            "this agent's own actions, gates, and business domain.",
            file=sys.stderr,
        )

    if include_static:
        tests += load_static(categories, mode, payloads_dir, include_platform)

    # Group by category (report order), then hardest-hitting first.
    order = {c: i for i, c in enumerate(categories)}
    tests.sort(key=lambda t: (
        order.get(t["category"], 99),
        0 if t["source"] == "grounded" else 1,
        SEVERITY_ORDER.get(t["severity"], 9),
    ))
    return tests
