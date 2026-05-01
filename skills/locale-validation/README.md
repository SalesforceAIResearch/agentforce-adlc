# locale-validation

A skill for validating Agentforce agent responses across multiple locales. Given any agent script (`.agent` file) or `genAiPluginMetadata`, it derives realistic test utterances per topic, translates them into the target languages, runs them against the agent in preview or batch mode, and validates that responses are in the correct language.

## Supported languages

All 23 Agentforce-supported locales. Source: [Agentforce Employee Agent Considerations](https://help.salesforce.com/s/articleView?id=ai.agent_employee_agent_considerations.htm&type=5) — Salesforce updates language support monthly, so check that page for new additions.

| Code | Language |
|------|----------|
| `ar` | Arabic |
| `zh_CN` | Chinese (Simplified) |
| `zh_TW` | Chinese (Traditional) |
| `da` | Danish |
| `nl` | Dutch |
| `fi` | Finnish |
| `fr` | French |
| `de` | German |
| `in` | Indonesian |
| `it` | Italian |
| `ja` | Japanese |
| `ko` | Korean |
| `ms` | Malay |
| `no` | Norwegian |
| `pl` | Polish |
| `pt_BR` | Portuguese (Brazil) |
| `pt_PT` | Portuguese (European) |
| `ru` | Russian |
| `es` | Spanish |
| `es_MX` | Spanish (Mexico) |
| `sv` | Swedish |
| `th` | Thai |
| `tr` | Turkish |

**Default set** (used when you say "use defaults"): `ja fr it de es es_MX pt_BR`

---

## Files

```
locale-validation/
├── SKILL.md                          # Skill definition & 5-phase workflow
├── README.md                         # This file
├── references/
│   ├── adlc-mode.md                  # sf agent preview + sf agent test execution guide
│   └── fit-tests-mode.md             # Maven/JUnit utterances.json + test class guide
└── scripts/
    └── validate_locale_responses.py  # Python validator for batch test results
```

---

## How to invoke

This skill is automatically triggered when Claude detects locale/language testing intent. You can also invoke it explicitly.

### Natural language triggers (automatic)

```
"Run locale validation on MySDRAgent"
"Test MyAgent in Japanese, French, and German"
"Generate multilingual test cases for EngagementAgent"
"Create a batch locale test suite for MyAgent"
"Validate that MyAgent responds in Spanish and Arabic"
"Check if additional_locales are working in MyAgent"
```

If your `.agent` file has `additional_locales` set and you ask about testing or quality, the skill also activates proactively.

### Explicit invocation

In any Claude Code session with `agentforce-adlc` loaded:

```
/locale-validation MyAgent.agent
```

Or with arguments:

```
/locale-validation force-app/main/default/aiAuthoringBundles/MyAgent/MyAgent.agent --locales ja fr de ko --mode preview
```

---

## Workflow

The skill runs five phases (plus two automatic checks after Phase 1). It pauses at Phase 1b if a locale patch is needed, and again after Phase 2 for utterance review.

| Phase | What happens |
|-------|-------------|
| 1. Introspect | Reads `.agent` or `genAiPluginMetadata`, extracts topics + actions |
| **1b. Check `additional_locales`** | Reads the `language:` block. If `additional_locales` is missing or empty, **presents the full 23-language list and asks you to pick locales**, then patches the `.agent` file before continuing |
| **1c. Check language-response instruction** | Searches `system.instructions` for the language-response rule. If missing, **patches it automatically** (no confirmation needed) so the agent responds in the user's language |
| 2. Derive utterances | Generates 2–3 English utterances per topic, **shows you for review** |
| 3. Translate | Translates each utterance into all target locales using Claude inline (no external API call) |
| 4. Run tests | Executes via `sf agent preview` (Mode A) or `sf agent test` (Mode B). **In Mode B, always writes both a `testSpec.yaml` and a companion `-input.csv`** for manual Testing Center UI upload |
| 5. Validate & report | Checks responses for correct language, reports ✅/❌ per locale per topic |

### Phase 1b — locale picker

When the skill detects a missing or empty `additional_locales`, it presents the full Agentforce language table and asks:

> "Reply with the codes you want (e.g. `ja fr de ko`) or say **"use defaults"** to add the standard seven: `ja, fr, it, de, es, es_MX, pt_BR`."

It then writes the confirmed locales into the `language:` block using the required format — a **quoted comma-separated string with no spaces** and 4-space indentation:

```
language:
    default_locale: "en_US"
    additional_locales: "ja,fr,de"
```

The patched locales become the working locale set for the rest of the workflow (merged with any `--locales` argument you passed).

---

## Execution modes

### Mode A — Preview (smoke testing)

Best for iterative development. Runs `sf agent preview` per locale and extracts responses from local trace files.

```
"Run locale validation on MyAgent in preview mode"
"Quick locale smoke test for MyAgent"
```

Claude reads `references/adlc-mode.md` for the exact `sf agent preview` commands.

### Mode B — Batch (regression testing)

Best for CI/CD and regression suites. Generates a `testSpec.yaml` and companion `-input.csv`, then runs via `sf agent test`.

```
"Create a batch locale test suite for MyAgent"
"Run locale regression tests for MyAgent in batch mode"
```

### fit-tests mode

When working in the `einstein-copilot-fit-tests` Maven project:

```
"Generate multilingual eval data for EngagementAgent"
```

---

## Validation logic

The validator flags two severity levels:

| Severity | Condition | Example |
|----------|-----------|---------|
| **CRITICAL** | Response is in English when target locale ≠ `en_US` | `ja` utterance → English response |
| **Warning** | No locale-specific characters detected in a Latin-script response | `fr` utterance → no accented characters in a long response |

Script detection method per locale:

| Script type | Locales | Detection method |
|-------------|---------|-----------------|
| Unicode range | `ja`, `zh_CN`, `zh_TW`, `ar`, `ko`, `th` | Character range match — CRITICAL if absent |
| Cyrillic range | `ru` | Cyrillic range (U+0400–U+04FF) — CRITICAL if absent |
| Diacritics | `fr`, `fr_CA`, `de`, `es`, `es_MX`, `it`, `pt_BR`, `pt_PT`, `nl`, `da`, `sv`, `no`, `fi`, `pl`, `tr` | Locale-specific accent characters — Warning if absent |
| Latin-only | `ms`, `in` | No diacritic check (these languages use unaccented Latin) — LLM-as-judge only |
| Skip | `en_US`, `en_GB` | Always passes |

---

## Using the Python validator directly

After a batch run, validate a results JSON file without Claude.

### Input JSON format

The script auto-detects two input formats.

**Format 1 — Raw `sf agent test results` output** (detected automatically):

```bash
sf agent test results --json --job-id <JOB_ID> --result-format json -o <org> \
  | tee /tmp/results.json
```

The script reads `inputs.utterance`, `generatedData.outcome`, and `generatedData.topic` from each test case. Because the raw format has no `locale` field, pass `--spec` (recommended) or `--locales` to assign locales.

**Format 2 — Custom intermediate format** (used by fit-tests and Claude-generated results):

```json
{
  "result": {
    "testCases": [
      {
        "testCaseName": "test_ja_web_reply",
        "locale": "ja",
        "utterance": "製品について教えてください",
        "botResponse": "Weloは...",
        "status": "pass",
        "topic": "web_reply"
      }
    ]
  }
}
```

Required fields: `locale`, `botResponse` (or `response` as fallback). Optional: `testCaseName`, `utterance`, `status`, `topic`.

### Options reference

| Option | Default | Description |
|--------|---------|-------------|
| `--results <path>` | *(required)* | Path to the JSON results file |
| `--spec <path>` | *(optional)* | Path to testSpec YAML — enables exact per-utterance locale assignment and preserves spec row order in the report |
| `--locales <codes...>` | `ja fr it de es es_MX pt_BR` | Space-separated locale codes to validate |
| `--agent-name <name>` | `Agent` | Agent name shown in the report header |
| `--output <path>` | stdout | Write markdown report to a file |
| `--llm-validate` | off | Enable LLM-as-judge on top of heuristic checks |
| `--llm-provider <name>` | `anthropic` | `anthropic` (default) or `openai` |
| `--llm-api-key <key>` | env var → interactive prompt | API key. Reads `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` by default |
| `--llm-model <name>` | `claude-haiku-4-5` / `gpt-4o` | Model name (provider-specific default applied automatically) |
| `--llm-endpoint <url>` | `https://api.openai.com/v1/chat/completions` | OpenAI-compatible URL (only used with `--llm-provider openai`) |
| `--llm-call-delay <secs>` | `1.0` | Pause between LLM calls — increase to 3–5 for low-rate-limit keys |

### Heuristic-only (fast, no API cost)

```bash
python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/locale-test-results.json \
  --locales ja fr it de es es_MX pt_BR \
  --agent-name MyAgent \
  --output /tmp/locale-validation-report.md
```

### LLM-as-judge via Claude (default)

```bash
# Key is read from ANTHROPIC_API_KEY; if unset, the script prompts at runtime
python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/locale-test-results.json \
  --locales ja fr de ko ar \
  --agent-name MyAgent \
  --llm-validate \
  --output /tmp/locale-validation-report.md
```

### LLM-as-judge via OpenAI (opt-in)

```bash
python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/locale-test-results.json \
  --locales ja fr de \
  --agent-name MyAgent \
  --llm-validate \
  --llm-provider openai \
  --llm-api-key "$OPENAI_API_KEY" \
  --llm-model gpt-4o \
  --output /tmp/locale-validation-report.md
```

### Azure OpenAI endpoint

```bash
python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/locale-test-results.json \
  --locales ja fr \
  --llm-validate \
  --llm-provider openai \
  --llm-endpoint "https://<resource>.openai.azure.com/openai/deployments/<deployment>/chat/completions?api-version=2024-02-01" \
  --llm-api-key "$AZURE_OPENAI_KEY" \
  --llm-model gpt-4o
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All validations passed |
| `1` | One or more **critical** failures (English response in non-English locale) — use as a CI gate |

---

## Validating the skill itself

### Quick sanity check

1. Open a Claude Code session in the `agentforce-adlc` directory
2. Verify the skill is loaded:
   ```
   What skills do you have available?
   ```
   You should see `locale-validation` in the list.

3. Trigger it with a test prompt:
   ```
   I want to test MyAgent in Japanese, French, and Korean.
   ```
   Claude should start the 5-phase workflow at Phase 1 (introspect).

4. Confirm it does NOT activate for unrelated prompts:
   ```
   Deploy my agent to production.
   ```
   Claude should use `developing-agentforce` instead.

### Functional validation with an agent file

```bash
cd /path/to/agentforce-adlc
claude

# Ask Claude to run locale validation on the example agent
"Run locale validation on force-app/main/default/aiAuthoringBundles/MS_Agent_hp_Apr22_adlc/MS_Agent_hp_Apr22_adlc.agent — just derive and show me the utterances, don't run them yet."
```

Expected: Claude reads the `.agent` file, lists topics, proposes 2–3 English utterances per topic, and waits for your review before translating or running anything.

### Validate the Python script

```bash
python3 -c "
import json
mock = {'result': {'testCases': [
  {'testCaseName': 'test_ja', 'locale': 'ja', 'utterance': 'check order', 'botResponse': 'Your order is ready.', 'status': 'pass'},
  {'testCaseName': 'test_fr', 'locale': 'fr', 'utterance': 'check order', 'botResponse': 'Votre commande est prête.', 'status': 'pass'},
  {'testCaseName': 'test_ar', 'locale': 'ar', 'utterance': 'check order', 'botResponse': 'Your order is ready.', 'status': 'pass'},
]}}
print(json.dumps(mock))
" > /tmp/mock-results.json

python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/mock-results.json \
  --locales ja fr ar \
  --agent-name TestAgent
```

Expected: `test_ja` and `test_ar` flagged as CRITICAL (English response for non-English locale), `test_fr` passes.

---

## Related skills

| Skill | When to use instead |
|-------|-------------------|
| `testing-agentforce` | General agent testing without locale focus |
| `developing-agentforce` | Authoring/editing `.agent` files |
| `observing-agentforce` | Analyzing production session traces for locale failures |
