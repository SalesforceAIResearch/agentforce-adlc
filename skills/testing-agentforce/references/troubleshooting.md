# Troubleshooting, Best Practices, and Dependencies — Reference

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Session timeout | Long-running tests | Split into smaller batches |
| Trace not found | CLI version issue | Update to sf CLI 2.121.7+ |
| Action mock fails | Complex inputs | Use `--use-live-actions` flag |
| Context variables missing | Preview limitation | Use Runtime API for context tests |
| `jq` parse error on preview output | Control characters in CLI output | Use Python `re.sub` + `json.loads` (see below). `tr` via bash pipes is unreliable -- control chars survive `echo "$VAR"` expansion. |

## NGT (Agentforce Studio) Issues

For NGT-specific concepts (scorer catalog, multi-input cases, detection probe), see `SKILL.md` → Mode B and `references/ngt-batch-testing.md`. The entries below cover failure modes you'll actually hit at the CLI.

### Detection / Environment

| Issue | Cause | Solution |
|-------|-------|----------|
| `sf agent test create --test-runner agentforce-studio` errors on the flag | `@salesforce/plugin-agent` < 1.40.0 | `sf plugins install @salesforce/plugin-agent@latest`. The flag has shipped since 1.40.0 so this is uncommon; the native error message is clear. |
| Deploy fails with "AiTestingDefinition type not supported" | Project `sourceApiVersion` < 66.0 in `sfdx-project.json` | Bump `sourceApiVersion` to `"66.0"` (or higher). The detection probe in `SKILL.md` catches this before authoring. |
| Org rejects `AiTestingDefinition` metadata at deploy | Target org doesn't have NGT enabled yet | Confirm org has Agentforce Studio entitlement; otherwise fall back to legacy (`--test-runner testing-center`) for this org |
| `AmbiguousTestDefinition` on `sf agent test run` | A test name exists in BOTH `AiEvaluationDefinition` and `AiTestingDefinition` in the same org | Pass `--test-runner` explicitly to `sf agent test run` / `sf agent test results` to disambiguate. Long-term: rename one of the suites. |
| `RunnerMismatch` on `sf agent generate test-spec --from-definition` (1.43.0+) | The `--test-runner` flag disagrees with the file extension on the XML | Either drop `--test-runner` (extension inference handles it) or match the flag to `.aiTestingDefinition-meta.xml` / `.aiEvaluationDefinition-meta.xml` |
| Deploy fails with `DeveloperName: The AI Test Suite Definition API Name can only contain underscores and alphanumeric characters...` | YAML top-level `name:` contained a space or other invalid character. NGT treats `name:` as the test suite's **DeveloperName** (the `<name>` XML element), not a display name. Legacy is permissive about this and will deploy with a space, but NGT is strict and rejects at deploy time. | Change `name:` to alphanumeric + underscore only, start with a letter, no double underscores, no trailing underscore (e.g. `name: OrderService_Smoke_Tests`). Put human-readable text in `description:`. See `references/ngt-batch-testing.md` → Required Fields. |
| Deploy fails with `duplicate value found: <unknown> duplicates value on record with id: <unknown>` (both `<unknown>`) | YAML top-level `name:` does NOT match the `--api-name` value passed to `sf agent test create`. The CLI uses `--api-name` for the filename but does not rewrite the YAML's `name:`, so the deployed XML's `<name>` element and the filename disagree. The server-side error message is misleading — neither name needs to already exist on the org. | Pass `--api-name` set to the same value as YAML `name:`, or change `name:` to match `--api-name`. Example: if YAML has `name: OrderService_Smoke_Tests`, deploy with `sf agent test create --api-name OrderService_Smoke_Tests ...`. See `references/ngt-batch-testing.md` → Required Fields. |
| Deploy fails with `Label: data value too large: <value> (max length=100)` | YAML top-level `description:` exceeds 100 characters. It compiles to `MasterLabel` on the deployed metadata, which has a hard 100-char limit. | Shorten `description:` to ≤ 100 chars. Put longer rationale in code comments or commit messages instead. |

### Authoring / Validation Errors

These are thrown by `validateNgtSpec` at `sf agent test create` time, before any deploy. Every error message is keyed — the key is in the JSON output and is the most useful thing to grep on.

| Error key | Cause | Fix |
|---|---|---|
| `ngtMissingTestCases` | Empty / missing `testCases:` | Add at least one test case |
| `ngtTestCaseMissingInputs` | Test case has no `inputs:` entries | Add at least one input. NGT uses `inputs: [- utterance: ...]`, not top-level `utterance:` (which is the legacy shape) |
| `ngtTestCaseMissingScorers` | Test case has no `scorers:` entries | Add at least one scorer |
| `ngtScorerMissingExpected` | Scorer with `needsExpected: true` (per the catalog in `SKILL.md`) has no `expected:` | Add the `expected:` value, or swap to a quality scorer (`coherence`, `factuality`, etc.) that doesn't need one |
| `ngtTaskResolutionRequiresConversationHistory` | `task_resolution` scorer on a case with no `conversationHistory` on any input | Add `conversationHistory` to one input, OR drop `task_resolution` from this case. The lib enforces this because `task_resolution` is graded on the multi-turn trajectory; a single-turn case can't be scored. |
| `ngtMultiAgentMissingHandoff` | Subject Bot has `IsMultiAgent=true` but the test case lacks `agent_handoff_match` with `expected:` | Add an `agent_handoff_match` scorer with the target Bot's API name. The lib reads `IsMultiAgent` from the org directly — there's nothing in the YAML to declare. |
| `ngtConversationHistoryIndexAllOrNothing` | Mixed turns: some have `index:`, some don't | All-or-nothing per case. Either set `index:` on every turn or drop it from every turn. |
| `ngtLooksLikeLegacySpec` | YAML uses top-level `utterance:` / `expectedTopic:` / `customEvaluations:` (the legacy `AiEvaluationDefinition` shape) | Re-author against NGT shape (see `references/ngt-batch-testing.md` → Phase 1). Or, if you actually want legacy, pass `--test-runner testing-center`. |

### Silent Failures (No Error, Wrong Behavior)

| Issue | Symptom | Solution |
|-------|---------|----------|
| Unknown scorer name doesn't fail validation | `validateNgtSpec` emits a Lifecycle warning and lets the deploy through; the server-side metadata validator rejects it at deploy | Don't rely on local validation for scorer-name typos. Cross-check every scorer name against the catalog probe in `SKILL.md` → Scorer Catalog before deploying. |
| `sf agent test run` returns `status: COMPLETED` with `testCases: []` (NGT only) | Subject bot has no `BotVersion.Status = 'Active'`. The NGT runner returns an empty envelope with no error message. `sf agent publish authoring-bundle` does NOT activate — it only creates a new BotVersion (still `Inactive`). | Activate a version: `sf agent activate --api-name <bot> --version <N> -o <org>`. Verify with `sf data query --query "SELECT VersionNumber, Status FROM BotVersion WHERE BotDefinition.DeveloperName='<bot>'"`. If activation fails with `This Agent Type should have a user assigned`, the bot needs a runtime user assignment — see `/developing-agentforce` for the activation runbook. The skill's pre-run probe in `SKILL.md` → Pre-Run Probe catches this before you wait through a useless run. |
| Legacy run returns `status: IN_PROGRESS`, all cases `status: RETRY`, all `actualValue: ""`, `errorMessage: "Retrying (N/M) due to: Unknown error"` | Same root cause as the NGT empty-cases mode — subject bot has no `BotVersion.Status = 'Active'`. The **legacy** runner surfaces it differently: it returns the full case set with empty actuals and retry status instead of an empty envelope. | Same fix as the NGT case above — activate a BotVersion. The Pre-Run Probe in `SKILL.md` covers both modes; see `references/test-report-format.md` → Legacy Result JSON Shape for the envelope contract. |
| `action_sequence_match` FAILs even though the expected actions all ran | NGT's match is **order-sensitive** (sequence equality), unlike legacy's **superset matching** | Either align the `expected:` list with the actual invocation order, or drop `action_sequence_match` and use `response_match` / `bot_response_rating` for a looser check |
| Multi-input case appears as N separate cases in results | Expected. The lib fans out N `<testCase>` XML elements with a shared scorer set; `<number>` increments globally | Group result rows by `subjectResponse` similarity or original input index when summarizing |
| `task_resolution` score is unexpectedly low | The `conversationHistory` you supplied doesn't actually represent the trajectory you think it does (missing turns, wrong final state, role mislabel) | Walk through the history turn-by-turn; remember `agent` turns require `topic:`. Use `sf agent preview` to capture a real conversation, then transcribe it into the YAML rather than hand-writing. |
| `topic_sequence_match` FAILs and you can't see what the agent actually chose | NGT result rows don't expose runtime `topic` on the root the way legacy does | Re-run with `--verbose` (surfaces `generatedData` analogues), or open the run in Agentforce Studio UI |
| Tests pass locally, FAIL after `sf agent publish` | Topic hash drift — promoted topic `developerName` hash suffixes change on every republish | Re-run topic-name discovery after each publish. Same root cause as legacy; same workflow applies. |
| LLM-judged scorer scores swing across runs | Inherent to `LLM_PASS_FAIL` / `LLM_0_100` / `LLM_0_5` grades — the judge is a separate LLM call with its own variance | Use a small retry budget or set thresholds with margin. Reserve `PASS_FAIL` (deterministic) scorers as the hard gate. |
| `output_latency_milliseconds` "fails" when score is reasonable | The scorer never reports PASS/FAIL — it always returns a raw millisecond number. Threshold comparison is the caller's responsibility | Compare the numeric value against your latency budget downstream of the runner; don't expect the runner to do it |

### Defensive JSON Parsing

`sf agent preview` output may contain control characters (e.g. `\x08`, `\x1b`) that break `jq` and `json.loads`. Always sanitize before parsing.

**Use Python `re.sub`** -- this is the only reliable approach. The `tr` command via `echo "$VAR" | tr -d ...` is unreliable because bash variable expansion and `echo` can re-introduce or mangle control characters:

```bash
# Recommended: Python re.sub (handles all control characters reliably)
python3 -c "
import json, sys, re
raw = sys.stdin.read()
clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)
data = json.loads(clean)
print(json.dumps(data.get('result', {}), indent=2))
" <<< "$RESPONSE"
```

## Debug Mode

Enable detailed logging for preview sessions:

```bash
# Enable SF CLI debug output
export SF_LOG_LEVEL=debug

# Run preview with verbose output (--authoring-bundle for local traces)
sf agent preview start --authoring-bundle MyAgent -o myorg --json 2>&1 | tee /tmp/preview_debug.json
```

## Best Practices

### Test Strategy

1. **Start with smoke tests** - Basic happy path scenarios
2. **Add edge cases** - Boundary conditions, invalid inputs
3. **Test transitions** - Multi-turn conversations
4. **Verify guardrails** - Off-topic and safety boundaries
5. **Performance baseline** - Establish acceptable response times

### Test Maintenance

- Version test cases with agent versions
- Update expected outputs when agent evolves
- Archive historical test results
- Monitor test flakiness and address root causes

## Dependencies

This skill uses `sf` CLI commands directly. Required tools:
- `sf` CLI 2.121.7+ (for preview trace support)
- `jq` (system) - JSON processing
- `python3` - For result parsing scripts

## Exit Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 0 | All tests passed | Safe to deploy |
| 1 | Some tests failed | Review failures before deploying |
| 2 | Critical test failure | Block deployment |
| 3 | Test execution error | Fix test infrastructure |
