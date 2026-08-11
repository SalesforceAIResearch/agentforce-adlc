"""Orchestrates Data Cloud SQL queries + StdmBuilder to produce canonical STDM JSON.

Replaces src/session_fetcher.py (Apex-helper-based) for the STDM-building path.
"""
from __future__ import annotations

import concurrent.futures
import json
import subprocess

from . import datacloud_query, stdm_builder


def discover_org_id(org_alias: str) -> str:
    """Fetch the 18-char org ID via `sf org display`.

    NOTE: this is NOT reliably the value stored in STDM's
    ``ssot__ExternalSourceId__c``. Depending on how sessions were ingested that
    field can hold a *different* 18-char id, or be null. Prefer
    ``resolve_external_source_id()`` for STDM filtering; this helper remains for
    callers that genuinely need the org's own id.
    """
    proc = subprocess.run(
        ["sf", "org", "display", "-o", org_alias, "--json"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"sf org display failed: {proc.stderr.strip() or proc.stdout.strip()}")
    payload = json.loads(proc.stdout)
    result = payload.get("result") or {}
    org_id = result.get("id")
    if not org_id:
        raise RuntimeError(f"could not extract org id from sf org display response: {payload}")
    return org_id


def resolve_external_source_id(org_alias: str) -> str | None:
    """Determine the ExternalSourceId to filter STDM by, from the data itself.

    Queries the dominant non-null ``ssot__ExternalSourceId__c`` actually present in
    the session DMO. Returns that id, or ``None`` when the field is empty across the
    board (in which case callers skip the filter and rely on dataspace scoping).

    This avoids the mismatch where ``sf org display`` returns one org id but the
    ingested sessions carry another. When a single dominant id exists we still scope
    to it (safer for shared dataspaces); when the data is entirely null we don't.
    """
    sql = (
        f'SELECT {datacloud_query.EXTERNAL_SOURCE_ID_COL} AS ext, '
        f'COUNT({datacloud_query.SESSION_ID_COL}) AS c '
        f'FROM {datacloud_query.SESSION_TABLE} '
        f'GROUP BY {datacloud_query.EXTERNAL_SOURCE_ID_COL} '
        f'ORDER BY c DESC LIMIT 5'
    )
    try:
        rows = datacloud_query.run_sql(org_alias, sql)
    except Exception:
        return None
    for r in rows:
        ext = r.get("ext")
        if ext and str(ext).strip() and str(ext) != "NOT_SET":
            return str(ext)
    return None


def list_sessions(
    org_alias: str,
    *,
    org_id: str | None = None,
    agent_api_name: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """List recent sessions in the org, newest first. No Apex helper needed.

    ``org_id`` is the ExternalSourceId to scope by. When omitted, it is resolved
    from the STDM data itself (``resolve_external_source_id``); if that yields
    nothing, the ExternalSourceId filter is skipped and the query relies on
    dataspace scoping.
    """
    if org_id is None:
        org_id = resolve_external_source_id(org_alias)
    sql = datacloud_query.build_session_list_sql(
        org_id, agent_api_name=agent_api_name, limit=limit,
    )
    rows = datacloud_query.run_sql(org_alias, sql)
    # Map to a light summary dict. Column aliases already match what CLI expects.
    return [
        {
            "session_id": r.get("sessionId"),
            "start_time": r.get("sessionStartTimestamp"),
            "channel": r.get("sessionChannel"),
        }
        for r in rows
    ]


def list_agents(
    org_alias: str,
    *,
    org_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """List distinct agents that have participated in sessions in this org."""
    if org_id is None:
        org_id = resolve_external_source_id(org_alias)
    sql = datacloud_query.build_agent_list_sql(org_id, limit=limit)
    rows = datacloud_query.run_sql(org_alias, sql)
    return [
        {
            "agent_api_name": r.get("aiAgentApiName"),
            "agent_type": r.get("aiAgentType"),
        }
        for r in rows
    ]


def fetch_session_stdm(
    org_alias: str,
    session_id: str,
    *,
    org_id: str | None = None,
) -> dict:
    """Fetch one session and assemble it into canonical STDM JSON via the builder.

    Returns the single Session dict (not wrapped in a list). Raises if the session
    couldn't be assembled (no actors / no interactions / step with null id).
    """
    # `org_id` here is the ExternalSourceId used to scope the SQL (may be None →
    # no filter). The STDM assembler separately requires a non-empty org identifier
    # for its DTO, so we fall back to the org's own id for that argument only.
    if org_id is None:
        org_id = resolve_external_source_id(org_alias)
    assembler_org_id = org_id or discover_org_id(org_alias)

    session_ids = [session_id]
    message_sql = datacloud_query.build_message_sql(session_ids, org_id)
    step_sql = datacloud_query.build_step_sql(session_ids, org_id)
    participant_sql = datacloud_query.build_participant_sql(session_ids, org_id)

    # Run the 3 queries in parallel. Each shells out to `sf api request rest`, which is
    # process-level and releases the GIL while waiting.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            "messages": pool.submit(datacloud_query.run_sql, org_alias, message_sql),
            "steps": pool.submit(datacloud_query.run_sql, org_alias, step_sql),
            "participants": pool.submit(datacloud_query.run_sql, org_alias, participant_sql),
        }
        results = {k: f.result() for k, f in futures.items()}

    sessions = stdm_builder.assemble_stdm_detail_views(
        assembler_org_id,
        results["messages"],
        results["steps"],
        results["participants"],
    )
    if not sessions:
        raise RuntimeError(
            f"STDM assembly produced no sessions for {session_id}. Likely causes: "
            f"no participant rows, no messages, or data integrity issues. "
            f"Query row counts: messages={len(results['messages'])}, "
            f"steps={len(results['steps'])}, participants={len(results['participants'])}"
        )
    return sessions[0]
