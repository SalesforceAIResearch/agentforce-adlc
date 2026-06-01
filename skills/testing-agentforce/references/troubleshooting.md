# Troubleshooting, Best Practices, and Dependencies — Reference

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Session timeout | Long-running tests | Split into smaller batches |
| Trace not found | CLI version issue | Update to sf CLI 2.121.7+ |
| Action mock fails | Complex inputs | Use `--use-live-actions` flag |
| Context variables missing | Preview limitation | Use Runtime API for context tests |
| `jq` parse error on preview output | Control characters in CLI output | Use Python `re.sub` + `json.loads` (see below). `tr` via bash pipes is unreliable -- control chars survive `echo "$VAR"` expansion. |

## NGT-specific issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `INVALID_TYPE: Cannot use: AiEvaluationDefinition in this organization` (from `sf agent test list`) | Org doesn't have testing-center capability enabled (gated server-side by the `aFStudioTestingCenter` org permission) | Sign up for a [free Agentforce Developer Edition][de-signup], OR have your Salesforce admin enable testing-center on an existing sandbox (see the [Agentforce DX setup guide][dx-setup]), OR pin `agentforce-adlc@0.6.x` for legacy authoring. |
| `INSUFFICIENT_ACCESS: ...ModifyAllData or ModifyMetadata` (from `sf agent test list`) | Operator account lacks Metadata API perms | Use a different user, or assign a permset that grants `ModifyAllData` or `ModifyMetadata`. |
| `AmbiguousTestDefinition` error on `sf agent test run` / `results` / `resume` | A test with the same API name exists as both legacy and NGT runner types in the org | Pass `--test-runner agentforce-studio` explicitly to disambiguate. |
| Spec deployed but the test is the wrong type (legacy `AiEvaluationDefinition` instead of NGT) | `sf agent test create` was called without `--test-runner agentforce-studio` (the default is `testing-center`) | Verify with `sf agent test list --json` — look for `type: "agentforce-studio"`. If wrong type, delete the test and re-run create with the flag. |
| Deploy succeeds but server rejects the metadata | NGT requires Metadata API ≥ 66.0 | Set `"sourceApiVersion": "66.0"` in `sfdx-project.json`. The lib does NOT preflight this. |
| `ngtMultiAgentMissingHandoff` validator error | Subject is a multi-agent (`BotDefinition.IsMultiAgent = true`) and a test case lacks `agent_handoff_match` | Add `agent_handoff_match` with the target sub-agent's `DeveloperName` (NOT label) to every test case. |
| `ngtTaskResolutionRequiresConversationHistory` validator error | A test case has `task_resolution` scorer but no `conversationHistory:` on any input | Add `conversationHistory:` to one of the inputs, or remove `task_resolution`. |
| Testing-center capability still not detected after admin enablement | Setup toggles may need re-enabling | In the org's Setup, toggle on Einstein Setup → "Turn on Einstein", Agentforce Agents, "Setup with Agentforce (Beta)". Re-run the canonical probe. If still negative, contact your Salesforce admin or account team. |

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

## Links

[de-signup]: https://www.salesforce.com/form/developer-signup/?d=pb
[dx-setup]: https://developer.salesforce.com/docs/ai/agentforce/guide/agent-dx-set-up-env.html
