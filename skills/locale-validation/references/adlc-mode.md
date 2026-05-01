# Locale Validation — ADLC Execution Reference

## Preview mode (Mode A)

Use `sf agent preview` to run each locale test interactively. Each locale requires its own session because `$Context.EndUserLanguage` is set at session creation time.

### Start a session with a locale

```bash
# Start session for a specific locale
sf agent preview start \
  --json \
  --authoring-bundle <AgentName> \
  -o <org-alias> \
  > /tmp/locale_session_<locale>.json

SESSION_ID=$(cat /tmp/locale_session_<locale>.json | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['sessionId'])")
```

> **Note:** `sf agent preview` does not natively accept `$Context.EndUserLanguage` as a CLI flag. To test locale routing, either:
> 1. Deploy a test variant of the agent with `default_locale` set to the target locale, or
> 2. Include the locale in the utterance context (e.g., "Respond only in Japanese: check my order") for quick smoke-testing, or
> 3. Use the org's user language setting if your org supports it.
>
> For rigorous locale testing, prefer Mode B (batch) which allows full session context injection.

### Send a translated utterance

```bash
sf agent preview send \
  --json \
  --session-id "$SESSION_ID" \
  --utterance "<translated utterance>" \
  --authoring-bundle <AgentName> \
  -o <org-alias> \
  > /tmp/locale_response_<locale>_<topic>.json
```

### End the session

```bash
sf agent preview end \
  --json \
  --session-id "$SESSION_ID" \
  --authoring-bundle <AgentName> \
  -o <org-alias>
```

### Extract the agent's response

```bash
# Get the last bot response from the trace
cat /tmp/locale_response_<locale>_<topic>.json | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d['result'].get('response', ''))"
```

### Validate the response language

For each response, check:
1. Is the response in the target language? (Not English when target ≠ en_US)
2. Does it correctly route to the expected topic?

Read the topic routing from the trace:
```bash
TRACE_DIR=".sfdx/agents/<AgentName>/sessions/$SESSION_ID/traces/"
ls "$TRACE_DIR"
python3 -c "
import json, glob, sys
for f in glob.glob('$TRACE_DIR/*.json'):
    d = json.load(open(f))
    topic = d.get('topic', {}).get('name', 'unknown')
    print(f'Topic: {topic}')
"
```

### Loop pattern for all locales

```bash
AGENT=MyAgent
ORG=my-org
LOCALES="ja fr it de es es_MX pt_BR"
UTTERANCES_FILE=/tmp/locale_utterances.json   # {locale: {topic: utterance}}

for LOCALE in $LOCALES; do
  echo "=== Testing locale: $LOCALE ==="
  SESSION=$(sf agent preview start --json --authoring-bundle $AGENT -o $ORG | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['sessionId'])")
  
  # Read utterances for this locale from your utterances file
  UTTERANCE=$(python3 -c "import json; u=json.load(open('$UTTERANCES_FILE')); print(u.get('$LOCALE', {}).get('topic1', ''))")
  
  sf agent preview send --json --session-id "$SESSION" --utterance "$UTTERANCE" \
    --authoring-bundle $AGENT -o $ORG > /tmp/resp_${LOCALE}.json
  
  sf agent preview end --json --session-id "$SESSION" --authoring-bundle $AGENT -o $ORG
done
```

---

## Batch mode (Mode B)

Mode B lets you inject full session context including `$Context.EndUserLanguage`, making it the most accurate way to test locale behavior.

### Build a locale-aware test spec

Generate a test spec YAML with utterances in each locale. Each test case entry should include a locale prefix in its ID for clarity:

```yaml
# test-spec-locales.yaml
name: "<AgentName> Locale Validation"
subjectType: AGENT
subjectName: <AgentName>

testCases:
  # Japanese
  - utterance: "<ja translation of topic1 utterance>"
    expectedTopic: "<TopicName>"
    expectedOutcome: "Agent responds in Japanese. Response is culturally appropriate, polite, and does not contain English text."

  - utterance: "<ja translation of topic2 utterance>"
    expectedTopic: "<TopicName2>"
    expectedOutcome: "Agent responds in Japanese. Response correctly addresses the user's request."

  # French
  - utterance: "<fr translation>"
    expectedTopic: "<TopicName>"
    expectedOutcome: "Agent responds in French. Response is culturally appropriate for French-speaking users."

  # Italian
  - utterance: "<it translation>"
    expectedTopic: "<TopicName>"
    expectedOutcome: "Agent responds in Italian. Response is grammatically correct and professional."

  # German
  - utterance: "<de translation>"
    expectedTopic: "<TopicName>"
    expectedOutcome: "Agent responds in German. Response uses appropriate formal register (Sie form)."

  # Spanish
  - utterance: "<es translation>"
    expectedTopic: "<TopicName>"
    expectedOutcome: "Agent responds in Spanish. Response is appropriate for Latin American or European Spanish context."

  # Spanish Mexico
  - utterance: "<es_MX translation>"
    expectedTopic: "<TopicName>"
    expectedOutcome: "Agent responds in Mexican Spanish. Response reflects appropriate regional phrasing."

  # Portuguese Brazil
  - utterance: "<pt_BR translation>"
    expectedTopic: "<TopicName>"
    expectedOutcome: "Agent responds in Brazilian Portuguese. Response is grammatically correct and professional."

  # Regression: English should still work
  - utterance: "<original English utterance>"
    expectedTopic: "<TopicName>"
    expectedOutcome: "Agent responds in English."
```

> **On session context injection:** The `AiEvaluationDefinition` format (used by `sf agent test create`) does not currently support per-test `$Context.EndUserLanguage` injection in the public YAML spec. If your agent relies on this variable for locale routing, set up dedicated test orgs or profiles with the user language set to the target locale, or use the fit-tests approach (see `fit-tests-mode.md`) which supports full session context via JSON.

### Deploy and run the test suite

```bash
# Create the test suite from spec
sf agent test create \
  --json \
  --spec test-spec-locales.yaml \
  --api-name <AgentName>LocaleValidation \
  -o <org-alias>

# Run it
sf agent test run \
  --json \
  --api-name <AgentName>LocaleValidation \
  --wait 30 \
  --result-format json \
  -o <org-alias> \
  > /tmp/locale-test-results.json
```

### Parse results

```bash
python3 -c "
import json
results = json.load(open('/tmp/locale-test-results.json'))
for tc in results.get('result', {}).get('testCases', []):
    name = tc.get('testCaseName', 'unknown')
    status = tc.get('status', 'unknown')
    verdict = tc.get('verdict', '')
    print(f'{name}: {status} — {verdict}')
"
```

### Evaluate responses with the language validator

For richer validation, run the locale validator after getting results:

```bash
python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/locale-test-results.json \
  --locales ja fr it de es es_MX pt_BR \
  --output /tmp/locale-validation-report.md
```

See `scripts/validate_locale_responses.py` for the implementation.
