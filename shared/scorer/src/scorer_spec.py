"""Load and validate scorer specifications from YAML."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

SCORER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
# Salesforce caps AiAgentScorerDefinition fullName at 35 characters. Catching
# this client-side avoids a wasted round-trip through deploy/retrieve/activate
# only to fail at step 4 with a generic "unknown error" from the metadata API.
SCORER_NAME_MAX_LEN = 35
BUNDLED_DIR = Path(__file__).resolve().parent.parent / "scorer_specs"


class ScorerSpecError(ValueError):
    pass


ALLOWED_OUTCOME_TYPES = ("Pass", "Fail", "NotApplicable")

# One of the 12 lightning subtypes supported by AiAgentScorerDefinition.
# Mirrors SUPPORTED_LIGHTNING_TYPES in @salesforce/agents' agentScorer.ts.
SUPPORTED_LIGHTNING_TYPES = (
    "lightning__textType",
    "lightning__multilineTextType",
    "lightning__richTextType",
    "lightning__numberType",
    "lightning__integerType",
    "lightning__booleanType",
    "lightning__dateType",
    "lightning__dateTimeType",
    "lightning__dateTimeStringType",
    "lightning__urlType",
    "lightning__objectType",
    "lightning__listType",
)

ALLOWED_SEMANTIC_TYPES = ("Dimension", "Measurement")
ALLOWED_SCORER_TYPES = ("Predefined", "OpenEnded")
# The three GenAiPromptTemplate types the platform recognizes for scorers.
PT_TYPE_MULTILABEL = "scorerMultilabel"
PT_TYPE_MEASUREMENT = "scorerMeasurement"
PT_TYPE_OPEN_ENDED = "scorerOpenEnded"


@dataclass(frozen=True)
class ScorerSpec:
    name: str
    description: str
    # User-facing type: "Text" | "Number" | "OpenEnded".
    data_type: str
    primary_model: str
    # For OpenEnded scorers with no predefined values, allowed_labels is an
    # empty tuple and fallback_label is the empty string. Callers that render
    # the AiAgentScorerDefinition XML consult `values`/`metadata_data_type`
    # instead of these two fields.
    allowed_labels: tuple[str, ...]
    fallback_label: str
    prompt: str
    # OpenEnded-only. One of SUPPORTED_LIGHTNING_TYPES.
    lightning_type: str | None = None
    # Explicit scorerType override. Auto-derived from data_type when absent:
    # OpenEnded → "OpenEnded"; Text/Number → "Predefined".
    scorer_type: str | None = None
    # None | "Dimension" | "Measurement". Auto-derived when absent:
    # Number → "Measurement"; Text/OpenEnded → "Dimension".
    semantic_type: str | None = None
    # Optional — only used when deploying as a full AiAgentScorerDefinition
    # (not needed for the generations-endpoint scoring path).
    agent_api_name: str | None = None
    is_active: bool = False
    sampling_rate: float = 1.0
    # Numeric-scorer extras. Only meaningful when data_type == "Number".
    value_specification: dict | None = None  # {"min": float, "max": float, "step": float, "threshold": float | None}
    outcome_types: dict | None = None  # maps allowed_labels entry -> "Pass" | "Fail" | "NotApplicable"
    label_meanings: dict | None = None  # maps allowed_labels entry -> human-readable scale legend text

    @property
    def metadata_data_type(self) -> str:
        """The value that goes into <dataType> in the scorer XML.

        - "Text" or "Number" for Predefined scorers.
        - "LightningType" for OpenEnded scorers (the actual subtype goes in
          the separate <lightningType> element).
        """
        if self.data_type == "OpenEnded":
            return "LightningType"
        return self.data_type

    @property
    def pt_template_type(self) -> str:
        """The GenAiPromptTemplate <type> element value (without the
        `agentforce_session_tracing__` prefix).

        Mirrors getPromptTemplateType() in agentScorer.ts:154-162.

        Note: scorerMeasurement is picked ONLY when semantic_type is
        EXPLICITLY set to Measurement in the YAML. Existing Number specs
        that don't set it stay on the historical scorerMultilabel PT — their
        prompts use {!$Input:AllowedLabels} markers, and switching them to
        Measurement would require rewriting to {!$Input:AllowedRange}.
        """
        if self.effective_scorer_type == "OpenEnded":
            return PT_TYPE_OPEN_ENDED
        if self.semantic_type == "Measurement":
            return PT_TYPE_MEASUREMENT
        return PT_TYPE_MULTILABEL

    @property
    def effective_scorer_type(self) -> str:
        if self.scorer_type is not None:
            return self.scorer_type
        return "OpenEnded" if self.data_type == "OpenEnded" else "Predefined"

    @property
    def effective_semantic_type(self) -> str:
        if self.semantic_type is not None:
            return self.semantic_type
        return "Measurement" if self.data_type == "Number" else "Dimension"

    @property
    def values(self) -> tuple[str, ...]:
        """Alias for allowed_labels. Empty tuple = free-form OpenEnded."""
        return self.allowed_labels

    @property
    def fallback_value(self) -> str:
        """Alias for fallback_label."""
        return self.fallback_label


def load(source: str) -> ScorerSpec:
    """Load a scorer spec by path or by bundled name.

    If `source` ends in .yaml/.yml or contains a path separator, treat it as a path.
    Otherwise look it up in the bundled scorer_specs/ directory.
    """
    path = _resolve_path(source)
    if not path.exists():
        raise ScorerSpecError(f"Scorer spec not found: {source} (looked at {path})")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ScorerSpecError(f"Scorer spec must be a YAML mapping, got {type(raw).__name__}")
    return _validate(raw, origin=str(path))


def _resolve_path(source: str) -> Path:
    if "/" in source or source.endswith((".yaml", ".yml")):
        return Path(source).expanduser()
    return BUNDLED_DIR / f"{source}.yaml"


def _validate(raw: dict, *, origin: str) -> ScorerSpec:
    required = ["name", "description", "data_type", "primary_model", "prompt"]
    missing = [k for k in required if k not in raw]
    if missing:
        raise ScorerSpecError(f"{origin}: missing required fields: {missing}")

    name = raw["name"]
    if not isinstance(name, str) or not SCORER_NAME_RE.match(name):
        raise ScorerSpecError(
            f"{origin}: `name` must match {SCORER_NAME_RE.pattern} (got {name!r})"
        )
    if len(name) > SCORER_NAME_MAX_LEN:
        raise ScorerSpecError(
            f"{origin}: `name` must be at most {SCORER_NAME_MAX_LEN} characters "
            f"(Salesforce AiAgentScorerDefinition limit) — got {len(name)}: {name!r}"
        )

    data_type = raw["data_type"]
    # Text/Number are BC-only for existing YAMLs on disk; the scorer-create skill
    # now always emits OpenEnded (its 12 lightning subtypes cover both).
    if data_type not in ("Text", "Number", "OpenEnded"):
        raise ScorerSpecError(
            f"{origin}: data_type must be one of 'Text', 'Number', 'OpenEnded' "
            f"(got {data_type!r})"
        )

    # `values` is the new field name; `allowed_labels` is the legacy one.
    # Text/Number require a non-empty list; OpenEnded may omit it entirely
    # (fully free-form) or provide a nudge list (constrained-plus-open).
    labels_raw = _first_present(raw, ("values", "allowed_labels"))
    if data_type in ("Text", "Number"):
        if labels_raw is None:
            raise ScorerSpecError(
                f"{origin}: data_type={data_type} requires `values` "
                f"(or the legacy `allowed_labels`)"
            )
    if labels_raw is not None and (not isinstance(labels_raw, list)):
        raise ScorerSpecError(
            f"{origin}: `values` must be a list (got {type(labels_raw).__name__})"
        )
    labels: list[str] = [str(x) for x in (labels_raw or [])]
    if data_type in ("Text", "Number") and not labels:
        raise ScorerSpecError(
            f"{origin}: `values` must be non-empty for data_type={data_type}"
        )
    if len(labels) != len(set(labels)):
        raise ScorerSpecError(f"{origin}: `values` has duplicates")
    if data_type == "Number":
        for lbl in labels:
            try:
                float(lbl)
            except ValueError:
                raise ScorerSpecError(
                    f"{origin}: data_type=Number requires numeric values "
                    f"(got {lbl!r})"
                )

    # Fallback is required for Text and Number (both have closed lists). For
    # OpenEnded it's optional — free-form scorers may omit it entirely, and
    # constrained-plus-open scorers may or may not designate a fallback.
    fallback_raw = _first_present(raw, ("fallback_value", "fallback_label"))
    if data_type in ("Text", "Number"):
        if fallback_raw is None:
            raise ScorerSpecError(
                f"{origin}: data_type={data_type} requires `fallback_value` "
                f"(or the legacy `fallback_label`)"
            )
        fallback = str(fallback_raw)
        if fallback not in labels:
            raise ScorerSpecError(
                f"{origin}: `fallback_value` ({fallback!r}) must be one of `values`"
            )
    else:
        # OpenEnded: fallback is optional and, unlike Text/Number, is NOT
        # required to be a member of `values`. A synthetic "can't decide"
        # label (e.g. `NA`, `Uncertain`, `NOT_SET`) is a legitimate fallback
        # — the scorer-definition XML template will materialize it as its
        # own <outputEnumValue> with <isFallback>true</isFallback>+
        # <isSystemFallback>true</isSystemFallback> when it isn't already
        # present in `values`. Matches the reference tc07_number_measurement_pt
        # scorer's use of NOT_SET as a synthetic fallback.
        fallback = "" if fallback_raw is None else str(fallback_raw)

    # OpenEnded requires a lightning_type; Text/Number reject it.
    lightning_type = raw.get("lightning_type")
    if data_type == "OpenEnded":
        if lightning_type is None:
            raise ScorerSpecError(
                f"{origin}: data_type=OpenEnded requires `lightning_type` "
                f"(one of {SUPPORTED_LIGHTNING_TYPES})"
            )
        if lightning_type not in SUPPORTED_LIGHTNING_TYPES:
            raise ScorerSpecError(
                f"{origin}: `lightning_type` must be one of "
                f"{SUPPORTED_LIGHTNING_TYPES} (got {lightning_type!r})"
            )
    else:
        if lightning_type is not None:
            raise ScorerSpecError(
                f"{origin}: `lightning_type` is only valid for data_type=OpenEnded"
            )

    scorer_type = raw.get("scorer_type")
    if scorer_type is not None and scorer_type not in ALLOWED_SCORER_TYPES:
        raise ScorerSpecError(
            f"{origin}: `scorer_type` must be one of {ALLOWED_SCORER_TYPES} "
            f"(got {scorer_type!r})"
        )

    semantic_type = raw.get("semantic_type")
    if semantic_type is not None and semantic_type not in ALLOWED_SEMANTIC_TYPES:
        raise ScorerSpecError(
            f"{origin}: `semantic_type` must be one of {ALLOWED_SEMANTIC_TYPES} "
            f"(got {semantic_type!r})"
        )

    prompt = raw["prompt"]
    if not isinstance(prompt, str) or not prompt.strip():
        raise ScorerSpecError(f"{origin}: `prompt` must be a non-empty string")
    _validate_prompt_markers(prompt, data_type=data_type, origin=origin)

    agent_api_name = raw.get("agent_api_name")
    if agent_api_name is not None and not isinstance(agent_api_name, str):
        raise ScorerSpecError(f"{origin}: `agent_api_name` must be a string if present")

    is_active = raw.get("is_active", False)
    if not isinstance(is_active, bool):
        raise ScorerSpecError(f"{origin}: `is_active` must be a boolean if present")

    sampling_rate = raw.get("sampling_rate", 1.0)
    if not isinstance(sampling_rate, (int, float)) or not 0.0 <= float(sampling_rate) <= 1.0:
        raise ScorerSpecError(f"{origin}: `sampling_rate` must be a number in [0.0, 1.0]")

    value_specification = _validate_value_specification(
        raw.get("value_specification"), data_type=data_type, origin=origin,
    )
    outcome_types = _validate_outcome_types(
        raw.get("outcome_types"), labels=labels, origin=origin,
    )
    _cross_validate_outcome_threshold(
        outcome_types=outcome_types,
        value_specification=value_specification,
        data_type=data_type,
        origin=origin,
    )
    label_meanings = _validate_label_meanings(
        raw.get("label_meanings"), labels=labels, origin=origin,
    )

    return ScorerSpec(
        name=name,
        description=str(raw["description"]),
        data_type=data_type,
        primary_model=str(raw["primary_model"]),
        allowed_labels=tuple(labels),
        fallback_label=fallback,
        prompt=prompt,
        lightning_type=lightning_type,
        scorer_type=scorer_type,
        semantic_type=semantic_type,
        agent_api_name=agent_api_name,
        is_active=is_active,
        sampling_rate=float(sampling_rate),
        value_specification=value_specification,
        outcome_types=outcome_types,
        label_meanings=label_meanings,
    )


def _first_present(raw: dict, keys: tuple[str, ...]):
    """Return the value of the first key in `keys` that exists in `raw`, else None.
    Used for legacy field aliases (values vs allowed_labels)."""
    for k in keys:
        if k in raw:
            return raw[k]
    return None


def _validate_prompt_markers(
    prompt: str, *, data_type: str, origin: str,
) -> None:
    # Every prompt must reference the session via one of two markers. The
    # Data Action form is preferred — it's the shape Salesforce's UI emits and
    # the platform's auto-sampling pipeline drives. The raw Input:Session form
    # stays supported for callers that want the full nested STDM payload.
    session_markers = (
        "{!$SalesforceDataAction:getSession.chatTranscript}",
        "{!$Input:Session}",
    )
    if not any(m in prompt for m in session_markers):
        raise ScorerSpecError(
            f"{origin}: prompt must reference the session via either "
            f"{session_markers[0]} (recommended; works with platform "
            f"auto-sampling) or {session_markers[1]} (raw STDM JSON)"
        )
    # For closed-list scorers, the prompt must reference the label markers —
    # they're required PT inputs. For OpenEnded free-form, the markers are
    # optional; when values ARE supplied (constrained-plus-open), we still
    # accept a prompt without the markers because the runtime supplies the
    # values via input variables regardless.
    if data_type in ("Text", "Number"):
        for marker in ("{!$Input:AllowedLabels}", "{!$Input:FallbackLabel}"):
            if marker not in prompt:
                raise ScorerSpecError(
                    f"{origin}: prompt is missing required marker {marker}"
                )


def _validate_value_specification(
    raw: dict | None, *, data_type: str, origin: str,
) -> dict | None:
    if raw is None:
        return None
    if data_type != "Number":
        raise ScorerSpecError(
            f"{origin}: `value_specification` is only valid for data_type=Number"
        )
    if not isinstance(raw, dict):
        raise ScorerSpecError(
            f"{origin}: `value_specification` must be a mapping"
        )
    required_keys = ("min", "max", "step")
    missing = [k for k in required_keys if k not in raw]
    if missing:
        raise ScorerSpecError(
            f"{origin}: `value_specification` missing required keys: {missing}"
        )
    spec: dict = {}
    for k in ("min", "max", "step"):
        v = raw[k]
        if not isinstance(v, (int, float)):
            raise ScorerSpecError(
                f"{origin}: `value_specification.{k}` must be a number (got {v!r})"
            )
        spec[k] = float(v)
    if spec["min"] > spec["max"]:
        raise ScorerSpecError(
            f"{origin}: `value_specification.min` ({spec['min']}) "
            f"must be <= max ({spec['max']})"
        )
    if spec["step"] <= 0:
        raise ScorerSpecError(
            f"{origin}: `value_specification.step` must be > 0 (got {spec['step']})"
        )
    if "threshold" in raw and raw["threshold"] is not None:
        t = raw["threshold"]
        if not isinstance(t, (int, float)):
            raise ScorerSpecError(
                f"{origin}: `value_specification.threshold` must be a number"
            )
        spec["threshold"] = float(t)
    return spec


def _validate_outcome_types(
    raw: dict | None, *, labels: list, origin: str,
) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ScorerSpecError(f"{origin}: `outcome_types` must be a mapping")
    out: dict[str, str] = {}
    for k, v in raw.items():
        key = str(k)
        if key not in labels:
            raise ScorerSpecError(
                f"{origin}: `outcome_types` key {key!r} is not in `values`"
            )
        if v not in ALLOWED_OUTCOME_TYPES:
            raise ScorerSpecError(
                f"{origin}: `outcome_types[{key!r}]` must be one of "
                f"{ALLOWED_OUTCOME_TYPES} (got {v!r})"
            )
        out[key] = v
    return out


def _cross_validate_outcome_threshold(
    *,
    outcome_types: dict | None,
    value_specification: dict | None,
    data_type: str,
    origin: str,
) -> None:
    """Enforce the server-side rule for Number scorers with a threshold:
    - value >= threshold → outcomeType must be 'Pass'
    - value <  threshold → outcomeType must be 'Fail'
    Rows with outcomeType 'NotApplicable' are ignored.
    """
    if data_type != "Number" or not outcome_types or not value_specification:
        return
    threshold = value_specification.get("threshold")
    if threshold is None:
        return
    for label, outcome in outcome_types.items():
        if outcome == "NotApplicable":
            continue
        try:
            numeric = float(label)
        except ValueError:
            continue
        expected = "Pass" if numeric >= threshold else "Fail"
        if outcome != expected:
            raise ScorerSpecError(
                f"{origin}: outcome_types[{label!r}] is {outcome!r} but the "
                f"server requires {expected!r} "
                f"(value {numeric} {'>=' if numeric >= threshold else '<'} "
                f"threshold {threshold})."
            )


def _validate_label_meanings(
    raw: dict | None, *, labels: list, origin: str,
) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ScorerSpecError(f"{origin}: `label_meanings` must be a mapping")
    out: dict[str, str] = {}
    for k, v in raw.items():
        key = str(k)
        if key not in labels:
            raise ScorerSpecError(
                f"{origin}: `label_meanings` key {key!r} is not in `values`"
            )
        if not isinstance(v, str):
            raise ScorerSpecError(
                f"{origin}: `label_meanings[{key!r}]` must be a string"
            )
        out[key] = v
    return out
