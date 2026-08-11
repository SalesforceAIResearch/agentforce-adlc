"""Check-or-deploy a GenAiPromptTemplate scorer in the target org.

Idempotent: if the template already exists (by DeveloperName), returns without deploying.
Otherwise runs the canonical 3-step flow from the playground repo's
`sf-ai-agentforce-scorer` skill:
  1. Deploy the prompt template XML (inactive, no activeVersionIdentifier).
  2. Retrieve to read the server-assigned <versionIdentifier>.
  3. Inject <activeVersionIdentifier> and redeploy to activate.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

import json

from . import sf_apex
from .scorer_spec import ScorerSpec
from .xml_render import render as render_template
from .xml_render import render_scorer_definition


RENDERED_XML_DIR = Path(__file__).resolve().parent.parent / "scorer_specs" / "rendered"


def persist_rendered_xmls(scorer: ScorerSpec) -> Path:
    """Write the rendered PT and (when agent-bound) scorer-definition XMLs to disk.

    Files land at:
        scorer_specs/rendered/<name>/<name>.genAiPromptTemplate-meta.xml
        scorer_specs/rendered/<name>/<name>.aiAgentScorerDefinition-meta.xml

    The scorer-definition file is only written when `scorer.agent_api_name`
    is set — a template-only deploy has no scorer definition to render.

    Returns the directory the files were written to. Idempotent — subsequent
    deploys of the same scorer overwrite the same files.
    """
    out_dir = RENDERED_XML_DIR / scorer.name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{scorer.name}.genAiPromptTemplate-meta.xml").write_text(
        render_template(scorer), encoding="utf-8",
    )
    if scorer.agent_api_name:
        (out_dir / f"{scorer.name}.aiAgentScorerDefinition-meta.xml").write_text(
            render_scorer_definition(scorer), encoding="utf-8",
        )
    return out_dir


def ensure_prompt_template_deployed(
    org_alias: str,
    scorer: ScorerSpec,
    *,
    verbose: bool = True,
) -> str:
    """Ensure the prompt template exists AND is active. Returns 'active', 'activated', or 'deployed'.

    Three states we handle:
      - Template does not exist → full 3-step deploy.
      - Template exists but is not active → retrieve + activate (steps 2–3 only).
      - Template exists and is active → fast path.
    """
    exists = template_exists(org_alias, scorer.name)
    if not exists:
        if verbose:
            print(f"Prompt template '{scorer.name}' not found in {org_alias}. Deploying...")
        deploy_prompt_template(org_alias, scorer, verbose=verbose)
        return "deployed"

    # Template exists — check activation by retrieving current XML.
    if verbose:
        print(f"Prompt template '{scorer.name}' is deployed. Checking activation...")
    active_id = _fetch_active_version_identifier(org_alias, scorer)
    if active_id:
        if verbose:
            print(f"  Template is active (version {active_id}); skipping deploy.")
        return "active"

    if verbose:
        print("  Template deployed but not active. Activating...")
    activate_existing_template(org_alias, scorer, verbose=verbose)
    return "activated"


def template_exists(org_alias: str, developer_name: str) -> bool:
    """Check metadata-api listing for a GenAiPromptTemplate by fullName.

    GenAiPromptTemplate is not SOQL-queryable (even via Tooling API returns INVALID_TYPE),
    so we enumerate deployed templates via the Metadata API instead.
    """
    records = sf_apex.list_metadata(org_alias, "GenAiPromptTemplate")
    return any(r.get("fullName") == developer_name for r in records)


def deploy_prompt_template(
    org_alias: str,
    scorer: ScorerSpec,
    *,
    verbose: bool = True,
) -> None:
    """Run the 3-step deploy. Raises SfCliError on any failure."""
    tmpdir = Path(tempfile.mkdtemp(prefix="scorer-deploy-"))
    success = False
    try:
        _, xml_path = _prepare_package(tmpdir, scorer, active_version_identifier=None)

        if verbose:
            print(f"  [1/3] Deploying prompt template XML ({scorer.name})...")
        sf_apex.project_deploy(org_alias, str(xml_path), project_root=str(tmpdir))

        if verbose:
            print("  [2/3] Retrieving versionIdentifier from server...")
        sf_apex.project_retrieve(org_alias, str(xml_path), project_root=str(tmpdir))
        retrieved = xml_path.read_text()
        version_id = _extract_version_identifier(retrieved)
        if verbose:
            print(f"        versionIdentifier: {version_id}")
            print("  [3/3] Activating template (injecting activeVersionIdentifier)...")
        # Edit the retrieved XML in place — do NOT re-render from Jinja. Salesforce
        # compares template content byte-for-byte; regenerated whitespace differences
        # are treated as a new version, which then fails CANNOT_DELETE_ACTIVE_VERSION.
        activated = _inject_active_version(retrieved, version_id)
        xml_path.write_text(activated)
        sf_apex.project_deploy(org_alias, str(xml_path), project_root=str(tmpdir))

        if verbose:
            print(f"Prompt template '{scorer.name}' deployed and active.")
        success = True
    finally:
        if success:
            shutil.rmtree(tmpdir, ignore_errors=True)
        elif verbose:
            print(f"  (deploy artifacts kept at {tmpdir} for debugging)")


def _inject_active_version(xml: str, version_id: str) -> str:
    """Return xml with <activeVersionIdentifier> added as a child of <GenAiPromptTemplate>,
    placed just before <developerName>. Idempotent — if already present, replaces the value."""
    if _ACTIVE_VERSION_RE.search(xml):
        return _ACTIVE_VERSION_RE.sub(
            f"<activeVersionIdentifier>{version_id}</activeVersionIdentifier>",
            xml, count=1,
        )
    return xml.replace(
        "<developerName>",
        f"<activeVersionIdentifier>{version_id}</activeVersionIdentifier>\n    <developerName>",
        1,
    )


def activate_existing_template(
    org_alias: str,
    scorer: ScorerSpec,
    *,
    verbose: bool = True,
) -> None:
    """Retrieve the existing deployed template, read its versionIdentifier, and redeploy with
    activeVersionIdentifier set. Use when the template exists in the org but never got the
    step-3 activation (e.g., a prior deploy aborted after step 1).

    We edit the retrieved XML in place — do NOT re-render from Jinja. See _inject_active_version.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="scorer-activate-"))
    success = False
    try:
        _, xml_path = _prepare_package(tmpdir, scorer, active_version_identifier=None)
        if verbose:
            print("  [1/2] Retrieving current template XML + versionIdentifier...")
        sf_apex.project_retrieve(org_alias, str(xml_path), project_root=str(tmpdir))
        retrieved = xml_path.read_text()
        version_id = _extract_version_identifier(retrieved)
        if verbose:
            print(f"        versionIdentifier: {version_id}")
            print("  [2/2] Injecting activeVersionIdentifier and redeploying...")
        activated = _inject_active_version(retrieved, version_id)
        xml_path.write_text(activated)
        sf_apex.project_deploy(org_alias, str(xml_path), project_root=str(tmpdir))
        if verbose:
            print(f"Prompt template '{scorer.name}' activated.")
        success = True
    finally:
        if success:
            shutil.rmtree(tmpdir, ignore_errors=True)
        elif verbose:
            print(f"  (activation artifacts kept at {tmpdir} for debugging)")


def _fetch_active_version_identifier(org_alias: str, scorer: ScorerSpec) -> str | None:
    """Retrieve the deployed template and return its activeVersionIdentifier (or None if
    not active)."""
    tmpdir = Path(tempfile.mkdtemp(prefix="scorer-check-"))
    try:
        _, xml_path = _prepare_package(tmpdir, scorer, active_version_identifier=None)
        sf_apex.project_retrieve(org_alias, str(xml_path), project_root=str(tmpdir))
        return _extract_active_version_identifier(xml_path.read_text())
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _prepare_package(
    tmpdir: Path,
    scorer: ScorerSpec,
    *,
    active_version_identifier: str | None,
) -> tuple[Path, Path]:
    """Write an sfdx-project + the rendered XML into tmpdir. Returns (pkg_root, xml_path)."""
    pkg_dir = tmpdir / "force-app" / "main" / "default" / "genAiPromptTemplates"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    xml_path = pkg_dir / f"{scorer.name}.genAiPromptTemplate-meta.xml"
    xml_path.write_text(render_template(scorer, active_version_identifier=active_version_identifier))

    _write_sfdx_project(tmpdir)
    return pkg_dir, xml_path


# Without this registry block, `sf project deploy start` rejects
# .aiAgentScorerDefinition-meta.xml as an unknown metadata type.
# Confirmed against nnaffar/custom-scorer-claude-playground.
_SFDX_PROJECT = {
    "packageDirectories": [{"path": "force-app", "default": True}],
    "sourceApiVersion": "66.0",
    "registryCustomizations": {
        "suffixes": {"aiAgentScorerDefinition": "aiagentscorerdefinition"},
        "types": {
            "aiagentscorerdefinition": {
                "id": "aiagentscorerdefinition",
                "name": "AiAgentScorerDefinition",
                "suffix": "aiAgentScorerDefinition",
                "directoryName": "aiAgentScorerDefinitions",
                "inFolder": False,
                "strictDirectoryName": False,
            },
        },
    },
}


def _write_sfdx_project(tmpdir: Path) -> None:
    (tmpdir / "sfdx-project.json").write_text(json.dumps(_SFDX_PROJECT) + "\n")


def scorer_definition_exists(org_alias: str, developer_name: str) -> bool:
    """Check metadata listing for an AiAgentScorerDefinition by fullName."""
    records = sf_apex.list_metadata(org_alias, "AiAgentScorerDefinition")
    return any(r.get("fullName") == developer_name for r in records)


def list_scorer_definitions(org_alias: str) -> list[dict]:
    """Return a flat list of all AiAgentScorerDefinition records in the org.

    Fast path: uses `sf org list metadata` only, so each record has just
    `fullName` and a handful of metadata fields. Use
    `retrieve_scorer_definitions_detailed()` when you need the agent binding,
    isActive, samplingRate, etc.
    """
    return sf_apex.list_metadata(org_alias, "AiAgentScorerDefinition")


_SCORER_FIELD_RE = {
    "dataType": re.compile(r"<dataType>([^<]*)</dataType>"),
    "engineRef": re.compile(r"<engineRef>([^<]*)</engineRef>"),
    "agentApiName": re.compile(r"<agentApiName>([^<]*)</agentApiName>"),
    "isActive": re.compile(r"<isActive>([^<]*)</isActive>"),
    "samplingRate": re.compile(r"<samplingRate>([^<]*)</samplingRate>"),
    "description": re.compile(r"<description>([^<]*)</description>"),
}


def retrieve_scorer_definitions_detailed(
    org_alias: str,
    names: list[str] | None = None,
) -> list[dict]:
    """Retrieve scorer-definition XMLs and parse the agent-binding fields.

    If `names` is None, discovers them via `list_scorer_definitions` first.
    Returns one dict per scorer with keys: `name`, `dataType`, `engineRef`,
    `agentApiName`, `isActive`, `samplingRate`, `description`.
    """
    resolved: list[str] = (
        list(names) if names is not None
        else [r["fullName"] for r in list_scorer_definitions(org_alias) if r.get("fullName")]
    )
    if not resolved:
        return []

    tmpdir = Path(tempfile.mkdtemp(prefix="scorer-list-"))
    try:
        _write_sfdx_project(tmpdir)
        pkg_dir = tmpdir / "force-app" / "main" / "default" / "aiAgentScorerDefinitions"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        # Retrieve all at once. `sf project retrieve start --source-dir <dir>` works
        # with just the directory present, but we need file stubs so sf knows what
        # to pull. Writing empty stubs and letting retrieve overwrite them works.
        for n in resolved:
            (pkg_dir / f"{n}.aiAgentScorerDefinition-meta.xml").write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<AiAgentScorerDefinition xmlns="http://soap.sforce.com/2006/04/metadata"/>\n'
            )
        sf_apex.project_retrieve(org_alias, str(pkg_dir), project_root=str(tmpdir))
        out: list[dict] = []
        for n in resolved:
            xml_path = pkg_dir / f"{n}.aiAgentScorerDefinition-meta.xml"
            if not xml_path.exists():
                out.append({"name": n, "error": "retrieve did not produce XML"})
                continue
            xml = xml_path.read_text()
            parsed: dict = {"name": n}
            for key, rx in _SCORER_FIELD_RE.items():
                m = rx.search(xml)
                parsed[key] = m.group(1) if m else None
            is_active = parsed.get("isActive")
            if isinstance(is_active, str):
                parsed["isActive"] = is_active.lower() == "true"
            sampling = parsed.get("samplingRate")
            if isinstance(sampling, str):
                try:
                    parsed["samplingRate"] = float(sampling)
                except ValueError:
                    pass
            out.append(parsed)
        return out
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def deploy_scorer_definition(
    org_alias: str,
    scorer: ScorerSpec,
    *,
    verbose: bool = True,
) -> None:
    """Deploy the AiAgentScorerDefinition XML (step 4 of the 4-step flow).

    Requires the prompt template to already be deployed and active in the org,
    because `engineRef` must resolve to an active template.
    """
    if not scorer.agent_api_name:
        raise ValueError(
            f"Cannot deploy scorer definition for '{scorer.name}': "
            "agent_api_name is not set on the spec."
        )
    tmpdir = Path(tempfile.mkdtemp(prefix="scorer-def-deploy-"))
    success = False
    try:
        pkg_dir = tmpdir / "force-app" / "main" / "default" / "aiAgentScorerDefinitions"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        xml_path = pkg_dir / f"{scorer.name}.aiAgentScorerDefinition-meta.xml"
        xml_path.write_text(render_scorer_definition(scorer))
        _write_sfdx_project(tmpdir)

        if verbose:
            print(f"  [4/4] Deploying AiAgentScorerDefinition ({scorer.name})...")
        sf_apex.project_deploy(org_alias, str(xml_path), project_root=str(tmpdir))
        if verbose:
            print(f"Scorer definition '{scorer.name}' deployed.")
        success = True
    finally:
        if success:
            shutil.rmtree(tmpdir, ignore_errors=True)
        elif verbose:
            print(f"  (scorer-def deploy artifacts kept at {tmpdir} for debugging)")


def ensure_scorer_fully_deployed(
    org_alias: str,
    scorer: ScorerSpec,
    *,
    verbose: bool = True,
) -> None:
    """Deploy the prompt template (3-step) AND the scorer definition (step 4).

    If `scorer.agent_api_name` is not set, only the template is deployed —
    caller should have already decided this path is appropriate.
    """
    ensure_prompt_template_deployed(org_alias, scorer, verbose=verbose)
    if scorer.agent_api_name:
        deploy_scorer_definition(org_alias, scorer, verbose=verbose)


_VERSION_RE = re.compile(r"<versionIdentifier>([^<]+)</versionIdentifier>")
_ACTIVE_VERSION_RE = re.compile(r"<activeVersionIdentifier>([^<]+)</activeVersionIdentifier>")


def _extract_version_identifier(xml: str) -> str:
    m = _VERSION_RE.search(xml)
    if not m:
        raise RuntimeError(
            "Could not find <versionIdentifier> in retrieved XML. "
            "This means the retrieve succeeded but Salesforce did not assign a version id — "
            "likely a deployment problem. Check the tempdir for the XML."
        )
    return m.group(1)


def _extract_active_version_identifier(xml: str) -> str | None:
    m = _ACTIVE_VERSION_RE.search(xml)
    return m.group(1) if m else None
