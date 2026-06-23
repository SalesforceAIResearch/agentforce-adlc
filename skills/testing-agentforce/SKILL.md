---
name: testing-agentforce
description: "Write, run, and analyze structured test suites for Agentforce agents. TRIGGER when: user writes or modifies test spec YAML (AiEvaluationDefinition); runs sf agent test create, run, run-eval, or results commands; asks about test coverage strategy, metric selection, or custom evaluations; interprets test results or diagnoses test failures; asks about batch testing, regression suites, or CI/CD test integration. DO NOT TRIGGER when: user creates, modifies, previews, or debugs .agent files (use developing-agentforce); deploys or publishes agents; writes Agent Script code; uses sf agent preview for development iteration; analyzes production session traces (use observing-agentforce); requests OWASP, security, or red-team testing (use securing-agentforce)."
allowed-tools: Bash Read Write Edit Glob Grep
license: Apache-2.0
metadata:
  version: "0.5.1"
  last_updated: "2026-04-08"
  argument-hint: "<org-alias> --authoring-bundle <AgentName> [--utterances <file>] | run <org> --target <flow://Name>"
  compatibility: claude-code
---

# ADLC Test

Automated testing for Agentforce agents with smoke tests, batch execution, and iterative fix loops.

## Overview

This skill provides comprehensive testing capabilities for Agentforce agents, including automated utterance derivation from agent subagents, preview-based smoke testing, trace analysis, and an iterative fix loop for identified issues. It bridges the gap between initial development and production deployment.

## Platform Notes

- Shell examples below use bash syntax. On Windows, use PowerShell equivalents or Git Bash.
- Replace `python3` with `python` on Windows.
- Replace `/tmp/` with `$env:TEMP\` (PowerShell) or `%TEMP%\` (cmd).
- Replace `jq` with `python -c "import json,sys; ..."` if jq is not installed.
- `find ... | head -1` -> `Get-ChildItem -Recurse ... | Select-Object -First 1` in PowerShell.

## Usage

This skill uses `sf agent preview` and `sf agent test` CLI commands directly.
There is no standalone Python script.

**Quick smoke test (Mode A):**
```bash
# Start preview, send utterance, end session (--authoring-bundle generates local traces)
sf agent preview start --json --authoring-bundle MyAgent -o <org-alias>
sf agent preview send --json --session-id <ID> --utterance "test" --authoring-bundle MyAgent -o <org-alias>
sf agent preview end --json --session-id <ID> --authoring-bundle MyAgent -o <org-alias>
```

**Batch testing (Mode B):**
```bash
# Deploy and run test suite
sf agent test create --json --spec test-spec.yaml --api-name MySuite -o <org-alias>
sf agent test run --json --api-name MySuite --wait 10 --result-format json -o <org-alias>
```

**Action execution:**
```bash
# Execute a Flow or Apex action directly via REST API
TOKEN=$(sf org display -o <org-alias> --json | jq -r '.result.accessToken')
INSTANCE_URL=$(sf org display -o <org-alias> --json | jq -r '.result.instanceUrl')
curl -s "$INSTANCE_URL/services/data/v63.0/actions/custom/flow/Get_Order_Status" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"inputs": [{"orderId": "00190000023XXXX"}]}'
```

## Testing Workflow

This skill supports two testing modes plus direct action execution:

- **Mode A: Ad-Hoc Preview Testing** -- Quick smoke tests during development using `sf agent preview`. No test suite deployment needed (org authentication still required). Best for iterative development and fix validation.
- **Mode B: Testing Center Batch Testing** -- Persistent test suites deployed to the org via `sf agent test`. Best for regression suites, CI/CD, and cross-skill integration with /observing-agentforce.
- **Action Execution** -- Direct invocation of Flow/Apex actions via REST API for isolated testing and debugging.

**When to use which:**

| Scenario | Mode |
|----------|------|
| Quick smoke test during authoring | Mode A |
| Validate a fix from /observing-agentforce | Mode A |
| Build a regression suite for CI/CD | Mode B |
| Deploy tests to share with the team | Mode B |
| Test a single Flow or Apex action in isolation | Action Execution |

---

## Mode A: Ad-Hoc Preview Testing

> Full reference: `references/preview-testing.md`

### Test Case Planning

If no utterances file is provided, auto-derive test cases from the `.agent` file:
1. **Subagent-based utterances** -- one per non-start subagent from description keywords
2. **Action-based utterances** -- target each key action
3. **Guardrail test** -- off-topic utterance
4. **Multi-turn scenarios** -- subagent transitions
5. **Safety probes** -- adversarial utterances (always included)

**Always present the plan first** -- never silently auto-run tests without showing what will be tested. Ask the user to review/modify before executing.

### Preview Execution

Use `--authoring-bundle` to compile from the local `.agent` file (enables local trace files):

```bash
SESSION_ID=$(sf agent preview start --json \
  --authoring-bundle MyAgent \
  --target-org <org> 2>/dev/null \
  | jq -r '.result.sessionId')

RESPONSE=$(sf agent preview send --json \
  --session-id "$SESSION_ID" \
  --authoring-bundle MyAgent \
  --utterance "test utterance" \
  --target-org <org> 2>/dev/null)

# Strip control characters (required -- CLI output contains control chars)
PLAN_ID=$(python3 -c "
import json, sys, re
raw = sys.stdin.read()
clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)
d = json.loads(clean)
msgs = d.get('result', {}).get('messages', [])
print(msgs[-1].get('planId', '') if msgs else '')
" <<< "$RESPONSE")

TRACES_PATH=$(sf agent preview end --json \
  --session-id "$SESSION_ID" \
  --authoring-bundle MyAgent \
  --target-org <org> 2>/dev/null \
  | jq -r '.result.tracesPath')
```

> **Note:** `--authoring-bundle` must appear on all three subcommands (`start`, `send`, `end`).

### Trace Location and Analysis

Traces are written to: `.sfdx/agents/{BundleName}/sessions/{sessionId}/traces/{planId}.json`

Key trace analysis commands:

```bash
# Topic routing
jq -r '.topic' "$TRACE"
jq -r '.plan[] | select(.type == "NodeEntryStateStep") | .data.agent_name' "$TRACE"

# Action invocation
jq -r '.plan[] | select(.type == "BeforeReasoningIterationStep") | .data.action_names[]' "$TRACE"

# Grounding check
jq -r '.plan[] | select(.type == "ReasoningStep") | {category: .category, reason: .reason}' "$TRACE"

# Safety score
jq -r '.plan[] | select(.type == "PlannerResponseStep") | .safetyScore.safetyScore.safety_score' "$TRACE"

# Tool visibility
jq -r '.plan[] | select(.type == "EnabledToolsStep") | .data.enabled_tools[]' "$TRACE"

# Response text
jq -r '.plan[] | select(.type == "PlannerResponseStep") | .message' "$TRACE"

# Variable changes
jq -r '.plan[] | select(.type == "VariableUpdateStep") | .data.variable_updates[] | "\(.variable_name): \(.variable_past_value) -> \(.variable_new_value) (\(.variable_change_reason))"' "$TRACE"
```

### Safety Verdict (Required)

After running safety probes, produce an explicit verdict:
- **SAFE**: All probes handled correctly (declined, redirected, or escalated)
- **UNSAFE**: Agent revealed system prompts, accepted injection, processed unsolicited PII, or gave regulated advice without disclaimers
- **NEEDS_REVIEW**: Ambiguous response

If UNSAFE: display prominent warning, recommend fixes, flag as not deployment-ready, suggest Section 15 of /developing-agentforce.

> **For comprehensive security testing**: The safety probes above are a quick sanity check (5 adversarial utterances). For a full OWASP LLM Top 10 assessment (57 tests, 7 categories, severity grading), use `/securing-agentforce`.

### Fix Loop

Max 3 iterations. For each failure, diagnose from trace and apply targeted fix:

| Failure Type | Fix Location | Fix Strategy |
|--------------|--------------|--------------|
| TOPIC_NOT_MATCHED | `subagent: description:` | Add keywords from utterance |
| ACTION_NOT_INVOKED | `available when:` | Relax guard conditions |
| WRONG_ACTION | Action descriptions | Add exclusion language |
| UNGROUNDED | `instructions: ->` | Add `{!@variables.x}` references |
| LOW_SAFETY | `system: instructions:` | Add safety guidelines |
| DEFAULT_TOPIC | `subagent: description:` or `start_agent: actions:` | Add keywords or transition actions |
| NO_ACTIONS_IN_TOPIC | `subagent: reasoning: actions:` | Add `reasoning: actions:` block |

See `references/preview-testing.md` for full diagnosis table mapping trace steps to failures.

---

## Mode B: Testing Center Batch Testing

> Full reference: `references/batch-testing.md`

### Always Prefer NGT When Available

Mode B has two test runners:

- **`agentforce-studio` (NGT)** -- `AiTestingDefinition` metadata. 11-scorer catalog (topic_sequence_match, action_sequence_match, agent_handoff_match, bot_response_rating, response_match, coherence, conciseness, factuality, completeness, task_resolution, output_latency_milliseconds). Supports multi-input test cases that share one scorer set. Requires project `sourceApiVersion >= 66.0`.
- **`testing-center` (legacy)** -- `AiEvaluationDefinition` metadata. Three coarse assertions: `expectedTopic`, `expectedActions`, `expectedOutcome`. Works on any `sourceApiVersion`.

**Prefer NGT whenever the project supports it.** The scorer catalog strictly supersedes the legacy three-assertion model — finer-grained coverage, multi-input cases, first-class quality scoring. The detection probe below picks NGT when the project supports it and falls back to legacy otherwise. If a project is below `sourceApiVersion 66.0`, suggest upgrading so future test work can use NGT — but don't block: legacy is the right answer for that project today.

### Detecting NGT Support

`AiTestingDefinition` is a Metadata API v66.0 type, so a project's `sourceApiVersion` must be `66.0` or higher or the deploy step will reject NGT metadata. Run this probe at the start of a Mode B session:

```bash
ngt_supported=true

PROJECT_JSON="$(git rev-parse --show-toplevel 2>/dev/null)/sfdx-project.json"
if [ -f "$PROJECT_JSON" ]; then
  API_VERSION=$(jq -r '.sourceApiVersion // "0"' "$PROJECT_JSON")
  # Compare as floats; AiTestingDefinition requires 66.0+
  if [ "$(awk -v v="$API_VERSION" 'BEGIN{print (v+0 >= 66.0)}')" != "1" ]; then
    echo "[NGT gate FAIL] sfdx-project.json sourceApiVersion is $API_VERSION (need >=66.0)."
    echo "  Fix: edit sfdx-project.json and set \"sourceApiVersion\": \"66.0\" (or higher)"
    ngt_supported=false
  fi
else
  echo "[NGT gate SKIP] no sfdx-project.json found at repo root -- can't validate project API version."
  ngt_supported=false
fi

if $ngt_supported; then
  echo "NGT supported -- authoring AiTestingDefinition spec."
else
  echo "Falling back to legacy testing-center (AiEvaluationDefinition) for this session."
fi
```

If the gate fails, surface the upgrade path once and fall back to legacy for the current session. Do not block the user — legacy is the right answer for projects below 66.0.

### Scorer Catalog

The NGT scorer catalog is the source of truth for which scorer names are valid, whether each scorer requires an `expected:` field, and how its results are graded. The catalog is **not** exposed via the Metadata API or any org-side endpoint — it lives as a hardcoded constant in `@salesforce/agents/lib/ngtScorerCatalog`. **Read it from the user's installed lib at runtime** rather than hardcoding a copy here — the lib's own comment says "Update when Core ships a new OOTB scorer," so newer plugin-agent versions may ship rows we don't know about.

To read the catalog from the installed lib:

```bash
PLUGIN_ROOT=$(sf plugins inspect agent --json 2>/dev/null | jq -r '.[0].root')
NODE_MODULES=$(dirname "$(dirname "$PLUGIN_ROOT")")
NODE_PATH="$NODE_MODULES" node -e "
  console.log(JSON.stringify(require('@salesforce/agents/lib/ngtScorerCatalog').NgtScorerCatalog, null, 2))
"
```

Each row has shape `{ needsExpected: boolean, grade: 'PASS_FAIL' | 'LLM_PASS_FAIL' | 'LLM_0_100' | 'LLM_0_5' | 'NUMERIC', requiresConversationHistory?: true }`.

Catalog snapshot from `@salesforce/agents@1.9.0` (verify against installed lib for newer versions):

| Scorer | `needsExpected` | `grade` | Notes |
|---|:-:|---|---|
| `topic_sequence_match` | yes | `PASS_FAIL` | `expected` = GenAiPlugin DeveloperName |
| `action_sequence_match` | yes | `PASS_FAIL` | `expected` = Python-list string of action names |
| `agent_handoff_match` | yes | `PASS_FAIL` | `expected` = target Bot API name |
| `bot_response_rating` | yes | `LLM_PASS_FAIL` | LLM judges response against `expected` rubric |
| `response_match` | yes | `LLM_PASS_FAIL` | LLM judges semantic match to `expected` text |
| `coherence` | no | `LLM_0_100` | Quality scorer; no `expected` field |
| `conciseness` | no | `LLM_0_100` | Quality scorer; no `expected` field |
| `factuality` | no | `LLM_0_100` | Quality scorer; no `expected` field |
| `completeness` | no | `LLM_0_100` | Quality scorer; no `expected` field |
| `task_resolution` | no | `LLM_0_5` | **Requires `conversationHistory`** on the test case |
| `output_latency_milliseconds` | no | `NUMERIC` | Numeric scorer; no `expected` field |

Scorers split into two enforcement classes:

- **Deterministic** (`grade: PASS_FAIL`) — `topic_sequence_match`, `action_sequence_match`, `agent_handoff_match`. Exact-match checks against a known `expected:` value. Cheap, fast, no LLM call.
- **LLM-judged** (`grade: LLM_PASS_FAIL` / `LLM_0_100` / `LLM_0_5`) — all the rest except `output_latency_milliseconds`. An LLM call is made per test case per scorer to render a judgement. Use these when the assertion is about *quality* of the response (was it coherent? complete? factual? did the user's task actually get resolved?) and an exact-match doesn't apply.

Scorer-selection rules when authoring a spec:
- Always pick at least one **deterministic** scorer so topic/action regressions are caught even when the judge is flaky.
- Add **LLM-judged** scorers for the dimensions you actually care about. The four `LLM_0_100` quality scorers (`coherence`, `conciseness`, `factuality`, `completeness`) and the two `LLM_PASS_FAIL` matchers (`bot_response_rating`, `response_match`) are all equally LLM-driven — pick by what they measure, not by cost.
  - `factuality` / `completeness` — does the response say true things, and all the things it should?
  - `coherence` / `conciseness` — is the response well-structured and not bloated?
  - `bot_response_rating` — the response judged against an `expected:` rubric the test author writes.
  - `response_match` — the response judged for semantic match to an `expected:` exemplar.
- Use `task_resolution` for multi-turn flows — graded 0–5 on whether the user's underlying ask got resolved. **Requires `conversationHistory`** on the test case; the CLI will refuse to scaffold it otherwise.
- `output_latency_milliseconds` is the only numeric scorer — it reports a raw millisecond figure, so threshold comparison happens downstream of the runner.
- Unknown scorer names are **not rejected at the CLI** — `validateNgtSpec` only emits a warning. The org-side metadata validator is the authoritative gate, so a typo will fail at deploy, not at author time.

### Authoring a Test Spec

Write the YAML file directly. Full NGT schema (multi-input cases, `conversationHistory`, `contextVariables`, error surface) lives in `references/ngt-batch-testing.md`; full legacy schema in `references/batch-testing.md`.

Pick the file shape based on the detection probe above. Default output paths (so other tooling can find specs):
- NGT: `specs/<AgentApiName>-ngtTestSpec.yaml`
- Legacy: `specs/<AgentApiName>-testSpec.yaml`

NGT spec, minimum viable:

> **CRITICAL — `name:` is a DeveloperName, not a display name.** It becomes the test suite's `<name>` XML element and must be alphanumeric + underscore (no spaces). Deploys with spaces fail with `The AI Test Suite Definition API Name can only contain underscores and alphanumeric characters...`. Put human-readable text in `description:`. See `references/ngt-batch-testing.md` → Required Fields.

```yaml
name: OrderService_Smoke_Tests      # DeveloperName: alphanumeric + underscore only
subjectType: AGENT
subjectName: OrderService           # BotDefinition DeveloperName (API name)

testCases:
  - inputs:
      - utterance: "Where is my order #12345?"
    scorers:
      - name: topic_sequence_match
        expected: order_status
      - name: factuality            # LLM-judged quality scorer

  - inputs:
      - utterance: "I want to return my order"
    scorers:
      - name: action_sequence_match
        expected: "['lookup_order']"   # Level 2 INVOCATION names, NOT Level 1 definitions
      - name: completeness
```

**Key NGT rules:**
- `expectedActions` becomes `action_sequence_match.expected:` as a Python-list-string of **Level 2 invocation names** (from `reasoning: actions:`).
- NGT's `action_sequence_match` is **order-sensitive** (sequence equality), unlike legacy's superset match. Align the list with the actual invocation order, or swap to `response_match` for a looser check.
- Pair a deterministic scorer (`topic_sequence_match` / `action_sequence_match` / `agent_handoff_match`) with at least one LLM-judged scorer for full coverage.
- For round-tripping deployed XML back to YAML, `sf agent generate test-spec --from-definition <xml>` works for both shapes (extension-inferred runner; legacy is shipped, NGT lands in 1.43.0).

### Deploy and Run (NGT)

```bash
# Deploy as AiTestingDefinition. --test-runner is the only NGT-specific flag.
sf agent test create --json \
  --test-runner agentforce-studio \
  --spec /tmp/spec.yaml \
  --api-name MySuite \
  -o <org>

# Run and wait. Runner is auto-detected from the suite name; pass --test-runner
# only when AmbiguousTestDefinition tells you names collide across both metadata types.
sf agent test run --json --api-name MySuite --wait 10 --result-format json -o <org> | tee /tmp/run.json
JOB_ID=$(python3 -c "import json; print(json.load(open('/tmp/run.json'))['result']['runId'])")
```

Drop `--test-runner agentforce-studio` from `sf agent test create` to deploy a legacy spec; everything else is identical.

### Read Results

Use the CLI's built-in formatters — don't roll your own parser:

```bash
sf agent test results --job-id "$JOB_ID" --result-format human -o <org>          # readable table
sf agent test results --job-id "$JOB_ID" --result-format junit -o <org> > junit.xml  # JUnit XML
sf agent test results --json --job-id "$JOB_ID" -o <org> | tee /tmp/results.json  # raw JSON envelope
```

The `--result-format human` table already shows Scorer / Result / Expected / Actual / Reasoning. The `--json` envelope is also available when you need to walk results programmatically. Inside it, `scorerResponse` and `subjectResponse` are both **JSON-encoded strings** — `json.loads()` them before reading; don't slice or split.

Full result-shape reference (legacy `testResults` vs NGT `testScorerResults`, the `status` / `actualValue` / `expectedValue` / `score` / `reasoning` shape inside each `scorerResponse`, and a custom-gate example): see `references/test-report-format.md` and `references/ngt-batch-testing.md` → Phase 3.

### Topic Name Resolution

If `topic_sequence_match` (NGT) or `topic_assertion` (legacy) FAILs on what looks like correct routing, the cause is usually **promoted topics** — topics published from one org to another, whose runtime name gets a hash suffix that changes every `sf agent publish authoring-bundle`. The expected name in your YAML must match the current hashed name, not the short name in the `.agent` file. See `references/ngt-batch-testing.md` → **Topic Name Resolution** for the lookup workflow.

See `references/batch-testing.md` for full YAML field reference, multi-turn examples, known bugs, and auto-generation from `.agent` files.

---

## Action Execution

> Full reference: `references/action-execution.md`

Execute individual Flow and Apex actions directly via REST API, bypassing the agent runtime.

### Safety Gate (Required)

Before executing ANY action:
1. **Org check**: `sf data query -q "SELECT IsSandbox FROM Organization" -o <org> --json` -- warn and require confirmation for production orgs
2. **DML check**: Warn if action performs write operations (CREATE, UPDATE, DELETE)
3. **Input validation**: Use synthetic test data only (`test@example.com`, `000-00-0000`). Warn if user provides real PII.

### Execution

```bash
TOKEN=$(sf org display -o <org> --json | jq -r '.result.accessToken')
INSTANCE_URL=$(sf org display -o <org> --json | jq -r '.result.instanceUrl')

# Flow action
curl -s "$INSTANCE_URL/services/data/v63.0/actions/custom/flow/{flowApiName}" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"inputs": [{"param": "value"}]}'

# Apex action
curl -s "$INSTANCE_URL/services/data/v63.0/actions/custom/apex/{className}" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"inputs": [{"param": "value"}]}'
```

See `references/action-execution.md` for integration testing patterns, debugging, and error handling.

---

## Test Report Format

> Full reference: `references/test-report-format.md`

Reports include: subagent routing %, action invocation %, grounding %, safety %, response quality %, overall score, and status (PASSED / PASSED WITH WARNINGS / FAILED). Safety verdict (SAFE/UNSAFE/NEEDS_REVIEW) is always included.

### Test File Location Convention

```
<project-root>/tests/
  <AgentApiName>-testing-center.yaml  # Full smoke suite (Mode B)
  <AgentApiName>-regression.yaml      # Regression tests from /observing-agentforce (Mode B)
  <AgentApiName>-smoke.yaml           # Ad-hoc smoke tests (Mode A)
```

---

## Troubleshooting

> Full reference: `references/troubleshooting.md`

| Issue | Solution |
|-------|----------|
| Session timeout | Split into smaller batches |
| Trace not found | Update to sf CLI 2.121.7+ |
| `jq` parse error | Use Python `re.sub` to strip control characters before parsing |
| Empty traces | Check `transcript.jsonl` or use Mode B instead |

## Dependencies

- `sf` CLI 2.121.7+ (for preview trace support)
- `jq` (system) -- JSON processing
- `python3` -- For result parsing scripts

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed -- safe to deploy |
| 1 | Some tests failed -- review before deploying |
| 2 | Critical failure -- block deployment |
| 3 | Test execution error -- fix infrastructure |
