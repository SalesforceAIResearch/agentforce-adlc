---
name: testing-agentforce
description: "Write, run, and analyze structured test suites for Agentforce agents using NGT (Next-Gen Testing). TRIGGER when: user writes or modifies an NGT test spec YAML (AiTestingDefinition); runs sf agent test create, run, results, or list with --test-runner agentforce-studio; asks about NGT, Agentforce Studio, scorers, test coverage strategy, metric selection; interprets test results or diagnoses test failures; asks about batch testing, regression suites, or CI/CD test integration. For existing legacy aiEvaluationDefinitions/ suites: see references/legacy-testing-center.md (archaeology only — pin agentforce-adlc@0.6.x to author new legacy specs). DO NOT TRIGGER when: user creates, modifies, previews, or debugs .agent files (use developing-agentforce); deploys or publishes agents; writes Agent Script code; uses sf agent preview for development iteration; analyzes production session traces (use observing-agentforce)."
allowed-tools: Bash Read Write Edit Glob Grep
license: Apache-2.0
metadata:
  version: "0.7.0"
  last_updated: "2026-05-29"
  argument-hint: "<org-alias> --authoring-bundle <AgentName> [--utterances <file>] | run <org> --target <flow://Name> | ngt <org> --spec <yaml>"
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

**Batch testing (Mode B — NGT):**
```bash
# Deploy and run an NGT test suite. --test-runner agentforce-studio is REQUIRED
# on `create`; without it, the CLI silently authors a legacy AiEvaluationDefinition.
sf agent test create --json --test-runner agentforce-studio \
  --spec test-spec.ngt.yaml --api-name MySuite -o <org-alias>
sf agent test run --json --test-runner agentforce-studio \
  --api-name MySuite --wait 30 --result-format json -o <org-alias>
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
- **Mode B: NGT Batch Testing (Agentforce Studio)** -- Persistent NGT test suites deployed as `AiTestingDefinition` metadata via `sf agent test create --test-runner agentforce-studio`. Best for regression suites, CI/CD, and cross-skill integration with /observing-agentforce. Requires the target org to have the `aFStudioTestingCenter` org-perm enabled.
- **Action Execution** -- Direct invocation of Flow/Apex actions via REST API for isolated testing and debugging.

**When to use which:**

| Scenario | Mode |
|----------|------|
| Quick smoke test during authoring | Mode A |
| Validate a fix from /observing-agentforce | Mode A |
| Build a regression suite for CI/CD (NGT) | Mode B |
| Deploy tests to share with the team | Mode B |
| Maintain an existing legacy `aiEvaluationDefinitions/` suite | See `references/legacy-testing-center.md`; pin `agentforce-adlc@0.6.x` for legacy authoring |
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

## Mode B: NGT Batch Testing (Agentforce Studio)

> Full reference: `references/batch-testing.md`
> Canonical YAML fixture: `assets/ngt-test-spec.yaml`
> Legacy `AiEvaluationDefinition` archaeology: `references/legacy-testing-center.md`

### Org capability precondition

Before any NGT authoring session, confirm the target org has `aFStudioTestingCenter` enabled. Run the canonical probe:

```bash
sf agent test list --target-org <org-alias> --json 2>&1 | grep -E '"(name|message|type)":'
```

If the probe reports `INVALID_TYPE: Cannot use: AiEvaluationDefinition in this organization`, the org doesn't have the testing-center capability enabled. Either get an Agentforce-enabled org ([free Developer Edition][de-signup], or have an admin enable testing-center on a sandbox per the [Agentforce DX setup guide][dx-setup]) or pin `agentforce-adlc@0.6.x` for legacy authoring. Full options table in `references/troubleshooting.md`.

### Test Spec YAML

NGT YAML uses `inputs[]` arrays (one or more utterances per test case sharing a scorer set) and `scorers[]` arrays (named scorers from the v1 catalog). See `references/batch-testing.md` for the full schema and `assets/ngt-test-spec.yaml` for the canonical example.

Minimal valid spec:

```yaml
name: MySuite
subjectType: AGENT
subjectName: MyAgent
testCases:
  - inputs:
      - utterance: "Hello"
    scorers:
      - name: topic_sequence_match
        expected: greeting
```

### CLI invocations

> ⚠️ **Footgun.** `sf agent test create` defaults to `--test-runner testing-center` (legacy). Forgetting `--test-runner agentforce-studio` silently authors an `AiEvaluationDefinition` instead of an `AiTestingDefinition`. The skill must pass the flag on every NGT create call.

**Create + deploy:**
```bash
sf agent test create --json \
  --spec specs/MyAgent.ngt.yaml \
  --api-name MyAgent_NGT \
  --test-runner agentforce-studio \
  -o <org>
# -> writes force-app/main/default/aiTestingDefinitions/MyAgent_NGT.aiTestingDefinition-meta.xml
# -> also deploys to org
```

**Validate YAML without deploying** (`--preview` is a static check — generates XML on disk, makes no live agent call; not the same as Mode A's runtime preview):
```bash
sf agent test create --json \
  --spec specs/MyAgent.ngt.yaml \
  --api-name MyAgent_NGT \
  --test-runner agentforce-studio \
  --preview \
  -o <org>
# -> writes force-app/main/default/aiTestingDefinitions/MyAgent_NGT-preview-<ISO>.xml
```

**Run + results:**
```bash
sf agent test run --json --test-runner agentforce-studio \
  --api-name MyAgent_NGT --wait 30 --result-format json -o <org> | tee /tmp/run.json

JOB_ID=$(python3 -c "import json; print(json.load(open('/tmp/run.json'))['result']['runId'])")

sf agent test results --json --test-runner agentforce-studio \
  --job-id "$JOB_ID" --result-format json -o <org>
```

`run`, `results`, and `resume` auto-detect the runner type from org metadata when `--test-runner` is omitted; `create` does not. Pass it explicitly to avoid `AmbiguousTestDefinition` errors when an API name exists as both runner types.

### Validator errors and result parsing

NGT validation runs in the lib before any org call. Errors carry structured codes (`ngtMissingTestCases`, `ngtTestCaseMissingInputs`, `ngtScorerMissingExpected`, etc.). For the full validator-error remediation table, the 11-entry scorer catalog, the result-parsing snippet, and known gotchas, see `references/batch-testing.md`.

If the user opens an existing `<Name>.aiEvaluationDefinition-meta.xml` (legacy), do **not** author or extend it here — point them at `references/legacy-testing-center.md`.

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
  <AgentApiName>-ngt.yaml             # NGT test suite (Mode B)
  <AgentApiName>-regression.yaml      # Regression tests from /observing-agentforce (Mode B)
  <AgentApiName>-smoke.yaml           # Ad-hoc smoke tests (Mode A)
```

(The legacy `<AgentApiName>-testing-center.yaml` convention is retired for new files. Existing files in repos using the older convention continue to work for users on `agentforce-adlc@0.6.x`.)

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

`sf agent test create` returns structured exit codes routed by `code`/`name` fields (per `salesforcecli/plugin-agent` PR #430):

| Code | Meaning |
|------|---------|
| 0 | All tests passed -- safe to deploy |
| 1 | NGT validator error (`ngt*` codes) — fix YAML and retry |
| 2 | Critical failure or spec file not found (ENOENT) -- block deployment |
| 3 | Test execution error -- fix infrastructure |
| 4 | Deploy failure -- check org connectivity / metadata API version (NGT requires ≥ 66.0) |

## Links

[de-signup]: https://www.salesforce.com/form/developer-signup/?d=pb
[dx-setup]: https://developer.salesforce.com/docs/ai/agentforce/guide/agent-dx-set-up-env.html
