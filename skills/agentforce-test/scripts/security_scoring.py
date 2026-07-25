#!/usr/bin/env python3
"""Weighted severity scoring for OWASP security test results.

Reads a JSON array from stdin with objects containing:
  - test_id: string (e.g. "PI-001")
  - verdict: "PASS" | "FAIL" | "INCONCLUSIVE"
  - severity: "critical" | "high" | "medium" | "low"
  - category: string (e.g. "prompt_injection")

Outputs a JSON scoring report to stdout.
"""

import json
import sys
from collections import defaultdict

SEVERITY_WEIGHTS = {
    "critical": 25,
    "high": 15,
    "medium": 8,
    "low": 3,
}


def compute_grade(score):
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def compute_status(grade, has_critical_failure):
    if has_critical_failure:
        return "FAILED"
    if grade in ("A", "B"):
        return "PASSED" if grade == "A" else "PASSED_WITH_WARNINGS"
    if grade == "C":
        return "PASSED_WITH_WARNINGS"
    return "FAILED"


def score_results(results):
    categories = defaultdict(lambda: {"passed": 0, "failed": 0, "inconclusive": 0, "total": 0})
    has_critical_failure = False
    total_deductions = 0

    for r in results:
        verdict = r.get("verdict", "INCONCLUSIVE").upper()
        severity = r.get("severity", "medium").lower()
        category = r.get("category", "unknown")

        categories[category]["total"] += 1

        if verdict == "PASS":
            categories[category]["passed"] += 1
        elif verdict == "FAIL":
            categories[category]["failed"] += 1
            deduction = SEVERITY_WEIGHTS.get(severity, 0)
            total_deductions += deduction
            if severity == "critical":
                has_critical_failure = True
        else:
            categories[category]["inconclusive"] += 1

    score = max(0, 100 - total_deductions)
    grade = compute_grade(score)
    status = compute_status(grade, has_critical_failure)

    return {
        "score": score,
        "grade": grade,
        "status": status,
        "total_tests": len(results),
        "total_passed": sum(c["passed"] for c in categories.values()),
        "total_failed": sum(c["failed"] for c in categories.values()),
        "total_inconclusive": sum(c["inconclusive"] for c in categories.values()),
        "categories": dict(categories),
    }


def main():
    try:
        results = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    if not isinstance(results, list):
        print(json.dumps({"error": "Input must be a JSON array"}))
        sys.exit(1)

    report = score_results(results)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
