# Locale Validation — einstein-copilot-fit-tests Reference

This reference covers how to generate and run multilingual locale validation tests using the
`einstein-copilot-fit-tests` Maven/JUnit framework. It is also applicable when the skill is
invoked from within that repository.

## Framework overview

The framework is built on `EvalParameterizedTest` (a JUnit 5 abstract base class). The key mechanism is:

- `testCaseFilePath` — JSON template with placeholders like `{{utterance}}`, `{{languageKey}}`, `{{language}}`
- `utteranceFilePath` — JSON with utterances nested by test type and locale
- `utteranceSourceMultiLang()` / `utteranceSourceMultiLangSanity()` / `utteranceSourceMultiLangSmoke()` — method sources that expand the matrix of (utterance × locale) into parameterized test arguments

`EvalLocaleTestUtil` provides the LLM-as-judge validation prompt. `UtteranceTranslationUtil` provides LLM-backed utterance translation at runtime.

---

## Step 1 — Generate utterances.json

The utterances file must follow the nested structure: `{ "TestType": { "localeCode": { "testKey": "utterance" } } }`.

**Template:**

```json
{
  "Sanity": {
    "en_US": {
      "topic1_utterance1": "Your English utterance here"
    },
    "ja": {
      "topic1_utterance1": "日本語の発話（EvalLocaleTestUtil翻訳または手動）"
    },
    "fr": {
      "topic1_utterance1": "Votre énoncé en français"
    },
    "it": {
      "topic1_utterance1": "Il tuo enunciato in italiano"
    },
    "de": {
      "topic1_utterance1": "Ihre Äußerung auf Deutsch"
    },
    "es": {
      "topic1_utterance1": "Su enunciado en español"
    },
    "es_MX": {
      "topic1_utterance1": "Su enunciado en español mexicano"
    },
    "pt_BR": {
      "topic1_utterance1": "Seu enunciado em português brasileiro"
    }
  },
  "Smoke": {
    "en_US": {
      "topic1_utterance1": "Smoke-level English utterance"
    },
    "ja": {
      "topic1_utterance1": "スモークレベルの日本語発話"
    }
  }
}
```

When using `UtteranceTranslationUtil` at runtime (preferred), you only need to supply `en_US`
utterances — the framework translates them dynamically. Pre-translated utterances are better for
regression stability (same input every run).

Canonical file location:
```
src/test/resources/testdata/evals/<cloud>/<feature>/<AgentName>/utterances.json
```

---

## Step 2 — Generate test-case.json

The test case file is a JSON template with `{{placeholder}}` tokens. The framework replaces:

| Placeholder | Value |
|-------------|-------|
| `{{utterance}}` | The translated utterance for this locale |
| `{{languageKey}}` | The locale code, e.g. `ja` |
| `{{language}}` | The human-readable language name, e.g. `Japanese` |
| `{{plannerId}}` | The agent planner ID (set in `placeHolderContext`) |
| `{{testType}}` | `Sanity`, `Smoke`, or `Regression` |

**Minimal test-case.json template:**

```json
{
  "tests": [{
    "id": "locale_validation_{{testType}}",
    "description": "Locale validation test for {{language}}",
    "steps": [
      {
        "type": "agent.create_session",
        "planner_id": "{{plannerId}}",
        "setup_session_context": {
          "variables": [
            {
              "name": "$Context.EndUserLanguage",
              "value": "{{languageKey}}"
            }
          ]
        }
      },
      {
        "type": "agent.send_message",
        "utterance": "{{utterance}}"
      },
      {
        "type": "evaluator.llm_assertion",
        "prompt": "{{languageCheckPrompt}}",
        "operator": "contains",
        "expected": "\"overall_evaluation\": \"Good\""
      }
    ]
  }]
}
```

The `{{languageCheckPrompt}}` placeholder is populated at runtime by calling:
```java
placeHolderContext.put("languageCheckPrompt",
    EvalLocaleTestUtil.buildLanguageValidationPrompt(languageKey, agentResponse));
```

Canonical file location:
```
src/test/resources/testdata/evals/<cloud>/<feature>/<AgentName>/test-case.json
```

---

## Step 3 — Generate the Java test class

Create a class that extends `EvalParameterizedTest` (or the appropriate cloud-specific subclass).

**Template:**

```java
package com.salesforce.einstein_copilot.test.evals.<cloud>.<feature>.<AgentName>;

import com.salesforce.einstein_copilot.test.evals.util.EvalLocaleTestUtil;
import com.salesforce.einstein_copilot.test.evals.util.LocalizationTranslatorHolder;
import com.salesforce.einstein_copilot.test.evals.util.UtteranceTranslationUtil;
import com.salesforce.einstein_copilot.test.evalsv2.EvalParameterizedTest;
import com.salesforce.atf.context.TestRunContext;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

// Import your @EvalTestParameters annotation and eval utilities

public class <AgentName>LocaleEvalTest extends EvalParameterizedTest {

    private static final String AGENT_NAME = "<AgentDeveloperName>";
    private static final String CREDENTIAL_NAME = "<credential-name>";

    @BeforeAll
    public static void initInputFiles() {
        testCaseFilePath.set("/testdata/evals/<cloud>/<feature>/<AgentName>/test-case.json");
        utteranceFilePath.set("/testdata/evals/<cloud>/<feature>/<AgentName>/utterances.json");
    }

    @BeforeEach
    public void setupTranslator(TestRunContext context) {
        // Set up LLM-based translator if available (falls back to pre-translated utterances)
        var translator = UtteranceTranslationUtil.createTranslatorFromContext(context);
        if (translator != null) {
            LocalizationTranslatorHolder.setTranslator(translator);
        }
    }

    @ParameterizedTest(name = "LocaleValidation-Sanity-{0}")
    @MethodSource("utteranceSourceMultiLangSanity")
    public void testLocaleValidation_Sanity(String testName, org.json.JSONObject request) throws Exception {
        // Extract language key from the request for validation
        String languageKey = EvalLocaleTestUtil.extractLanguageKeyFromRequest(request.toString());

        // Set the planner ID and any other context your agent needs
        placeHolderContext.put("plannerId", /* resolve planner id */);

        // Run the eval
        var evalResponse = evalUtil.evaluate(request.toString(), placeHolderContext);

        // Set language validation prompt for the eval assertion step
        String agentResponse = /* extract response from evalResponse */;
        placeHolderContext.put("languageCheckPrompt",
            EvalLocaleTestUtil.buildLanguageValidationPrompt(languageKey, agentResponse));

        runEvalValidations(evalResponse, request.toString(), placeHolderContext);
    }

    @ParameterizedTest(name = "LocaleValidation-Smoke-{0}")
    @MethodSource("utteranceSourceMultiLangSmoke")
    public void testLocaleValidation_Smoke(String testName, org.json.JSONObject request) throws Exception {
        testLocaleValidation_Sanity(testName, request);
    }
}
```

**Placement:** `src/test/java/com/salesforce/einstein_copilot/test/evals/<cloud>/<feature>/<AgentName>/`

---

## Step 4 — Run the tests

```bash
# Run sanity locale tests
mvn clean test \
  -Dtest="<AgentName>LocaleEvalTest#testLocaleValidation_Sanity" \
  -Ptestlocal \
  -Dsut_config=src/test/resources/stc-config-sdb15.json

# Run a specific locale only (JUnit filter)
mvn clean test \
  -Dtest="<AgentName>LocaleEvalTest#testLocaleValidation_Sanity[LocaleValidation-Sanity-topic1_utterance1_ja]" \
  -Ptestlocal \
  -Dsut_config=src/test/resources/stc-config-sdb15.json

# Run all locales
mvn clean test \
  -Dtest="<AgentName>LocaleEvalTest" \
  -Ptestlocal \
  -Dsut_config=src/test/resources/stc-config-sdb15.json
```

---

## EvalLocaleTestUtil — key methods

| Method | Use |
|--------|-----|
| `extractLanguageKeyFromRequest(String requestJson)` | Pulls `$Context.EndUserLanguage` from test request JSON; defaults to `en_US` |
| `buildLanguageValidationPrompt(String languageKey, String responseString)` | Builds the LLM-as-judge prompt for validating response language/quality |
| `buildLanguageValidationPromptFromRequest(String requestJson, String responseString)` | Convenience: extracts locale from request then builds prompt |
| `translateText(String text, String targetLanguageCode)` | Translates via `LocalizationTranslatorHolder`; returns original if no translator |

## Language validation prompt behavior

The prompt (in `EvalLocaleTestUtil.languagePrompt`) instructs the LLM judge to:

- **Critical failure:** Return `overall_evaluation: POOR` immediately if the target is not English but the response is in English
- **Lenient pass:** Allow minor regional/dialect differences, minor formality deviations
- **Issue types:** `Untranslated Text`, `Grammar/Spelling`, `Tone/Structure`, `Formatting`, `Culture & Business Alignment`, `Sensitive Content`
- **Output:** JSON with `validation_results` list and `overall_evaluation` (`Good` or `Bad`)

The `overall_evaluation` key in the JSON output is what the `evaluator.llm_assertion` step checks via `contains "\"overall_evaluation\": \"Good\""`.

---

## Supported locale codes

From `EvalParameterizedTest.LANGUAGE_MAPPING`:

| Code | Language | Code | Language |
|------|----------|------|----------|
| `en_US` | English | `fr` | French |
| `ja` | Japanese | `it` | Italian |
| `de` | German | `es` | Spanish |
| `es_MX` | Spanish (Mexico) | `pt_BR` | Portuguese (Brazil) |
| `pt_PT` | Portuguese (European) | `fr_CA` | French (Canadian) |
| `en_GB` | English (UK) | `en_AU` | English (Australian) |
| `zh_CN` | Chinese (Simplified) | `zh_TW` | Chinese (Traditional) |
| `ar` | Arabic | `ko` | Korean |
| `nl` | Dutch | `da` | Danish |
