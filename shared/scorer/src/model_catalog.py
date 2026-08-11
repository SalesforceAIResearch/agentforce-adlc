"""Catalog of LLM models supported as `primaryModel` on Agentforce scorers.

Source: https://developer.salesforce.com/docs/ai/agentforce/guide/supported-models.html
Snapshot date: 2026-05-11

Salesforce does not publish a Connect/REST endpoint that lists available
models for an org — the supported-models page above is the authoritative
catalog. When that page changes (new model GA'd, beta promoted, model
retired), refresh the entries below by hand.

Each entry carries:
  - identifier — the exact string that goes into <primaryModel> in the
    GenAiPromptTemplate metadata XML, i.e. the value of `primary_model`
    in scorer YAML.
  - label — human-friendly display name.
  - provider — provider/gateway, used to group options in the picker.
  - modality — "chat" or "embeddings". Only "chat" models can drive a
    scorerMultilabel prompt template.
  - flags — set of strings; recognized values: "beta", "geo-aware",
    "trust-boundary".
  - notes — free-text caveats (region restrictions, retirement dates).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Model:
    identifier: str
    label: str
    provider: str
    modality: str  # "chat" | "embeddings"
    flags: frozenset[str] = field(default_factory=frozenset)
    notes: str = ""

    @property
    def is_beta(self) -> bool:
        return "beta" in self.flags

    @property
    def is_embeddings(self) -> bool:
        return self.modality == "embeddings"


CATALOG: tuple[Model, ...] = (
    # Bedrock / Amazon
    Model("sfdc_ai__DefaultBedrockAmazonNovaLite",
          "Amazon Nova Lite on Amazon Bedrock", "Amazon Bedrock", "chat",
          frozenset({"trust-boundary"})),
    Model("sfdc_ai__DefaultBedrockAmazonNovaPro",
          "Amazon Nova Pro on Amazon Bedrock", "Amazon Bedrock", "chat",
          frozenset({"trust-boundary"})),

    # Bedrock / Anthropic
    Model("sfdc_ai__DefaultBedrockAnthropicClaude45Haiku",
          "Anthropic Claude Haiku 4.5 on Amazon Bedrock", "Anthropic / Bedrock", "chat",
          frozenset({"trust-boundary"})),
    Model("sfdc_ai__DefaultBedrockAnthropicClaude45Opus",
          "Anthropic Claude Opus 4.5 on Amazon Bedrock", "Anthropic / Bedrock", "chat",
          frozenset({"trust-boundary"})),
    Model("sfdc_ai__DefaultBedrockAnthropicClaude46Opus",
          "Anthropic Claude Opus 4.6 on Amazon Bedrock", "Anthropic / Bedrock", "chat",
          frozenset({"trust-boundary", "beta"})),
    Model("sfdc_ai__DefaultBedrockAnthropicClaude47Opus",
          "Anthropic Claude Opus 4.7 on Amazon Bedrock", "Anthropic / Bedrock", "chat",
          frozenset({"trust-boundary", "beta"})),
    Model("sfdc_ai__DefaultBedrockAnthropicClaude4Sonnet",
          "Anthropic Claude Sonnet 4 on Amazon Bedrock", "Anthropic / Bedrock", "chat",
          frozenset({"trust-boundary"})),
    Model("sfdc_ai__DefaultBedrockAnthropicClaude45Sonnet",
          "Anthropic Claude Sonnet 4.5 on Amazon Bedrock", "Anthropic / Bedrock", "chat",
          frozenset({"trust-boundary"})),
    Model("sfdc_ai__DefaultBedrockAnthropicClaude46Sonnet",
          "Anthropic Claude Sonnet 4.6 on Amazon Bedrock", "Anthropic / Bedrock", "chat",
          frozenset({"trust-boundary"})),

    # Bedrock / NVIDIA
    Model("sfdc_ai__DefaultBedrockNvidiaNemotronNano330b",
          "NVIDIA Nemotron 3 Nano 30B on Amazon Bedrock", "Amazon Bedrock", "chat",
          frozenset({"beta"})),

    # Embeddings (won't drive a scorer; surfaced only with --include-embeddings)
    Model("sfdc_ai__DefaultAzureOpenAITextEmbeddingAda_002",
          "Azure OpenAI Ada 002", "Azure OpenAI", "embeddings",
          notes="Models API only"),
    Model("sfdc_ai__DefaultOpenAITextEmbeddingAda_002",
          "OpenAI Ada 002", "OpenAI", "embeddings",
          notes="Models API only"),

    # GPT-4o family (geo-aware OpenAI/Azure cross-routed)
    Model("sfdc_ai__DefaultGPT4Omni", "GPT-4o (OpenAI / Azure OpenAI)",
          "OpenAI / Azure OpenAI", "chat", frozenset({"geo-aware"})),
    Model("sfdc_ai__DefaultGPT4OmniMini", "GPT-4o mini (OpenAI / Azure OpenAI)",
          "OpenAI / Azure OpenAI", "chat", frozenset({"geo-aware"})),

    # GPT-4o mini, OpenAI-only (the historical default in scorer_specs/)
    Model("sfdc_ai__DefaultOpenAIGPT4OmniMini", "GPT-4o mini (OpenAI only)",
          "OpenAI", "chat"),

    # GPT 4.1 / 5.x family (geo-aware)
    Model("sfdc_ai__DefaultGPT41", "GPT-4.1 (OpenAI / Azure OpenAI)",
          "OpenAI / Azure OpenAI", "chat", frozenset({"geo-aware"})),
    Model("sfdc_ai__DefaultGPT41Mini", "GPT-4.1 Mini (OpenAI / Azure OpenAI)",
          "OpenAI / Azure OpenAI", "chat", frozenset({"geo-aware"})),
    Model("sfdc_ai__DefaultGPT5", "GPT-5 (OpenAI / Azure OpenAI)",
          "OpenAI / Azure OpenAI", "chat", frozenset({"geo-aware"})),
    Model("sfdc_ai__DefaultGPT5Mini", "GPT-5 Mini (OpenAI / Azure OpenAI)",
          "OpenAI / Azure OpenAI", "chat", frozenset({"geo-aware"})),
    Model("sfdc_ai__DefaultGPT51", "GPT-5.1 (OpenAI / Azure OpenAI)",
          "OpenAI / Azure OpenAI", "chat", frozenset({"geo-aware"})),
    Model("sfdc_ai__DefaultGPT52", "GPT-5.2 (OpenAI / Azure OpenAI)",
          "OpenAI / Azure OpenAI", "chat", frozenset({"geo-aware"})),
    Model("sfdc_ai__DefaultGPT54", "GPT-5.4 (OpenAI / Azure OpenAI)",
          "OpenAI / Azure OpenAI", "chat", frozenset({"geo-aware"})),
    Model("sfdc_ai__DefaultGPT54Mini", "GPT-5.4 Mini (OpenAI / Azure OpenAI)",
          "OpenAI / Azure OpenAI", "chat", frozenset({"geo-aware", "beta"})),
    Model("sfdc_ai__DefaultGPT55", "GPT-5.5 (OpenAI / Azure OpenAI)",
          "OpenAI / Azure OpenAI", "chat", frozenset({"geo-aware", "beta"})),

    # OpenAI o-series reasoning models
    Model("sfdc_ai__DefaultO3", "O3 (OpenAI / Azure OpenAI)",
          "OpenAI / Azure OpenAI", "chat", frozenset({"geo-aware"})),
    Model("sfdc_ai__DefaultO4Mini", "O4 Mini (OpenAI / Azure OpenAI)",
          "OpenAI / Azure OpenAI", "chat", frozenset({"geo-aware"})),

    # Vertex AI / Google
    Model("sfdc_ai__DefaultVertexAIGemini25Flash001",
          "Vertex AI Gemini 2.5 Flash", "Google Vertex AI", "chat"),
    Model("sfdc_ai__DefaultVertexAIGemini25FlashLite001",
          "Vertex AI Gemini 2.5 Flash Lite", "Google Vertex AI", "chat"),
    Model("sfdc_ai__DefaultVertexAIGeminiPro25",
          "Vertex AI Gemini 2.5 Pro", "Google Vertex AI", "chat"),
    Model("sfdc_ai__DefaultVertexAIGemini30Flash",
          "Vertex AI Gemini 3 Flash", "Google Vertex AI", "chat"),
    Model("sfdc_ai__DefaultVertexAIGeminiPro30",
          "Vertex AI Gemini 3 Pro", "Google Vertex AI", "chat",
          frozenset({"beta"}), notes="Retiring 2026-04-23"),
    Model("sfdc_ai__DefaultVertexAIGemini31FlashLite",
          "Vertex AI Gemini 3.1 Flash Lite", "Google Vertex AI", "chat",
          frozenset({"beta"})),
    Model("sfdc_ai__DefaultVertexAIGeminiPro31",
          "Vertex AI Gemini 3.1 Pro", "Google Vertex AI", "chat",
          frozenset({"beta"})),
)


# Sensible defaults the skill picks as the top 3 options when running
# `models` without filters. Order matters — first is the recommended default.
DEFAULT_PICKS: tuple[str, ...] = (
    "sfdc_ai__DefaultOpenAIGPT4OmniMini",            # cheap baseline, current default in scorer_specs
    "sfdc_ai__DefaultGPT5",                          # premium OpenAI tier
    "sfdc_ai__DefaultBedrockAnthropicClaude45Sonnet",  # alt-vendor strong reasoner
)


def list_models(
    *,
    include_beta: bool = False,
    include_embeddings: bool = False,
) -> list[Model]:
    """Return the catalog filtered for use as a scorer primary model.

    Defaults exclude embeddings (can't drive a scorer prompt template) and
    beta entries (they churn). Pass include_* to opt in.
    """
    out: list[Model] = []
    for m in CATALOG:
        if not include_embeddings and m.is_embeddings:
            continue
        if not include_beta and m.is_beta:
            continue
        out.append(m)
    return out


def lookup(identifier: str) -> Model | None:
    """Return the catalog entry for an identifier, or None if unknown.

    Useful for displaying the friendly label of a model already pinned in
    a scorer YAML.
    """
    for m in CATALOG:
        if m.identifier == identifier:
            return m
    return None


def to_jsonable(m: Model) -> dict:
    """Serialize a Model for JSON output."""
    return {
        "identifier": m.identifier,
        "label": m.label,
        "provider": m.provider,
        "modality": m.modality,
        "flags": sorted(m.flags),
        "notes": m.notes,
    }
