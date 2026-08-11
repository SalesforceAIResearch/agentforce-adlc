"""Data Cloud SQL builders and executor.

Ports Core's three query builders from
  core/agentforce-session-tracing-impl/java/src/agentforce/session/tracing/impl/datacloud/query/
    - MessageQueryBuilder.java
    - StepQueryBuilder.java
    - SessionParticipantQueryBuilder.java

Uses the default dataspace only: tables get `ssot__<base>__dlm`, fields get `ssot__<base>__c`.
Callers don't pass `DataSpaceDto`; we hardcode the default behavior.

Also provides `run_sql(org, sql)` which POSTs to /services/data/v62.0/ssot/query and
normalizes the {data:[{rowData:[...]}], metadata:[{name:...}]} response into a list of
column-name-keyed dicts, matching Java's `List<Map<String, Object>>` shape that Core's
`StdmBuilder` consumes.
"""
from __future__ import annotations

from typing import Any, Sequence

from . import sf_apex

SSOT_QUERY_PATH = "/services/data/v62.0/ssot/query"

# Column identifiers for the default dataspace. These mirror DataSpaceUtil.tableIdentifier()
# and DataSpaceUtil.fieldIdentifier() with dataspace="default".

# Tables
SESSION_TABLE = '"ssot__AiAgentSession__dlm"'
INTERACTION_TABLE = '"ssot__AiAgentInteraction__dlm"'
MESSAGE_TABLE = '"ssot__AiAgentInteractionMessage__dlm"'
STEP_TABLE = '"ssot__AiAgentInteractionStep__dlm"'
PARTICIPANT_TABLE = '"ssot__AiAgentSessionParticipant__dlm"'

# Common fields
SESSION_ID_COL = '"ssot__Id__c"'
SESSION_START_TS_COL = '"ssot__StartTimestamp__c"'
EXTERNAL_SOURCE_ID_COL = '"ssot__ExternalSourceId__c"'

# Interaction
INTERACTION_ID_COL = '"ssot__Id__c"'
INTERACTION_START_TS_COL = '"ssot__StartTimestamp__c"'
INTERACTION_END_TS_COL = '"ssot__EndTimestamp__c"'
INTERACTION_SESSION_ID_COL = '"ssot__AiAgentSessionId__c"'
INTERACTION_TYPE_COL = '"ssot__AiAgentInteractionType__c"'
TOPIC_API_NAME_COL = '"ssot__TopicApiName__c"'

# Session
SESSION_VOICE_CALL_ID_COL = '"ssot__RelatedVoiceCallId__c"'
SESSION_CHANNEL_COL = '"ssot__AiAgentChannelType__c"'
MESSAGING_SESSION_ID_COL = '"ssot__RelatedMessagingSessionId__c"'

# Message
MESSAGE_ID_COL = '"ssot__Id__c"'
MESSAGE_TYPE_COL = '"ssot__AiAgentInteractionMessageType__c"'
MESSAGE_CONTENT_COL = '"ssot__ContentText__c"'
MESSAGE_TS_COL = '"ssot__MessageSentTimestamp__c"'
MESSAGE_SESSION_PARTICIPANT_ID_COL = '"ssot__AiAgentSessionParticipantId__c"'
MESSAGE_INTERACTION_ID_COL = '"ssot__AiAgentInteractionId__c"'

# Step
STEP_ID_COL = '"ssot__Id__c"'
STEP_INTERACTION_ID_COL = '"ssot__AiAgentInteractionId__c"'
STEP_NAME_COL = '"ssot__Name__c"'
STEP_INPUT_COL = '"ssot__InputValueText__c"'
STEP_OUTPUT_COL = '"ssot__OutputValueText__c"'
STEP_START_TS_COL = '"ssot__StartTimestamp__c"'
STEP_END_TS_COL = '"ssot__EndTimestamp__c"'
STEP_TYPE_COL = '"ssot__AiAgentInteractionStepType__c"'

# Participant
PARTICIPANT_SESSION_ID_COL = '"ssot__AiAgentSessionId__c"'
AI_AGENT_API_NAME_COL = '"ssot__AiAgentApiName__c"'
PARTICIPANT_ROLE_COL = '"ssot__AiAgentSessionParticipantRole__c"'
AI_AGENT_TEMPLATE_API_NAME_COL = '"ssot__AiAgentTemplateApiName__c"'
AI_AGENT_TYPE_COL = '"ssot__AiAgentType__c"'
AI_AGENT_VERSION_API_NAME_COL = '"ssot__AiAgentVersionApiName__c"'
PARTICIPANT_ID_FIELD_COL = '"ssot__ParticipantId__c"'
PARTICIPANT_OBJECT_COL = '"ssot__ParticipantObject__c"'
SESSION_PARTICIPANT_ID_COL = '"ssot__Id__c"'
PARTICIPANT_START_TS_COL = '"ssot__StartTimestamp__c"'


def _escape(value: str) -> str:
    return value.replace("'", "''")


def _session_filter(session_ids: Sequence[str]) -> str:
    if not session_ids:
        raise ValueError("session_ids cannot be empty")
    return ", ".join(f"'{_escape(sid)}'" for sid in session_ids)


def _external_source_filter(org_id: str | None, *, alias: str) -> str:
    """Return an `AND <alias>.ExternalSourceId = '<org_id>'` clause, or '' when org_id is None.

    The STDM `ssot__ExternalSourceId__c` value is NOT always the org id returned by
    `sf org display` — depending on how sessions were ingested it can be a different
    18-char id, or null. Callers that can't determine the right value (or want all
    sessions in the dataspace) pass org_id=None to skip the filter entirely.
    """
    if org_id is None:
        return ""
    return f"  AND {alias}.{EXTERNAL_SOURCE_ID_COL} = '{_escape(org_id)}'\n"


def build_message_sql(session_ids: Sequence[str], org_id: str | None) -> str:
    """Port of MessageQueryBuilder.getQueryTemplate() for default dataspace, no time window."""
    session_filter = _session_filter(session_ids)
    return (
        "SELECT\n"
        f"    s.{SESSION_ID_COL} AS sessionId,\n"
        f"    ia.{INTERACTION_ID_COL} AS interactionId,\n"
        f"    ia.{INTERACTION_START_TS_COL} AS interactionStartTimestamp,\n"
        f"    ia.{INTERACTION_END_TS_COL} AS interactionEndTimestamp,\n"
        f"    ia.{TOPIC_API_NAME_COL} AS topicApiName,\n"
        f"    ia.{INTERACTION_TYPE_COL} AS interactionType,\n"
        f"    im.{MESSAGE_TYPE_COL} AS messageType,\n"
        f"    im.{MESSAGE_CONTENT_COL} AS contentText,\n"
        f"    im.{MESSAGE_TS_COL} AS messageSentTimestamp,\n"
        f"    im.{MESSAGE_SESSION_PARTICIPANT_ID_COL} AS sessionParticipantId,\n"
        f"    im.{MESSAGE_ID_COL} AS messageId\n"
        f"FROM {SESSION_TABLE} s\n"
        "LEFT JOIN (\n"
        "    SELECT \n"
        f"        {INTERACTION_ID_COL}, \n"
        f"        {INTERACTION_SESSION_ID_COL}, \n"
        f"        {INTERACTION_START_TS_COL}, \n"
        f"        {INTERACTION_END_TS_COL},\n"
        f"        {TOPIC_API_NAME_COL},\n"
        f"        {INTERACTION_TYPE_COL}\n"
        f"    FROM {INTERACTION_TABLE}\n"
        f") ia ON ia.{INTERACTION_SESSION_ID_COL} = s.{SESSION_ID_COL}\n"
        "LEFT JOIN (\n"
        "    SELECT \n"
        f"        {MESSAGE_ID_COL},\n"
        f"        {MESSAGE_INTERACTION_ID_COL}, \n"
        f"        {MESSAGE_TYPE_COL}, \n"
        f"        {MESSAGE_CONTENT_COL}, \n"
        f"        {MESSAGE_TS_COL}, \n"
        f"        {MESSAGE_SESSION_PARTICIPANT_ID_COL}\n"
        f"    FROM {MESSAGE_TABLE}\n"
        f") im ON im.{MESSAGE_INTERACTION_ID_COL} = ia.{INTERACTION_ID_COL}\n"
        f"WHERE s.{SESSION_ID_COL} IN ({session_filter})\n"
        f"{_external_source_filter(org_id, alias='s')}"
    )


def build_step_sql(session_ids: Sequence[str], org_id: str | None) -> str:
    """Port of StepQueryBuilder.getQueryTemplate() — INNER JOINs, filters TURN + ACTION_STEP.

    Core's template has `<subqueryWhere> AND <type>='TURN'` where the first part is empty
    when no time window is set (leading to malformed SQL). We emit `WHERE <type>='TURN'`
    directly since we always operate without a time window for the CLI use case.
    """
    session_filter = _session_filter(session_ids)
    return (
        "SELECT\n"
        f"    s.{SESSION_ID_COL} AS sessionId,\n"
        f"    st.{STEP_INTERACTION_ID_COL} AS stepInteractionId,\n"
        f"    st.{STEP_ID_COL} AS stepId,\n"
        f"    st.{STEP_NAME_COL} AS stepName,\n"
        f"    st.{STEP_INPUT_COL} AS stepInput,\n"
        f"    st.{STEP_OUTPUT_COL} AS stepOutput,\n"
        f"    st.{STEP_START_TS_COL} AS stepStartTimestamp,\n"
        f"    st.{STEP_END_TS_COL} AS stepEndTimestamp,\n"
        f"    st.{STEP_TYPE_COL} AS stepType\n"
        f"FROM {SESSION_TABLE} s\n"
        "JOIN (\n"
        "    SELECT \n"
        f"        {INTERACTION_ID_COL}, \n"
        f"        {INTERACTION_SESSION_ID_COL}, \n"
        f"        {INTERACTION_START_TS_COL}\n"
        f"    FROM {INTERACTION_TABLE}\n"
        f"    WHERE {INTERACTION_TYPE_COL} = 'TURN'\n"
        f") ia ON ia.{INTERACTION_SESSION_ID_COL} = s.{SESSION_ID_COL}\n"
        "JOIN (\n"
        "    SELECT \n"
        f"        {STEP_ID_COL},\n"
        f"        {STEP_INTERACTION_ID_COL},\n"
        f"        {STEP_NAME_COL},\n"
        f"        {STEP_INPUT_COL},\n"
        f"        {STEP_OUTPUT_COL},\n"
        f"        {STEP_START_TS_COL},\n"
        f"        {STEP_END_TS_COL},\n"
        f"        {STEP_TYPE_COL}\n"
        f"    FROM {STEP_TABLE}\n"
        f"    WHERE {STEP_TYPE_COL} = 'ACTION_STEP'\n"
        f") st ON st.{STEP_INTERACTION_ID_COL} = ia.{INTERACTION_ID_COL}\n"
        f"WHERE s.{SESSION_ID_COL} IN ({session_filter})\n"
        f"{_external_source_filter(org_id, alias='s')}"
    )


def build_participant_sql(session_ids: Sequence[str], org_id: str | None) -> str:
    """Port of SessionParticipantQueryBuilder.getQueryTemplate()."""
    session_filter = _session_filter(session_ids)
    return (
        "SELECT\n"
        f"    s.{SESSION_ID_COL} AS sessionId,\n"
        f"    s.{SESSION_START_TS_COL} AS sessionStartTimestamp,\n"
        f"    s.{SESSION_VOICE_CALL_ID_COL} AS sessionVoiceCallId,\n"
        f"    s.{SESSION_CHANNEL_COL} AS sessionChannel,\n"
        f"    s.{MESSAGING_SESSION_ID_COL} AS messagingSessionId,\n"
        f"    participant.{AI_AGENT_API_NAME_COL} AS aiAgentApiName,\n"
        f"    participant.{PARTICIPANT_ROLE_COL} AS participantRole,\n"
        f"    participant.{AI_AGENT_TEMPLATE_API_NAME_COL} AS aiAgentTemplateApiName,\n"
        f"    participant.{AI_AGENT_TYPE_COL} AS aiAgentType,\n"
        f"    participant.{AI_AGENT_VERSION_API_NAME_COL} AS aiAgentVersionApiName,\n"
        f"    participant.{PARTICIPANT_ID_FIELD_COL} AS participantId,\n"
        f"    participant.{PARTICIPANT_OBJECT_COL} AS participantObject,\n"
        f"    participant.{SESSION_PARTICIPANT_ID_COL} AS sessionParticipantId\n"
        f"FROM {SESSION_TABLE} s\n"
        "LEFT JOIN (\n"
        "    SELECT \n"
        f"        {PARTICIPANT_SESSION_ID_COL}, \n"
        f"        {AI_AGENT_API_NAME_COL}, \n"
        f"        {PARTICIPANT_ROLE_COL},\n"
        f"        {AI_AGENT_TEMPLATE_API_NAME_COL}, \n"
        f"        {AI_AGENT_TYPE_COL}, \n"
        f"        {AI_AGENT_VERSION_API_NAME_COL},\n"
        f"        {PARTICIPANT_ID_FIELD_COL}, \n"
        f"        {PARTICIPANT_OBJECT_COL}, \n"
        f"        {SESSION_PARTICIPANT_ID_COL}, \n"
        f"        {PARTICIPANT_START_TS_COL}\n"
        f"    FROM {PARTICIPANT_TABLE}\n"
        f") participant ON participant.{PARTICIPANT_SESSION_ID_COL} = s.{SESSION_ID_COL}\n"
        f"WHERE s.{SESSION_ID_COL} IN ({session_filter})\n"
        f"{_external_source_filter(org_id, alias='s')}"
    )


def build_session_list_sql(
    org_id: str | None,
    *,
    agent_api_name: str | None = None,
    limit: int = 20,
) -> str:
    """List recent sessions in the org. Optional filter by agent API name.

    Replaces AgentforceOptimizeService.findSessions. Simpler: no GenAiPlannerDefinition
    fallback — for agents that populate ssot__AiAgentApiName__c the direct filter works;
    we document the limitation.
    """
    filter_clause = ""
    if agent_api_name:
        escaped_agent = _escape(agent_api_name)
        # Restrict via EXISTS on participant table.
        filter_clause = (
            f"  AND EXISTS (\n"
            f"    SELECT 1 FROM {PARTICIPANT_TABLE} p\n"
            f"    WHERE p.{PARTICIPANT_SESSION_ID_COL} = s.{SESSION_ID_COL}\n"
            f"      AND p.{AI_AGENT_API_NAME_COL} = '{escaped_agent}'\n"
            f"  )\n"
        )
    return (
        "SELECT\n"
        f"    s.{SESSION_ID_COL} AS sessionId,\n"
        f"    s.{SESSION_START_TS_COL} AS sessionStartTimestamp,\n"
        f"    s.{SESSION_CHANNEL_COL} AS sessionChannel\n"
        f"FROM {SESSION_TABLE} s\n"
        f"WHERE s.{SESSION_ID_COL} IS NOT NULL\n"
        f"{_external_source_filter(org_id, alias='s')}"
        f"{filter_clause}"
        f"ORDER BY s.{SESSION_START_TS_COL} DESC\n"
        f"LIMIT {int(limit)}\n"
    )


def build_agent_list_sql(org_id: str | None, *, limit: int = 100) -> str:
    """List distinct agents that have participated in sessions in this org.

    Pulls from the participant table and filters to AGENT role rows. Returns
    aiAgentApiName + aiAgentType so callers can tell bot types apart.
    """
    return (
        "SELECT DISTINCT\n"
        f"    p.{AI_AGENT_API_NAME_COL} AS aiAgentApiName,\n"
        f"    p.{AI_AGENT_TYPE_COL} AS aiAgentType\n"
        f"FROM {PARTICIPANT_TABLE} p\n"
        f"JOIN {SESSION_TABLE} s ON s.{SESSION_ID_COL} = p.{PARTICIPANT_SESSION_ID_COL}\n"
        f"WHERE p.{PARTICIPANT_ROLE_COL} = 'AGENT'\n"
        f"{_external_source_filter(org_id, alias='s')}"
        f"  AND p.{AI_AGENT_API_NAME_COL} IS NOT NULL\n"
        f"  AND p.{AI_AGENT_API_NAME_COL} != 'NOT_SET'\n"
        f"ORDER BY p.{AI_AGENT_API_NAME_COL}\n"
        f"LIMIT {int(limit)}\n"
    )


def run_sql(org_alias: str, sql: str) -> list[dict[str, Any]]:
    """Run a Data Cloud SQL query and return rows as column-name-keyed dicts.

    The /services/data/v62.0/ssot/query response already returns `data` as a list of
    column-name-keyed dicts (the alias set via `AS xxx` in the SELECT becomes the key),
    so we just pass it through after error-check.
    """
    payload = sf_apex.api_request(
        org_alias, SSOT_QUERY_PATH, method="POST", body={"sql": sql},
    )
    return _normalize_rows(payload)


def _normalize_rows(payload: Any) -> list[dict[str, Any]]:
    # Error responses come back as {"errorCode": "...", "message": "..."} or a list wrapping one.
    if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "errorCode" in payload[0]:
        err = payload[0]
        raise RuntimeError(f"Data Cloud SQL error: {err.get('errorCode')}: {err.get('message')}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected /ssot/query response shape: {type(payload).__name__}")
    if "errorCode" in payload:
        raise RuntimeError(f"Data Cloud SQL error: {payload.get('errorCode')}: {payload.get('message')}")
    data = payload.get("data") or []
    rows: list[dict[str, Any]] = []
    for row in data:
        if isinstance(row, dict):
            rows.append(row)
    return rows
