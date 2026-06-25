# Test Report Format, Coverage Analysis, and CI/CD — Reference

## Summary Report

```text
Agentforce Agent Test Report
===========================================

Agent: OrderManagementAgent
Org: production
Test Cases: 6
Duration: 45.2s

Results:
  Subagent Routing: 5/6 passed (83.3%)
  Action Invocation: 4/6 passed (66.7%)
  Grounding: 6/6 passed (100%)
  Safety: 6/6 passed (100%)
  Response Quality: 5/6 passed (83.3%)

Overall Score: 86.7%
Status: PASSED WITH WARNINGS
```

## Detailed Test Cases

```text
Test Case 1: "Where is my order?"
  Expected Topic: order_mgmt
  Actual Topic: order_mgmt (pass)
  Expected Action: get_order_status
  Actual Action: get_order_status (pass)
  Grounding: GROUNDED (pass)
  Safety Score: 0.95 (pass)
  Response Quality: Relevant (pass)

Test Case 2: "I want to return this"
  Expected Topic: returns
  Actual Topic: order_mgmt (fail - misrouted)
  Fix Applied: Expanded 'returns' subagent description
  Retry Result: Correctly routed (pass)
```

## Legacy Result JSON Shape

The `--json` envelope from `sf agent test results` for legacy runs surfaces per-case assertions under `testCases[].testResults[]`. Each entry has these fields:

| Field | Meaning |
|---|---|
| `name` / `metricLabel` | One of three fixed values — see assertion-name mapping below |
| `result` | `"PASS"` / `"FAILURE"` / `"ERROR"` — the canonical pass/fail field |
| `status` | Run-state for this assertion — `"COMPLETE"` on a finished test, `"RETRY"` while the runner is reattempting. Distinct from `result`. |
| `expectedValue` | The YAML's `expectedTopic` / `expectedActions` value, echoed back |
| `actualValue` | What the agent did. **Empty string when the runner failed to invoke the bot** (e.g. no active BotVersion). |
| `score` | `0` or `1` — a numeric mirror of `result`. Not load-bearing; prefer `result`. |
| `errorCode` / `errorMessage` | Populated when the assertion errored. `errorMessage: "Retrying (N/M) due to: <reason>"` appears on each assertion while the runner retries. |
| `startTime` / `endTime` | ISO-8601 timestamps |

### Assertion-name mapping (XML → JSON result)

The XML metadata uses one set of assertion names; the JSON result envelope renames them. Scripts parsing the result JSON should grep for the JSON-side names — the XML names do not appear in the result envelope at all.

| YAML field | XML `<expectation><name>` | JSON `name` / `metricLabel` |
|---|---|---|
| `expectedTopic` | `topic_sequence_match` | `topic_assertion` |
| `expectedActions` | `action_sequence_match` | `actions_assertion` |
| (implicit, always present) | `bot_response_rating` | `output_validation` |

The CLI's `--result-format human` table hides this drift — it labels the columns "Topic" / "Action" / "Outcome" regardless of which side you're looking at.

### Legacy failure mode when no active BotVersion exists

When the subject bot has no `BotVersion.Status = 'Active'`, the legacy runner does **not** return `testCases: []` (that's the NGT failure mode). Instead it returns the full set of N test cases with:
- Top-level `status: "IN_PROGRESS"` and no `runId`
- Per-case `status: "RETRY"` and `errorMessage: "Retrying (N/M) due to: Unknown error"`
- Per-assertion `result: "FAILURE"`, `status: "RETRY"`, and `actualValue: ""` (empty string)

This is the same root cause as the NGT `testCases: []` silent-failure mode — just a different envelope. The Pre-Run Probe in `SKILL.md` catches both before the wait.

## Coverage Analysis

Track which subagents and actions are tested across both modes:

| Dimension | Target | How to measure |
|-----------|--------|----------------|
| Subagent coverage | 100% of non-entry subagents | Count subagents with at least 1 test case |
| Action coverage | 100% of actions | Count actions with at least 1 test case targeting them |
| Phrasing diversity | 3+ utterances per subagent (production) | Multiple wordings per intent |
| Guardrail coverage | At least 1 off-topic test | Verify agent deflects non-relevant queries |
| Multi-turn coverage | Test subagent transitions | Conversation history tests |
| Escalation coverage | Test escalation triggers | Verify human handoff works |

## CI/CD with Testing Center

For CI/CD pipelines, use Mode B (Testing Center) for persistent regression suites:

```yaml
# .github/workflows/agent-testing.yml
name: Agent Testing
on:
  pull_request:
    paths:
      - 'force-app/**/*.agent'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Authenticate org
        run: |
          echo "${{ secrets.SFDX_AUTH_URL }}" > auth.txt
          sf org login sfdx-url --sfdx-url-file auth.txt --alias testorg

      - name: Deploy test suite
        run: |
          sf agent test create --json \
            --spec tests/${{ vars.AGENT_NAME }}-testing-center.yaml \
            --api-name ${{ vars.AGENT_NAME }}_CI \
            --force-overwrite \
            -o testorg

      - name: Run tests
        run: |
          sf agent test run --json \
            --api-name ${{ vars.AGENT_NAME }}_CI \
            --wait 15 \
            --result-format junit \
            --output-dir test-results \
            -o testorg

      - name: Upload test results
        uses: actions/upload-artifact@v3
        with:
          name: agent-test-results
          path: test-results/
```

## Cross-Skill Integration (/observing-agentforce)

The /observing-agentforce skill creates test cases during its Phase 3.7 after fixing issues found through STDM session analysis. These test cases use **Testing Center format** so they can be deployed directly to the org.

### Test Case Convention

Test cases from /observing-agentforce follow Testing Center YAML format:

```yaml
# tests/<AgentApiName>-regression.yaml
name: "<AgentName> Regression Tests"
subjectType: AGENT
subjectName: <AgentApiName>

testCases:
  - utterance: "find me a home in San Jose"
    expectedTopic: home_search
    expectedActions:
      - search_homes_and_communities

  - utterance: "I have a legal dispute"
    expectedTopic: escalation
    expectedActions:
      - transfer_to_agent
```

### Deploying Cross-Skill Tests

When /observing-agentforce generates test cases, deploy them using Mode B:

```bash
# Deploy the regression test suite
sf agent test create --json \
  --spec tests/<AgentApiName>-regression.yaml \
  --api-name <AgentApiName>_Regression \
  --force-overwrite \
  -o <org>

# Run
sf agent test run --json \
  --api-name <AgentApiName>_Regression \
  --wait 10 \
  --result-format json \
  -o <org>
```

### Test File Location Convention

```text
<project-root>/
  tests/
    <AgentApiName>-testing-center.yaml  # Full smoke suite (Mode B -- Testing Center)
    <AgentApiName>-regression.yaml      # Regression tests from /observing-agentforce (Mode B)
    <AgentApiName>-smoke.yaml           # Ad-hoc smoke tests (Mode A -- preview only)
```

Both this skill and /observing-agentforce write to the `tests/` directory using the agent's API name as prefix. Testing Center files (`-testing-center.yaml`, `-regression.yaml`) use the `name/subjectType/subjectName/testCases` format.

---

# NGT (Agentforce Studio) Result Shape

This section mirrors the structure above but for NGT (`AiTestingDefinition`) suites. The result shape, summary rollups, and per-case detail differ from legacy because NGT uses an 11-scorer catalog instead of three fixed assertion fields. For the scorer catalog itself, see `SKILL.md` → Scorer Catalog. For the full authoring/run reference, see `references/ngt-batch-testing.md`.

## NGT Result JSON Shape

The `--json` envelope from `sf agent test results` has a different shape for NGT runs than for legacy runs. The key axes:

| Axis | Legacy (`AiEvaluationDefinition`) | NGT (`AiTestingDefinition`) |
|------|-----------------------------------|------------------------------|
| Per-case assertions container | `testCases[].testResults[]` | `testCases[].testScorerResults[]` |
| Assertion identifier | `name` is one of three fixed values (`topic_assertion` / `actions_assertion` / `output_validation` — see Legacy Result JSON Shape above) | `scorerName` is any scorer from the catalog |
| Pass/fail field | `result: PASS / FAILURE / ERROR` | `scorerResponse` (JSON-encoded string) |
| Agent's actual response | `generatedData.outcome` | `subjectResponse` (JSON-encoded string, sibling of `testScorerResults`) |
| Agent's runtime topic | `generatedData.topic` | Not directly exposed; read it out of the `topic_sequence_match` scorer's `actualValue` |
| Actions invoked | `generatedData.actionsSequence` | Not directly exposed; read it out of the `action_sequence_match` scorer's `actualValue` |
| Per-case index | `testNumber` (sequential) | `testNumber` (sequential, fans out across multi-input cases) |

Both `subjectResponse` and `scorerResponse` are **JSON-encoded strings** — `json.loads()` them before reading; don't slice or split.

`subjectResponse` parses to an object with at minimum:
- `userInput` — the utterance the agent was asked to respond to (mirrored from the test case input)

`scorerResponse` parses to an object with this shape (fields populated per-scorer):

| Field | Present on | Meaning |
|---|---|---|
| `status` | All scorers | `"PASS"` or `"FAIL"`. The canonical pass/fail field. |
| `score` | LLM scorers (`LLM_0_5`, `LLM_0_100`) | Numeric judge score |
| `reasoning` | LLM scorers | Free-text judge rationale |
| `actualValue` | Deterministic scorers (`PASS_FAIL`) and `NUMERIC` | What the agent did (topic name, action list, handoff target, or latency ms) |
| `expectedValue` | Deterministic scorers | The `expected:` value from the YAML, echoed back for diff display |

## NGT Summary Report

NGT rollups key off the scorer name (any from the 11-row catalog), not the three legacy axes. A typical summary:

```
Agentforce Agent Test Report (NGT)
===========================================

Agent: OrderManagementAgent
Suite: OrderManagementAgent_Smoke
Org: production
Test Cases: 6
Duration: 51.8s

Results by scorer:
  topic_sequence_match           5/6 PASS  (83.3%)
  action_sequence_match          4/6 PASS  (66.7%)
  factuality                     6/6 PASS  (100%)
  completeness                   5/6 PASS  (83.3%)
  coherence                      6/6 PASS  (100%)
  output_latency_milliseconds    avg 2.4s, max 4.1s

Overall: 5/6 test cases all-PASS
Status: PASSED WITH WARNINGS
```

Notes:
- Numeric scorers (`output_latency_milliseconds`) don't roll up as PASS/FAIL — report the raw distribution (avg, max, or p95) instead.
- Group rollups by the catalog `grade` (`PASS_FAIL` / `LLM_PASS_FAIL` / `LLM_0_100` / `LLM_0_5` / `NUMERIC`) when deciding what's blocking and what's advisory.

## NGT Detailed Test Cases

Each case shows the agent's response plus a row per scorer with `status`, `expectedValue`, `actualValue`, and (for LLM scorers) `reasoning`. This mirrors the table the CLI's `--result-format human` already renders.

```
Test Case 1: "Where is my order #12345?"
  topic_sequence_match           PASS   expected=order_status     actual=order_status
  action_sequence_match          PASS   expected=['lookup_order'] actual=['lookup_order']
  factuality                     PASS   score=88   "Order status accurately reflected from the action result."
  completeness                   PASS   score=82   "Covered status and ETA; no follow-up needed."

Test Case 2: "I want to return this"
  topic_sequence_match           FAIL   expected=returns          actual=order_status
  factuality                     PASS   score=75
  completeness                   FAIL   score=42   "Did not initiate return flow."
  Fix Applied: Expanded 'returns' subagent description
  Retry: topic_sequence_match PASS
```

For multi-input cases, the runner fans out one row per input — `testNumber` increments globally, so the second utterance in case 2 appears as test case 3 in the result envelope.

## NGT CI/CD Example

For CI/CD pipelines using NGT suites, the workflow shape is the same as legacy with three flag changes: `--test-runner agentforce-studio` on `create`, the NGT spec filename, and the test-runner-aware result format flag.

```yaml
# .github/workflows/agent-testing-ngt.yml
name: Agent Testing (NGT)
on:
  pull_request:
    paths:
      - 'force-app/**/*.agent'
      - 'specs/**/*-ngtTestSpec.yaml'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Authenticate org
        run: |
          echo "${{ secrets.SFDX_AUTH_URL }}" > auth.txt
          sf org login sfdx-url --sfdx-url-file auth.txt --alias testorg

      - name: Install latest plugin-agent
        run: sf plugins install @salesforce/plugin-agent@latest

      - name: Deploy NGT test suite
        run: |
          sf agent test create --json \
            --test-runner agentforce-studio \
            --spec specs/${{ vars.AGENT_NAME }}-ngtTestSpec.yaml \
            --api-name ${{ vars.AGENT_NAME }}_CI \
            --force-overwrite \
            -o testorg

      - name: Run tests
        run: |
          sf agent test run --json \
            --api-name ${{ vars.AGENT_NAME }}_CI \
            --wait 15 \
            --result-format junit \
            --output-dir test-results \
            -o testorg

      - name: Upload test results
        uses: actions/upload-artifact@v3
        with:
          name: agent-test-results
          path: test-results/
```

The `--test-runner` flag is required on `create` (selects the metadata type). It is **not** required on `run` / `results` — the runner is auto-inferred from the suite name; pass it explicitly only when `AmbiguousTestDefinition` tells you a name collides across both metadata types.

## NGT Cross-Skill Integration (/observing-agentforce)

When /observing-agentforce generates regression test cases for an NGT project, the YAML uses the NGT shape (`inputs:` + `scorers:`), not the legacy shape (`utterance:` + `expectedTopic:`):

```yaml
# specs/<AgentApiName>-ngtRegressionSpec.yaml
name: "<AgentName> Regression Tests"
subjectType: AGENT
subjectName: <AgentApiName>

testCases:
  - inputs:
      - utterance: "find me a home in San Jose"
    scorers:
      - name: topic_sequence_match
        expected: home_search
      - name: action_sequence_match
        expected: "['search_homes_and_communities']"
      - name: factuality

  - inputs:
      - utterance: "I have a legal dispute"
    scorers:
      - name: topic_sequence_match
        expected: escalation
      - name: agent_handoff_match
        expected: HumanEscalationAgent     # only if subject Bot is multi-agent
```

### Deploying NGT Cross-Skill Tests

```bash
sf agent test create --json \
  --test-runner agentforce-studio \
  --spec specs/<AgentApiName>-ngtRegressionSpec.yaml \
  --api-name <AgentApiName>_Regression \
  --force-overwrite \
  -o <org>

sf agent test run --json \
  --api-name <AgentApiName>_Regression \
  --wait 10 \
  --result-format json \
  -o <org>
```

### NGT Test File Location Convention

```
<project-root>/
  specs/
    <AgentApiName>-ngtTestSpec.yaml         # Full NGT smoke suite (Mode B -- NGT)
    <AgentApiName>-ngtRegressionSpec.yaml   # NGT regression tests from /observing-agentforce
  tests/
    <AgentApiName>-testing-center.yaml      # Legacy Testing Center suite (Mode B -- legacy)
    <AgentApiName>-regression.yaml          # Legacy regression tests
    <AgentApiName>-smoke.yaml               # Ad-hoc preview-only suite (Mode A)
```

NGT specs live under `specs/` per `SKILL.md` → Authoring a Test Spec; legacy Testing Center files continue to live under `tests/` for backward compatibility. The path is how downstream tooling tells the two shapes apart without parsing.
