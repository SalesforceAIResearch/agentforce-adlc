# Mode B: Agentforce Studio (NGT) Batch Testing — Full Reference

NGT (Next-Generation Testing, runner key `agentforce-studio`) is the preferred Mode B runner. Tests are authored as YAML, compiled by `@salesforce/agents` into `AiTestingDefinition` metadata XML, deployed to the org, then executed via the same `sf agent test run` / `sf agent test results` CLI commands as legacy.

Read this file alongside `SKILL.md` — the scorer catalog, runner-choice rationale, and detection probe live there and are not duplicated here.

- Detection probe (CLI + project `sourceApiVersion >= 66.0`) — see SKILL.md → **Detecting NGT Support**.
- Scorer catalog (11 OOTB rows, `needsExpected`, `grade`) — see SKILL.md → **Scorer Catalog**.
- Legacy Testing Center reference — see `references/batch-testing.md`.

## Phase 1: Create Test Spec YAML

NGT uses a different YAML shape than legacy. The two are not interchangeable — passing an NGT YAML to legacy tooling (or vice versa) fails at validation, not silently.

> **CRITICAL — `name:` must be a valid DeveloperName.** The top-level `name:` becomes the test suite's `<name>` XML element, which Salesforce treats as the **DeveloperName** (alphanumeric + underscore, starts with a letter, no double underscores, no trailing underscore, **no spaces**). NGT rejects violations at deploy with `The AI Test Suite Definition API Name can only contain underscores and alphanumeric characters...`. Use `description:` for human-readable text.
>
> **CRITICAL — `name:` must match `--api-name` on `sf agent test create`.** The CLI uses `--api-name` as the metadata filename (`<api-name>.aiTestingDefinition-meta.xml`) but does NOT overwrite the YAML's `name:` in the generated XML. If the two diverge, deploy fails with the misleading error `duplicate value found: <unknown> duplicates value on record with id: <unknown>` even when neither name exists on the org. Always pass `--api-name <same value as YAML name:>`.
>
> **CRITICAL — `description:` is capped at 100 characters.** It compiles down to `MasterLabel` on the deployed metadata, which has a 100-char hard limit. Exceeding it fails deploy with `Label: data value too large: <value> (max length=100)`. Keep `description:` short; put longer rationale in code comments or commit messages.

```yaml
# /tmp/<AgentApiName>-ngt-test-spec.yaml
name: OrderService_Smoke_Tests       # DeveloperName: alphanumeric + underscore only
description: "Routing, action invocation, escalation, and quality scorers."
subjectType: AGENT
subjectName: OrderService            # BotDefinition DeveloperName
subjectVersion: v1                   # Optional; defaults to v1

testCases:
  # Single-input case with deterministic scorers
  - inputs:
      - utterance: "Where is my order #12345?"
    scorers:
      - name: topic_sequence_match
        expected: order_status
      - name: action_sequence_match
        expected: "['lookup_order']"   # Python-list string literal

  # Multi-input case — one scorer set, multiple utterances
  # All inputs run against the SAME scorers (saves authoring effort
  # when the assertion shape is identical and only the utterance varies)
  - inputs:
      - utterance: "What's my order status?"
      - utterance: "Track order 99887"
      - utterance: "Where is my package?"
    scorers:
      - name: topic_sequence_match
        expected: order_status
      - name: factuality            # LLM-judged, no expected
      - name: coherence

  # Multi-turn case — task_resolution REQUIRES conversationHistory
  - inputs:
      - utterance: "Yes, my email is john@example.com"
        conversationHistory:
          - role: user
            message: "I need to check my mortgage status"
          - role: agent
            topic: identity_verification
            message: "Sure -- what is your email address on file?"
    scorers:
      - name: task_resolution        # LLM_0_5, requires conversationHistory
      - name: factuality

  # Handoff test (multi-agent subjects only)
  - inputs:
      - utterance: "I need to speak with a billing specialist"
    scorers:
      - name: agent_handoff_match
        expected: BillingAgent       # Target Bot API name
      - name: response_match
        expected: "Agent acknowledges transfer and routes to billing"

  # Context-variable injection
  - inputs:
      - utterance: "Show me my open cases"
        contextVariables:
          - name: UserId
            value: "005000000000123"
          - name: TenantRegion
            value: "us-east-1"
    scorers:
      - name: topic_sequence_match
        expected: case_lookup

  # Latency SLA
  - inputs:
      - utterance: "Hello"
    scorers:
      - name: output_latency_milliseconds   # NUMERIC; threshold checked downstream
```

### Required Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | **DeveloperName** for the test suite. Becomes the `<name>` XML element, which Salesforce uses as the metadata API name. Alphanumeric + underscore only, starts with a letter, no double underscores, no trailing underscore, no spaces. **Must match the `--api-name` value passed to `sf agent test create`** — the CLI does not reconcile them, and a mismatch fails deploy with a misleading `duplicate value found` error. Put human-readable text in `description:` instead. |
| `subjectType` | Yes | Always `AGENT` |
| `subjectName` | Yes | Agent BotDefinition DeveloperName (API name) |
| `subjectVersion` | No | Defaults to `v1`. Pin only when testing a specific saved version. |
| `description` | No | Free-form description. **Max 100 characters** — compiles to `MasterLabel` on the deployed metadata. |
| `testCases` | Yes | At least one entry. Empty list fails `ngtMissingTestCases`. |
| `testCases[].inputs` | Yes | At least one entry. Empty list fails `ngtTestCaseMissingInputs`. |
| `testCases[].inputs[].utterance` | Yes | User input message |
| `testCases[].inputs[].contextVariables` | No | List of `{name, value}` pairs injected as session context |
| `testCases[].inputs[].conversationHistory` | No | List of prior turns; see below |
| `testCases[].scorers` | Yes | At least one entry. Empty list fails `ngtTestCaseMissingScorers`. |
| `testCases[].scorers[].name` | Yes | Scorer name from the catalog (see SKILL.md → Scorer Catalog) |
| `testCases[].scorers[].expected` | Conditional | Required when the catalog says `needsExpected: true` |

### Multi-Input Test Cases (NGT-Only)

NGT's biggest authoring win over legacy is the multi-input case: one `scorers:` set applies to many `inputs:`. Use this when the *assertion shape* is identical across utterances and only the *prompt wording* varies — typical for paraphrase coverage, regional spelling, or short-utterance/long-utterance pairs.

```yaml
testCases:
  - inputs:
      - utterance: "What's my balance?"
      - utterance: "Show me my account balance"
      - utterance: "balance"
      - utterance: "how much money do I have"
    scorers:
      - name: topic_sequence_match
        expected: account_overview
      - name: factuality
```

At the XML layer this fans out to N `<testCase>` elements sharing the scorer set; `<number>` increments globally across the document.

### Scorer Selection by Grade Class

The scorer catalog (SKILL.md → Scorer Catalog) splits scorers into three enforcement classes. Each class implies a different authoring contract:

**Deterministic (`grade: PASS_FAIL`)** — `topic_sequence_match`, `action_sequence_match`, `agent_handoff_match`.
- `expected:` REQUIRED. Missing → `ngtScorerMissingExpected`.
- `expected` shape per scorer:
  - `topic_sequence_match`: GenAiPlugin DeveloperName (e.g. `order_status`)
  - `action_sequence_match`: Python-list-string literal (e.g. `"['lookup_order', 'verify_customer']"`). Use **Level 2 invocation names** from `reasoning: actions:`, NOT Level 1 definition names.
  - `agent_handoff_match`: target Bot API name (e.g. `BillingAgent`)
- No LLM call. Cheap, fast, deterministic.

**LLM-judged (`grade: LLM_PASS_FAIL` / `LLM_0_100` / `LLM_0_5`)** — `bot_response_rating`, `response_match`, `coherence`, `conciseness`, `factuality`, `completeness`, `task_resolution`.
- `expected:` required only for `bot_response_rating` and `response_match` (the matchers); the four quality scorers and `task_resolution` are unconditional.
- LLM call per case per scorer. Cost scales with case count × scorer count.
- `task_resolution` ADDITIONALLY requires `conversationHistory` on at least one input — missing → `ngtTaskResolutionRequiresConversationHistory`.

**Numeric (`grade: NUMERIC`)** — `output_latency_milliseconds`.
- No `expected:`. No LLM call.
- Reports a raw millisecond figure in results; threshold enforcement is the caller's job, downstream of the runner.

### `conversationHistory` Format

```yaml
conversationHistory:
  - role: user
    message: "I need help with my order"
    index: 0                     # Optional; all-or-nothing per case
  - role: agent
    topic: order_status          # Required on agent turns
    message: "Sure, what's the order number?"
    index: 1
  - role: user
    message: "12345"
    index: 2
```

**Rules:**
- Two role values only: `user`, `agent`.
- `agent` turns MUST include a `topic:` (the agent's subagent at that point).
- `index:` is all-or-nothing per case: either every turn has one, or none do. Mixing fails `ngtConversationHistoryIndexAllOrNothing`.
- `task_resolution` requires at least one input to have a non-empty `conversationHistory`.

### Multi-Agent Subjects (Cross-Bot Handoff)

Agentforce distinguishes two kinds of agent-to-agent routing, and they're tested with different scorers:

| Routing type | Boundary | `.agent` syntax | NGT scorer |
|---|---|---|---|
| **Intra-agent subagent** | Within the same `BotDefinition` | `@utils.transition` to `@subagent.X` | `topic_sequence_match` |
| **Cross-Bot handoff** | Crosses `BotDefinition` boundary; gated by `IsMultiAgent: true` on the calling Bot | `@utils.escalate` (and connection-based handoff patterns) | `agent_handoff_match` |

The keyword in `.agent` files is `subagent` — Salesforce migrated from `topic` to `subagent` in 2026 with `topic` kept as a backward-compat alias. NGT scorer names use the older `topic_*` spelling and still refer to intra-Bot routing.

**Where to scope tests:**

Test the multi-agent orchestrator and each downstream Bot as **independent test suites**, one per `BotDefinition`. A downstream Bot is a complete agent on its own — given enough context, the same Bot can be invoked directly without going through the orchestrator, so its subagent routing, action invocation, and quality scoring should be verified in isolation. Two suites — one per Bot — also lets you triangulate failures:

| Orchestrator suite | Downstream Bot suite | Likely cause |
|---|---|---|
| FAIL | PASS | Orchestrator routing / handoff target wrong, or the orchestrator is failing before handoff fires |
| FAIL | FAIL | Downstream defect (the orchestrator test sees the bad downstream response after handoff) |
| PASS | FAIL | Downstream defect on inputs the orchestrator doesn't exercise, OR the orchestrator masks the defect |
| PASS | PASS | Healthy |

Running both is what makes the boundary debuggable. An orchestrator-only failing test gives you "something is broken downstream of handoff" but not where.

**Scorers for the orchestrator's outgoing transition:**

- **`agent_handoff_match`** — the right scorer when execution actually crosses the Bot boundary. `expected:` is the **target Bot's `BotDefinition` DeveloperName** (e.g. `BillingAgent`) — the same value the UI labels "Expected Agent". Server-side validation rejects this scorer with `"scorer 'agent_handoff_match' is only supported for multi-agent orchestrators"` when the subject Bot's multi-agent flag is off, so you'll see the gate fire at deploy time, not at runtime.
- **`topic_sequence_match`** — for *intra-agent* routing within the orchestrator itself (which of its own subagents the LLM picked). `expected:` is a subagent DeveloperName — a subagent inside the same `BotDefinition`. This scorer does not evaluate cross-Bot transitions.

A typical orchestrator test case combines both — first verify the orchestrator routed to the right *internal subagent* (the one that knows when to escalate), then verify the handoff fired to the right *target Bot*:

```yaml
testCases:
  - inputs:
      - utterance: "I need a billing specialist for a refund dispute"
    scorers:
      - name: topic_sequence_match
        expected: escalation_router      # Subagent inside the orchestrator
      - name: agent_handoff_match
        expected: BillingAgent           # Target Bot's BotDefinition DeveloperName
      - name: factuality
```

**Validation enforcement:**

The server reads the subject Bot's multi-agent status at `sf agent test create` time (it checks whether the agent has related-agent references, not just a flag) and enforces an additional rule for multi-agent orchestrators: **every test case must include an `agent_handoff_match` scorer with a non-empty `expected:`** ("Expected Agent" in the UI). Missing handoff scorer raises `"Multi-agent testing requires 'agent_handoff' scorer to validate agent handoff behavior"`. Missing `expected:` on a present scorer raises `"'agent_handoff' scorer requires an expectedValue"`. There's nothing to declare in the YAML — the runner queries the org directly.

The corollary: a downstream Bot that doesn't itself orchestrate further is tested as a single-agent subject. No `agent_handoff_match` scorers are required (or even allowed — the server rejects them at deploy with the "only supported for multi-agent orchestrators" message above). Use `topic_sequence_match`, `action_sequence_match`, and the LLM-judged scorers exactly as you would for any single-agent Bot.

## Phase 2: Deploy and Run Tests

The CLI surface is identical to legacy. The only NGT-specific bit is passing `--test-runner agentforce-studio` to `sf agent test create`.

```bash
# Step 1: Confirm runner availability (see SKILL.md detection probe).

# Step 2: Deploy the test suite as AiTestingDefinition.
sf agent test create --json \
  --test-runner agentforce-studio \
  --spec /tmp/<AgentApiName>-ngt-test-spec.yaml \
  --api-name <TestSuiteName> \
  -o <org>

# Deployed metadata lands at:
# force-app/main/default/aiTestingDefinitions/<TestSuiteName>.aiTestingDefinition-meta.xml

# Step 3: Run the tests. Runner is auto-detected from the suite name; pass
# --test-runner only when a name collides across both metadata types
# (the AmbiguousTestDefinition error tells you when this is needed).
sf agent test run --json \
  --api-name <TestSuiteName> \
  --wait 10 \
  --result-format json \
  -o <org> | tee /tmp/test_run.json

# Step 4: Extract job ID
JOB_ID=$(python3 -c "import json; print(json.load(open('/tmp/test_run.json'))['result']['runId'])")

# Step 5: Get detailed results
sf agent test results --json \
  --job-id "$JOB_ID" \
  --result-format json \
  -o <org> | tee /tmp/test_results.json
```

### Updating an Existing NGT Test Suite

```bash
sf agent test create --json \
  --test-runner agentforce-studio \
  --spec /tmp/<AgentApiName>-ngt-test-spec.yaml \
  --api-name <TestSuiteName> \
  --force-overwrite \
  -o <org>
```

### Retrieving an Existing NGT Definition

```bash
sf project retrieve start --json --metadata "AiTestingDefinition:<TestSuiteName>" -o <org>
# Retrieved to: force-app/main/default/aiTestingDefinitions/<TestSuiteName>.aiTestingDefinition-meta.xml
```

### Preview Without Deploying

```bash
sf agent test create \
  --test-runner agentforce-studio \
  --spec /tmp/spec.yaml \
  --api-name <TestSuiteName> \
  --preview \
  -o <org>
# Writes <TestSuiteName>-preview-<ISO timestamp>.xml to cwd. Does NOT deploy.
```

## Phase 3: Analyze Results

NGT result shape differs from legacy. Map the key axes before parsing:

| Axis | Legacy (`AiEvaluationDefinition`) | NGT (`AiTestingDefinition`) |
|------|-----------------------------------|------------------------------|
| Per-case assertions container | `testCases[].testResults[]` | `testCases[].testScorerResults[]` |
| Assertion identifier | `name` is one of three fixed values | `scorerName` is any name from the scorer catalog |
| Pass/fail field | `result: PASS / FAILURE / ERROR` | `scorerResponse` (string; shape depends on `grade`) |
| Agent's actual response | `generatedData.outcome` | `subjectResponse` (sibling of `testScorerResults`) |
| Agent's runtime topic | `generatedData.topic` | Not directly exposed; infer from `topic_sequence_match` scorer's response |
| Actions invoked | `generatedData.actionsSequence` (stringified list) | Not directly exposed; infer from `action_sequence_match` scorer's response |
| Per-case index | `testNumber` (sequential) | `testNumber` (sequential, fans out across multi-input cases) |

### `subjectResponse` and `scorerResponse` Shapes

Both fields are **JSON-encoded strings** — not freeform text. Always `json.loads()` before reading. Parsing the string with `.split()` or `[:N]` slicing will yield wrapper characters (`{"status":`), not the values you want.

`subjectResponse` parses to an object with at minimum:
- `userInput` — the utterance the agent was asked to respond to (mirrored from the test case input)

`scorerResponse` parses to an object with this shape, populated per-scorer:

| Field | Present on | Meaning |
|---|---|---|
| `status` | All scorers | `"PASS"` or `"FAIL"`. The single canonical pass/fail field. |
| `score` | LLM scorers (`LLM_0_5`, `LLM_0_100`) | Numeric judge score |
| `reasoning` | LLM scorers | Free-text judge rationale |
| `actualValue` | Deterministic scorers (`PASS_FAIL`) and `NUMERIC` | What the agent actually did (topic name, action list, handoff target, or latency ms) |
| `expectedValue` | Deterministic scorers | The `expected:` value from your YAML, echoed back for diff display |

The `status` field is what the shipping `sf agent test results` CLI reads to decide PASS/FAIL across all grade classes — there's no per-grade special-casing needed. The other fields are for display (the table the CLI prints has columns Scorer / Result / Expected / Actual / Reasoning, populated from these fields directly).

For `NUMERIC` scorers (`output_latency_milliseconds`), `status` is still populated (the server applies its own gate); the raw millisecond figure is in `actualValue` if you need a threshold compare.

### Pass/Fail Summary

The CLI ships built-in formatters — prefer them over hand-written parsers.

```bash
# Human-readable table (Scorer / Result / Expected / Actual / Reasoning)
sf agent test results --job-id "$JOB_ID" --result-format human -o <org>

# JUnit XML
sf agent test results --job-id "$JOB_ID" --result-format junit -o <org> > results.xml

# Raw JSON envelope, when you need to walk results programmatically
sf agent test results --json --job-id "$JOB_ID" -o <org> | tee /tmp/results.json
```

When you do walk the JSON envelope, parse the per-scorer payload — it's a JSON-encoded string, not freeform text:

```bash
python3 -c "
import json, sys

data = json.load(open('/tmp/test_results.json'))
failures = []
for tc in data['result']['testCases']:
    for sr in tc.get('testScorerResults', []):
        parsed = json.loads(sr.get('scorerResponse') or '{}')
        if parsed.get('status') == 'FAIL':
            failures.append((tc['testNumber'], sr['scorerName'], parsed.get('actualValue'), parsed.get('expectedValue')))
for n, name, actual, expected in failures:
    print(f'Test #{n} {name}: expected={expected!r} actual={actual!r}')
sys.exit(1 if failures else 0)
"
```

Same parse shape as the shipping CLI — `status` is the pass/fail axis, `actualValue` / `expectedValue` show the diff for deterministic scorers, `score` / `reasoning` for LLM scorers.

### Filtering by Grade Class

When deciding what to fail the run on, key on the catalog `grade`, not on the scorer name. A common policy:

- **Fail the run** if any deterministic scorer (`PASS_FAIL`) returns `FAIL`. These are exact-match assertions on routing/actions/handoffs — there's no judgement.
- **Warn** if an LLM-judged scorer is below threshold. Pick thresholds per scorer based on what you actually need:
  - `LLM_PASS_FAIL`: fail on `FAIL`, but expect LLM flakiness — use a small retry budget or accept variance with a margin of error.
  - `LLM_0_100`: warn below 70, fail below 50 (tune to your agent, and pick thresholds with enough margin to absorb judge variance).
  - `LLM_0_5`: warn below 3, fail below 2.
- **Report** numeric scorers (`output_latency_milliseconds`) against whatever latency threshold matters for your use.

The catalog row's `grade` field is the right join key for this policy logic. See SKILL.md → Scorer Catalog for the runtime probe that returns it.

## Phase 4: Fix Loop

NGT failures fall into three diagnostic buckets by scorer class. The fix recipes differ from legacy because there's no `expectedTopic` / `expectedActions` / `expectedOutcome` axis — there's an axis per scorer.

### Deterministic Scorer Failed

1. **`topic_sequence_match` FAIL** — compare `expected` (your YAML) with the agent's runtime topic.
   - Runtime topic isn't on the result root; you'll need to re-run with `--verbose` (which surfaces `generatedData` analogues in NGT) or open the run in Agentforce Studio UI.
   - Topic-name resolution rules from legacy still apply — see **Topic Name Resolution** below.
   - Fix: correct the YAML `expected:` value, OR fix the `.agent` file subagent description if the wrong subagent is being chosen.

2. **`action_sequence_match` FAIL** — the agent invoked a different action list.
   - The `expected:` value must be a Python-list string of **Level 2 invocation names** (from `reasoning: actions:`), not Level 1 definitions.
   - Unlike legacy's superset match, NGT's `action_sequence_match` is order-sensitive: the actual sequence must equal the expected sequence position-for-position. If you need a looser check, drop this scorer and use `response_match` or `bot_response_rating` instead.

3. **`agent_handoff_match` FAIL** — wrong handoff target Bot, or no handoff fired.
   - Verify the multi-agent subject is configured with handoff edges to the expected target.
   - Confirm the target Bot's API name (case-sensitive).

### LLM-Judged Scorer Failed

1. **`bot_response_rating` / `response_match` FAIL** — the LLM judge said the response didn't match the `expected:` rubric / exemplar.
   - Read the rationale in `scorerResponse` (appended after `PASS` / `FAIL`).
   - Either rewrite the `expected:` value to be more lenient/specific, or tighten the subagent instructions in `.agent`.

2. **`coherence` / `conciseness` / `factuality` / `completeness` low score** — quality dimension below your threshold.
   - These are unconditional (no `expected:`), so the fix is on the agent side: rephrase subagent instructions, add examples, or constrain output format.
   - `factuality` and `completeness` are the most useful here — they catch hallucinations and missing-detail responses. `coherence` and `conciseness` mostly catch verbose models.

3. **`task_resolution` low score** — the agent didn't actually solve the user's underlying ask.
   - Graded 0–5 on a multi-turn flow. Read the rationale; common causes are early escalation, asking redundant clarifying questions, or stopping before the action that resolves the task.
   - Confirm your `conversationHistory` actually represents the state you intended — `task_resolution` reads the full multi-turn trajectory and judges resolution against the final agent state.

### Numeric Scorer Threshold Failed

1. **`output_latency_milliseconds` over threshold** — agent took too long.
   - This isn't a content problem. Investigate slow actions (Flow / Apex callouts), long planner steps, or oversized prompts in the `.agent` file.
   - The scorer never "fails" in the result data — it always reports a number. Threshold comparison is the caller's responsibility, downstream of the runner.

### Redeploy and Re-Run

```bash
# Redeploy agent (changes to .agent file)
sf agent publish authoring-bundle --json --api-name <AgentApiName> -o <org>

# Re-run NGT suite
sf agent test run --json \
  --api-name <TestSuiteName> \
  --wait 10 \
  --result-format json \
  -o <org>
```

If you edited the YAML, re-create with `--force-overwrite`. If you only edited the `.agent` file, no re-create is needed — same metadata, new agent behavior.

## Reverse XML → YAML

When you need to round-trip a deployed NGT suite back to YAML — for diffing, version control, or moving a hand-edited XML back to authored shape:

```bash
sf agent generate test-spec \
  --from-definition force-app/main/default/aiTestingDefinitions/MySuite.aiTestingDefinition-meta.xml
```

Runner is inferred from the file extension (`.aiTestingDefinition-meta.xml` → NGT, `.aiEvaluationDefinition-meta.xml` → legacy). The `--from-definition` flag is non-interactive — fine to drive from this skill.

`--from-definition` for NGT XML lands in `@salesforce/plugin-agent@1.43.0` (PR #450). For legacy XML it has been shipped longer. Passing `--test-runner` alongside `--from-definition` is optional; if you pass it and it disagrees with the extension, the CLI raises `RunnerMismatch` with a remediation message.

## Error Surface

Validation errors thrown by `validateNgtSpec` (raised at `sf agent test create` time, before deploy):

| Error key | Cause | Fix |
|---|---|---|
| `ngtMissingTestCases` | `testCases:` is empty or missing | Add at least one test case |
| `ngtTestCaseMissingInputs` | Test case has no `inputs:` entries | Add at least one input |
| `ngtTestCaseMissingScorers` | Test case has no `scorers:` entries | Add at least one scorer |
| `ngtScorerMissingExpected` | Scorer with `needsExpected: true` has no `expected:` | Add the value, or pick a different scorer |
| `ngtTaskResolutionRequiresConversationHistory` | `task_resolution` scorer on a case with no `conversationHistory` | Add `conversationHistory` to one input, OR drop `task_resolution` |
| `ngtMultiAgentMissingHandoff` | Multi-agent subject case missing `agent_handoff_match` with `expected:` | Add an `agent_handoff_match` scorer with the target Bot API name |
| `ngtConversationHistoryIndexAllOrNothing` | Mixed turns with and without `index:` | Set `index:` on every turn or none |
| `ngtLooksLikeLegacySpec` | YAML uses top-level `utterance:` / `expectedTopic:` (legacy shape) | Re-author against NGT shape, OR pass `--test-runner testing-center` for legacy |

Unknown scorer names do **not** throw — `validateNgtSpec` emits a Lifecycle warning and lets the deploy proceed. The org-side metadata validator (`AITestingOOTBEvaluations.resolveByKeyOrName`) is the authoritative gate, so a typo in a scorer name fails at deploy, not at author time.

Runtime errors thrown elsewhere in the flow:

| Error name | Cause | Fix |
|---|---|---|
| `AmbiguousTestDefinition` | Test name exists in BOTH `AiEvaluationDefinition` and `AiTestingDefinition` in the same org | Pass `--test-runner` explicitly to `sf agent test run` / `results` to disambiguate |
| `RunnerMismatch` (1.43.0+) | `--from-definition` extension and `--test-runner` flag disagree | Match the flag to the file extension, or drop `--test-runner` and let extension inference handle it |

## Topic Name Resolution

NGT inherits the same topic-name quirks as legacy because both runners report the agent's runtime topic the same way:

| Subagent type | Name to use in `expected:` | Example |
|---|---|---|
| Standard topics | `localDeveloperName` (short name) | `Escalation`, `Off_Topic` |
| Custom subagents | Short name from `.agent` file | `home_search`, `warranty_service` |
| Promoted topics | Full runtime `developerName` with hash suffix | `p_16jPl000000GwEX_Topic_16j8eeef13560aa` |

**Discovery workflow when `topic_sequence_match` FAILs unexpectedly:**

1. Run the test with best-guess names.
2. Re-run with `--verbose` to surface the runtime topic the agent actually chose (NGT exposes this via `generatedData` analogues in verbose mode).
3. Update `expected:` with the actual runtime name.
4. Redeploy with `--force-overwrite` and re-run.

**Topic hash drift**: runtime topic hash suffix changes after each agent republish for promoted topics. Re-run discovery after each `sf agent publish authoring-bundle`.

## Auto-Generation from `.agent` File

The same heuristics that derive a legacy spec from `.agent` apply to NGT, with two differences:

1. **Scorer mix per case**, not three fixed assertion fields. A reasonable default scorer set per generated case:
   - `topic_sequence_match` with the subagent name (deterministic regression gate)
   - `factuality` (quality)
   - `completeness` (quality)
   - Add `action_sequence_match` when the case is action-triggering, with the Level 2 names
   - Add `task_resolution` + boilerplate `conversationHistory` for multi-turn flows
2. **Multi-input grouping**: collapse paraphrase variations of a single subagent test into one multi-input case rather than emitting N separate cases.

The Level 1 vs Level 2 action-name rule from legacy still applies — use the names from `reasoning: actions:`, not from `subagent: actions:`. Same root cause: the runtime reports invocation names, not definition names. See `references/batch-testing.md` → **Level 1 vs Level 2 Action Names** for the full callout.

## Differences from Legacy at a Glance

| Axis | Legacy (`testing-center`) | NGT (`agentforce-studio`) |
|------|---------------------------|----------------------------|
| Metadata type | `AiEvaluationDefinition` | `AiTestingDefinition` |
| Min Metadata API | (any current version) | `66.0` |
| YAML root | `testCases[].utterance` directly | `testCases[].inputs[].utterance` |
| Assertion model | 3 fixed fields (`expectedTopic`, `expectedActions`, `expectedOutcome`) | 11-row scorer catalog (see SKILL.md) |
| Multi-input per case | No (one utterance per case) | Yes (N inputs share one scorer set) |
| Action-match semantics | Superset (extra actions OK) | Order-sensitive sequence |
| Quality grading | Numeric metrics under `metrics:` | First-class quality scorers (`factuality`, `coherence`, `completeness`, `conciseness`) |
| Result container | `testResults[]` with fixed names | `testScorerResults[]` with scorer-defined names |
| Custom evaluations | `customEvaluations:` with JSONPath operators | Not exposed in NGT YAML — hand-edit XML for `<scorer scorerType="Custom">` blocks |
| Topic hash drift | Yes | Yes (same root cause) |
| Subject version | Not modeled | `subjectVersion` field, defaults to `v1` |

## Known Gaps and Workarounds

| Gap | Severity | Workaround |
|-----|----------|------------|
| `sf agent generate test-spec --from-definition` for NGT XML not yet released (PR #450 merged but unshipped as of 1.42.1) | Low | Round-tripping deployed NGT XML back to YAML is currently a manual exercise. `--from-definition` for legacy XML already works. Authoring NGT YAML from scratch is the primary path either way. |
| Custom scorers (`scorerType="Custom"`) not exposed in NGT YAML | Medium | Hand-edit the deployed XML; document the `<scorer>` block separately |
| Runtime `topic` / `actionsSequence` not on result root | Low | Re-run with `--verbose`, or open the run in Agentforce Studio UI |
| Unknown scorer names emit only a warning at validate time | Low | Don't rely on local validation for scorer-name correctness; expect deploy-time failure on typos |
| `task_resolution` scoring depends heavily on `conversationHistory` accuracy | Low | When auto-generating, hand-review every `task_resolution` case before deploy |
