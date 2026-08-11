"""Snapshot tests for datacloud_query module."""
from __future__ import annotations

from src.datacloud_query import (
    build_message_sql,
    build_step_sql,
    build_participant_sql,
    build_session_list_sql,
    _normalize_rows,
)

ORG_ID = "00DSB00000u1Hkx2AE"
SID = "019dc9c6-30aa-788c-98d7-02aebd2c03ed"


def test_message_sql_has_all_expected_columns():
    sql = build_message_sql([SID], ORG_ID)
    for col_alias in [
        "AS sessionId", "AS interactionId", "AS interactionStartTimestamp",
        "AS interactionEndTimestamp", "AS topicApiName", "AS interactionType",
        "AS messageType", "AS contentText", "AS messageSentTimestamp",
        "AS sessionParticipantId", "AS messageId",
    ]:
        assert col_alias in sql, f"missing {col_alias} in message SQL"
    assert "LEFT JOIN" in sql
    assert 'FROM "ssot__AiAgentSession__dlm" s' in sql
    assert 'FROM "ssot__AiAgentInteraction__dlm"' in sql
    assert 'FROM "ssot__AiAgentInteractionMessage__dlm"' in sql
    assert f"'{SID}'" in sql
    assert f"'{ORG_ID}'" in sql


def test_step_sql_filters_turn_and_action_step():
    sql = build_step_sql([SID], ORG_ID)
    for col_alias in [
        "AS sessionId", "AS stepInteractionId", "AS stepId", "AS stepName",
        "AS stepInput", "AS stepOutput", "AS stepStartTimestamp",
        "AS stepEndTimestamp", "AS stepType",
    ]:
        assert col_alias in sql
    # Inner JOINs in step SQL (not LEFT JOIN).
    assert "LEFT JOIN" not in sql
    # Interaction filter for TURN.
    assert 'WHERE "ssot__AiAgentInteractionType__c" = \'TURN\'' in sql
    # Step filter for ACTION_STEP.
    assert 'WHERE "ssot__AiAgentInteractionStepType__c" = \'ACTION_STEP\'' in sql


def test_participant_sql_has_all_expected_columns():
    sql = build_participant_sql([SID], ORG_ID)
    for col_alias in [
        "AS sessionId", "AS sessionStartTimestamp", "AS sessionVoiceCallId",
        "AS sessionChannel", "AS messagingSessionId", "AS aiAgentApiName",
        "AS participantRole", "AS aiAgentTemplateApiName", "AS aiAgentType",
        "AS aiAgentVersionApiName", "AS participantId", "AS participantObject",
        "AS sessionParticipantId",
    ]:
        assert col_alias in sql
    assert "LEFT JOIN" in sql
    assert 'FROM "ssot__AiAgentSessionParticipant__dlm"' in sql


def test_session_list_sql_no_agent_filter():
    sql = build_session_list_sql(ORG_ID, limit=10)
    assert "LIMIT 10" in sql
    assert "ORDER BY" in sql
    assert "AS sessionId" in sql
    assert "AS sessionStartTimestamp" in sql
    assert "AS sessionChannel" in sql
    # No EXISTS when agent filter is absent.
    assert "EXISTS" not in sql


def test_session_list_sql_with_agent_filter():
    sql = build_session_list_sql(ORG_ID, agent_api_name="My_Agent", limit=5)
    assert "EXISTS" in sql
    assert "'My_Agent'" in sql
    assert "LIMIT 5" in sql


def test_escaping_single_quotes_in_ids():
    sql = build_message_sql(["session'1"], ORG_ID)
    assert "'session''1'" in sql


# ---- ExternalSourceId filter is optional (regression: sf-org-display id != STDM
#      ssot__ExternalSourceId__c, which zeroed out every query on some orgs) ----

_EXT_COL = "ssot__ExternalSourceId__c"


def test_message_sql_omits_external_source_filter_when_org_id_none():
    sql = build_message_sql([SID], None)
    assert _EXT_COL not in sql
    # The session id filter must still be present.
    assert f"'{SID}'" in sql


def test_step_sql_omits_external_source_filter_when_org_id_none():
    sql = build_step_sql([SID], None)
    assert _EXT_COL not in sql
    assert f"'{SID}'" in sql


def test_participant_sql_omits_external_source_filter_when_org_id_none():
    sql = build_participant_sql([SID], None)
    assert _EXT_COL not in sql
    assert f"'{SID}'" in sql


def test_session_list_sql_omits_external_source_filter_when_org_id_none():
    sql = build_session_list_sql(None, limit=10)
    assert _EXT_COL not in sql
    assert "LIMIT 10" in sql
    assert "AS sessionId" in sql


def test_session_list_sql_includes_external_source_filter_when_org_id_given():
    sql = build_session_list_sql(ORG_ID, limit=10)
    assert _EXT_COL in sql
    assert f"'{ORG_ID}'" in sql


def test_session_list_sql_agent_filter_works_without_org_id():
    """Both filters are independent: agent EXISTS clause present, org filter absent."""
    sql = build_session_list_sql(None, agent_api_name="NGA_ASA_Agent", limit=5)
    assert _EXT_COL not in sql
    assert "EXISTS" in sql
    assert "'NGA_ASA_Agent'" in sql


def test_agent_list_sql_omits_external_source_filter_when_org_id_none():
    from src.datacloud_query import build_agent_list_sql
    sql = build_agent_list_sql(None, limit=50)
    assert _EXT_COL not in sql
    # AGENT role filter must survive.
    assert "'AGENT'" in sql
    assert "LIMIT 50" in sql


def test_agent_list_sql_includes_external_source_filter_when_org_id_given():
    from src.datacloud_query import build_agent_list_sql
    sql = build_agent_list_sql(ORG_ID, limit=50)
    assert _EXT_COL in sql
    assert f"'{ORG_ID}'" in sql


def test_empty_session_ids_rejected():
    import pytest
    with pytest.raises(ValueError, match="cannot be empty"):
        build_message_sql([], ORG_ID)


def test_normalize_rows_passes_through_dict_rows():
    payload = {
        "data": [
            {"col1": "a", "col2": "b"},
            {"col1": "c", "col2": "d"},
        ],
        "metadata": {"col1": {}, "col2": {}},
        "rowCount": 2,
        "done": True,
    }
    rows = _normalize_rows(payload)
    assert rows == [{"col1": "a", "col2": "b"}, {"col1": "c", "col2": "d"}]


def test_normalize_rows_handles_empty_data():
    assert _normalize_rows({"data": [], "metadata": {}, "rowCount": 0}) == []
    assert _normalize_rows({"data": None, "metadata": {}}) == []


def test_normalize_rows_raises_on_error_object():
    import pytest
    with pytest.raises(RuntimeError, match="Data Cloud SQL error"):
        _normalize_rows({"errorCode": "MALFORMED_QUERY", "message": "bad syntax"})


def test_normalize_rows_raises_on_error_list():
    import pytest
    with pytest.raises(RuntimeError, match="INVALID_TYPE"):
        _normalize_rows([{"errorCode": "INVALID_TYPE", "message": "no such col"}])
