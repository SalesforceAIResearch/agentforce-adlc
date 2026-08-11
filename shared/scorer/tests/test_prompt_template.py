"""Tests for response parsing in prompt_template.

Regression coverage for the Einstein Prompt Template Generations `outputs`
(plural) response shape. A constrained OpenEnded / Measurement scorer routes
through `_split_label_reason`, which must extract the value from
`{"outputs":[{"value":"..."}], "explanation":"..."}` — the same shape
`_split_openended_value_reason` already handled — and split a "value\nreason"
blob when the model packs both into one field.
"""
from src.prompt_template import _split_label_reason, _split_openended_value_reason

ALLOWED = ("1", "2", "3", "4", "5")
FALLBACK = "NA"


def test_split_label_reason_outputs_plural_with_inline_reason():
    """The real failing case: value+reason packed into outputs[0].value."""
    raw = (
        '{"outputs":[{"value":"4\\nThe agent scheduled the delivery as requested."}],'
        '"explanation":"Largely achieved the goals, hence a 4."}'
    )
    label, reason = _split_label_reason(raw, allowed=ALLOWED, fallback=FALLBACK)
    assert label == "4"
    # Explanation wins over the inline reason when both are present.
    assert reason == "Largely achieved the goals, hence a 4."


def test_split_label_reason_outputs_plural_no_explanation_uses_inline():
    raw = '{"outputs":[{"value":"3\\nPartially helpful answer."}]}'
    label, reason = _split_label_reason(raw, allowed=ALLOWED, fallback=FALLBACK)
    assert label == "3"
    assert reason == "Partially helpful answer."


def test_split_label_reason_outputs_plural_value_only():
    raw = '{"outputs":[{"value":"5"}],"explanation":"Fully resolved."}'
    label, reason = _split_label_reason(raw, allowed=ALLOWED, fallback=FALLBACK)
    assert label == "5"
    assert reason == "Fully resolved."


def test_split_label_reason_outputs_plural_label_key():
    """Some responses key the value as `label` rather than `value`."""
    raw = '{"outputs":[{"label":"2"}],"explanation":"Barely helpful."}'
    label, reason = _split_label_reason(raw, allowed=ALLOWED, fallback=FALLBACK)
    assert label == "2"
    assert reason == "Barely helpful."


def test_split_label_reason_output_singular_still_works():
    """The pre-existing `output` (singular) shape must keep working."""
    raw = '{"output":["4"],"explanation":"Helpful."}'
    label, reason = _split_label_reason(raw, allowed=ALLOWED, fallback=FALLBACK)
    assert label == "4"
    assert reason == "Helpful."


def test_split_label_reason_unmatched_value_returned_as_is():
    """A value outside the allowed set is surfaced verbatim, not dropped."""
    raw = '{"outputs":[{"value":"7"}],"explanation":"Off-scale."}'
    label, reason = _split_label_reason(raw, allowed=ALLOWED, fallback=FALLBACK)
    assert label == "7"
    assert reason == "Off-scale."


def test_split_openended_outputs_plural_unchanged():
    """The free-form path already handled outputs-plural; guard against regression."""
    raw = '{"outputs":[{"value":"a paragraph summary"}],"explanation":"why"}'
    value, reason = _split_openended_value_reason(raw)
    assert value == "a paragraph summary"
    assert reason == "why"
