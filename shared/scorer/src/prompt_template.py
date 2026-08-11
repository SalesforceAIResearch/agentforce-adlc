"""Invoke a deployed GenAiPromptTemplate via the generatePromptResponse invocable action.

Endpoint: POST /services/data/v64.0/actions/custom/generatePromptResponse/{dev_name}

Response shape (Connect API invocable): a list of `{isSuccess, outputValues, ...}` entries,
one per input in the request. The outputValues contain the hydrated LLM response, typically
under a key like `promptResponse` or the generation text directly — exact shape is discovered
at runtime since the docs we could access didn't pin it down. We return both the parsed
label/reason pair we can surface and the raw response for debugging.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import sf_apex
from .scorer_spec import ScorerSpec

API_VERSION = "v64.0"
# Connect API "Einstein Prompt Template Generations" resource. Public docs:
# https://developer.salesforce.com/docs/atlas.en-us.chatterapi.meta/chatterapi/connect_resources_prompt_template.htm
# This is the CORRECT endpoint for scorer templates with stdmDetailViewType inputs.
# (The older /actions/custom/generatePromptResponse invocable layer rejects nested
# object inputs with a confusing "$.sessionState is missing" error.)
ENDPOINT = f"/services/data/{API_VERSION}/einstein/prompt-templates"


@dataclass
class ScoringResult:
    # For Predefined (Text/Number) scorers: the matched label from the allowed
    # list, or None if the LLM's output didn't match any entry.
    # For OpenEnded free-form scorers: always None (the value lives in raw_value).
    label: str | None
    # Rationale text the model produced alongside the label/value. May be None
    # if the model returned only the value.
    reason: str | None
    # The free-form scorer output as a plain string. For Predefined scorers
    # this mirrors `label` (or the raw candidate string when unmatched). For
    # OpenEnded scorers this is the primary result — free-form text, a number,
    # a boolean literal, etc., depending on the scorer's lightning_type.
    raw_value: str | None
    raw_response_text: str
    # Verbatim response from the Connect API. Usually a dict, but the invocable
    # form of the endpoint returns a list — keep the type permissive.
    raw_api_payload: dict | list

    @property
    def pretty(self) -> str:
        value = self.label or self.raw_value or "<no-value-parsed>"
        reason = self.reason or "<no-reason>"
        return f"{value}\n  reason: {reason}"


def run_scorer(
    org_alias: str,
    scorer: ScorerSpec,
    session_payload: dict | str,
) -> ScoringResult:
    """Run a scorer against session data.

    `session_payload`: either the canonical STDM dict (for templates declaring
    Input:Session as `stdmDetailViewType`) or a plain string (for `primitive://String`
    session inputs). Passed through unchanged as the `Input:Session` value.
    """
    path = f"{ENDPOINT}/{scorer.name}/generations"
    value_map: dict = {"Input:Session": {"value": session_payload}}
    pt = scorer.pt_template_type
    if pt == "scorerMultilabel":
        # Predefined Text/Number path — both inputs are required.
        value_map["Input:AllowedLabels"] = {"value": ",".join(scorer.allowed_labels)}
        value_map["Input:FallbackLabel"] = {"value": scorer.fallback_label}
    elif pt == "scorerMeasurement":
        # Number + explicit Measurement path — single range input.
        vs = scorer.value_specification or {}
        value_map["Input:AllowedRange"] = {
            "value": f"{vs.get('min')}-{vs.get('max')} step {vs.get('step')}"
        }
    elif pt == "scorerOpenEnded":
        # OpenEnded may or may not carry predefined values. If it does
        # (constrained-plus-open), pass them so the prompt author can still
        # reference the markers as a nudge — the LLM is free to ignore.
        if scorer.allowed_labels:
            value_map["Input:AllowedLabels"] = {"value": ",".join(scorer.allowed_labels)}
        if scorer.fallback_label:
            value_map["Input:FallbackLabel"] = {"value": scorer.fallback_label}
    body = {
        "isPreview": False,
        "inputParams": {"valueMap": value_map},
        "additionalConfig": {"applicationName": "PromptTemplateGenerationsInvocable"},
    }
    payload = sf_apex.api_request(org_alias, path, method="POST", body=body)
    raw_text = _extract_response_text(payload)

    if pt == "scorerOpenEnded" and not scorer.allowed_labels:
        # Fully open: return the raw output as-is; no label matching to do.
        raw_value, reason = _split_openended_value_reason(raw_text)
        return ScoringResult(
            label=None,
            reason=reason,
            raw_value=raw_value,
            raw_response_text=raw_text,
            raw_api_payload=payload,
        )

    label, reason = _split_label_reason(
        raw_text, allowed=scorer.allowed_labels, fallback=scorer.fallback_label,
    )
    return ScoringResult(
        label=label,
        reason=reason,
        # Mirror label into raw_value so downstream consumers can rely on
        # raw_value being populated for both predefined and open paths. When
        # label matching failed, fall back to the raw candidate line.
        raw_value=label if label is not None else raw_text.splitlines()[0].strip() if raw_text.strip() else None,
        raw_response_text=raw_text,
        raw_api_payload=payload,
    )


def _extract_response_text(payload: dict | list) -> str:
    """Extract the LLM's generated text from the Connect API response.

    Einstein Prompt Template Generations returns:
      {
        "generations": [{
          "text": "<raw LLM output>",
          "structuredResponse": {"output": [...], "explanation": "..."},
          ...
        }],
        "generationErrors": [{"errorMessage": "...", ...}],  # present on failures
        "prompt": "<hydrated prompt>",
        ...
      }
    If generationErrors is populated, raise — the LLM never ran.
    """
    if isinstance(payload, dict):
        errors = payload.get("generationErrors") or []
        if errors:
            first_err = errors[0] if isinstance(errors[0], dict) else {}
            msg = first_err.get("errorMessage") or first_err.get("localizedErrorMessage") or str(first_err)
            raise RuntimeError(f"Scorer generation failed: {msg}")
        gens = payload.get("generations") or []
        if gens and isinstance(gens[0], dict):
            first = gens[0]
            text = first.get("text")
            if isinstance(text, str) and text.strip():
                return text
            sr = first.get("structuredResponse")
            if isinstance(sr, dict):
                out = sr.get("output")
                explanation = sr.get("explanation") or ""
                if isinstance(out, list) and out:
                    return f"{out[0]}\n{explanation}".strip()
                if isinstance(out, str):
                    return f"{out}\n{explanation}".strip()
    return str(payload)


def _split_openended_value_reason(text: str) -> tuple[str | None, str | None]:
    """Split raw text into (value, reason) for OpenEnded free-form scorers.

    Formats we handle:
    - Structured JSON: `{"output": "<value>", "explanation": "<reason>"}` — the
      Einstein Prompt Template Generations default. `output` may be a string
      or a list; we pick the first element.
    - Plain text: the whole response is the value; reason is None. We do NOT
      try to split first-line vs. rest here because open scorer values may
      legitimately span multiple lines (e.g. a paragraph-long summary).
    """
    stripped = text.strip()
    if not stripped:
        return None, None
    if stripped.startswith("{"):
        import json as _json
        try:
            obj = _json.loads(stripped)
        except Exception:
            obj = None
        if isinstance(obj, dict):
            out = obj.get("output")
            if out is None:
                outs = obj.get("outputs")
                if isinstance(outs, list) and outs:
                    first = outs[0]
                    if isinstance(first, dict):
                        out = first.get("value") if first.get("value") is not None else first.get("label")
                    else:
                        out = first
            explanation = obj.get("explanation") or obj.get("reason")
            reason = str(explanation).strip() if explanation else None
            if isinstance(out, list) and out:
                return str(out[0]).strip(), reason
            if isinstance(out, str):
                return out.strip(), reason
    return stripped, None


def _split_label_reason(
    text: str,
    *,
    allowed: tuple[str, ...],
    fallback: str,
) -> tuple[str | None, str | None]:
    """Parse label + reason from the LLM response.

    Two response formats are common:
    1. Structured JSON (Einstein Prompt Template Generations default):
       `{"output":["<Label>"],"explanation":"<reason>"}`
    2. Plain text — label on line 1, reason on line 2+.

    Be permissive: match labels case-insensitively against the allowed set.
    """
    stripped = text.strip()
    if not stripped:
        return None, None

    # Structured JSON response
    if stripped.startswith("{"):
        import json as _json
        try:
            obj = _json.loads(stripped)
        except Exception:
            obj = None
        if isinstance(obj, dict):
            out = obj.get("output")
            if out is None:
                # The Einstein Prompt Template Generations endpoint returns the
                # value under `outputs` (plural) as a list of {value|label} objects,
                # not `output` (singular). Handle both — mirrors
                # _split_openended_value_reason.
                outs = obj.get("outputs")
                if isinstance(outs, list) and outs:
                    first = outs[0]
                    if isinstance(first, dict):
                        out = first.get("value") if first.get("value") is not None else first.get("label")
                    else:
                        out = first
            explanation = obj.get("explanation") or obj.get("reason")
            candidate_label = None
            if isinstance(out, list) and out:
                candidate_label = str(out[0])
            elif isinstance(out, str):
                candidate_label = out
            elif out is not None:
                candidate_label = str(out)
            if candidate_label is not None:
                # The model sometimes packs "<label>\n<reason>" into a single
                # value field. Split the first line off as the label candidate
                # and fall back to it for the reason when no explanation was given.
                inline_reason = None
                if "\n" in candidate_label:
                    head, _, tail = candidate_label.partition("\n")
                    candidate_label = head
                    inline_reason = tail.strip() or None
                reason_text = str(explanation).strip() if explanation else inline_reason
                candidate_label = candidate_label.strip()
                # Case-insensitive match to allowed set.
                all_labels = (*allowed, fallback)
                for cand in all_labels:
                    if candidate_label.lower() == cand.lower():
                        return cand, reason_text
                # No match but we have a label-like output — return it as-is.
                return candidate_label, reason_text

    lines = [ln.rstrip() for ln in stripped.splitlines()]
    first = lines[0].strip()
    first_clean = re.sub(r"^[`*_'\"\s]+|[`*_'\"\s]+$", "", first)

    label = None
    all_labels = (*allowed, fallback)
    for candidate in all_labels:
        if first_clean.lower() == candidate.lower():
            label = candidate
            break
    # Sometimes the model returns "Label: reason" on a single line.
    if label is None and ":" in stripped.split("\n", 1)[0]:
        prefix, rest = stripped.split(":", 1)
        for candidate in all_labels:
            if prefix.strip().lower() == candidate.lower():
                label = candidate
                return label, rest.strip()

    reason = "\n".join(lines[1:]).strip() or None
    if label is None:
        reason = stripped
    return label, reason
