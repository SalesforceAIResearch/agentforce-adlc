"""Port of Core's StdmBuilder to Python.

Source:
  core/agentforce-session-tracing-impl/java/src/agentforce/session/tracing/impl/evals/runtime/
    event/processing/enrichment/StdmBuilder.java

Output schema matches Core's DTOs under `evals/dto/stdm/` exactly:
  Session { orgId (@JsonIgnore), sessionState, actors[], metrics, runs[] }
  StdmSessionState { sessionId, startTimestamp, channel, messagingSessionId?, voiceCallId? }
  StdmActor { id, participantObject, role, agentApiName?, agentVersion?, agentType?,
              agentTemplate?  (sessionParticipantId is @JsonIgnore) }
  StdmMetrics { durationMs, turns }
  StdmRun { runId, topicName, startTimestamp, endTimestamp, durationMs,
            messages[], agentLoop (interactionType is @JsonIgnore) }
  StdmMessage { message, timestamp, actorRole, actorId, type }
  StdmAgentLoop { steps[] }
  StdmStep { stepId, type, name, startTimestamp, endTimestamp, durationMs, input?, output? }

All DTOs are @JsonInclude(NON_NULL): null fields omitted from output.

Key column-name constants match Core's QueryResultFields (the SQL column aliases).
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone

# ---- Column name constants (must match SQL aliases in datacloud_query.py) ----

class MessageCol:
    SESSION_ID = "sessionId"
    INTERACTION_ID = "interactionId"
    MESSAGE_ID = "messageId"
    INTERACTION_TYPE = "interactionType"
    INTERACTION_START_TIMESTAMP = "interactionStartTimestamp"
    INTERACTION_END_TIMESTAMP = "interactionEndTimestamp"
    TOPIC_API_NAME = "topicApiName"
    MESSAGE_TYPE = "messageType"
    CONTENT_TEXT = "contentText"
    MESSAGE_SENT_TIMESTAMP = "messageSentTimestamp"
    SESSION_PARTICIPANT_ID = "sessionParticipantId"


class StepCol:
    SESSION_ID = "sessionId"
    INTERACTION_ID = "stepInteractionId"  # aliased differently in Core's Step query
    STEP_ID = "stepId"
    STEP_NAME = "stepName"
    STEP_INPUT = "stepInput"
    STEP_OUTPUT = "stepOutput"
    STEP_START_TIMESTAMP = "stepStartTimestamp"
    STEP_END_TIMESTAMP = "stepEndTimestamp"
    STEP_TYPE = "stepType"


class ParticipantCol:
    SESSION_ID = "sessionId"
    SESSION_START_TIMESTAMP = "sessionStartTimestamp"
    SESSION_VOICE_CALL_ID = "sessionVoiceCallId"
    SESSION_CHANNEL = "sessionChannel"
    MESSAGING_SESSION_ID = "messagingSessionId"
    AI_AGENT_API_NAME = "aiAgentApiName"
    PARTICIPANT_ROLE = "participantRole"
    AI_AGENT_TEMPLATE_API_NAME = "aiAgentTemplateApiName"
    AI_AGENT_TYPE = "aiAgentType"
    AI_AGENT_VERSION_API_NAME = "aiAgentVersionApiName"
    PARTICIPANT_ID = "participantId"
    PARTICIPANT_OBJECT = "participantObject"
    SESSION_PARTICIPANT_ID = "sessionParticipantId"


TURN = "TURN"
PLACEHOLDER_TOPIC = "placeHolder"
EMPTY_VALUE_STRING = "NOT_SET"


# ---- Utility functions (ports of EventProcessingUtils) ----

def get_field_as_string(fields: dict, key: str) -> str | None:
    """Port of EventProcessingUtils.getFieldAsString. Returns null for missing, null,
    empty-string, or the 'NOT_SET' sentinel used by Data Cloud."""
    if not fields or key is None:
        return None
    value = fields.get(key)
    if value is None:
        return None
    s = str(value)
    if s == EMPTY_VALUE_STRING or s == "":
        return None
    return s


def parse_timestamp(timestamp: str | None) -> datetime | None:
    """Port of EventProcessingUtils.parseTimestamp. Tolerates 'YYYY-MM-DD HH:MM:SS',
    ISO '2024-01-15T14:30:00', and ISO with timezone offset ('2026-04-26T12:35:40.476Z').
    Returns None on failure."""
    if timestamp is None or timestamp == "" or timestamp == "null":
        return None
    normalized = timestamp.replace(" ", "T") if " " in timestamp else timestamp
    # Python's fromisoformat doesn't accept 'Z' before 3.11; our interpreter is 3.11 so Z works.
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None


def calculate_duration_ms(start: datetime | None, end: datetime | None) -> int:
    """Port of EventProcessingUtils.calculateDurationMs. Returns 0 if either is null."""
    if start is None or end is None:
        return 0
    # Normalize timezone to avoid naive/aware mismatch.
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    delta = end - start
    return int(delta.total_seconds() * 1000)


def group_rows_by_field(rows: list[dict], field_key: str) -> "OrderedDict[str, list[dict]]":
    """Port of EventProcessingUtils.groupRowsByField. Preserves insertion order (mirrors
    Java's HashMap iteration as experienced in fixture tests — but OrderedDict gives us
    determinism). Raises IllegalStateException-equivalent on missing key."""
    grouped: "OrderedDict[str, list[dict]]" = OrderedDict()
    for row in rows:
        value = get_field_as_string(row, field_key)
        if not value or not value.strip():
            raise RuntimeError(f"Row missing required field: {field_key}")
        grouped.setdefault(value, []).append(row)
    return grouped


def _iso(dt: datetime | None) -> str | None:
    """Serialize datetime to the format Core's Connect API expects for dateTimeString inputs:
    'YYYY-MM-DDTHH:MM:SS.sss+0000'. Matches Core's test fixture exactly."""
    if dt is None:
        return None
    # Normalize to UTC; emit Java-style +0000 (not +00:00).
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    # Always emit milliseconds; never microseconds.
    ms = dt.microsecond // 1000
    return dt.strftime(f"%Y-%m-%dT%H:%M:%S.{ms:03d}+0000")


def _non_null(d: dict) -> dict:
    """Strip keys whose value is None (mirrors @JsonInclude(NON_NULL))."""
    return {k: v for k, v in d.items() if v is not None}


# ---- Public API ----

def assemble_stdm_detail_views(
    org_id: str,
    message_rows: list[dict],
    step_rows: list[dict] | None,
    session_participant_rows: list[dict],
) -> list[dict]:
    """Port of StdmBuilder.assembleStdmDetailViews.

    Returns a list of Session dicts (one per input session) matching Core's Session DTO
    JSON serialization, sans orgId (which is @JsonIgnore in Core's output).
    """
    if org_id is None or not org_id.strip():
        raise ValueError("orgId cannot be null or empty")
    if not session_participant_rows:
        raise ValueError("sessionParticipantRows cannot be null or empty")
    if not message_rows:
        raise ValueError("messageRows cannot be null or empty")
    if step_rows is None:
        step_rows = []

    messages_by_session = group_rows_by_field(message_rows, MessageCol.SESSION_ID)
    steps_by_session = group_rows_by_field(step_rows, StepCol.SESSION_ID) if step_rows else {}
    participants_by_session = group_rows_by_field(
        session_participant_rows, ParticipantCol.SESSION_ID,
    )

    result: list[dict] = []
    for session_id, participants in participants_by_session.items():
        messages = messages_by_session.get(session_id, [])
        steps = steps_by_session.get(session_id, [])
        try:
            detail = _build_stdm_detail_view(messages, steps, participants)
            result.append(detail)
        except Exception as e:
            # Mirror Core: log and skip.
            import sys
            print(f"Failed to build detail view for sessionId {session_id}: {e}", file=sys.stderr)
    return result


def _build_stdm_detail_view(
    message_rows: list[dict],
    step_rows: list[dict],
    session_participant_rows: list[dict],
) -> dict:
    session_state = _build_session_state(session_participant_rows)
    actors = _build_actors(session_participant_rows)
    if not actors:
        raise ValueError(f"No actors found for sessionId {session_state.get('sessionId')}")
    runs = _build_runs(message_rows, step_rows, actors)
    # Metrics with ALL interactions (before TURN filter).
    metrics = _build_metrics(session_state, runs)
    # Filter runs to only TURN interactions; sort by startTimestamp.
    turn_runs = [r for r in runs if r.get("_interactionType") == TURN]
    turn_runs.sort(key=lambda r: r.get("startTimestamp") or "")
    # Strip the internal _interactionType marker before output.
    output_runs = [_non_null({k: v for k, v in r.items() if not k.startswith("_")}) for r in turn_runs]

    # Deduplicate actors by id keeping first occurrence.
    dedup_actors = _deduplicate_actors_by_id(actors)
    # Strip internal _sessionParticipantId.
    output_actors = [
        _non_null({k: v for k, v in a.items() if not k.startswith("_")})
        for a in dedup_actors
    ]

    return _non_null({
        "sessionState": session_state,
        "actors": output_actors,
        "metrics": metrics,
        "runs": output_runs,
    })


def _deduplicate_actors_by_id(actors: list[dict]) -> list[dict]:
    """Port of StdmBuilder.deduplicateActorsById. Keeps first occurrence per actor id."""
    seen: "OrderedDict[str, dict]" = OrderedDict()
    for a in actors:
        aid = a.get("id")
        if aid is None:
            continue
        if aid not in seen:
            seen[aid] = a
    return list(seen.values())


def _build_session_state(session_participant_rows: list[dict]) -> dict:
    fields = session_participant_rows[0]
    start_ts = parse_timestamp(get_field_as_string(fields, ParticipantCol.SESSION_START_TIMESTAMP))
    return _non_null({
        "sessionId": get_field_as_string(fields, ParticipantCol.SESSION_ID),
        "startTimestamp": _iso(start_ts),
        "channel": get_field_as_string(fields, ParticipantCol.SESSION_CHANNEL),
        "messagingSessionId": get_field_as_string(fields, ParticipantCol.MESSAGING_SESSION_ID),
        "voiceCallId": get_field_as_string(fields, ParticipantCol.SESSION_VOICE_CALL_ID),
    })


def _build_actors(session_participant_rows: list[dict]) -> list[dict]:
    actors: list[dict] = []
    for row in session_participant_rows:
        actor = _build_actor(row)
        if actor is not None:
            actors.append(actor)
    return actors


def _build_actor(fields: dict) -> dict | None:
    session_participant_id = get_field_as_string(fields, ParticipantCol.SESSION_PARTICIPANT_ID)
    if session_participant_id is None:
        return None
    role = get_field_as_string(fields, ParticipantCol.PARTICIPANT_ROLE)
    participant_object = get_field_as_string(fields, ParticipantCol.PARTICIPANT_OBJECT)
    # `participantObject` is required by the STDM schema but some DMO rows have it null
    # (e.g. older agent data). Infer from role when missing — matches Core's own test
    # fixtures: USER → "User", AGENT → "GenAiPlannerDefinition".
    if participant_object is None:
        if role == "USER":
            participant_object = "User"
        elif role == "AGENT":
            participant_object = "GenAiPlannerDefinition"
    return {
        "id": get_field_as_string(fields, ParticipantCol.PARTICIPANT_ID),
        "_sessionParticipantId": session_participant_id,  # @JsonIgnore — internal-only
        "participantObject": participant_object,
        "role": role,
        "agentApiName": get_field_as_string(fields, ParticipantCol.AI_AGENT_API_NAME),
        "agentVersion": get_field_as_string(fields, ParticipantCol.AI_AGENT_VERSION_API_NAME),
        "agentType": get_field_as_string(fields, ParticipantCol.AI_AGENT_TYPE),
        "agentTemplate": get_field_as_string(fields, ParticipantCol.AI_AGENT_TEMPLATE_API_NAME),
    }


def _build_runs(
    message_rows: list[dict],
    step_rows: list[dict],
    actors: list[dict],
) -> list[dict]:
    # Validate first message has interaction id (mirrors Core's loud failure).
    if not message_rows or get_field_as_string(message_rows[0], MessageCol.INTERACTION_ID) is None:
        session_id = (
            get_field_as_string(message_rows[0], MessageCol.SESSION_ID)
            if message_rows else "<unknown>"
        )
        raise ValueError(f"Session has no interactions (sessionId={session_id})")

    messages_by_interaction = group_rows_by_field(message_rows, MessageCol.INTERACTION_ID)
    steps_by_interaction = (
        group_rows_by_field(step_rows, StepCol.INTERACTION_ID) if step_rows else {}
    )
    # Build actor index by sessionParticipantId for message → actor lookup.
    actor_by_spid: dict[str, dict] = {}
    for a in actors:
        spid = a.get("_sessionParticipantId")
        if spid and spid not in actor_by_spid:
            actor_by_spid[spid] = a

    runs: list[dict] = []
    for interaction_id, interaction_messages in messages_by_interaction.items():
        run = _build_run(
            interaction_id,
            interaction_messages,
            steps_by_interaction.get(interaction_id, []),
            actor_by_spid,
        )
        if run is not None:
            runs.append(run)
    # Sort by startTimestamp (Core's StdmRun implements Comparable on startTimestamp).
    runs.sort(key=lambda r: r.get("startTimestamp") or "")
    return runs


def _build_run(
    interaction_id: str,
    interaction_messages: list[dict],
    interaction_steps: list[dict],
    actor_by_spid: dict[str, dict],
) -> dict | None:
    first = interaction_messages[0]
    start_ts = parse_timestamp(get_field_as_string(first, MessageCol.INTERACTION_START_TIMESTAMP))
    end_ts = parse_timestamp(get_field_as_string(first, MessageCol.INTERACTION_END_TIMESTAMP))
    interaction_type = get_field_as_string(first, MessageCol.INTERACTION_TYPE)
    # Non-TURN interactions get a placeholder topic (will be filtered out in assemble phase
    # since we only emit TURN runs — the placeholder only surfaces if someone changes that
    # filter). Matches Core.
    #
    # TURN interactions must always carry a topicName: the prompt-template generations
    # schema marks `runs[].topicName` as required, and _non_null() would otherwise strip
    # the key when the source topicApiName is null/NOT_SET (common when a turn didn't
    # resolve to a named topic). Fall back to the placeholder so the field is always present.
    if interaction_type == TURN:
        topic_name = get_field_as_string(first, MessageCol.TOPIC_API_NAME) or PLACEHOLDER_TOPIC
    else:
        topic_name = PLACEHOLDER_TOPIC

    messages = _build_messages(interaction_messages, actor_by_spid)
    agent_loop = _build_agent_loop(interaction_steps)

    return {
        "runId": interaction_id,
        "topicName": topic_name,
        "startTimestamp": _iso(start_ts),
        "endTimestamp": _iso(end_ts),
        "durationMs": calculate_duration_ms(start_ts, end_ts),
        "messages": messages,
        "agentLoop": agent_loop,
        "_interactionType": interaction_type,  # @JsonIgnore — for filter/metrics
    }


def _build_messages(message_rows: list[dict], actor_by_spid: dict[str, dict]) -> list[dict]:
    out: list[dict] = []
    for row in message_rows:
        msg = _build_message(row, actor_by_spid)
        if msg is not None:
            out.append(msg)
    out.sort(key=lambda m: m.get("timestamp") or "")
    return out


def _build_message(fields: dict, actor_by_spid: dict[str, dict]) -> dict | None:
    message_id = get_field_as_string(fields, MessageCol.MESSAGE_ID)
    if message_id is None:
        return None
    message_content = get_field_as_string(fields, MessageCol.CONTENT_TEXT)
    participant_id = get_field_as_string(fields, MessageCol.SESSION_PARTICIPANT_ID)
    actor = actor_by_spid.get(participant_id) if participant_id else None
    if actor is None:
        raise ValueError(
            f"Actor not found for participantId: {participant_id} "
            f"(available: {list(actor_by_spid.keys())})"
        )
    ts = parse_timestamp(get_field_as_string(fields, MessageCol.MESSAGE_SENT_TIMESTAMP))
    return _non_null({
        "message": message_content,
        "timestamp": _iso(ts),
        "actorRole": actor.get("role"),
        "actorId": actor.get("id"),
        "type": get_field_as_string(fields, MessageCol.MESSAGE_TYPE),
    })


def _build_agent_loop(step_rows: list[dict]) -> dict:
    steps = [_build_step(row) for row in step_rows]
    steps.sort(key=lambda s: s.get("startTimestamp") or "")
    return {"steps": [_non_null(s) for s in steps]}


def _build_step(fields: dict) -> dict:
    step_id = get_field_as_string(fields, StepCol.STEP_ID)
    if step_id is None:
        # Core's StdmStep.Builder.build() Objects.requireNonNull throws when stepId is null.
        raise ValueError("stepId is required")
    start_ts = parse_timestamp(get_field_as_string(fields, StepCol.STEP_START_TIMESTAMP))
    end_ts = parse_timestamp(get_field_as_string(fields, StepCol.STEP_END_TIMESTAMP))
    return {
        "stepId": step_id,
        "name": get_field_as_string(fields, StepCol.STEP_NAME),
        "type": get_field_as_string(fields, StepCol.STEP_TYPE),
        "startTimestamp": _iso(start_ts),
        "endTimestamp": _iso(end_ts),
        "durationMs": calculate_duration_ms(start_ts, end_ts),
        "input": get_field_as_string(fields, StepCol.STEP_INPUT),
        "output": get_field_as_string(fields, StepCol.STEP_OUTPUT),
    }


def _build_metrics(session_state: dict, runs: list[dict]) -> dict:
    total_duration_ms = 0
    turns = 0
    if runs:
        # Sort runs by endTimestamp to find the latest, matching Core.
        sorted_runs = sorted(runs, key=lambda r: r.get("endTimestamp") or "")
        last_run = sorted_runs[-1]
        start_ts = parse_timestamp(session_state.get("startTimestamp"))
        end_ts = parse_timestamp(last_run.get("endTimestamp"))
        total_duration_ms = calculate_duration_ms(start_ts, end_ts)
        turns = sum(1 for r in runs if r.get("_interactionType") == TURN)
    return {"durationMs": total_duration_ms, "turns": turns}
