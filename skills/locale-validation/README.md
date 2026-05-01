# locale-validation

A skill for validating Agentforce agent responses across multiple locales. Given any agent script (`.agent` file) or `genAiPluginMetadata`, it derives realistic test utterances per topic, translates them into the target languages, runs them against the agent in preview or batch mode, and validates that responses are in the correct language.

## Target locales

`ja` · `fr` · `it` · `de` · `es` · `es_MX` · `pt_BR`

Override the set at any time by telling Claude which locales you want.

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
"Validate that MyAgent responds in Spanish"
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
/locale-validation force-app/main/default/aiAuthoringBundles/MyAgent/MyAgent.agent --locales ja fr de --mode preview
```

---

## Workflow

The skill runs five phases (plus an automatic locale gate after Phase 1). It pauses at Phase 1b if a patch is needed, and again after Phase 2 for utterance review.

| Phase | What happens |
|-------|-------------|
| 1. Introspect | Reads `.agent` or `genAiPluginMetadata`, extracts topics + actions |
| **1b. Check `additional_locales`** | Reads the `language:` block. If `additional_locales` is missing or empty, **asks you which locales to add** and patches the `.agent` file before continuing |
| **1c. Check language-response instruction** | Searches `system.instructions` for the language-response rule. If missing, **patches it automatically** (no confirmation needed) so the agent responds in the user's language |
| 2. Derive utterances | Generates 2–3 English utterances per topic, **shows you for review** |
| 3. Translate | Translates each utterance into all target locales |
| 4. Run tests | Executes via `sf agent preview` (Mode A) or `sf agent test` (Mode B). **In Mode B, always writes both a `testSpec.yaml` and a companion `-input.csv`** for manual Testing Center UI upload |
| 5. Validate & report | Checks responses for correct language, reports ✅/❌ per locale per topic |

### Phase 1b — `additional_locales` patch detail

When the skill detects a missing or empty `additional_locales`, it asks:

> "The agent script does not declare any `additional_locales`. Which locales should I add?
> Default set: `ja, fr, it, de, es, es_MX, pt_BR`
> Reply with the list you want or say **"use defaults"**."

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

Best for CI/CD and regression suites. Generates a `test-spec-locales.yaml` and runs it via `sf agent test`.

```
"Create a batch locale test suite for MyAgent"
"Run locale regression tests for MyAgent in batch mode"
```

### fit-tests mode

When working in the `einstein-copilot-fit-tests` Maven project (see that repo's skill copy for full detail):

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

For Japanese, Chinese, Arabic, and Korean, the validator uses Unicode range detection (no LLM call needed for the critical check). For Latin-script languages, it looks for locale-specific accented characters.

For deep LLM-backed validation, the skill uses the same prompt template as `EvalLocaleTestUtil.languagePrompt` from `einstein-copilot-fit-tests`.

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

The script reads `inputs.utterance`, `generatedData.outcome`, and `generatedData.topic` from each test case. Because the raw format has no `locale` field, you must pass `--locales` to specify which locale(s) to assert against — the same locale is applied to all entries.

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

The format is detected per test case — mixed files (some raw, some custom) are handled correctly.

### Options reference

| Option | Default | Description |
|--------|---------|-------------|
| `--results <path>` | *(required)* | Path to the JSON results file (see format above) |
| `--spec <path>` | *(optional)* | Path to the testSpec YAML. When provided, per-utterance `locale:` fields are used for exact locale assignment and report rows are sorted to match spec order |
| `--locales <codes...>` | `ja fr it de es es_MX pt_BR` | Space-separated locale codes to validate. Pass a subset to limit scope. |
| `--agent-name <name>` | `Agent` | Agent name shown in the report header |
| `--output <path>` | stdout | Write markdown report to a file instead of printing it |
| `--llm-validate` | off | Enable LLM-as-judge validation on top of heuristic checks |
| `--llm-endpoint <url>` | `https://api.openai.com/v1/chat/completions` | Any OpenAI-compatible chat completions URL |
| `--llm-api-key <key>` | `$OPENAI_API_KEY` → interactive prompt | API key. Omit to read from `OPENAI_API_KEY`; if unset, the script prompts for it at runtime |
| `--llm-model <name>` | `gpt-4o` | Model name passed to the endpoint |

### Heuristic-only (fast, no API cost)

```bash
python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/locale-test-results.json \
  --locales ja fr it de es es_MX pt_BR \
  --agent-name MyAgent \
  --output /tmp/locale-validation-report.md
```

### With LLM-as-judge (uses `EvalLocaleTestUtil.languagePrompt`)

```bash
# Optional — if not set the script will prompt at runtime
export OPENAI_API_KEY=sk-...

python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/locale-test-results.json \
  --locales ja fr de \
  --agent-name MyAgent \
  --llm-validate \
  --output /tmp/locale-validation-report.md
```

Override model or endpoint:

```bash
# Azure OpenAI
python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/locale-test-results.json \
  --locales ja fr \
  --llm-validate \
  --llm-endpoint "https://<resource>.openai.azure.com/openai/deployments/<deployment>/chat/completions?api-version=2024-02-01" \
  --llm-api-key "$AZURE_OPENAI_KEY" \
  --llm-model gpt-4o

# Different model
python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/locale-test-results.json \
  --locales es es_MX \
  --llm-validate \
  --llm-model gpt-4-turbo
```

### Supported locales

| Code | Language | Script detection |
|------|----------|-----------------|
| `ja` | Japanese | Unicode range (U+3040–U+30FF, U+4E00–U+9FFF) |
| `zh_CN` | Chinese (Simplified) | Unicode range (U+4E00–U+9FFF) |
| `zh_TW` | Chinese (Traditional) | Unicode range (U+4E00–U+9FFF) |
| `ar` | Arabic | Unicode range (U+0600–U+06FF) |
| `ko` | Korean | Unicode range (U+AC00–U+D7AF) |
| `fr` | French | Accent characters (à â ç é è ê ë…) |
| `fr_CA` | French (Canadian) | LLM-only (no heuristic accent check) |
| `de` | German | Accent characters (ä ö ü ß) |
| `es` | Spanish | Accent characters (á é í ó ú ñ ¿ ¡) |
| `es_MX` | Spanish (Mexico) | Accent characters (same as `es`) |
| `it` | Italian | Accent characters (à è é ì ò ù) |
| `pt_BR` | Portuguese (Brazil) | Accent characters (ã õ á é â ô ç…) |
| `pt_PT` | Portuguese (European) | Accent characters (same as `pt_BR`) |
| `en_US` | English | Skipped (no-op) |
| `en_GB` | English (UK) | Skipped (no-op) |

**Note on `fr_CA`:** No locale-specific characters are checked heuristically (French Canadian uses the same accents as French but the heuristic doesn't cover it). Use `--llm-validate` for reliable `fr_CA` validation.

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

3. Trigger it with a test prompt that should activate it:
   ```
   I want to test MyAgent in Japanese and French.
   ```
   Claude should respond by starting the 5-phase locale validation workflow (Phase 1: introspect).

4. Trigger it with a prompt that should NOT activate it:
   ```
   Deploy my agent to production.
   ```
   Claude should use `developing-agentforce` instead, not `locale-validation`.

### Functional validation with an agent file

Use the example agent bundled in this repo:

```bash
# 1. Start Claude Code in agentforce-adlc
cd /path/to/agentforce-adlc
claude

# 2. Ask Claude to run locale validation on the example agent
"Run locale validation on force-app/main/default/aiAuthoringBundles/MS_Agent_hp_Apr22_adlc/MS_Agent_hp_Apr22_adlc.agent — just derive and show me the utterances, don't run them yet."
```

Expected: Claude reads the `.agent` file, lists topics, proposes 2–3 English utterances per topic, and waits for your go-ahead before translating or running anything.

### End-to-end batch validation

```bash
# Requires: authenticated SF org, agent deployed
"Generate a locale test spec YAML for MS_Agent_hp_Apr22_adlc and run it in batch mode against org my-dev-org."
```

Expected output includes a `test-spec-locales.yaml` with utterances in all 7 locales, sf agent test commands, and a summary table.

### Validate the Python script

```bash
# Create a minimal mock results file
python3 -c "
import json
mock = {'result': {'testCases': [
  {'testCaseName': 'test_ja', 'locale': 'ja', 'utterance': 'check order', 'botResponse': 'Your order is ready.', 'status': 'pass'},
  {'testCaseName': 'test_fr', 'locale': 'fr', 'utterance': 'check order', 'botResponse': 'Votre commande est prête.', 'status': 'pass'},
]}}
print(json.dumps(mock))
" > /tmp/mock-results.json

python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/mock-results.json \
  --locales ja fr \
  --agent-name TestAgent
```

Expected: `test_ja` flagged as CRITICAL (English response for Japanese locale), `test_fr` passes.

---

## Related skills

| Skill | When to use instead |
|-------|-------------------|
| `testing-agentforce` | General agent testing without locale focus |
| `developing-agentforce` | Authoring/editing `.agent` files |
| `observing-agentforce` | Analyzing production session traces for locale failures |
