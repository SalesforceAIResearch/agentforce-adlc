"""Tests for transcript extraction + preview rendering.

Fixtures use the canonical STDM SessionView shape produced by stdm_builder:
`runs[].messages[]`, each message carrying `actorRole` + `message` text.
"""
from __future__ import annotations

from src.transcript import extract_transcript, transcript_preview


def _msg(role, text, ts):
    return {"message": text, "actorRole": role, "timestamp": ts, "type": "X"}


def _session(*runs):
    return {"runs": list(runs)}


def _run(*messages):
    return {"runId": "i1", "messages": list(messages)}


def test_extract_orders_turns_and_labels_speakers():
    sv = _session(
        _run(
            _msg("USER", "I want a refund", "2024-01-15T14:30:01Z"),
            _msg("AGENT", "I can help with that", "2024-01-15T14:30:03Z"),
        ),
        _run(
            _msg("USER", "Thanks", "2024-01-15T14:31:00Z"),
        ),
    )
    turns = extract_transcript(sv)
    assert [(t["speaker"], t["text"]) for t in turns] == [
        ("User", "I want a refund"),
        ("Agent", "I can help with that"),
        ("User", "Thanks"),
    ]
    assert turns[0]["role"] == "USER"


def test_extract_drops_empty_and_whitespace_messages():
    sv = _session(_run(
        _msg("USER", "   ", "t1"),
        _msg("AGENT", "", "t2"),
        _msg("AGENT", "real answer", "t3"),
    ))
    turns = extract_transcript(sv)
    assert [t["text"] for t in turns] == ["real answer"]


def test_extract_unknown_role_defaults_to_agent():
    """System/tool text must not masquerade as a user utterance."""
    sv = _session(_run(_msg("SYSTEM", "tool output", "t1")))
    turns = extract_transcript(sv)
    assert turns[0]["speaker"] == "Agent"
    assert turns[0]["role"] == "SYSTEM"


def test_extract_tolerates_malformed_input():
    assert extract_transcript(None) == []
    assert extract_transcript({}) == []
    assert extract_transcript({"runs": None}) == []
    assert extract_transcript({"runs": [None, "nope", {}]}) == []
    assert extract_transcript({"runs": [{"messages": None}]}) == []


def test_preview_shows_user_and_agent():
    turns = [
        {"speaker": "User", "role": "USER", "text": "I want a refund"},
        {"speaker": "Agent", "role": "AGENT", "text": "I can help with that"},
    ]
    preview = transcript_preview(turns)
    assert preview == "User: I want a refund / Agent: I can help with that"


def test_preview_truncates_with_ellipsis():
    long_user = "u" * 200
    long_agent = "a" * 200
    turns = [
        {"speaker": "User", "role": "USER", "text": long_user},
        {"speaker": "Agent", "role": "AGENT", "text": long_agent},
    ]
    preview = transcript_preview(turns, user_chars=10, agent_chars=12)
    assert preview == "User: uuuuuuuuu… / Agent: aaaaaaaaaaa…"
    # Each side is clipped to its budget (including the ellipsis).
    assert "uuuuuuuuu…" in preview
    assert "aaaaaaaaaaa…" in preview


def test_preview_collapses_whitespace():
    turns = [{"speaker": "User", "role": "USER", "text": "line one\n\n  line two"}]
    assert transcript_preview(turns) == "User: line one line two"


def test_preview_first_of_each_speaker():
    """Even with many turns, the preview surfaces the first user + first agent."""
    turns = [
        {"speaker": "User", "role": "USER", "text": "first q"},
        {"speaker": "Agent", "role": "AGENT", "text": "first a"},
        {"speaker": "User", "role": "USER", "text": "second q"},
    ]
    assert transcript_preview(turns) == "User: first q / Agent: first a"


def test_preview_empty_when_no_turns():
    assert transcript_preview([]) == ""


def test_extract_decodes_html_entities():
    """Data Cloud stores message text HTML-encoded (e.g. `I&#39;m`); the display
    transcript must show the real characters, not the entities."""
    sv = _session(_run(
        _msg("AGENT", "Hi, I&#39;m an AI service assistant &amp; here to help.", "t1"),
        _msg("USER", "It&#39;s &quot;urgent&quot; &lt;really&gt;", "t2"),
    ))
    turns = extract_transcript(sv)
    assert turns[0]["text"] == "Hi, I'm an AI service assistant & here to help."
    assert turns[1]["text"] == 'It\'s "urgent" <really>'


def test_preview_decodes_html_entities():
    sv = _session(_run(
        _msg("USER", "can you help?", "t1"),
        _msg("AGENT", "Sure, I&#39;m happy to help.", "t2"),
    ))
    preview = transcript_preview(extract_transcript(sv))
    assert preview == "User: can you help? / Agent: Sure, I'm happy to help."
    assert "&#39;" not in preview


def test_preview_agent_only_session():
    turns = [{"speaker": "Agent", "role": "AGENT", "text": "Hello, how can I help?"}]
    assert transcript_preview(turns) == "Agent: Hello, how can I help?"
