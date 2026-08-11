"""Parity tests against Core's StdmBuilderTest.java.

Each test here mirrors a test in
  core/agentforce-session-tracing-impl/test/unit/java/src/agentforce/session/tracing/impl/
    evals/runtime/enrichment/StdmBuilderTest.java

Row fixtures are ports of createSessionParticipantRow/createMessageRow/createStepRow
helpers in that file.
"""
from __future__ import annotations

import pytest

from src.stdm_builder import (
    assemble_stdm_detail_views,
    get_field_as_string,
    parse_timestamp,
    calculate_duration_ms,
)


# ---- Row fixture helpers (ports of StdmBuilderTest.java) ----

def make_participant_row(session_id: str = "session1", participant_id: str = "participant1") -> dict:
    return {
        "sessionId": session_id,
        "sessionStartTimestamp": "2024-01-15 14:30:00",
        "sessionVoiceCallId": None,
        "sessionChannel": "Web",
        "messagingSessionId": None,
        "aiAgentApiName": "TestAgent",
        "participantRole": "USER",
        "aiAgentTemplateApiName": None,
        "aiAgentType": None,
        "aiAgentVersionApiName": None,
        "participantId": participant_id,
        "participantObject": "User",
        "sessionParticipantId": f"session-participant-{participant_id}",
    }


def make_message_row(session_id: str, interaction_id: str, participant_id: str) -> dict:
    return {
        "sessionId": session_id,
        "interactionId": interaction_id,
        "interactionStartTimestamp": "2024-01-15 14:30:00",
        "interactionEndTimestamp": "2024-01-15 14:30:05",
        "topicApiName": "TestTopic",
        "interactionType": "TURN",
        "messageType": "USER_MESSAGE",
        "contentText": "Test message content",
        "messageSentTimestamp": "2024-01-15 14:30:01",
        "sessionParticipantId": participant_id,
        "messageId": f"message-{interaction_id}",
    }


def make_step_row(session_id: str, interaction_id: str) -> dict:
    return {
        "sessionId": session_id,
        "stepInteractionId": interaction_id,
        "stepId": "step1",
        "stepName": "TestStep",
        "stepInput": "input data",
        "stepOutput": "output data",
        "stepStartTimestamp": "2024-01-15 14:30:01",
        "stepEndTimestamp": "2024-01-15 14:30:02",
        "stepType": "ACTION_STEP",
    }


# ---- Tests ----

def test_throws_when_org_id_null():
    with pytest.raises(ValueError):
        assemble_stdm_detail_views(None, [], [], [make_participant_row()])  # type: ignore[arg-type]


def test_throws_when_session_participant_rows_empty():
    with pytest.raises(ValueError):
        assemble_stdm_detail_views(
            "orgId",
            [make_message_row("s", "i", "session-participant-participant1")],
            [],
            [],
        )


def test_throws_when_message_rows_empty():
    with pytest.raises(ValueError):
        assemble_stdm_detail_views("orgId", [], [], [make_participant_row()])


def test_builds_session_successfully():
    result = assemble_stdm_detail_views(
        "00D123456789ABC",
        [make_message_row("session1", "interaction1", "session-participant-participant1")],
        [make_step_row("session1", "interaction1")],
        [make_participant_row()],
    )
    assert len(result) == 1
    s = result[0]
    assert s["sessionState"]["sessionId"] == "session1"
    assert s["actors"]
    assert s["metrics"]
    assert s["runs"]


def test_builds_multiple_sessions():
    result = assemble_stdm_detail_views(
        "orgId",
        [
            make_message_row("session1", "interaction1", "session-participant-participant1"),
            make_message_row("session2", "interaction2", "session-participant-participant2"),
        ],
        [
            make_step_row("session1", "interaction1"),
            make_step_row("session2", "interaction2"),
        ],
        [
            make_participant_row("session1", "participant1"),
            make_participant_row("session2", "participant2"),
        ],
    )
    assert len(result) == 2


def test_calculates_metrics_correctly():
    result = assemble_stdm_detail_views(
        "orgId",
        [
            make_message_row("session1", "interaction1", "session-participant-participant1"),
            make_message_row("session1", "interaction2", "session-participant-participant1"),
        ],
        [
            make_step_row("session1", "interaction1"),
            make_step_row("session1", "interaction2"),
        ],
        [make_participant_row()],
    )
    s = result[0]
    metrics = s["metrics"]
    assert metrics["turns"] == 2
    assert metrics["durationMs"] >= 0


def test_filters_messages_with_missing_actor():
    """Message references an actor not in the actors list → whole session is dropped
    (exception caught in Core's assembleStdmDetailViews per-session try/catch)."""
    result = assemble_stdm_detail_views(
        "orgId",
        [
            make_message_row("session1", "interaction1", "session-participant-participant1"),
            make_message_row("session2", "interaction2", "nonexistent"),
        ],
        [
            make_step_row("session1", "interaction1"),
            make_step_row("session2", "interaction2"),
        ],
        [
            make_participant_row("session1", "participant1"),
            make_participant_row("session2", "participant2"),
        ],
    )
    assert len(result) == 1
    assert result[0]["sessionState"]["sessionId"] == "session1"
    assert len(result[0]["runs"]) == 1
    assert len(result[0]["runs"][0]["messages"]) == 1


def test_filters_steps_with_null_id():
    participant = make_participant_row()
    message = make_message_row("session1", "interaction1", "session-participant-participant1")
    step_null_id = make_step_row("session1", "interaction1")
    step_null_id["stepId"] = None
    valid_step = make_step_row("session1", "interaction1")
    result = assemble_stdm_detail_views(
        "orgId",
        [message],
        [step_null_id, valid_step],
        [participant],
    )
    # Core behavior: any null stepId makes StdmStep.build() throw, which bubbles up and
    # the whole session is excluded from the output list.
    assert len(result) == 0


def test_session_without_participant_id_drops_actor():
    """participant row with null SESSION_PARTICIPANT_ID → actor dropped → no actors → session excluded."""
    participant = make_participant_row("session1", "participant1")
    participant["sessionParticipantId"] = None
    message = make_message_row("session1", "interaction1", "session-participant-participant1")
    result = assemble_stdm_detail_views(
        "orgId", [message], [], [participant],
    )
    assert len(result) == 0


def test_session_without_interaction_id_excluded():
    """Message with null INTERACTION_ID → 'Session has no interactions' → excluded."""
    participant = make_participant_row("session1", "participant1")
    message = make_message_row("session1", "interaction1", "session-participant-participant1")
    message["interactionId"] = None
    result = assemble_stdm_detail_views(
        "orgId", [message], [], [participant],
    )
    assert len(result) == 0


def test_deduplicates_actors_by_id():
    """Two rows for the same participantId with different sessionParticipantIds → one actor."""
    p1 = make_participant_row("session1", "participant1")
    p1["sessionParticipantId"] = "sp-A"
    p1["aiAgentApiName"] = "Agent1"
    p2 = make_participant_row("session1", "participant1")
    p2["sessionParticipantId"] = "sp-B"
    p2["aiAgentApiName"] = "Agent2"
    message = {
        **make_message_row("session1", "interaction1", "sp-A"),
    }
    result = assemble_stdm_detail_views("orgId", [message], [], [p1, p2])
    assert len(result) == 1
    actors = result[0]["actors"]
    assert len(actors) == 1
    assert actors[0]["id"] == "participant1"
    # First occurrence wins.
    assert actors[0]["agentApiName"] == "Agent1"


def test_output_schema_shape_matches_core():
    """Structural check: output has sessionState, actors, metrics, runs with all
    required fields populated and matching Core's SessionView shape."""
    result = assemble_stdm_detail_views(
        "orgId",
        [make_message_row("session1", "interaction1", "session-participant-participant1")],
        [make_step_row("session1", "interaction1")],
        [make_participant_row()],
    )
    s = result[0]
    # Top-level shape.
    assert set(s.keys()) >= {"sessionState", "actors", "metrics", "runs"}
    # SessionState required fields (per SessionView.validate()).
    assert "sessionId" in s["sessionState"]
    assert "startTimestamp" in s["sessionState"]
    assert "channel" in s["sessionState"]
    # Actor required fields (ActorView.validate()).
    for actor in s["actors"]:
        assert "id" in actor
        assert "participantObject" in actor
        assert "role" in actor
        # sessionParticipantId must NOT leak — it's @JsonIgnore in Core.
        assert "sessionParticipantId" not in actor
        assert "_sessionParticipantId" not in actor
    # Metrics required fields.
    assert "durationMs" in s["metrics"]
    assert "turns" in s["metrics"]
    # Run required fields (RunView.validate()).
    for run in s["runs"]:
        assert "runId" in run
        assert "topicName" in run
        assert "startTimestamp" in run
        assert "endTimestamp" in run
        assert "durationMs" in run
        assert "messages" in run
        assert "agentLoop" in run
        # interactionType must NOT leak.
        assert "interactionType" not in run
        assert "_interactionType" not in run
        # Each message has required fields.
        for msg in run["messages"]:
            assert "message" in msg
            assert "timestamp" in msg
            assert "actorRole" in msg
            assert "actorId" in msg
            assert "type" in msg
        # Agent loop has steps array.
        assert "steps" in run["agentLoop"]
        for step in run["agentLoop"]["steps"]:
            assert "stepId" in step
            assert "type" in step
            assert "name" in step
            assert "startTimestamp" in step
            assert "endTimestamp" in step
            assert "durationMs" in step


def test_turn_run_always_has_topic_name_when_topic_null():
    """Regression: prompt-template generations schema requires runs[].topicName, but
    _non_null() stripped the key when a TURN's topicApiName was null/NOT_SET. TURN runs
    must fall back to the placeholder so the required field is always present."""
    from src.stdm_builder import PLACEHOLDER_TOPIC
    participant = make_participant_row()
    msg_null_topic = make_message_row("session1", "interaction1", "session-participant-participant1")
    msg_null_topic["topicApiName"] = None  # Data Cloud null topic.
    msg_not_set_topic = make_message_row("session1", "interaction2", "session-participant-participant1")
    msg_not_set_topic["topicApiName"] = "NOT_SET"  # Data Cloud sentinel.
    result = assemble_stdm_detail_views(
        "orgId", [msg_null_topic, msg_not_set_topic], [], [participant],
    )
    assert len(result) == 1
    runs = result[0]["runs"]
    assert len(runs) == 2
    for run in runs:
        # The key must exist AND be non-empty (schema-required).
        assert "topicName" in run, "topicName missing — would fail generations schema"
        assert run["topicName"] == PLACEHOLDER_TOPIC


def test_turn_run_preserves_real_topic_name():
    """A present topicApiName is passed through unchanged (not clobbered by the fallback)."""
    participant = make_participant_row()
    msg = make_message_row("session1", "interaction1", "session-participant-participant1")
    msg["topicApiName"] = "OrderManagement"
    result = assemble_stdm_detail_views("orgId", [msg], [], [participant])
    assert result[0]["runs"][0]["topicName"] == "OrderManagement"


def test_not_set_sentinel_becomes_null():
    """Data Cloud returns 'NOT_SET' for null values; getFieldAsString strips that."""
    assert get_field_as_string({"k": "NOT_SET"}, "k") is None
    assert get_field_as_string({"k": ""}, "k") is None
    assert get_field_as_string({"k": None}, "k") is None
    assert get_field_as_string({"k": "value"}, "k") == "value"


def test_parse_timestamp_handles_iso_and_space_forms():
    assert parse_timestamp("2024-01-15 14:30:00") is not None
    assert parse_timestamp("2024-01-15T14:30:00") is not None
    assert parse_timestamp("2026-04-26T12:35:40.476Z") is not None
    assert parse_timestamp(None) is None
    assert parse_timestamp("") is None
    assert parse_timestamp("null") is None
    assert parse_timestamp("bogus") is None


def test_duration_ms_zero_when_start_or_end_missing():
    from datetime import datetime
    assert calculate_duration_ms(None, datetime(2024, 1, 1)) == 0
    assert calculate_duration_ms(datetime(2024, 1, 1), None) == 0
    assert calculate_duration_ms(None, None) == 0


def test_non_turn_run_filtered_out_of_runs():
    """Non-TURN interactions appear in metrics.durationMs calculation but not in runs[]."""
    participant = make_participant_row()
    # One TURN, one non-TURN session-end-ish interaction.
    turn_msg = make_message_row("session1", "interaction1", "session-participant-participant1")
    session_end_msg = make_message_row("session1", "interaction2", "session-participant-participant1")
    session_end_msg["interactionType"] = "SESSION_END"
    result = assemble_stdm_detail_views(
        "orgId", [turn_msg, session_end_msg], [], [participant],
    )
    assert len(result) == 1
    runs = result[0]["runs"]
    # Only TURN should appear.
    assert len(runs) == 1
    # But turn count still 1 (only TURN interactions counted).
    assert result[0]["metrics"]["turns"] == 1
