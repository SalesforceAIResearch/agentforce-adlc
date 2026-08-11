"""Tests for session_stdm — focused on resolve_external_source_id, the fix for the
sf-org-display-id vs. ssot__ExternalSourceId__c mismatch that returned 0 sessions on
some orgs (e.g. blitz-sdb40-1, where org id 00DoB…bhgz != source id 00DoB…nW6f)."""
from __future__ import annotations

from src import session_stdm


def _patch_run_sql(monkeypatch, rows=None, exc=None):
    """Replace datacloud_query.run_sql (used by resolve_external_source_id) with a stub."""
    def fake_run_sql(org_alias, sql):
        if exc is not None:
            raise exc
        return rows or []
    monkeypatch.setattr(session_stdm.datacloud_query, "run_sql", fake_run_sql)


def test_resolve_returns_dominant_non_null_source_id(monkeypatch):
    # Query is ORDER BY count DESC — first non-null row wins.
    _patch_run_sql(monkeypatch, rows=[
        {"ext": "00DoB000003nW6fUAE", "c": 84},
        {"ext": "00DoB000003otherAB", "c": 10},
    ])
    assert session_stdm.resolve_external_source_id("any-org") == "00DoB000003nW6fUAE"


def test_resolve_skips_leading_null_and_takes_next_real_id(monkeypatch):
    # This is the exact blitz-sdb40-1 shape: null is the biggest bucket, a real id follows.
    _patch_run_sql(monkeypatch, rows=[
        {"ext": None, "c": 110},
        {"ext": "00DoB000003nW6fUAE", "c": 84},
    ])
    assert session_stdm.resolve_external_source_id("any-org") == "00DoB000003nW6fUAE"


def test_resolve_skips_not_set_sentinel(monkeypatch):
    _patch_run_sql(monkeypatch, rows=[
        {"ext": "NOT_SET", "c": 50},
        {"ext": "00DoB000003nW6fUAE", "c": 20},
    ])
    assert session_stdm.resolve_external_source_id("any-org") == "00DoB000003nW6fUAE"


def test_resolve_returns_none_when_all_null(monkeypatch):
    # No usable source id anywhere → None → callers skip the filter (dataspace scoping).
    _patch_run_sql(monkeypatch, rows=[{"ext": None, "c": 110}])
    assert session_stdm.resolve_external_source_id("any-org") is None


def test_resolve_returns_none_on_empty(monkeypatch):
    _patch_run_sql(monkeypatch, rows=[])
    assert session_stdm.resolve_external_source_id("any-org") is None


def test_resolve_returns_none_when_query_fails(monkeypatch):
    # A broken/absent DMO must degrade gracefully (skip filter), not raise.
    _patch_run_sql(monkeypatch, exc=RuntimeError("Data Cloud SQL error: INVALID_TYPE"))
    assert session_stdm.resolve_external_source_id("any-org") is None


def test_list_sessions_auto_resolves_source_id(monkeypatch):
    """list_sessions with org_id=None must resolve the source id from data, not from
    sf org display (the whole point of the fix)."""
    calls = {}

    monkeypatch.setattr(
        session_stdm, "resolve_external_source_id",
        lambda org: "00DoB000003nW6fUAE",
    )

    def fake_build(org_id, *, agent_api_name=None, limit=20):
        calls["org_id"] = org_id
        calls["agent"] = agent_api_name
        return "SELECT 1"

    monkeypatch.setattr(session_stdm.datacloud_query, "build_session_list_sql", fake_build)
    monkeypatch.setattr(session_stdm.datacloud_query, "run_sql", lambda org, sql: [])

    session_stdm.list_sessions("any-org", agent_api_name="NGA_ASA_Agent", limit=3)
    assert calls["org_id"] == "00DoB000003nW6fUAE"
    assert calls["agent"] == "NGA_ASA_Agent"


def test_list_sessions_passes_none_when_no_source_id(monkeypatch):
    """When no source id can be resolved, list_sessions passes org_id=None so the
    builder omits the ExternalSourceId filter entirely."""
    monkeypatch.setattr(session_stdm, "resolve_external_source_id", lambda org: None)
    seen = {}

    def fake_build(org_id, *, agent_api_name=None, limit=20):
        seen["org_id"] = org_id
        return "SELECT 1"

    monkeypatch.setattr(session_stdm.datacloud_query, "build_session_list_sql", fake_build)
    monkeypatch.setattr(session_stdm.datacloud_query, "run_sql", lambda org, sql: [])

    session_stdm.list_sessions("any-org", limit=5)
    assert seen["org_id"] is None
