"""CLI entry points for the custom scorer spike.

Commands:
  sessions         — list recent sessions in an org
  agents           — list distinct agents that have participated in sessions
  models           — list LLM models supported as `primary_model` on a scorer
  scorers          — list AiAgentScorerDefinition records deployed in an org
  score            — run a scorer against one or more session IDs (auto-deploys if missing)
  score-and-fetch  — convenience: list the N most recent sessions, then score them
  deploy-scorer    — deploy a scorer prompt template without running it
  ui               — launch the local single-page companion UI
"""
from __future__ import annotations

import json
import sys
import time
from typing import Iterable

import click

from . import _ui as ui
from . import model_catalog, run_store, scorer_deployer, scorer_spec, session_stdm, prompt_template


@click.group()
def cli() -> None:
    """Custom Scorer Prompt CLI."""


# ----------------------------------------------------------------------------
# sessions
# ----------------------------------------------------------------------------
@cli.command()
@click.option("--org", required=True, help="Salesforce org alias (sf org login target).")
@click.option("--agent", default=None, help="Agent MasterLabel to filter on (optional).")
@click.option("--days", default=7, show_default=True, type=int, help="Lookback window.")
@click.option("--limit", default=10, show_default=True, type=int, help="Max sessions.")
@click.option("--json", "as_json", is_flag=True, help="Emit raw JSON instead of a table.")
def sessions(org: str, agent: str | None, days: int, limit: int, as_json: bool) -> None:
    """List recent agent sessions in an org."""
    _ = days  # reserved
    if as_json:
        result = session_stdm.list_sessions(org, agent_api_name=agent, limit=limit)
        click.echo(json.dumps(result, indent=2))
        return
    ui.header(f"Listing sessions in {org}")
    with ui.spinner(f"Querying Data Cloud for up to {limit} recent session(s)…"):
        result = session_stdm.list_sessions(org, agent_api_name=agent, limit=limit)
    if not result:
        ui.substep("No sessions found.", warn=True)
        return
    ui.substep(f"Retrieved {len(result)} session(s).", ok=True)
    click.echo()
    _print_session_table(result)


# ----------------------------------------------------------------------------
# agents
# ----------------------------------------------------------------------------
@cli.command()
@click.option("--org", required=True, help="Salesforce org alias.")
@click.option("--limit", default=100, show_default=True, type=int,
              help="Max distinct agents to return.")
@click.option("--json", "as_json", is_flag=True, help="Emit raw JSON instead of a table.")
def agents(org: str, limit: int, as_json: bool) -> None:
    """List distinct agents that have participated in sessions in the org.

    Useful for discovering the agent_api_name values accepted by `--agent`
    in `sessions` and `score-and-fetch`.
    """
    if as_json:
        result = session_stdm.list_agents(org, limit=limit)
        click.echo(json.dumps(result, indent=2))
        return
    ui.header(f"Listing agents in {org}")
    with ui.spinner("Querying Data Cloud for distinct agents…"):
        result = session_stdm.list_agents(org, limit=limit)
    if not result:
        ui.substep("No agents found.", warn=True)
        return
    ui.substep(f"Retrieved {len(result)} agent(s).", ok=True)
    click.echo()
    _print_agent_table(result)


# ----------------------------------------------------------------------------
# models
# ----------------------------------------------------------------------------
@cli.command()
@click.option("--org", required=False, default=None,
              help="Salesforce org alias. Currently informational — the catalog "
                   "is a pinned snapshot from the Agentforce supported-models doc; "
                   "the org alias is accepted for API symmetry and forward-compat.")
@click.option("--include-beta", is_flag=True,
              help="Include models flagged Beta. Off by default — betas churn.")
@click.option("--include-embeddings", is_flag=True,
              help="Include embeddings models. Off by default — embeddings can't "
                   "drive a scorerMultilabel prompt template.")
@click.option("--json", "as_json", is_flag=True, help="Emit raw JSON instead of a table.")
def models(org: str | None, include_beta: bool, include_embeddings: bool,
           as_json: bool) -> None:
    """List LLM models supported as `primary_model` on a scorer YAML.

    Catalog source: https://developer.salesforce.com/docs/ai/agentforce/guide/supported-models.html
    The catalog is a pinned snapshot in src/model_catalog.py; refresh by hand
    when Salesforce updates the supported-models page. Salesforce does not
    publish a Connect/REST endpoint for the model list.
    """
    _ = org  # accepted for API symmetry; unused while catalog is hardcoded
    entries = model_catalog.list_models(
        include_beta=include_beta, include_embeddings=include_embeddings,
    )
    if as_json:
        click.echo(json.dumps(
            [model_catalog.to_jsonable(m) for m in entries], indent=2,
        ))
        return
    ui.header(f"Supported scorer models ({len(entries)})")
    _print_model_table(entries)


# ----------------------------------------------------------------------------
# scorers
# ----------------------------------------------------------------------------
@cli.command()
@click.option("--org", required=True, help="Salesforce org alias.")
@click.option("--detailed", is_flag=True,
              help="Retrieve each scorer's XML to show agent binding, isActive, "
                   "samplingRate, and engineRef. Slower than the default flat list.")
@click.option("--agent", "agent_filter", default=None,
              help="Filter to scorers bound to this agent_api_name. Implies --detailed.")
@click.option("--json", "as_json", is_flag=True, help="Emit raw JSON instead of a table.")
def scorers(org: str, detailed: bool, agent_filter: str | None, as_json: bool) -> None:
    """List AiAgentScorerDefinition records deployed in the org.

    Default output is a flat list of fullNames (fast — one metadata call).
    Use --detailed to also fetch agent binding, isActive, samplingRate, and
    engineRef by retrieving each XML. --agent filters by bound agent
    (implies --detailed).
    """
    need_detail = detailed or agent_filter is not None
    if as_json and not need_detail:
        flat = scorer_deployer.list_scorer_definitions(org)
        click.echo(json.dumps(flat, indent=2))
        return
    if as_json:
        details = scorer_deployer.retrieve_scorer_definitions_detailed(org)
        if agent_filter:
            details = [d for d in details if d.get("agentApiName") == agent_filter]
        click.echo(json.dumps(details, indent=2))
        return

    ui.header(f"Listing scorers in {org}")
    if not need_detail:
        with ui.spinner("Listing AiAgentScorerDefinition metadata…"):
            flat = scorer_deployer.list_scorer_definitions(org)
        if not flat:
            ui.substep("No scorer definitions found.", warn=True)
            return
        ui.substep(f"Retrieved {len(flat)} scorer(s).", ok=True)
        click.echo()
        _print_scorer_flat_table(flat)
        return

    with ui.spinner("Retrieving scorer definitions (XML) from the org…"):
        details = scorer_deployer.retrieve_scorer_definitions_detailed(org)
    if agent_filter:
        details = [d for d in details if d.get("agentApiName") == agent_filter]
    if not details:
        ui.substep(
            f"No scorer definitions found"
            + (f" bound to agent '{agent_filter}'." if agent_filter else "."),
            warn=True,
        )
        return
    ui.substep(f"Retrieved {len(details)} scorer(s).", ok=True)
    click.echo()
    _print_scorer_detailed_table(details)


# ----------------------------------------------------------------------------
# score
# ----------------------------------------------------------------------------
@cli.command()
@click.option("--org", required=True, help="Salesforce org alias.")
@click.option("--scorer", "scorer_ref", required=True,
              help="Bundled name (e.g. response_quality) or path to a scorer YAML.")
@click.option("--session-id", "session_ids", multiple=True, required=True,
              help="One or more session IDs to score. Repeat to score multiple.")
@click.option("--no-auto-deploy", is_flag=True,
              help="Fail instead of auto-deploying the prompt template if missing.")
@click.option("--json", "as_json", is_flag=True, help="Emit raw JSON.")
def score(
    org: str,
    scorer_ref: str,
    session_ids: tuple[str, ...],
    no_auto_deploy: bool,
    as_json: bool,
) -> None:
    """Run a scorer against one or more sessions.

    Auto-deploys the scorer's GenAiPromptTemplate to the org if not already present.
    """
    if as_json:
        # Keep --json output clean: no banners, no spinners.
        _score_json(org, scorer_ref, session_ids, no_auto_deploy)
        return
    _score_interactive(org, scorer_ref, session_ids, no_auto_deploy)


def _score_json(org, scorer_ref, session_ids, no_auto_deploy):
    spec = scorer_spec.load(scorer_ref)
    if no_auto_deploy:
        if not scorer_deployer.template_exists(org, spec.name):
            click.echo(
                f"Error: prompt template '{spec.name}' is not deployed in {org} "
                f"and --no-auto-deploy was set.",
                err=True,
            )
            sys.exit(2)
    else:
        scorer_deployer.ensure_prompt_template_deployed(org, spec, verbose=False)
    org_id = session_stdm.resolve_external_source_id(org)
    results = []
    stdms: dict[str, dict] = {}
    for sid in session_ids:
        try:
            session_view = session_stdm.fetch_session_stdm(org, sid, org_id=org_id)
        except Exception as e:
            click.echo(f"Failed to build STDM for session {sid}: {e}", err=True)
            continue
        res = prompt_template.run_scorer(org, spec, session_view)
        results.append((sid, res))
        stdms[sid] = session_view
    if not results:
        click.echo("No sessions successfully scored.", err=True)
        sys.exit(3)
    result_dicts = [
        {"session_id": sid, "label": r.label, "reason": r.reason,
         "raw_value": r.raw_value, "raw_response_text": r.raw_response_text}
        for sid, r in results
    ]
    try:
        run_store.save_run(
            spec=spec,
            spec_source_path=scorer_spec._resolve_path(scorer_ref),
            org=org,
            sessions=[{"session_id": sid} for sid, _ in results],
            stdms=stdms,
            results=result_dicts,
        )
    except Exception as e:
        # Don't fail the score command on a snapshot bug; surface on stderr.
        click.echo(f"(warning: failed to save run snapshot: {e})", err=True)
    click.echo(json.dumps(result_dicts, indent=2))


def _score_interactive(org, scorer_ref, session_ids, no_auto_deploy):
    """Narrated version of `score`: prints steps, spinners, and a pretty scorecard."""
    total_steps = 3  # load spec → ensure deployed → score each session

    ui.header(f"Scoring {len(session_ids)} session(s) in {org}")

    # --- Step 1: load + validate scorer spec ---
    ui.step(1, total_steps, f"Loading scorer spec: {scorer_ref}")
    try:
        spec = scorer_spec.load(scorer_ref)
    except Exception as e:
        ui.substep(f"Failed to load spec: {e}", err=True)
        sys.exit(2)
    if spec.pt_template_type == "scorerOpenEnded" and not spec.allowed_labels:
        summary = f"open free-form ({spec.lightning_type})"
    elif spec.allowed_labels:
        summary = (
            f"{len(spec.allowed_labels)} labels, fallback '{spec.fallback_label}'"
        )
    else:
        summary = spec.pt_template_type
    ui.substep(f"Loaded '{spec.name}' — {summary}.", ok=True)

    # --- Step 2: ensure the prompt template is deployed + active ---
    ui.step(2, total_steps, f"Ensuring template '{spec.name}' is deployed and active")
    if no_auto_deploy:
        with ui.spinner("Checking template status in the org…"):
            exists = scorer_deployer.template_exists(org, spec.name)
        if not exists:
            ui.substep(
                f"Template '{spec.name}' not found and --no-auto-deploy was set.",
                err=True,
            )
            sys.exit(2)
        ui.substep("Template present; skipping deploy.", ok=True)
    else:
        _deploy_with_progress(org, spec)

    # --- Step 3: per-session STDM build + score ---
    ui.step(3, total_steps, f"Scoring {len(session_ids)} session(s)")
    org_id = session_stdm.resolve_external_source_id(org)
    results: list[tuple[str, object]] = []
    stdms: dict[str, dict] = {}
    for i, sid in enumerate(session_ids, start=1):
        short = ui.short_id(sid)
        click.echo()
        ui.info(f"session {i}/{len(session_ids)} — {sid}")

        try:
            with ui.spinner(f"[{short}] Building STDM JSON from Data Cloud (3 parallel queries)…") as sp:
                t0 = time.monotonic()
                session_view = session_stdm.fetch_session_stdm(org, sid, org_id=org_id)
                dt = time.monotonic() - t0
            turns = len(session_view.get("runs") or [])
            actors = len(session_view.get("actors") or [])
            ui.substep(
                f"STDM built: {turns} turn(s), {actors} actor(s), "
                f"{_rough_kb(session_view)} — {dt:.1f}s.",
                ok=True,
            )
        except Exception as e:
            ui.substep(f"Failed to build STDM: {e}", err=True)
            continue

        try:
            with ui.spinner(f"[{short}] Invoking scorer via Einstein Prompt Template Generations…"):
                t0 = time.monotonic()
                res = prompt_template.run_scorer(org, spec, session_view)
                dt = time.monotonic() - t0
            display_value = res.label or res.raw_value or "(unparseable)"
            ui.substep(
                f"LLM responded in {dt:.1f}s — value: {ui.color_label(display_value)}",
                ok=True,
            )
            results.append((sid, res))
            stdms[sid] = session_view
        except Exception as e:
            ui.substep(f"Scoring failed: {e}", err=True)
            continue

    if not results:
        ui.error_banner("No sessions successfully scored.")
        sys.exit(3)

    try:
        run_id = run_store.save_run(
            spec=spec,
            spec_source_path=scorer_spec._resolve_path(scorer_ref),
            org=org,
            sessions=[{"session_id": sid} for sid, _ in results],
            stdms=stdms,
            results=[
                {"session_id": sid, "label": r.label, "reason": r.reason,
                 "raw_value": r.raw_value, "raw_response_text": r.raw_response_text}
                for sid, r in results
            ],
        )
        ui.substep(f"Saved run snapshot: {run_id}", ok=True)
    except Exception as e:
        ui.substep(f"Could not save run snapshot: {e}", warn=True)

    _print_scorecard(spec, results)


def _deploy_with_progress(org: str, spec) -> None:
    """Run ensure_prompt_template_deployed with spinner narration instead of the
    library's built-in prints."""
    # Fast path check.
    with ui.spinner(f"Checking if '{spec.name}' is deployed in {org}…"):
        exists = scorer_deployer.template_exists(org, spec.name)
    if exists:
        with ui.spinner(f"Checking activation state of '{spec.name}'…"):
            active_id = scorer_deployer._fetch_active_version_identifier(org, spec)
        if active_id:
            ui.substep(f"Template is active (version {active_id[:16]}…). Skipping deploy.",
                       ok=True)
            return
        ui.substep("Template deployed but not active. Activating…", warn=True)
        with ui.spinner("Retrieving current versionIdentifier and redeploying…"):
            scorer_deployer.activate_existing_template(org, spec, verbose=False)
        ui.substep(f"'{spec.name}' activated.", ok=True)
        return

    # Slow path: not deployed — run the 3-step flow with per-step spinners.
    ui.substep(f"Template '{spec.name}' not found. Auto-deploying (3-step flow)…", warn=True)
    # We use the library's internal building blocks so we can wrap each phase.
    import tempfile
    import shutil
    from pathlib import Path
    from .xml_render import render as render_template
    from . import sf_apex as _sf_apex

    tmpdir = Path(tempfile.mkdtemp(prefix="scorer-deploy-"))
    success = False
    try:
        _, xml_path = scorer_deployer._prepare_package(
            tmpdir, spec, active_version_identifier=None,
        )
        with ui.spinner("[1/3] Deploying template (inactive)…"):
            _sf_apex.project_deploy(org, str(xml_path), project_root=str(tmpdir))
        ui.substep("[1/3] Inactive template deployed.", ok=True)

        with ui.spinner("[2/3] Retrieving server-assigned versionIdentifier…"):
            _sf_apex.project_retrieve(org, str(xml_path), project_root=str(tmpdir))
        retrieved = xml_path.read_text()
        version_id = scorer_deployer._extract_version_identifier(retrieved)
        ui.substep(f"[2/3] Got version {version_id[:16]}…", ok=True)

        with ui.spinner("[3/3] Injecting activeVersionIdentifier and redeploying…"):
            activated = scorer_deployer._inject_active_version(retrieved, version_id)
            xml_path.write_text(activated)
            _sf_apex.project_deploy(org, str(xml_path), project_root=str(tmpdir))
        ui.substep(f"[3/3] '{spec.name}' activated and invocable.", ok=True)
        success = True
    finally:
        if success:
            shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            ui.substep(f"Deploy artifacts kept at {tmpdir} for debugging.", warn=True)


def _rough_kb(obj) -> str:
    size = len(json.dumps(obj))
    if size < 1024:
        return f"{size} B"
    return f"{size / 1024:.1f} KB"


# ----------------------------------------------------------------------------
# score-and-fetch
# ----------------------------------------------------------------------------
@cli.command("score-and-fetch")
@click.option("--org", required=True)
@click.option("--scorer", "scorer_ref", required=True)
@click.option("--last", default=3, show_default=True, type=int,
              help="Score the N most recent sessions.")
@click.option("--agent", default=None)
@click.option("--days", default=7, show_default=True, type=int)
@click.option("--no-auto-deploy", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def score_and_fetch(ctx, org, scorer_ref, last, agent, days, no_auto_deploy, as_json):
    """List the most recent sessions then score them — one-command convenience."""
    _ = days
    if as_json:
        # JSON mode: skip the banner, delegate straight to `score`.
        recent = session_stdm.list_sessions(org, agent_api_name=agent, limit=last)
        if not recent:
            click.echo("No sessions found.", err=True)
            sys.exit(3)
        ctx.invoke(
            score,
            org=org, scorer_ref=scorer_ref,
            session_ids=tuple(s["session_id"] for s in recent),
            no_auto_deploy=no_auto_deploy, as_json=True,
        )
        return

    ui.header(f"score-and-fetch — org={org}, scorer={scorer_ref}, last={last}")
    with ui.spinner(f"Querying last {last} session(s) from {org}…"):
        recent = session_stdm.list_sessions(org, agent_api_name=agent, limit=last)
    if not recent:
        ui.error_banner("No sessions found.")
        sys.exit(3)
    ui.substep(f"Found {len(recent)} session(s) to score:", ok=True)
    for i, s in enumerate(recent, start=1):
        ui.info(f"  {i}. {s.get('session_id')}  ·  "
                f"{(s.get('start_time') or '')[:19]}  ·  "
                f"{s.get('channel') or '?'}")
    ctx.invoke(
        score,
        org=org, scorer_ref=scorer_ref,
        session_ids=tuple(s["session_id"] for s in recent),
        no_auto_deploy=no_auto_deploy, as_json=False,
    )


# ----------------------------------------------------------------------------
# deploy-scorer
# ----------------------------------------------------------------------------
@cli.command("deploy-scorer")
@click.option("--org", required=True)
@click.option("--scorer", "scorer_ref", required=True,
              help="Bundled name or path to a scorer YAML.")
@click.option("--force", is_flag=True, help="Redeploy even if the template already exists.")
@click.option("--agent-api-name", "agent_api_name", default=None,
              help="Agent API name to bind the scorer to. If set (here or in the "
                   "YAML), also deploys an AiAgentScorerDefinition so the scorer "
                   "shows up in Agentforce Studio.")
@click.option("--activate/--no-activate", "activate", default=None,
              help="Deploy scorer with isActive=true (overrides spec). "
                   "Only applies when an agent is bound.")
@click.option("--sampling-rate", "sampling_rate", type=float, default=None,
              help="Override the sampling rate (0.0–1.0) on the scorer definition.")
def deploy_scorer(org: str, scorer_ref: str, force: bool,
                  agent_api_name: str | None, activate: bool | None,
                  sampling_rate: float | None) -> None:
    """Deploy a scorer to Salesforce.

    Always deploys the GenAiPromptTemplate (3-step deploy-retrieve-activate).
    If an agent is bound (via --agent-api-name or the spec's agent_api_name),
    also deploys an AiAgentScorerDefinition so the scorer appears in
    Agentforce Studio and can sample real sessions.
    """
    ui.header(f"Deploying scorer '{scorer_ref}' to {org}")
    try:
        spec = scorer_spec.load(scorer_ref)
    except Exception as e:
        ui.error_banner(f"Failed to load spec: {e}")
        sys.exit(2)

    # CLI flags override spec fields.
    spec = _apply_scorer_overrides(
        spec, agent_api_name=agent_api_name, activate=activate,
        sampling_rate=sampling_rate,
    )
    bind_msg = (
        f" (bound to agent '{spec.agent_api_name}', "
        f"isActive={spec.is_active}, samplingRate={spec.sampling_rate})"
        if spec.agent_api_name else " (template only — no scorer definition)"
    )
    ui.substep(f"Loaded spec '{spec.name}'.{bind_msg}", ok=True)

    if not force:
        with ui.spinner(f"Checking if '{spec.name}' already exists in {org}…"):
            tpl_exists = scorer_deployer.template_exists(org, spec.name)
            def_exists = (
                scorer_deployer.scorer_definition_exists(org, spec.name)
                if spec.agent_api_name else False
            )
        if tpl_exists and (not spec.agent_api_name or def_exists):
            ui.substep(
                f"Template '{spec.name}' already deployed"
                + (" with scorer definition." if def_exists else ".")
                + " Use --force to redeploy.",
                warn=True,
            )
            out_dir = scorer_deployer.persist_rendered_xmls(spec)
            ui.substep(f"Rendered XMLs saved to {out_dir}.", ok=True)
            return
    # Steps 1–3 (prompt template).
    if force:
        scorer_deployer.deploy_prompt_template(org, spec, verbose=True)
    else:
        _deploy_with_progress(org, spec)
    # Step 4 (scorer definition) if an agent is bound.
    if spec.agent_api_name:
        with ui.spinner(f"[4/4] Deploying AiAgentScorerDefinition for '{spec.name}'…"):
            scorer_deployer.deploy_scorer_definition(org, spec, verbose=False)
        ui.substep(
            f"[4/4] Scorer definition deployed, bound to '{spec.agent_api_name}'.",
            ok=True,
        )
    out_dir = scorer_deployer.persist_rendered_xmls(spec)
    ui.substep(f"Rendered XMLs saved to {out_dir}.", ok=True)
    ui.success_banner(f"Scorer '{spec.name}' deployed.")


def _apply_scorer_overrides(
    spec,
    *,
    agent_api_name: str | None,
    activate: bool | None,
    sampling_rate: float | None,
):
    """Return a ScorerSpec with CLI-flag overrides applied on top of YAML values."""
    from dataclasses import replace
    kwargs: dict = {}
    if agent_api_name is not None:
        kwargs["agent_api_name"] = agent_api_name
    if activate is not None:
        kwargs["is_active"] = activate
    if sampling_rate is not None:
        if not 0.0 <= sampling_rate <= 1.0:
            ui.error_banner(f"--sampling-rate must be in [0.0, 1.0] (got {sampling_rate})")
            sys.exit(2)
        kwargs["sampling_rate"] = sampling_rate
    return replace(spec, **kwargs) if kwargs else spec


# ----------------------------------------------------------------------------
# ui
# ----------------------------------------------------------------------------
@cli.command("ui")
@click.option("--org", required=True, help="Salesforce org alias.")
@click.option("--port", default=8765, show_default=True, type=int)
@click.option("--no-browser", is_flag=True,
              help="Don't auto-open the browser (useful when launched in the background).")
def ui_cmd(org: str, port: int, no_browser: bool) -> None:
    """Launch the local scorer UI at http://127.0.0.1:<port>.

    Serves a single-page companion to the scorer-create workflow: browse scorer
    definitions, inspect per-session STDM JSON, and diff runs across iterations.
    Snapshot data is read from ./runs/, which is auto-populated by `score` and
    `score-and-fetch`.
    """
    from .web import create_app
    import threading
    import webbrowser

    app = create_app(org=org)
    url = f"http://127.0.0.1:{port}"
    click.echo(f"Scorer UI listening on {url}  (org={org})")
    if not no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    # Quiet Flask's default startup banner for a cleaner CLI experience.
    import logging
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


# ----------------------------------------------------------------------------
# presentation helpers
# ----------------------------------------------------------------------------
def _print_session_table(sessions: Iterable[dict]) -> None:
    rows = list(sessions)
    # Subtle table without clashing with ui colors.
    header = f"  {'#':>2}  {'Session ID':<38}  {'Start (UTC)':<24}  {'Channel':<12}"
    if sys.stdout.isatty():
        click.secho(header, bold=True)
    else:
        click.echo(header)
    click.echo("  " + "─" * (len(header) - 2))
    for i, s in enumerate(rows, start=1):
        click.echo(
            f"  {i:>2}  "
            f"{(s.get('session_id') or '?'):<38}  "
            f"{(s.get('start_time') or '')[:23]:<24}  "
            f"{(s.get('channel') or ''):<12}"
        )
    click.echo()


def _print_model_table(rows: list) -> None:
    header = (
        f"  {'#':>2}  {'Model':<48}  {'Provider':<22}  {'Identifier':<54}  Flags"
    )
    if sys.stdout.isatty():
        click.secho(header, bold=True)
    else:
        click.echo(header)
    click.echo("  " + "─" * (len(header) - 2))
    for i, m in enumerate(rows, start=1):
        flags_str = ",".join(sorted(m.flags)) or "—"
        click.echo(
            f"  {i:>2}  "
            f"{m.label:<48}  "
            f"{m.provider:<22}  "
            f"{m.identifier:<54}  "
            f"{flags_str}"
        )
    click.echo()


def _print_agent_table(rows: list[dict]) -> None:
    header = f"  {'#':>2}  {'Agent API Name':<44}  {'Type':<28}"
    if sys.stdout.isatty():
        click.secho(header, bold=True)
    else:
        click.echo(header)
    click.echo("  " + "─" * (len(header) - 2))
    for i, r in enumerate(rows, start=1):
        click.echo(
            f"  {i:>2}  "
            f"{(r.get('agent_api_name') or '?'):<44}  "
            f"{(r.get('agent_type') or ''):<28}"
        )
    click.echo()


def _print_scorer_flat_table(rows: list[dict]) -> None:
    header = f"  {'#':>2}  {'Scorer (fullName)':<44}  {'Type':<24}"
    if sys.stdout.isatty():
        click.secho(header, bold=True)
    else:
        click.echo(header)
    click.echo("  " + "─" * (len(header) - 2))
    for i, r in enumerate(rows, start=1):
        click.echo(
            f"  {i:>2}  "
            f"{(r.get('fullName') or '?'):<44}  "
            f"{(r.get('type') or 'AiAgentScorerDefinition'):<24}"
        )
    click.echo()


def _print_scorer_detailed_table(rows: list[dict]) -> None:
    header = (
        f"  {'#':>2}  {'Scorer':<28}  {'Agent':<36}  "
        f"{'Active':<7}  {'Rate':<5}  {'Engine ref':<28}"
    )
    if sys.stdout.isatty():
        click.secho(header, bold=True)
    else:
        click.echo(header)
    click.echo("  " + "─" * (len(header) - 2))
    for i, r in enumerate(rows, start=1):
        active = r.get("isActive")
        active_str = "yes" if active is True else ("no" if active is False else "?")
        rate = r.get("samplingRate")
        rate_str = f"{rate:.1f}" if isinstance(rate, (int, float)) else "?"
        click.echo(
            f"  {i:>2}  "
            f"{(r.get('name') or '?'):<28}  "
            f"{(r.get('agentApiName') or ''):<36}  "
            f"{active_str:<7}  "
            f"{rate_str:<5}  "
            f"{(r.get('engineRef') or ''):<28}"
        )
    click.echo()


def _print_scorecard(spec, results: list) -> None:
    """Pretty post-run scorecard with value color + reason wrapping + tally.

    For OpenEnded free-form scorers there are no predefined labels, so the
    header shows the lightning subtype and per-session lines print the raw
    value in place of a label. The tally is skipped for free-form scorers
    (a distribution over unique free-form strings is rarely meaningful).
    """
    is_open_free_form = (
        spec.pt_template_type == "scorerOpenEnded" and not spec.allowed_labels
    )
    click.echo()
    if is_open_free_form:
        header = (
            f"  ┌─ Scorer: {spec.name} "
            f"{ui.ICON_ARROW} {len(results)} session(s) "
            f"{ui.ICON_ARROW} open ({spec.lightning_type})"
        )
    else:
        header = (
            f"  ┌─ Scorer: {spec.name} "
            f"{ui.ICON_ARROW} {len(results)} session(s) "
            f"{ui.ICON_ARROW} labels: {', '.join(spec.allowed_labels)}"
        )
    click.secho(header, bold=True) if sys.stdout.isatty() else click.echo(
        f"  Scorer: {spec.name} → {len(results)} session(s)"
    )
    click.echo(f"  │")

    # Per-session card.
    for idx, (sid, r) in enumerate(results, start=1):
        display_value = r.label or r.raw_value or "(unparseable)"
        value_str = ui.color_label(display_value)
        value_label = "value" if is_open_free_form else "label"
        click.echo(f"  │  {idx:>2}. {sid}")
        click.echo(f"  │      {ui.LABEL_ICON} {value_label}:  {value_str}")
        if r.reason:
            click.echo(f"  │      {ui.REASON_ICON} reason:")
            for line in _wrap_for_card(r.reason, prefix="  │         "):
                click.echo(line)
        if not is_open_free_form and r.label is None and r.raw_response_text:
            click.echo(f"  │      (raw) {r.raw_response_text[:200]}")
        if idx < len(results):
            click.echo(f"  │")

    # Tally — only meaningful for closed-list scorers.
    if not is_open_free_form:
        click.echo(f"  │")
        tally: dict[str, int] = {}
        for _sid, r in results:
            key = r.label or "(unparseable)"
            tally[key] = tally.get(key, 0) + 1
        click.echo("  │  Distribution:")
        for label, n in sorted(tally.items(), key=lambda kv: -kv[1]):
            bar = "█" * min(n, 40)
            label_colored = ui.color_label(label)
            click.echo(f"  │    {label_colored:<30} {bar}  {n}")
    click.echo(f"  └─\n")


def _wrap_for_card(text: str, prefix: str, width: int = 76) -> list[str]:
    import textwrap
    avail = max(30, width - len(prefix))
    wrapped = textwrap.wrap(text.strip(), width=avail, break_long_words=False,
                            break_on_hyphens=False)
    if not wrapped:
        return [prefix.rstrip()]
    return [f"{prefix}{line}" for line in wrapped]


if __name__ == "__main__":
    cli()
