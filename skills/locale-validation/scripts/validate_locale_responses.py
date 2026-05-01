#!/usr/bin/env python3
"""
Validate agent responses for locale correctness after a batch test run.

Usage — heuristic only (fast, no LLM):
    python3 validate_locale_responses.py \
        --results /tmp/locale-test-results.json \
        --locales ja fr it de es es_MX pt_BR \
        --output /tmp/locale-validation-report.md

Usage — heuristic + LLM-as-judge via Claude (default):
    python3 validate_locale_responses.py \
        --results /tmp/locale-test-results.json \
        --locales ja fr it de es es_MX pt_BR \
        --llm-validate \
        --llm-api-key $ANTHROPIC_API_KEY \
        --output /tmp/locale-validation-report.md

Usage — heuristic + LLM-as-judge via OpenAI:
    python3 validate_locale_responses.py \
        --results /tmp/locale-test-results.json \
        --locales ja fr it de es es_MX pt_BR \
        --llm-validate \
        --llm-provider openai \
        --llm-api-key $OPENAI_API_KEY \
        --llm-model gpt-4o \
        --output /tmp/locale-validation-report.md

The heuristic layer runs first (fast, zero cost).
The LLM layer is only invoked when --llm-validate is passed and runs a Python
reimplementation of EvalLocaleTestUtil.buildLanguageValidationPrompt() / languagePrompt
from com.salesforce.einstein_copilot.test.evals.util.EvalLocaleTestUtil.

Provider defaults: anthropic (claude-haiku-4-5 via api.anthropic.com).
For OpenAI-compatible endpoints (Azure, etc.) use --llm-provider openai.
Azure OpenAI: https://<resource>.openai.azure.com/openai/deployments/<deployment>/chat/completions?api-version=2024-02-01
"""

import argparse
import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import date
from typing import Optional

# ---------------------------------------------------------------------------
# Language prompt — exact text of EvalLocaleTestUtil.languagePrompt
# (Java source: src/test/java/com/salesforce/einstein_copilot/test/evals/util/EvalLocaleTestUtil.java)
# Placeholders:
#   {{languageKey}}   — target locale code, e.g. "es", "ja"
#   {ResponseString}  — the agent response text to validate
# ---------------------------------------------------------------------------
LANGUAGE_VALIDATION_PROMPT = (
    'You are a localization expert specializing in business communication for **{{languageKey}}**. '
    'Your task is to analyze the provided response for cultural and linguistic issues.'
    '**Critical Language Check:**'
    'If the Target Language is NOT English (en_US) and the response is written entirely or predominantly in English, '
    "you MUST immediately return overall_evaluation as POOR with explanation "
    "'Response is in English but should be in {{languageKey}}'."
    'This is a critical failure that overrides all other evaluations. '
    'Your analysis must be lenient, prioritizing cultural appropriateness, fluency, and business tone over minor regionalisms (like spelling differences). '
    'Identify all issues and provide your feedback in a strict JSON format in en-US. '
    'The root object must contain a validation_results list. If there are no issues, return an empty list. '
    'Each issue object in the list must contain the following keys: '
    '* issue_type: (String) Must be one of: "Untranslated Text", "Grammar/Spelling", "Tone/Structure", "Formatting", "Culture & Business Alignment", "Sensitive Content". '
    '* problematic_text: (String) The exact text snippet that contains the error. '
    '* Be Lenient in your cultural evaluation: Your goal is to be a cultural guide, not a strict grammar checker. '
    '* Be Lenient in your Tone evaluation: Your goal is to validate the tone is polite, respectful & formal. '
    '* Do not penalize minor deviations in fluency or formality if the message is understandable and would be acceptable in a professional setting. '
    '* description: (String) A clear explanation of why it is an issue based on the target language and culture. '
    'Consider the expected level of formality. When identifying cultural mismatches, consider whether the phrasing might seem slightly off but still acceptable'
    '\u2014or whether it risks alienating, confusing, or disengaging the recipient. '
    '* suggestion: (String) A concrete, corrected version of the text. Do not suggest if the overall evaluation looks good. Provide suggestions only in English. '
    '* Provide an **overall_evaluation** as Good or Bad with an explanation. Provide explanation only in English. '
    '--- **Target Language:** {{languageKey}} **Response to Analyze:**{ResponseString}'
)

LANGUAGE_MAPPING = {
    # Agentforce supported languages
    # https://help.salesforce.com/s/articleView?id=ai.agent_employee_agent_considerations.htm
    "ar": "Arabic",
    "zh_CN": "Chinese (Simplified)",
    "zh_TW": "Chinese (Traditional)",
    "da": "Danish",
    "nl": "Dutch",
    "fi": "Finnish",
    "fr": "French",
    "de": "German",
    "in": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "ms": "Malay",
    "no": "Norwegian",
    "pl": "Polish",
    "pt_BR": "Portuguese (Brazil)",
    "pt_PT": "Portuguese (European)",
    "ru": "Russian",
    "es": "Spanish",
    "es_MX": "Spanish (Mexico)",
    "sv": "Swedish",
    "th": "Thai",
    "tr": "Turkish",
    # English variants
    "en_US": "English",
    "en_GB": "English (UK)",
    # Additional common variants
    "fr_CA": "French (Canadian)",
}

# Unicode range checks for non-Latin scripts
JAPANESE_RANGE = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff]')
CHINESE_RANGE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')
ARABIC_RANGE = re.compile(r'[\u0600-\u06ff]')
KOREAN_RANGE = re.compile(r'[\uac00-\ud7af\u1100-\u11ff]')
THAI_RANGE = re.compile(r'[\u0e00-\u0e7f]')
LATIN_RANGE = re.compile(r'[a-zA-Z]')

NON_LATIN_LOCALES = {
    "ja": JAPANESE_RANGE,
    "zh_CN": CHINESE_RANGE,
    "zh_TW": CHINESE_RANGE,
    "ar": ARABIC_RANGE,
    "ko": KOREAN_RANGE,
    "th": THAI_RANGE,
}


# ---------------------------------------------------------------------------
# LLM-backed validation (mirrors EvalLocaleTestUtil.buildLanguageValidationPrompt)
# ---------------------------------------------------------------------------

def build_language_validation_prompt(language_key: str, response_string: str) -> str:
    """Mirrors EvalLocaleTestUtil.buildLanguageValidationPrompt(languageKey, responseString)."""
    return (
        LANGUAGE_VALIDATION_PROMPT
        .replace("{{languageKey}}", language_key)
        .replace("{ResponseString}", response_string)
    )


def call_llm_anthropic(prompt: str, api_key: str, model: str) -> str:
    """Call the Anthropic Messages API. Returns assistant text or raises on error."""
    payload = json.dumps(
        {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=payload, method="POST"
    )
    req.add_unredirected_header("Content-Type", "application/json; charset=utf-8")
    req.add_unredirected_header("x-api-key", api_key)
    req.add_unredirected_header("anthropic-version", "2023-06-01")

    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    return body["content"][0]["text"]


def call_llm_openai(prompt: str, endpoint: str, api_key: str, model: str) -> str:
    """Call an OpenAI-compatible chat completions endpoint. Returns assistant text or raises."""
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    # Build request without passing headers dict to avoid Python's latin-1 header encoding
    req = urllib.request.Request(endpoint, data=payload, method="POST")
    req.add_unredirected_header("Content-Type", "application/json; charset=utf-8")
    req.add_unredirected_header("Authorization", f"Bearer {api_key}")

    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    return body["choices"][0]["message"]["content"]


def parse_llm_result(llm_text: str) -> dict:
    """
    Extract the JSON block from the LLM response.
    Returns dict with keys: overall_evaluation, validation_results, raw.
    overall_evaluation: "Good" | "Bad" | "POOR" | "unknown"
    """
    # Try to extract a JSON object from the response text
    json_match = re.search(r'\{.*\}', llm_text, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            return {
                "overall_evaluation": parsed.get("overall_evaluation", "unknown"),
                "validation_results": parsed.get("validation_results", []),
                "raw": llm_text,
            }
        except json.JSONDecodeError:
            pass

    # Fallback: look for overall_evaluation as a plain string
    match = re.search(r'"overall_evaluation"\s*:\s*"([^"]+)"', llm_text, re.IGNORECASE)
    overall = match.group(1) if match else "unknown"
    return {"overall_evaluation": overall, "validation_results": [], "raw": llm_text}


def llm_validate(response: str, locale: str, llm_config: dict) -> dict:
    """
    Run EvalLocaleTestUtil.languagePrompt against a single response via the LLM.
    Returns parse_llm_result dict, or {"overall_evaluation": "error", "error": str, "raw": ""}.
    """
    if locale == "en_US":
        return {"overall_evaluation": "skipped", "validation_results": [], "raw": ""}

    import time
    prompt = build_language_validation_prompt(locale, response)
    for attempt in range(3):
        try:
            if llm_config.get("provider", "anthropic") == "anthropic":
                text = call_llm_anthropic(
                    prompt,
                    api_key=llm_config["api_key"],
                    model=llm_config["model"],
                )
            else:
                text = call_llm_openai(
                    prompt,
                    endpoint=llm_config["endpoint"],
                    api_key=llm_config["api_key"],
                    model=llm_config["model"],
                )
            return parse_llm_result(text)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                retry_after = e.headers.get("Retry-After") or e.headers.get("x-ratelimit-reset-requests")
                try:
                    wait = float(retry_after) if retry_after else 20 * (attempt + 1)
                except (ValueError, TypeError):
                    wait = 20 * (attempt + 1)
                print(f"    rate limited (429), waiting {wait:.0f}s before retry {attempt + 1}/2...", file=sys.stderr)
                time.sleep(wait)
                continue
            return {"overall_evaluation": "error", "error": f"HTTP {e.code}: {e.reason}", "raw": ""}
        except Exception as e:
            return {"overall_evaluation": "error", "error": str(e), "raw": ""}
    return {"overall_evaluation": "error", "error": "max retries exceeded", "raw": ""}


# ---------------------------------------------------------------------------
# Heuristic validation
# ---------------------------------------------------------------------------

def detect_language_issue(response: str, locale: str) -> tuple[bool, str]:
    """
    Fast heuristic: check if response appears to be in the target locale.
    Returns (has_issue, description).
    """
    if not response or not response.strip():
        return True, "Empty response"

    if locale == "en_US":
        return False, ""

    if locale in NON_LATIN_LOCALES:
        pattern = NON_LATIN_LOCALES[locale]
        if not pattern.search(response):
            return True, f"CRITICAL: Response appears to be in English/Latin script, not {LANGUAGE_MAPPING.get(locale, locale)}"
        return False, ""

    # Cyrillic-script locales are treated like non-Latin: require Cyrillic characters
    cyrillic = re.compile(r'[Ѐ-ӿ]')
    if locale == "ru" and not cyrillic.search(response):
        return True, f"CRITICAL: Response appears to be in English/Latin script, not {LANGUAGE_MAPPING.get(locale, locale)}"

    locale_hints = {
        "fr":    re.compile(r'[àâçéèêëîïôùûü]', re.IGNORECASE),
        "fr_CA": re.compile(r'[àâçéèêëîïôùûü]', re.IGNORECASE),
        "de":    re.compile(r'[äöüß]', re.IGNORECASE),
        "es":    re.compile(r'[áéíóúüñ¿¡]', re.IGNORECASE),
        "es_MX": re.compile(r'[áéíóúüñ¿¡]', re.IGNORECASE),
        "it":    re.compile(r'[àèéìòù]', re.IGNORECASE),
        "pt_BR": re.compile(r'[ãõáéíóúâêôàç]', re.IGNORECASE),
        "pt_PT": re.compile(r'[ãõáéíóúâêôàç]', re.IGNORECASE),
        "nl":    re.compile(r'[áéíóúäëïöüèàê]', re.IGNORECASE),
        "da":    re.compile(r'[æøå]', re.IGNORECASE),
        "sv":    re.compile(r'[åäö]', re.IGNORECASE),
        "no":    re.compile(r'[æøå]', re.IGNORECASE),
        "fi":    re.compile(r'[äöå]', re.IGNORECASE),
        "pl":    re.compile(r'[ąćęłńóśźż]', re.IGNORECASE),
        "tr":    re.compile(r'[çğışöü]', re.IGNORECASE),
        "ms":    re.compile(r'[a-z]', re.IGNORECASE),   # Malay is Latin-only; skip diacritic check
        "in":    re.compile(r'[a-z]', re.IGNORECASE),   # Indonesian is Latin-only; skip diacritic check
    }

    if len(response.strip()) < 20:
        return False, ""

    hint_pattern = locale_hints.get(locale)
    if hint_pattern and not hint_pattern.search(response):
        latin_chars = len(LATIN_RANGE.findall(response))
        total_chars = len(response.replace(" ", ""))
        if total_chars > 0 and latin_chars / total_chars > 0.95:
            return True, f"POSSIBLE ISSUE: Response may be in English, not {LANGUAGE_MAPPING.get(locale, locale)} — no locale-specific characters detected"
    return False, ""


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def _is_raw_sf_format(tc: dict) -> bool:
    """Return True if this test case is raw sf agent test results format."""
    return "inputs" in tc or "generatedData" in tc or "testNumber" in tc


def extract_responses_from_results(results_data: dict) -> list[dict]:
    entries = []
    test_cases = results_data.get("result", {}).get("testCases", [])
    for tc in test_cases:
        if _is_raw_sf_format(tc):
            # Raw sf agent test results format:
            #   inputs.utterance, generatedData.outcome, generatedData.topic
            #   locale is not present in raw output — caller must pass --locales to assert
            gen = tc.get("generatedData", {})
            response = gen.get("outcome", "")
            # Also check testResults[].actualValue for output_validation if outcome missing
            if not response:
                for tr in tc.get("testResults", []):
                    if tr.get("name") == "output_validation" and tr.get("actualValue"):
                        response = tr["actualValue"]
                        break
            entries.append({
                "name": str(tc.get("testNumber", "unknown")),
                "utterance": tc.get("inputs", {}).get("utterance", ""),
                "response": response,
                "locale": tc.get("locale", "unknown"),
                "status": tc.get("status", "unknown"),
                "topic": gen.get("topic", ""),
            })
        else:
            # Custom intermediate format: top-level testCaseName, botResponse, locale
            entries.append({
                "name": tc.get("testCaseName", "unknown"),
                "utterance": tc.get("utterance", ""),
                "response": tc.get("botResponse", tc.get("response", "")),
                "locale": tc.get("locale", "unknown"),
                "status": tc.get("status", "unknown"),
                "topic": tc.get("topic", ""),
            })
    return entries


def _infer_locale_from_utterance(utterance: str, target_locales: list[str]) -> Optional[str]:
    """
    Infer the locale of an utterance from its script/characters.
    Returns the first matching locale from target_locales, or None.
    """
    if not utterance:
        return None

    # Non-Latin script detection (unambiguous)
    script_map = [
        ("ja", JAPANESE_RANGE),
        ("ko", KOREAN_RANGE),
        ("ar", ARABIC_RANGE),
        ("zh_CN", CHINESE_RANGE),
        ("zh_TW", CHINESE_RANGE),
    ]
    for code, pattern in script_map:
        if code in target_locales and pattern.search(utterance):
            return code

    # Latin-script locale detection via accent characters
    accent_map = [
        ("fr",    re.compile(r'[àâçéèêëîïôùûü]', re.IGNORECASE)),
        ("fr_CA", re.compile(r'[àâçéèêëîïôùûü]', re.IGNORECASE)),
        ("de",    re.compile(r'[äöüß]', re.IGNORECASE)),
        ("es",    re.compile(r'[áéíóúüñ¿¡]', re.IGNORECASE)),
        ("es_MX", re.compile(r'[áéíóúüñ¿¡]', re.IGNORECASE)),
        ("it",    re.compile(r'[àèéìòù]', re.IGNORECASE)),
        ("pt_BR", re.compile(r'[ãõáéíóúâêôàç]', re.IGNORECASE)),
        ("pt_PT", re.compile(r'[ãõáéíóúâêôàç]', re.IGNORECASE)),
    ]
    for code, pattern in accent_map:
        if code in target_locales and pattern.search(utterance):
            return code

    # Fall back to first English locale if utterance looks purely ASCII/English
    for code in ("en_US", "en_GB"):
        if code in target_locales:
            return code

    return None


def _load_spec_order(spec_path: str) -> list[dict]:
    """
    Load utterance→locale ordering from a testSpec YAML.
    Returns list of {utterance, locale} in spec order.
    Requires PyYAML; silently returns [] if unavailable or file missing.
    """
    try:
        import yaml
        with open(spec_path, encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        return [
            {"utterance": tc.get("utterance", ""), "locale": tc.get("locale", "")}
            for tc in spec.get("testCases", [])
        ]
    except Exception:
        return []


def _expand_entries(entries: list[dict], target_locales: list[str],
                    spec_order: Optional[list] = None) -> list[dict]:
    """
    Assign a locale to each entry using (in priority order):
      1. spec_order — matches entry by utterance text to the spec's declared locale
      2. utterance inference — detects locale from script/accent characters
      3. target_locales expansion — last resort for entries with no detectable locale
    Entries with a known locale (custom format) are filtered to target_locales unchanged.
    Result is sorted to match spec order when spec_order is provided.
    """
    # Build utterance→locale lookup from spec
    spec_lookup = {}
    if spec_order:
        for item in spec_order:
            utt = item.get("utterance", "").strip()
            loc = item.get("locale", "").strip()
            if utt and loc:
                spec_lookup[utt] = loc

    expanded = []
    for entry in entries:
        locale = entry.get("locale", "unknown")
        utterance = entry.get("utterance", "").strip()

        if locale != "unknown":
            # Custom format — already has locale; filter to requested locales
            if not target_locales or locale in target_locales:
                expanded.append(entry)
            continue

        # Raw sf format — no locale field; resolve it
        inferred = (
            spec_lookup.get(utterance)
            or _infer_locale_from_utterance(utterance, target_locales)
        )

        if inferred:
            if not target_locales or inferred in target_locales:
                expanded.append({**entry, "locale": inferred})
        else:
            # Cannot infer — expand one copy per target locale as last resort
            for loc in (target_locales or []):
                expanded.append({**entry, "locale": loc})

    # Re-sort to match spec order if available
    if spec_order:
        spec_positions = {
            item.get("utterance", "").strip(): i
            for i, item in enumerate(spec_order)
        }
        expanded.sort(key=lambda e: spec_positions.get(e.get("utterance", "").strip(), 9999))

    return expanded


def validate_responses(entries: list[dict], target_locales: list[str],
                       llm_config: Optional[dict] = None,
                       spec_order: Optional[list] = None) -> dict:
    results = {
        "total": 0, "passed": 0, "failed": 0, "critical": 0,
        "llm_enabled": llm_config is not None,
        "llm_provider": llm_config.get("provider", "anthropic") if llm_config else "",
        "details": [],
    }

    for entry in _expand_entries(entries, target_locales, spec_order=spec_order):
        locale = entry.get("locale", "")

        results["total"] += 1
        response = entry.get("response", "")

        # Heuristic layer
        heuristic_issue, heuristic_desc = detect_language_issue(response, locale)
        is_critical = "CRITICAL" in heuristic_desc

        # LLM layer (optional)
        llm_result = None
        if llm_config and response and locale != "en_US":
            import time as _time
            print(f"  LLM validating: {entry.get('name', '')} [{locale}]...", file=sys.stderr)
            _time.sleep(llm_config.get("call_delay", 1))
            llm_result = llm_validate(response, locale, llm_config)

        # Determine overall pass/fail:
        # Fail if heuristic found an issue OR LLM returned Bad/POOR
        llm_overall = llm_result["overall_evaluation"] if llm_result else None
        llm_failed = llm_overall in ("Bad", "POOR") if llm_overall else False
        llm_error = llm_result.get("error") if llm_result else None

        # LLM POOR = critical (English response in non-English locale)
        if llm_overall == "POOR":
            is_critical = True

        has_issue = heuristic_issue or llm_failed

        if has_issue:
            results["failed"] += 1
            if is_critical:
                results["critical"] += 1
        else:
            results["passed"] += 1

        # Build combined issue description
        issue_parts = []
        if heuristic_desc:
            issue_parts.append(f"[heuristic] {heuristic_desc}")
        if llm_result:
            if llm_error:
                issue_parts.append(f"[llm] error: {llm_error}")
            elif llm_failed:
                llm_issues = llm_result.get("validation_results", [])
                summary = "; ".join(
                    i.get("issue_type", "") + ": " + i.get("description", "")[:80]
                    for i in llm_issues[:3]
                ) if llm_issues else f"overall_evaluation={llm_overall}"
                issue_parts.append(f"[llm] {summary}")

        results["details"].append({
            "name": entry.get("name", ""),
            "locale": locale,
            "language": LANGUAGE_MAPPING.get(locale, locale),
            "utterance": entry.get("utterance", "")[:80],
            "response_excerpt": response[:150] if response else "",
            "status": "FAIL" if has_issue else "PASS",
            "heuristic_issue": heuristic_desc,
            "llm_overall": llm_overall,
            "llm_issues": llm_result.get("validation_results", []) if llm_result else [],
            "llm_error": llm_error,
            "issue": " | ".join(issue_parts) if issue_parts else "",
            "critical": is_critical,
        })

    return results


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_report(validation: dict, agent_name: str) -> str:
    llm_enabled = validation.get("llm_enabled", False)
    llm_provider = validation.get("llm_provider", "anthropic")
    if llm_enabled:
        llm_label = f"enabled ({llm_provider}, EvalLocaleTestUtil.languagePrompt)"
    else:
        llm_label = "disabled (heuristic only)"
    lines = [
        f"## Locale Validation Report — {agent_name}",
        f"Date: {date.today()}",
        f"LLM validation: {llm_label}",
        "",
        "| Name | Locale | Utterance | Heuristic | LLM | Actual Response | Issues |",
        "|------|--------|-----------|-----------|-----|-----------------|--------|",
    ]

    for d in validation["details"]:
        h_col = "❌" if d["heuristic_issue"] else "✅"
        llm_col = {
            "Good": "✅ Good",
            "Bad": "❌ Bad",
            "POOR": "🚨 POOR",
            "skipped": "—",
            "error": "⚠️ err",
            None: "—",
        }.get(d["llm_overall"], d["llm_overall"] or "—")
        issue = d["issue"] or "—"
        response = d["response_excerpt"].replace("|", "\\|").replace("\n", " ") if d["response_excerpt"] else "—"
        lines.append(
            f"| {d['name']} | {d['locale']} | {d['utterance'][:60]} | {h_col} | {llm_col} | {response} | {issue} |"
        )

    lines += [
        "",
        "### Summary",
        f"- Total: {validation['total']}",
        f"- Passed: {validation['passed']}",
        f"- Failed: {validation['failed']}",
        f"- Critical failures (English response in non-English locale): {validation['critical']}",
    ]

    failures = [d for d in validation["details"] if d["status"] == "FAIL"]
    if failures:
        lines += ["", "### Failures detail"]
        for d in failures:
            lines.append(f"\n**{d['name']}** ({d['locale']} — {d['language']})")
            lines.append(f"- Utterance: {d['utterance']}")
            if d["heuristic_issue"]:
                lines.append(f"- Heuristic: {d['heuristic_issue']}")
            if d["llm_overall"] and d["llm_overall"] not in ("skipped", None):
                lines.append(f"- LLM overall_evaluation: {d['llm_overall']}")
                for issue in d.get("llm_issues", [])[:5]:
                    lines.append(f"  - [{issue.get('issue_type', '?')}] {issue.get('description', '')[:120]}")
                    if issue.get("suggestion"):
                        lines.append(f"    Suggestion: {issue['suggestion'][:100]}")
            if d["llm_error"]:
                lines.append(f"- LLM error: {d['llm_error']}")
            if d["response_excerpt"]:
                lines.append(f"- Response excerpt: `{d['response_excerpt']}...`")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Validate locale responses from sf agent test results")
    parser.add_argument("--results", required=True, help="Path to sf agent test JSON results file")
    parser.add_argument("--locales", nargs="+", default=["ja", "fr", "it", "de", "es", "es_MX", "pt_BR"])
    parser.add_argument("--output", help="Path to write markdown report (default: stdout)")
    parser.add_argument("--agent-name", default="Agent", help="Agent name for the report header")
    parser.add_argument("--spec", default="", help="Path to testSpec YAML — used to infer per-utterance locale and preserve spec row order in the report")

    llm_group = parser.add_argument_group("LLM validation (Python reimplementation of EvalLocaleTestUtil.languagePrompt)")
    llm_group.add_argument(
        "--llm-validate", action="store_true",
        help="Enable LLM-as-judge validation on top of heuristic checks",
    )
    llm_group.add_argument(
        "--llm-provider", choices=["anthropic", "openai"], default="anthropic",
        help="LLM provider: anthropic (default) or openai",
    )
    llm_group.add_argument(
        "--llm-endpoint",
        default="https://api.openai.com/v1/chat/completions",
        help="OpenAI-compatible chat completions URL (only used with --llm-provider openai)",
    )
    llm_group.add_argument("--llm-api-key", default="", help="API key (or set ANTHROPIC_API_KEY / OPENAI_API_KEY env var)")
    llm_group.add_argument(
        "--llm-model", default="",
        help="Model name (default: claude-haiku-4-5 for anthropic, gpt-4o for openai)",
    )
    llm_group.add_argument("--llm-call-delay", type=float, default=1.0, help="Seconds to wait between LLM calls (default: 1.0, increase to 3-5 for low rate-limit keys)")

    args = parser.parse_args()

    import os

    # Apply provider-specific defaults for model and API key env var
    if args.llm_validate:
        if args.llm_provider == "anthropic":
            if not args.llm_model:
                args.llm_model = "claude-haiku-4-5"
            if not args.llm_api_key:
                args.llm_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not args.llm_api_key:
                try:
                    args.llm_api_key = input(
                        "\nANTHROPIC_API_KEY is not set. "
                        "Enter your Anthropic API key to continue: "
                    ).strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nAborted.", file=sys.stderr)
                    sys.exit(1)
        else:
            if not args.llm_model:
                args.llm_model = "gpt-4o"
            if not args.llm_api_key:
                args.llm_api_key = os.environ.get("OPENAI_API_KEY", "")
            if not args.llm_api_key:
                try:
                    args.llm_api_key = input(
                        "\nOPENAI_API_KEY is not set. "
                        "Enter your OpenAI API key to continue: "
                    ).strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nAborted.", file=sys.stderr)
                    sys.exit(1)

        if not args.llm_api_key:
            print("Error: no key provided — aborting LLM validation.", file=sys.stderr)
            sys.exit(1)

    results_path = Path(args.results)
    if not results_path.exists():
        print(f"Error: results file not found: {args.results}", file=sys.stderr)
        sys.exit(1)

    results_data = json.loads(results_path.read_text())
    entries = extract_responses_from_results(results_data)

    if not entries:
        print("Warning: no test case entries found in results file", file=sys.stderr)

    llm_config = None
    if args.llm_validate:
        llm_config = {
            "provider": args.llm_provider,
            "endpoint": args.llm_endpoint,
            "api_key": args.llm_api_key,
            "model": args.llm_model,
            "call_delay": args.llm_call_delay,
        }
        location = "api.anthropic.com" if args.llm_provider == "anthropic" else args.llm_endpoint
        print(f"LLM validation enabled — provider: {args.llm_provider}, model: {args.llm_model}, endpoint: {location}", file=sys.stderr)

    spec_order = _load_spec_order(args.spec) if args.spec else []
    validation = validate_responses(entries, args.locales, llm_config=llm_config, spec_order=spec_order)
    report = render_report(validation, args.agent_name)

    if args.output:
        Path(args.output).write_text(report)
        print(f"Report written to {args.output}")
    else:
        print(report)

    if validation["critical"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
