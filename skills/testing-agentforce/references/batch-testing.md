# Mode B: NGT Batch Testing (Agentforce Studio) — Full Reference

NGT (Next-Gen Testing) is Salesforce's current test infrastructure for Agentforce agents. Tests are authored as YAML, deployed as `AiTestingDefinition` metadata to the org, and scored by a catalog of named scorers (assertion, LLM-judged, and numeric). This document is the source of truth for authoring NGT specs from `/testing-agentforce`.

> Looking for the older `AiEvaluationDefinition` schema? See [`legacy-testing-center.md`](legacy-testing-center.md).

---

## When to use

Use Mode B (NGT) for **any new test spec**. Required: the target org has the `aFStudioTestingCenter` org-perm enabled.

| Situation | What to do |
|---|---|
| New test spec for an agent in an NGT-enabled org | **Mode B (this doc).** |
| Org doesn't have testing-center capability (probe says `INVALID_TYPE`) | Sign up for a [free Agentforce Developer Edition][de-signup], or have your Salesforce admin enable testing-center on an existing sandbox (see the [Agentforce DX setup guide][dx-setup]). Or pin `agentforce-adlc@0.6.x` for legacy authoring. |
| Maintaining a pre-existing `aiEvaluationDefinitions/` suite | See [`legacy-testing-center.md`](legacy-testing-center.md). The skill no longer authors legacy. To author *new* legacy specs, pin `agentforce-adlc@0.6.x`. |

NGT is sandbox/scratch-only as of `@salesforce/agents@1.7.0`. Production-org rollout is server-side.

---

## YAML schema

Single-file authoring shape. One YAML → one suite → one `*.aiTestingDefinition-meta.xml`.

### Top-level fields

| Field | Type | Required? | Notes |
|---|---|---|---|
| `name` | string | required | Suite developer name; maps to XML `<name>`. |
| `description` | string | optional | Free-text label. |
| `subjectType` | enum: `AGENT` | required | Only `AGENT` accepted. |
| `subjectName` | string | required | `BotDefinition.DeveloperName` of the agent under test. |
| `subjectVersion` | string | optional | Pin to `"v1"`, `"v2"`, …, or `"LATEST"`. Omit to test against the live agent. |
| `testCases` | array of test-case mappings | required (≥1) | See below. |

### Per-test-case fields

| Field | Type | Required? | Notes |
|---|---|---|---|
| `inputs` | array of input mappings | required (≥1) | Multi-input fan-out: one set of scorers run against each input. |
| `scorers` | array of scorer mappings | required (≥1) | Per-test scorer list. |

### Per-input fields

| Field | Type | Required? | Notes |
|---|---|---|---|
| `utterance` | string | required | The user input under test. |
| `contextVariables` | array of `{name, value}` | optional | Maps to `<inputs><contextVariable>…</contextVariable></inputs>` in XML. |
| `conversationHistory` | array of multi-turn entries | optional | Each entry has `role: user|agent`, `message`, optional `topic` (required for `agent` rows) and `index` (all-or-nothing). |

### Per-scorer fields

| Field | Type | Required? | Notes |
|---|---|---|---|
| `name` | string from the scorer catalog | required | Unknown name → lint warning at deploy. |
| `expected` | string | required for assertion scorers; ignored for quality/numeric scorers | Maps to `<expectedValue>` in XML. For `action_sequence_match` multi-action: Python-list-string format `"['Action_A','Action_B']"`. |

### Minimal valid spec

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

### Full reference example

The canonical example lives at `assets/ngt-test-spec.yaml`. It exercises every scorer category and the `inputs[]` fan-out idiom — read it as a template.

---

## Scorer catalog

The v1 catalog is fixed at 11 entries. Source of truth: `forcedotcom/agents/src/ngtScorerCatalog.ts` (in `@salesforce/agents@1.7.0`+).

| Scorer | Grade | `needsExpected` | Notes |
|---|---|---|---|
| `topic_sequence_match` | PASS_FAIL | yes | Subagent routing assertion. `expected` = topic developer name. |
| `action_sequence_match` | PASS_FAIL | yes | Action invocation. Single value bare (`Get_Order_Status`); multi-value Python-list-string (`"['Verify_Customer','Get_Order_Status']"`). Use Level 2 invocation names from `reasoning: actions:`. |
| `agent_handoff_match` | PASS_FAIL | yes | Handoff to a target agent. `expected` = target agent's `DeveloperName` (NOT label). |
| `bot_response_rating` | LLM_PASS_FAIL | yes | LLM-as-judge against a free-text expectation. |
| `response_match` | LLM_PASS_FAIL | yes | LLM-judged exact-text match. Distinct from `bot_response_rating`. |
| `coherence` | LLM_0_100 | no | Quality scorer. |
| `conciseness` | LLM_0_100 | no | Quality scorer. |
| `factuality` | LLM_0_100 | no | Quality scorer. |
| `completeness` | LLM_0_100 | no | Quality scorer. |
| `task_resolution` | LLM_0_5 | no | Multi-turn task scoring. **Requires `conversationHistory:`** on the test case (validator enforces). |
| `output_latency_milliseconds` | NUMERIC | no | Raw latency, not graded. |

**Conventions:**
- Assertion scorers (`needsExpected: yes`) require `expected:`.
- Quality / numeric scorers (`needsExpected: no`) must NOT have `expected:` (the field is ignored).
- Unknown scorer names emit a lint warning; deploy will fail server-side unless the scorer exists in the org's catalog.

### Multi-agent gating

If `subjectName` resolves to a `BotDefinition` with `IsMultiAgent = true`, **every test case** must include an `agent_handoff_match` scorer with non-empty `expected`. The validator throws `ngtMultiAgentMissingHandoff` otherwise.

> ⚠️ The lib's `fetchIsMultiAgent()` swallows all errors and defaults to `false`. A typo in `subjectName` means the multi-agent check silently no-ops. Verify your `subjectName` against the org with `sf data query --query "SELECT IsMultiAgent FROM BotDefinition WHERE DeveloperName = '<name>'"`.

---

## CLI invocations

> ⚠️ **Footgun.** `sf agent test create` defaults to `--test-runner testing-center` (legacy). Forgetting `--test-runner agentforce-studio` silently authors an `AiEvaluationDefinition` instead of an `AiTestingDefinition`. Always pass the flag.

### Preview only — fastest validation loop, no deploy

```bash
sf agent test create --json \
  --spec specs/MyAgent.ngt.yaml \
  --api-name MyAgent_NGT \
  --test-runner agentforce-studio \
  --preview \
  -o <org>
# -> writes force-app/main/default/aiTestingDefinitions/MyAgent_NGT-preview-<ISO>.xml
# -> JSON: { "result": { "path": "...", "contents": "<AiTestingDefinition>...</AiTestingDefinition>" } }
```

### Create + deploy

```bash
sf agent test create --json \
  --spec specs/MyAgent.ngt.yaml \
  --api-name MyAgent_NGT \
  --test-runner agentforce-studio \
  -o <org>
# -> writes force-app/main/default/aiTestingDefinitions/MyAgent_NGT.aiTestingDefinition-meta.xml
# -> also deploys to org
```

### Verify the test landed as NGT (not legacy)

```bash
sf agent test list --target-org <org> --json | python3 -c "
import json, sys
rows = json.load(sys.stdin).get('result', [])
for r in rows:
    print(r.get('name'), '->', r.get('type'))  # 'agentforce-studio' (NGT) or 'testing-center' (legacy)
"
```

### Run + results

```bash
sf agent test run --json \
  --api-name MyAgent_NGT \
  --test-runner agentforce-studio \
  --wait 30 --result-format json -o <org> | tee /tmp/run.json

JOB_ID=$(python3 -c "import json; print(json.load(open('/tmp/run.json'))['result']['runId'])")

sf agent test results --json \
  --job-id "$JOB_ID" \
  --test-runner agentforce-studio \
  --result-format json -o <org>
```

`run`, `results`, and `resume` auto-detect the runner type from org metadata when `--test-runner` is omitted; `create` does **not**.

---

## Org capability probe

Before authoring NGT tests against an org, confirm it has `aFStudioTestingCenter` enabled. Run the canonical probe:

```bash
sf agent test list --target-org <org-alias> --json 2>&1 | grep -E '"(name|message|type)":'
```

### Interpretation

| Output | NGT verdict | Action |
|---|---|---|
| `"name": "ListRetrievalFailed"` AND `"message": "...INVALID_TYPE: Cannot use: AiEvaluationDefinition in this organization"` | NGT **off** (definitive) | Provision an NGT-enabled org or pin `agentforce-adlc@0.6.x`. |
| `"name": "ListRetrievalFailed"` AND `"message": "...INSUFFICIENT_ACCESS..."` | Inconclusive | Operator lacks `ModifyAllData` / `ModifyMetadata`; rerun as a user with metadata perms. |
| Empty `result: []` array, exit 0 | Probably on | Fall through to Tier-2 probe. |
| Any `result[].type == "agentforce-studio"` row | NGT **on** (definitive) | Proceed. |

### Tier-2 fallback (when the probe returns 0 rows)

```bash
sf data query --target-org <org-alias> --json --use-tooling-api \
  --query "SELECT QualifiedApiName FROM EntityDefinition WHERE QualifiedApiName LIKE 'AiTesting%'"
```

Returns one or more rows including `AiTestingDefinition` → NGT on. Returns `records: []` → NGT off.

---

## Result parsing

NGT runs return `AgentforceStudioTestResultsResponse` (runner-specific shape). Parse with Python:

```bash
python3 -c "
import json
data = json.load(open('/tmp/results.json'))
result = data['result']
print(f'Status: {result.get(\"status\")}, Run ID: {result.get(\"runId\")}')
for tc in result.get('testCases', []):
    inputs = tc.get('inputs', {})
    utterance = (inputs.get('utterance') or '<no utterance>')[:50]
    scorer_results = tc.get('testScorerResults', [])
    scores = {s['name']: s.get('result') or s.get('score') for s in scorer_results}
    print(f'  {utterance:<50} scores={scores}')
"
```

Per-scorer `result` field is `PASS` / `FAIL` / a numeric score depending on the scorer's grade:
- `PASS_FAIL` / `LLM_PASS_FAIL` → `result: 'PASS' | 'FAIL'`
- `LLM_0_100` → `score: 0–100`
- `LLM_0_5` → `score: 0–5`
- `NUMERIC` → `score: <raw value>`

---

## Validator errors

NGT validation runs in `@salesforce/agents` before any org call. Errors carry structured codes (start with `ngt`); the plugin re-throws them with exit code 1 (per `04-plugin-agent-pr.md` § "Error mapping"). The validator throws on the **first** failure — fix one, re-run to find the next.

| Code | Meaning | Remediation |
|---|---|---|
| `ngtMissingTestCases` | Empty `testCases:` array | Add at least one test case. |
| `ngtTestCaseMissingInputs` | A test case has empty/missing `inputs:` | Add at least one `inputs[]` entry with an `utterance:`. |
| `ngtTestCaseMissingScorers` | A test case has empty/missing `scorers:` | Add at least one scorer from the v1 catalog. |
| `ngtScorerMissingExpected` | An assertion scorer has no `expected:` | Add an `expected:` value (topic name, action name, agent DeveloperName, etc.) per the catalog row. |
| `ngtTaskResolutionRequiresConversationHistory` | A test case has `task_resolution` but no `conversationHistory:` | Add `conversationHistory:` to one of the inputs, or remove `task_resolution`. |
| `ngtMultiAgentMissingHandoff` | The subject is a multi-agent and a test case has no `agent_handoff_match` | Add `agent_handoff_match` with the target agent's `DeveloperName` to every test case. |
| `ngtConversationHistoryIndexAllOrNothing` | Some `conversationHistory[]` entries have `index:` and some don't | All-or-nothing: either every entry has `index:` or none do. |
| (lint warning, not error) | Unknown scorer name | Either fix the typo or accept the warning if the scorer was added to the org out-of-band. |

---

## Hand-edit escape hatch

The YAML schema covers only the v1 OOTB scorer catalog (11 entries). If you need a scorer the YAML can't author — `instruction_following`, `instruction_adherence`, `expression_eval`, `custom_llm_evaluation`, or any `<scorer scorerType="Custom">` referencing a deployed `AiTagDefinition` — use the hand-edit workflow:

1. Author tests in YAML covering only the v1 scorer set.
2. Run `sf agent test create --preview --test-runner agentforce-studio` to convert YAML → XML in `aiTestingDefinitions/`.
3. Hand-edit the generated XML to add the deferred scorer as an additional `<scorer>` block inside the relevant `<testCase>`.
4. Deploy via `sf project deploy start --metadata AiTestingDefinition:<Name>` — Core's MD validator gates correctness.

> ⚠️ **Round-trip warning.** Re-running `sf agent test create` against the YAML will **NOT preserve** hand-edited deferred scorers. Once the XML is hand-edited, the **XML is the source of truth**. Treat the YAML as a starter, not a round-trippable spec.

---

## Known gotchas

1. **`agent test create` defaults to legacy.** Always pass `--test-runner agentforce-studio` for NGT (see "Footgun" above).
2. **`agent_handoff_match` expects a `DeveloperName`, not a label.** Easy to get wrong by copying the label out of a UI.
3. **`fetchIsMultiAgent` swallows errors and defaults `false`.** A misnamed `subjectName` silently skips the multi-agent handoff check. Verify your subject exists in the org first.
4. **Source-format suffix is `.aiTestingDefinition-meta.xml`.** The `-meta.xml` is required; SDR translates to MDAPI form `aiTestingDefinitions/<name>.aiTestingDefinition` at deploy time.
5. **NGT requires Metadata API ≥ 66.0 server-side.** Set `"sourceApiVersion": "66.0"` in `sfdx-project.json` so `sf project deploy start` picks the right Metadata layer. The lib does NOT preflight this.
6. **`expected` is always a string** even for `action_sequence_match` multi-action expectations — pass the Python-list-string verbatim, e.g. `"['Verify_Customer','Get_Order_Status']"`. XMLBuilder encodes `'` as `&apos;` in the output.
7. **`AmbiguousTestDefinition` error** when running an existing test name that exists as both runner types — pass `--test-runner agentforce-studio` explicitly to disambiguate.
8. **The lib's helpers are deep-imported.** `validateNgtSpec`, `convertToTestingMetadata`, `buildTestingMetadataXml` are NOT in `src/index.ts` — downstream consumers must `import { ... } from '@salesforce/agents/lib/agentTest.js'`. The skill itself doesn't need to do this (the CLI plumbs through `AgentTest.create()`), but if you ever want a local pre-deploy lint, that's the import shape.

## Links

[de-signup]: https://www.salesforce.com/form/developer-signup/?d=pb
[dx-setup]: https://developer.salesforce.com/docs/ai/agentforce/guide/agent-dx-set-up-env.html
