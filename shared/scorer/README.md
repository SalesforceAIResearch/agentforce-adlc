# custom-scorer-prompt-cli

A CLI for running Agentforce custom scorers against real agent sessions. Uses canonical STDM JSON + the Einstein Prompt Template Generations Connect API. No Apex, no mesh, no Sync API.

## What it does

1. Lists agent sessions in a target org (via Data Cloud SQL on STDM DMOs).
2. Builds canonical STDM JSON for a chosen session — direct Python port of Core's `StdmBuilder`.
3. Runs a scorer (an LLM-as-judge prompt template) against the session:
   - If the scorer's `GenAiPromptTemplate` is not deployed in the org, auto-deploys it.
   - Invokes via `POST /services/data/v64.0/einstein/prompt-templates/{scorer_name}/generations`.
4. Prints the scorer's label + reasoning per session.

## Architecture

```
User (or Claude Code)
    │
    ▼
Python CLI
    ├──► sf api request rest → POST /services/data/v62.0/ssot/query
    │      (3 parallel SOQL queries on STDM DMOs)
    │      - MessageQueryBuilder SQL  → message rows
    │      - StepQueryBuilder SQL     → step rows (ACTION_STEP + TURN only)
    │      - SessionParticipantQueryBuilder SQL → participant rows
    │
    ├──► stdm_builder.py (Python port of Core StdmBuilder.java)
    │      - Groups rows by session
    │      - Assembles SessionView JSON (sessionState, actors, metrics, runs)
    │      - Matches Core's DTO schema byte-for-structure
    │
    ├──► auto-deploy scorer template if missing (3-step flow)
    │
    └──► sf api request rest → POST /services/data/v64.0/einstein/prompt-templates/
                                      {scorer}/generations
           Body: {inputParams: {valueMap: {Input:Session: {value: <STDM>}, ...}}}
           Response: structured JSON {output:["Label"], explanation:"..."}
```

## Prerequisites

- Python 3.10+
- [Salesforce CLI](https://developer.salesforce.com/tools/salesforcecli) (`sf`) authenticated to your target org: `sf org login web --alias <alias>`
- Org must have Agentforce + Data Cloud + session-tracing DMOs provisioned

**No Apex helper deploy is required** — all data access uses direct Data Cloud SQL.

## First-time setup

```bash
# 1. Clone the repo.
git clone https://git.soma.salesforce.com/emaizenstein/custom-scorer-prompt-cli.git
cd custom-scorer-prompt-cli

# 2. Create a virtualenv (Python 3.10+).
python3.11 -m venv .venv

# 3. Activate the venv. Run this every time you open a new shell.
source .venv/bin/activate                  # macOS / Linux
# .venv\Scripts\Activate.ps1                # Windows PowerShell

# 4. Install the CLI + its dependencies (editable mode, with test extras).
pip install -e '.[dev]'

# 5. Make sure the sf CLI is authenticated against the org you'll target.
sf org login web --alias yuval-org1
```

After step 4 a `scorer-cli` command is installed in the venv. Either keep the
venv activated (then `scorer-cli ...` works directly) or invoke the CLI
explicitly via `.venv/bin/python -m src.cli ...` / `.venv/bin/scorer-cli ...`.

## Daily use

```bash
cd custom-scorer-prompt-cli
source .venv/bin/activate
scorer-cli agents --org yuval-org1
```

The examples below use `.venv/bin/python -m src.cli ...` for clarity — but if
your venv is activated you can substitute `scorer-cli` for the same effect.

## Usage

### List agents

```bash
.venv/bin/python -m src.cli agents --org yuval-org1
```

Lists distinct agents (`agent_api_name` + type) that have participated in sessions. Use the output with `--agent` in `sessions`, `score-and-fetch`, and `deploy-scorer`.

### List recent sessions

```bash
.venv/bin/python -m src.cli sessions --org yuval-org1 --limit 5

# Optionally filter by agent.
.venv/bin/python -m src.cli sessions --org yuval-org1 --agent ASA_Voice --limit 5
```

### List deployed scorers

```bash
# Flat fullName list (fast).
.venv/bin/python -m src.cli scorers --org yuval-org1

# Retrieve each XML to show agent binding, isActive, samplingRate, engineRef.
.venv/bin/python -m src.cli scorers --org yuval-org1 --detailed

# Filter to scorers bound to a specific agent (implies --detailed).
.venv/bin/python -m src.cli scorers --org yuval-org1 --agent Agentforce_Service_Agent_Dudi
```

### Score a session

```bash
.venv/bin/python -m src.cli score \
    --org yuval-org1 \
    --scorer response_quality_stdm \
    --session-id 019dc9c6-30aa-788c-98d7-02aebd2c03ed
```

On first run, the scorer's prompt template is auto-deployed (~30–60s). Subsequent runs hit the fast path.

### Convenience: score the N most recent sessions

```bash
# Across all agents.
.venv/bin/python -m src.cli score-and-fetch \
    --org yuval-org1 \
    --scorer response_quality_stdm \
    --last 3

# Restrict the sample to a specific agent's sessions.
.venv/bin/python -m src.cli score-and-fetch \
    --org yuval-org1 \
    --agent Agentforce_Sales_Development_Rep \
    --scorer response_quality_stdm \
    --last 3
```

### Bring your own scorer

Author a YAML:

```yaml
name: my_custom_scorer
description: "What I want to measure"
data_type: Text
primary_model: sfdc_ai__DefaultOpenAIGPT4OmniMini
allowed_labels: [Great, Okay, Bad, Unknown]
fallback_label: Unknown
prompt: |
  Evaluate this conversation against my criteria.
  Respond ONLY with one of: {!$Input:AllowedLabels}
  or fallback to: {!$Input:FallbackLabel}

  session audit data:
  {!$Input:Session}
```

Then:

```bash
.venv/bin/python -m src.cli score \
    --org yuval-org1 \
    --scorer ./my_custom_scorer.yaml \
    --session-id <uuid>
```

The CLI auto-deploys it on first use.

`primary_model` must be one of the identifiers Salesforce recognizes for prompt templates. Run `python -m src.cli models` to see the supported list (see [Refreshing the supported-models catalog](#refreshing-the-supported-models-catalog) below).

### Explicit deploy without running

Two deploy shapes, depending on whether you want the scorer to appear in Agentforce Studio:

```bash
# Template only — deploys the GenAiPromptTemplate (3-step deploy/retrieve/activate).
# Scoring via this CLI works; the scorer will NOT appear in Agentforce Studio.
.venv/bin/python -m src.cli deploy-scorer \
    --org yuval-org1 --scorer response_quality_stdm

# Full scorer — also deploys an AiAgentScorerDefinition bound to an agent.
# The scorer appears in Agentforce Studio and can sample live sessions.
.venv/bin/python -m src.cli deploy-scorer \
    --org yuval-org1 --scorer response_quality_stdm \
    --agent-api-name Agentforce_Service_Agent_Dudi \
    [--activate] [--sampling-rate 1.0] --force
```

`--activate` sets `isActive=true` on the scorer definition (off by default). `--sampling-rate` controls the fraction of live sessions the scorer samples automatically.

#### Prompt template vs scorer definition

| Metadata | Studio location | Required for |
|---|---|---|
| `GenAiPromptTemplate` (`scorerMultilabel`) | Prompt Builder → Prompt Templates | `score` / `score-and-fetch` (Einstein Prompt Template Generations endpoint) |
| `AiAgentScorerDefinition` | Agentforce Studio → Scorers | Showing up as a scorer in Studio; auto-sampling live sessions for an agent |

The scorer definition binds to the template by `developerName` only (no version), so **redeploying the template does not require redeploying the scorer definition**. Redeploy the scorer only when its own fields change (labels, bound agent, `isActive`, `samplingRate`).

## Refreshing the supported-models catalog

The list of LLM models you can pin as `primary_model` lives in `src/model_catalog.py` — a pinned snapshot of Salesforce's [Agentforce supported models](https://developer.salesforce.com/docs/ai/agentforce/guide/supported-models.html) page. Salesforce does not publish a runtime endpoint for this list, so the catalog is hand-refreshed.

### When to refresh

- A deploy fails with `INVALID_PRIMARY_MODEL` because the user picked an identifier the catalog doesn't know about.
- Salesforce release notes mention a new GA model, or a beta gets promoted.
- Otherwise: once a quarter is plenty. Stick a 15-minute calendar block on the first Monday of each quarter.

### How to refresh

1. **See what changed** (no writes):
   ```bash
   python scripts/refresh_model_catalog.py
   ```
   The script fetches the supported-models page, parses the first table, and prints `Added` / `Removed` / `Changed` against the current `CATALOG`. If nothing changed, you're done.

2. **Apply the changes**:
   ```bash
   python scripts/refresh_model_catalog.py --write
   ```
   Rewrites `src/model_catalog.py` in place and bumps the `Snapshot date:` line in the file header. Inspect the diff with `git diff src/model_catalog.py`, run `python -m src.cli models` to spot-check the table, then commit.

The script does not preserve manual edits to `notes` — if you've added local context to an entry, re-apply it after the rewrite.

### Why this isn't automated

A GitHub Actions cron that runs the refresh and opens a PR would work. We haven't added one yet because (a) the catalog churn is low — a few times a year — and (b) the script's heuristics for `provider` and `flags` benefit from a human glance after a doc update. If maintenance becomes annoying, see `scripts/refresh_model_catalog.py` — wiring it into a workflow is straightforward.

## Bundled scorers

Under `scorer_specs/`:

- **`response_quality_stdm`** — Excellent / Good / Adequate / Poor / Inconclusive (canonical STDM, recommended)
- **`user_frustration_stdm`** — Not_Frustrated / Mildly_Frustrated / Frustrated / Very_Frustrated / Unknown (canonical STDM)
- `response_quality_v2`, `user_frustration_v2`, `sentiment_analysis` — legacy primitive-string variants, kept for reference

## How the STDM is built

Three parallel Data Cloud SQL queries — ported verbatim from Core's `MessageQueryBuilder.java`, `StepQueryBuilder.java`, `SessionParticipantQueryBuilder.java`:

- `MessageQueryBuilder` → messages joined with their interactions (LEFT JOIN)
- `StepQueryBuilder` → steps joined with interactions, filtered to `ACTION_STEP` + `TURN`
- `SessionParticipantQueryBuilder` → session metadata + per-participant actor data

Rows are fed into `stdm_builder.py` — a line-by-line Python port of `StdmBuilder.assembleStdmDetailViews()`. Same grouping, same `actorById` lookup, same TURN filter, same metric math, same dedup-by-`participantId`. 16 parity tests verify the port against Core's own `StdmBuilderTest.java` fixtures.

Output matches Core's `SessionView` DTOs exactly: `sessionState`, `actors[]`, `metrics`, `runs[].messages[]`, `runs[].agentLoop.steps[]`. All `@JsonInclude(NON_NULL)` fields omitted when null; `@JsonIgnore` fields (`sessionParticipantId`, `interactionType`) stripped from output.

## Wire format

The CLI POSTs to the Connect API **Einstein Prompt Template Generations** endpoint:

```
POST /services/data/v64.0/einstein/prompt-templates/{dev_name}/generations
Content-Type: application/json

{
  "isPreview": false,
  "inputParams": {
    "valueMap": {
      "Input:Session":       {"value": {...canonical STDM JSON...}},
      "Input:AllowedLabels": {"value": "Excellent,Good,..."},
      "Input:FallbackLabel": {"value": "Inconclusive"}
    }
  },
  "additionalConfig": {"applicationName": "PromptTemplateGenerationsInvocable"}
}
```

**Important**: do NOT use `POST /actions/custom/generatePromptResponse/{dev_name}` — that endpoint rejects `stdmDetailViewType` inputs with a confusing `$.sessionState is missing` error. The Einstein Prompt Template Generations Connect API endpoint handles the type correctly.

See Salesforce's [Connect API reference for Prompt Templates](https://developer.salesforce.com/docs/atlas.en-us.chatterapi.meta/chatterapi/connect_resources_prompt_template.htm).

## Known limitations

- **Default dataspace only.** Table/field prefixes (`ssot__...__dlm`, `ssot__...__c`) are hardcoded.
- **Single-session STDM per call.** The builder handles multi-session input, but `fetch_session_stdm()` runs one at a time; CLI loops.
- **Per-session prompt length.** Long conversations with large action outputs may push `Input:Session` near LLM context limits. No truncation yet.
- **Scorer name collision.** The existence check uses `sf org list metadata`; if a template with the same `developerName` already exists in the org, the CLI assumes it's compatible and runs against it. Sanity-check template content if unsure.

## Project structure

```
src/
  cli.py                 # click entrypoint
  sf_apex.py             # sf CLI shell-out + response parsing
  datacloud_query.py     # 3 SOQL builders + run_sql (Data Cloud SQL wrapper)
  stdm_builder.py        # Python port of Core's StdmBuilder
  session_stdm.py        # orchestration: 3 parallel SQLs + builder
  scorer_spec.py         # YAML loader + validation
  xml_render.py          # Jinja2 → GenAiPromptTemplate XML
  scorer_deployer.py     # existence check + 3-step auto-deploy
  prompt_template.py     # Connect API einstein/prompt-templates invoker
scorer_specs/            # bundled YAML scorers
templates/               # Jinja2 XML template
tests/                   # 38 offline tests (SOQL snapshots, STDM parity, XML render, spec validation)
```

## Provenance

- **StdmBuilder port** — from `core/agentforce-session-tracing-impl/java/src/agentforce/session/tracing/impl/evals/runtime/event/processing/enrichment/StdmBuilder.java`.
- **SOQL query builders** — from `core/agentforce-session-tracing-impl/java/src/agentforce/session/tracing/impl/datacloud/query/{Message,Step,SessionParticipant}QueryBuilder.java`.
- **DTO schema reference** — `core/agentforce-session-tracing-impl/java/src/agentforce/session/tracing/impl/evals/dto/stdm/*.java`.
- **Scorer deploy protocol** — from the playground repo's `sf-ai-agentforce-scorer` skill.
