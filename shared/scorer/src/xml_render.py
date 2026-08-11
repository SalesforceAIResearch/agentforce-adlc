"""Render GenAiPromptTemplate XML from a ScorerSpec using Jinja2."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .scorer_spec import ScorerSpec

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _escape_xml(text: str) -> str:
    """XML-escape for element content. Matches Salesforce metadata conventions:
    &, <, >, and ' → entities. Quotes are only escaped in attribute values, not content."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("'", "&apos;"))


def _make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    env.filters["escape_xml"] = _escape_xml
    return env


def render(spec: ScorerSpec, *, active_version_identifier: str | None = None) -> str:
    """Render the GenAiPromptTemplate XML for the given scorer.

    On first deploy, pass active_version_identifier=None. After retrieving
    the server-assigned versionIdentifier, re-render with it to activate.
    """
    env = _make_env()
    template = env.get_template("genAiPromptTemplate.xml.j2")
    return template.render(spec=spec, active_version_identifier=active_version_identifier)


def render_scorer_definition(spec: ScorerSpec) -> str:
    """Render the AiAgentScorerDefinition XML for the given scorer.

    `spec.agent_api_name` must be set — it's required by the metadata type
    and has no sensible default.
    """
    if not spec.agent_api_name:
        raise ValueError(
            f"Cannot render scorer definition for '{spec.name}': "
            "agent_api_name is not set on the spec."
        )
    env = _make_env()
    template = env.get_template("aiAgentScorerDefinition.xml.j2")
    return template.render(spec=spec)
