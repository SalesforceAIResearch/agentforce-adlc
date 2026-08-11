"""Extract a human-readable chat transcript from a canonical STDM SessionView.

The STDM JSON built by `stdm_builder` nests conversation text under
`runs[].messages[]`, each message carrying `actorRole` (USER / AGENT / …) and
the raw `message` text. This module flattens that into an ordered list of
turns and renders compact previews for the results table + the companion UI.

Kept separate from `stdm_builder` on purpose: that module is a byte-for-shape
port of Core's `StdmBuilder` guarded by parity tests, so presentation-only
helpers live here.
"""
from __future__ import annotations

import html

# Roles the STDM actor model emits (see stdm_builder._build_actor). We normalize
# to two speaker buckets for display; anything unrecognized falls back to AGENT
# so system/tool text never masquerades as a user utterance.
_USER_ROLES = frozenset({"USER"})


def extract_transcript(session_view: dict) -> list[dict]:
    """Flatten a SessionView into ordered turns: [{speaker, role, text}, …].

    `speaker` is "User" or "Agent"; `role` is the raw STDM actorRole. Messages
    are already timestamp-sorted within each run, and runs are startTimestamp-
    sorted, so a straight walk preserves conversational order. Empty/whitespace
    messages are dropped.
    """
    turns: list[dict] = []
    if not isinstance(session_view, dict):
        return turns
    runs = session_view.get("runs") or []
    for run in runs:
        if not isinstance(run, dict):
            continue
        for msg in run.get("messages") or []:
            if not isinstance(msg, dict):
                continue
            # Message text arrives from Data Cloud HTML-encoded (e.g. `I&#39;m`);
            # decode for human display. This is presentation only — the STDM the
            # scorer LLM receives is untouched.
            text = html.unescape(msg.get("message") or "").strip()
            if not text:
                continue
            role = (msg.get("actorRole") or "").upper()
            speaker = "User" if role in _USER_ROLES else "Agent"
            turns.append({"speaker": speaker, "role": role, "text": text})
    return turns


def _first_by_speaker(turns: list[dict], speaker: str) -> str | None:
    for t in turns:
        if t.get("speaker") == speaker:
            return t.get("text")
    return None


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())  # collapse newlines/runs of whitespace
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def transcript_preview(turns: list[dict], *, user_chars: int = 90,
                       agent_chars: int = 120) -> str:
    """One-line "User: … / Agent: …" preview, each side truncated with an ellipsis.

    Always surfaces the first user utterance and the first agent response so the
    reviewer sees what was asked and (part of) how the agent answered — the shape
    the PM asked for. Returns "" when there are no turns.
    """
    if not turns:
        return ""
    user = _first_by_speaker(turns, "User")
    agent = _first_by_speaker(turns, "Agent")
    parts: list[str] = []
    if user:
        parts.append(f"User: {_clip(user, user_chars)}")
    if agent:
        parts.append(f"Agent: {_clip(agent, agent_chars)}")
    if not parts:
        # No user/agent split (rare) — fall back to the very first turn.
        parts.append(_clip(turns[0].get("text", ""), user_chars + agent_chars))
    return " / ".join(parts)
