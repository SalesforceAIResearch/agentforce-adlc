#!/usr/bin/env python3
"""Generate a self-contained HTML security assessment report.

Usage:
    python3 scripts/security_report.py --results <results.json> --scores <scores.json> \
        --agent <AgentName> --org <org-alias> [--output report.html]

The report is print-optimized — open in a browser and Cmd/Ctrl+P to save as PDF.

Input:
  --results: JSON array from security_runner.py (with verdicts added by LLM-as-judge)
  --scores:  JSON object from security_scoring.py
  --agent:   Agent name (for the report header)
  --org:     Org alias (for the report header)
  --output:  Output file path (default: /tmp/security_report.html)
"""

import argparse
import json
import os
import sys
from datetime import datetime


OWASP_LABELS = {
    "prompt_injection": ("LLM01", "Prompt Injection"),
    "sensitive_info": ("LLM02", "Sensitive Information Disclosure"),
    "output_handling": ("LLM05", "Improper Output Handling"),
    "excessive_agency": ("LLM06", "Excessive Agency"),
    "system_prompt_leakage": ("LLM07", "System Prompt Leakage"),
    "misinformation": ("LLM09", "Misinformation"),
    "unbounded_consumption": ("LLM10", "Unbounded Consumption"),
}

SEVERITY_COLORS = {
    "critical": "#dc2626",
    "high": "#ea580c",
    "medium": "#ca8a04",
    "low": "#6b7280",
}

GRADE_COLORS = {
    "A": "#16a34a",
    "B": "#2563eb",
    "C": "#ca8a04",
    "D": "#ea580c",
    "F": "#dc2626",
}


def generate_html(results, scores, agent, org, mode):
    grade = scores.get("grade", "?")
    score = scores.get("score", 0)
    status = scores.get("status", "UNKNOWN")
    total_tests = scores.get("total_tests", len(results))
    total_passed = scores.get("total_passed", 0)
    total_failed = scores.get("total_failed", 0)
    categories = scores.get("categories", {})
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build category rows
    category_rows = ""
    for cat_key, cat_data in categories.items():
        owasp_id, owasp_name = OWASP_LABELS.get(cat_key, ("?", cat_key))
        passed = cat_data.get("passed", 0)
        failed = cat_data.get("failed", 0)
        total = cat_data.get("total", 0)
        inconclusive = cat_data.get("inconclusive", 0)

        if failed > 0:
            row_class = "fail-row"
            badge = '<span class="badge badge-fail">FAIL</span>'
        elif inconclusive > 0:
            row_class = "warn-row"
            badge = '<span class="badge badge-warn">WARN</span>'
        else:
            row_class = "pass-row"
            badge = '<span class="badge badge-pass">PASS</span>'

        pct = round(passed / total * 100) if total else 0
        category_rows += f"""
        <tr class="{row_class}">
            <td><strong>{_escape(owasp_id)}</strong></td>
            <td>{_escape(owasp_name)}</td>
            <td>{passed}/{total}</td>
            <td>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {pct}%"></div>
                </div>
            </td>
            <td>{badge}</td>
        </tr>"""

    # Build findings (failures only)
    failures = [r for r in results if r.get("verdict") == "FAIL"]
    findings_html = ""
    if failures:
        for i, f in enumerate(failures, 1):
            sev = f.get("severity", "medium")
            sev_color = SEVERITY_COLORS.get(sev, "#6b7280")
            cat_key = f.get("category", "")
            owasp_id, _ = OWASP_LABELS.get(cat_key, ("?", ""))
            utterances = f.get("utterances_sent", [])
            last_utterance = utterances[-1] if utterances else "N/A"
            response = f.get("response", "")
            risk_analysis = f.get("risk_analysis", "")

            risk_html = ""
            if risk_analysis:
                risk_html = f'<p class="risk-analysis"><strong>Risk:</strong> {_escape(risk_analysis)}</p>'

            findings_html += f"""
            <div class="finding">
                <div class="finding-header">
                    <span class="severity-badge" style="background: {sev_color}">{_escape(sev.upper())}</span>
                    <strong>{_escape(f.get('test_id', '?'))}</strong> — {_escape(f.get('name', 'Unknown'))}
                    <span class="category-tag">{_escape(owasp_id)}</span>
                </div>
                <div class="finding-body">
                    <p><strong>Payload:</strong> <code>{_escape(last_utterance)}</code></p>
                    <p><strong>Response:</strong> <span class="response-text">{_escape(response)}</span></p>
                    {risk_html}
                </div>
            </div>"""
    else:
        findings_html = '<p class="no-findings">No failures detected. All tests passed.</p>'

    # Build full test log — all tests grouped by category
    test_log_html = ""
    current_cat = None
    for r in results:
        cat_key = r.get("category", "unknown")
        if cat_key != current_cat:
            if current_cat is not None:
                test_log_html += "</tbody></table>"
            current_cat = cat_key
            owasp_id, owasp_name = OWASP_LABELS.get(cat_key, ("?", cat_key))
            test_log_html += f"""
            <h3>{_escape(owasp_id)} — {_escape(owasp_name)}</h3>
            <table class="test-log-table">
            <thead><tr><th>ID</th><th>Test</th><th>Severity</th><th>Verdict</th></tr></thead>
            <tbody>"""

        verdict = r.get("verdict", "INCONCLUSIVE")
        verdict_class = {"PASS": "verdict-pass", "FAIL": "verdict-fail"}.get(verdict, "verdict-inconclusive")
        sev = r.get("severity", "medium")

        utterances = r.get("utterances_sent", [])
        payload_text = utterances[-1] if utterances else "N/A"
        if len(payload_text) > 120:
            payload_text = payload_text[:120] + "..."

        response = r.get("response", "")
        if len(response) > 200:
            response = response[:200] + "..."

        test_log_html += f"""
            <tr class="test-row">
                <td><strong>{_escape(r.get('test_id', '?'))}</strong></td>
                <td>{_escape(r.get('name', ''))}</td>
                <td><span class="severity-badge" style="background: {SEVERITY_COLORS.get(sev, '#6b7280')}">{sev.upper()}</span></td>
                <td><span class="{verdict_class}">{verdict}</span></td>
            </tr>
            <tr class="detail-row">
                <td colspan="4">
                    <details>
                        <summary>Payload &amp; Response</summary>
                        <div class="detail-content">
                            <p><strong>Payload:</strong> <code>{_escape(payload_text)}</code></p>
                            <p><strong>Response:</strong> <span class="response-text">{_escape(response)}</span></p>
                        </div>
                    </details>
                </td>
            </tr>"""

    if current_cat is not None:
        test_log_html += "</tbody></table>"

    grade_color = GRADE_COLORS.get(grade, "#6b7280")
    status_class = "status-pass" if "PASSED" in status else "status-fail"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OWASP LLM Security Assessment — {agent}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #1f2937; padding: 40px; max-width: 900px; margin: 0 auto; line-height: 1.5; }}

        @media print {{
            body {{ padding: 20px; font-size: 11px; }}
            .finding {{ break-inside: avoid; }}
            .no-print {{ display: none; }}
        }}

        h1 {{ font-size: 24px; margin-bottom: 4px; }}
        h2 {{ font-size: 18px; margin: 32px 0 16px; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }}

        .header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 32px; }}
        .header-left {{ flex: 1; }}
        .header-right {{ text-align: center; }}

        .grade-circle {{ width: 100px; height: 100px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 48px; font-weight: bold; color: white; background: {grade_color}; margin: 0 auto 8px; }}
        .score-text {{ font-size: 14px; color: #6b7280; }}

        .meta {{ color: #6b7280; font-size: 14px; }}
        .meta span {{ display: inline-block; margin-right: 20px; }}

        .status {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-weight: 600; font-size: 14px; margin-top: 12px; }}
        .status-pass {{ background: #dcfce7; color: #166534; }}
        .status-fail {{ background: #fee2e2; color: #991b1b; }}

        .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 20px 0; }}
        .summary-card {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; text-align: center; }}
        .summary-card .number {{ font-size: 32px; font-weight: bold; }}
        .summary-card .label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; }}

        table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
        th {{ text-align: left; padding: 8px 12px; background: #f3f4f6; border-bottom: 2px solid #e5e7eb; font-size: 12px; text-transform: uppercase; color: #6b7280; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; font-size: 14px; }}

        .progress-bar {{ width: 100px; height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; }}
        .progress-fill {{ height: 100%; background: #16a34a; border-radius: 4px; }}
        .fail-row .progress-fill {{ background: #dc2626; }}
        .warn-row .progress-fill {{ background: #ca8a04; }}

        .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
        .badge-pass {{ background: #dcfce7; color: #166534; }}
        .badge-fail {{ background: #fee2e2; color: #991b1b; }}
        .badge-warn {{ background: #fef3c7; color: #92400e; }}

        .finding {{ border: 1px solid #e5e7eb; border-radius: 8px; margin: 12px 0; overflow: hidden; }}
        .finding-header {{ padding: 12px 16px; background: #f9fafb; border-bottom: 1px solid #e5e7eb; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
        .finding-body {{ padding: 16px; }}
        .finding-body p {{ margin: 8px 0; font-size: 13px; }}

        .severity-badge {{ padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; color: white; }}
        .category-tag {{ padding: 2px 6px; background: #e5e7eb; border-radius: 3px; font-size: 11px; color: #4b5563; }}

        .response-text {{ color: #6b7280; font-style: italic; }}
        .risk-analysis {{ margin-top: 8px; padding: 8px 12px; background: #fef2f2; border-left: 3px solid #dc2626; border-radius: 4px; font-size: 13px; }}
        code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 3px; font-size: 12px; word-break: break-all; }}
        .no-findings {{ color: #166534; background: #dcfce7; padding: 16px; border-radius: 8px; text-align: center; }}

        .test-log-table {{ width: 100%; border-collapse: collapse; margin: 12px 0 24px; }}
        .test-log-table th {{ text-align: left; padding: 6px 10px; background: #f3f4f6; border-bottom: 2px solid #e5e7eb; font-size: 11px; text-transform: uppercase; color: #6b7280; }}
        .test-log-table td {{ padding: 8px 10px; border-bottom: 1px solid #f3f4f6; font-size: 13px; vertical-align: top; }}
        .test-row td {{ border-bottom: none; }}
        .detail-row td {{ padding-top: 0; }}
        .detail-content {{ padding: 8px 12px; background: #f9fafb; border-radius: 4px; margin-top: 4px; }}
        .detail-content p {{ margin: 4px 0; font-size: 12px; }}
        details summary {{ cursor: pointer; font-size: 12px; color: #6b7280; }}
        details summary:hover {{ color: #1f2937; }}
        h3 {{ font-size: 15px; margin: 24px 0 8px; color: #374151; }}
        .verdict-pass {{ color: #166534; font-weight: 600; }}
        .verdict-fail {{ color: #991b1b; font-weight: 600; }}
        .verdict-inconclusive {{ color: #92400e; font-weight: 600; }}

        .footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #e5e7eb; color: #9ca3af; font-size: 12px; text-align: center; }}
        .print-hint {{ margin-top: 16px; padding: 12px; background: #eff6ff; border-radius: 8px; color: #1e40af; font-size: 13px; text-align: center; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <h1>OWASP LLM Security Assessment</h1>
            <div class="meta">
                <span><strong>Agent:</strong> {_escape(agent)}</span>
                <span><strong>Org:</strong> {_escape(org)}</span>
                <span><strong>Mode:</strong> {mode}</span>
            </div>
            <div class="meta">
                <span><strong>Date:</strong> {timestamp}</span>
                <span><strong>Tests:</strong> {total_tests}</span>
            </div>
            <div class="{status_class} status">{status.replace('_', ' ')}</div>
        </div>
        <div class="header-right">
            <div class="grade-circle">{grade}</div>
            <div class="score-text">{score}/100</div>
        </div>
    </div>

    <div class="summary-grid">
        <div class="summary-card">
            <div class="number" style="color: #16a34a">{total_passed}</div>
            <div class="label">Passed</div>
        </div>
        <div class="summary-card">
            <div class="number" style="color: #dc2626">{total_failed}</div>
            <div class="label">Failed</div>
        </div>
        <div class="summary-card">
            <div class="number" style="color: #6b7280">{total_tests - total_passed - total_failed}</div>
            <div class="label">Inconclusive</div>
        </div>
    </div>

    <h2>Category Results</h2>
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Category</th>
                <th>Score</th>
                <th>Progress</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
            {category_rows}
        </tbody>
    </table>

    <h2>Findings</h2>
    {findings_html}

    <h2>Full Test Log</h2>
    {test_log_html}

    <div class="footer">
        <p>Generated by Agentforce ADLC — /agentforce-secure skill</p>
        <p>OWASP LLM Top 10 (2025) | Severity Scoring: Critical=25, High=15, Medium=8, Low=3</p>
    </div>

    <div class="print-hint no-print">
        <strong>To save as PDF:</strong> Press Cmd+P (Mac) or Ctrl+P (Windows/Linux) → Save as PDF
    </div>
</body>
</html>"""
    return html


def _escape(text):
    """HTML-escape a string."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def main():
    parser = argparse.ArgumentParser(description="Generate HTML security assessment report")
    parser.add_argument("--results", required=True, help="Path to results JSON (with verdicts)")
    parser.add_argument("--scores", required=True, help="Path to scores JSON from security_scoring.py")
    parser.add_argument("--agent", required=True, help="Agent name")
    parser.add_argument("--org", required=True, help="Org alias")
    parser.add_argument("--mode", default="full", help="Assessment mode (quick/full)")
    parser.add_argument("--output", default="/tmp/security_report.html", help="Output HTML path")

    args = parser.parse_args()

    with open(args.results) as f:
        results = json.load(f)
    with open(args.scores) as f:
        scores = json.load(f)

    html = generate_html(results, scores, args.agent, args.org, args.mode)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        f.write(html)

    print(f"Report generated: {args.output}", file=sys.stderr)
    print(f"Grade: {scores.get('grade', '?')} ({scores.get('score', 0)}/100)", file=sys.stderr)
    print(f"Open in browser and print to PDF (Cmd+P / Ctrl+P)", file=sys.stderr)


if __name__ == "__main__":
    main()
