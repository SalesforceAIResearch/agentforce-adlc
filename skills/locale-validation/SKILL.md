---
name: locale-validation
description: "Validate Agentforce agent responses across multiple locales by reading the agent script or genAiPluginMetadata, deriving test utterances per topic, and running them in all target languages. Automatically checks whether the agent declares additional_locales — if missing or empty, asks the user which locales to add and patches the .agent file before proceeding. TRIGGER when: user asks to test an agent in multiple languages or locales; mentions 'locale validation', 'multilingual testing', 'language support', 'additional_locales', or 'localization'; wants to verify agent responds correctly in Japanese, French, Italian, German, Spanish, or Portuguese; asks to generate locale test cases from an agent script; mentions 'ja', 'fr', 'it', 'de', 'es', 'es_MX', or 'pt_BR' testing. Also trigger proactively when you notice a .agent file has a non-empty additional_locales field or all_additional_locales: True and the user asks about testing or quality."
allowed-tools: Bash Read Write Edit Glob Grep
license: Apache-2.0
metadata:
  version: "0.5.0"
  last_updated: "2026-04-28"
  argument-hint: "<path/to/Agent.agent> [--locales ja,fr,it,de,es,es_MX,pt_BR] [--mode preview|batch]"
  compatibility: claude-code, agentforce-adlc, einstein-copilot-fit-tests
---

# Locale Validation for Agentforce Agents

Derive locale-specific test cases from any agent script or genAiPluginMetadata, then run them in preview or batch mode to verify the agent responds in the correct language.

## Target locales (default set)

| Code | Language |
|------|----------|
| `ja` | Japanese |
| `fr` | French |
| `it` | Italian |
| `de` | German |
| `es` | Spanish |
| `es_MX` | Spanish (Mexico) |
| `pt_BR` | Portuguese (Brazil) |

Override with `--locales` if the user specifies a subset or adds others.

## Workflow overview

```
1. Introspect agent  →  1b. Check & patch additional_locales  →  1c. Check & patch language-response instruction  →  2. Derive utterances  →  3. Translate  →  4. Run tests  →  5. Validate & report
```

Work through these phases in order. Pause after Phase 1b if a locale patch is needed. Phase 1c is fully automatic (no confirmation). Pause after Phase 2 for utterance review.

---

## Phase 1 — Introspect the agent

Accept: a path to a `.agent` file, a `genAiPluginMetadata` directory, or just an agent name (search for it).

**Find the agent file:**
```bash
# By path
cat path/to/MyAgent.agent

# By name in force-app
find . -name "*.agent" | xargs grep -l "MyAgent" 2>/dev/null

# genAiPluginMetadata (Salesforce metadata XML)
find . -path "*/genAiPlugins/*.genAiPlugin-meta.xml" | head -5
```

**Extract from `.agent`:**
- `config.developer_name` — agent API name
- `language.default_locale` and `language.additional_locales` — extend the default locale set with any locales already declared
- Every `topic <name>` block — collect the topic name and `description`
- Every `action` inside topics — collect action name and `description`
- Any `system.instructions` welcome/greeting text — use as inspiration for entry utterances

**Extract from `genAiPluginMetadata`:**
```bash
# List topics/actions from XML
grep -E "<masterLabel>|<description>|<developerName>" path/to/plugin.genAiPlugin-meta.xml
```

Build a table of topics and actions with their descriptions — this is the source for utterance derivation.

---

## Phase 1b — Check and patch `additional_locales`

**Always run this step immediately after reading the agent file, before deriving utterances.**

### Check

Look for the `language:` block in the `.agent` file. Three possible states:

| State | Condition | Action |
|---|---|---|
| **Present and populated** | `additional_locales` exists and is non-empty | Extract the declared locales, merge with `--locales` argument, proceed to Phase 2 |
| **Present but empty** | `additional_locales: ""` or `additional_locales:` with no value | Treat as missing — go to Ask step |
| **Missing** | No `language:` block, or block exists but has no `additional_locales` line | Go to Ask step |

### Ask

When `additional_locales` is missing or empty, stop and ask the user:

> "The agent script does not declare any `additional_locales`. Which locales should I add?
>
> Default set: `ja, fr, it, de, es, es_MX, pt_BR`
>
> Reply with the full list you want (e.g. `ja fr de`) or say **"use defaults"** to add all seven."

Wait for the user's answer before proceeding.

### Patch

Once the user confirms the locale list, update the `.agent` file using the Edit tool.

**If `language:` block exists but `additional_locales` is missing or empty**, add/replace the line:

```
language:
    default_locale: "en_US"
    additional_locales: "ja,fr,de"   ← replace with user's choices, comma-separated, no spaces
```

**If no `language:` block exists at all**, insert one after the `config:` block:

```
language:
    default_locale: "en_US"
    additional_locales: "ja,fr,de"
```

**Format rules (required for Agent Script compiler):**
- `additional_locales` value is a **quoted comma-separated string** with no spaces: `"ja,fr,de"` not `"ja, fr, de"`
- Indentation is **4 spaces** (tabs break the compiler)
- `default_locale` must always be present in the `language:` block

**After patching**, show the user the diff and confirm:

> "I've added `additional_locales: \"ja,fr,de\"` to the `language:` block. Continuing to Phase 2."

Use the confirmed locale list (union of the patched `additional_locales` and any `--locales` argument) as the working locale set for the rest of the workflow.

---

## Phase 1c — Check and patch language-response instruction

**Always run this step immediately after Phase 1b, before deriving utterances.**

### Check

Search `system: instructions:` in the `.agent` file for the presence of the language-response instruction. The canonical marker to search for is:

```
Always respond in the same language the user writes in
```

Use a case-insensitive substring match. Two states:

| State | Condition | Action |
|---|---|---|
| **Present** | The marker string is found anywhere in `system.instructions` | Nothing to do — proceed to Phase 2 silently |
| **Missing** | Marker string not found | Patch the file automatically (no user confirmation needed) |

### Patch

When the instruction is missing, append it as the last bullet inside `system: instructions:`, immediately before the blank line that follows the instruction block. Match the indentation of the surrounding bullet points (4 spaces).

**Instruction to insert (exact text):**

```
    - Always respond in the same language the user writes in. If the user writes in Japanese, respond entirely in Japanese. If French, respond entirely in French. Never mix languages in a single response. Use {!@variables.EndUserLanguage} as a locale hint when available.
```

**How to locate the insertion point:**

1. Find the last `- ` bullet line inside `system: instructions:` (before `messages:` or any other top-level key)
2. Insert the new bullet immediately after that line

**After patching**, tell the user:

> "Added language-response instruction to `system.instructions` — agent will now respond in the user's language. Continuing."

### Why this matters

`additional_locales` only declares platform support. Without an explicit instruction in `system.instructions`, the LLM defaults to English regardless of the utterance language or `EndUserLanguage` session variable.

---

## Phase 2 — Derive English utterances

For each topic, generate **2–3 realistic English utterances** a real user would send. Draw from the topic and action descriptions — the utterances should be natural questions or instructions that would route to that topic.

Aim for variety: one direct command ("Book a meeting for tomorrow"), one question ("Can you help me schedule something?"), one edge-case phrasing.

Present these to the user:
> "Here are the derived test utterances I'll use. Want to add, remove, or adjust any before I proceed?"

---

## Phase 3 — Translate utterances

For each English utterance, produce a translation in each target locale. Rules (matching `EvalLocaleTestUtil` and `UtteranceTranslationUtil` conventions):

- Keep **proper nouns in English**: Salesforce object names, field names, company names, person names, API identifiers (e.g., "Opportunity", "Chatter", "Einstein Copilot")
- Preserve the **intent and tone** exactly (approval → approval, command → command)
- Do not add quotes, extra punctuation, or explanations
- For `es` vs `es_MX`: es_MX is Mexican Spanish — use natural regional phrasing where it differs

Use Claude's own translation capability for this step (no external LLM call required in adlc mode).

---

## Phase 4 — Run tests

Read the appropriate reference based on execution mode:

- **Preview / smoke testing (Mode A):** Read `references/adlc-mode.md` → section "Preview mode"
- **Batch / regression testing (Mode B):** Read `references/adlc-mode.md` → section "Batch mode"
- **einstein-copilot-fit-tests (Maven):** Read `references/fit-tests-mode.md`

The mode is inferred from context:
- User says "preview", "smoke", "quick test", or you're iterating during development → Mode A
- User says "batch", "regression", "CI", or "test suite" → Mode B
- Current working directory is `einstein-copilot-fit-tests` or user mentions Maven/JUnit → fit-tests mode

### Mode B — companion CSV (always generate alongside YAML)

**Every time you write a `testSpec.yaml` for Mode B, you must also write a companion `.csv` file at the same path with `-input.csv` replacing `-testSpec.yaml`.**

The CSV is a Testing Center UI upload template — it lets the user import the same test cases manually via the browser without running CLI commands.

**CSV format rules:**
- Header row (exactly): `utterance,expectedTopic,expectedActions,expectedOutcome`
- One row per test case, same order as the YAML
- `utterance` — the translated utterance (same value as YAML `utterance:`)
- `expectedTopic` — leave **blank** for locale test cases (runtime topic names hash-drift; outcome assertion is sufficient). Only fill if you have a confirmed stable runtime name.
- `expectedActions` — leave **blank** unless the test case explicitly asserts a specific action invocation
- `expectedOutcome` — same value as YAML `expectedOutcome:` (natural-language LLM-as-judge description)
- Wrap values containing commas or apostrophes in double quotes
- No trailing spaces or BOM

**Naming convention:**
```
tests/<AgentApiName>-locale-<locales>-testSpec.yaml   ← YAML (sf agent test create)
tests/<AgentApiName>-locale-<locales>-input.csv       ← CSV  (Testing Center UI upload)
```

**testSpec YAML — always include `locale:` per test case** so the validator can assign the correct locale without inference and preserve spec order in the report:

```yaml
testCases:
  - utterance: "WeloはどのようなITソリューションを提供していますか？"
    locale: "ja"
    expectedOutcome: "Agent responds in Japanese. ..."

  - utterance: "Quelles solutions IT Welo propose-t-elle ?"
    locale: "fr"
    expectedOutcome: "Agent responds in French. ..."
```

**Validator command — always pass `--spec`** alongside `--results` so locale assignment and row order match the spec exactly:

```bash
python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/locale-test-results.json \
  --spec tests/<AgentApiName>-locale-<locales>-testSpec.yaml \
  --locales ja fr \
  --agent-name <AgentName> \
  --output /tmp/locale-validation-report.md
```

**Example CSV output** for a ja+fr locale suite:

```csv
utterance,expectedTopic,expectedActions,expectedOutcome
WeloはどのようなITソリューションを提供していますか？,,,Agent responds in Japanese. Response describes Welo's IT solutions or data center services. Response does not contain English text.
データセンターサービスについて教えてください,,,Agent responds in Japanese. Response provides information about data center services. Response does not contain English text.
Quelles solutions IT Welo propose-t-elle ?,,,Agent responds in French. Response describes Welo's IT solutions or data center services. Response does not contain English text.
Parlez-moi de vos services pour centres de données,,,Agent responds in French. Response provides information about data center services. Response does not contain English text.
```

After writing both files, tell the user:

> "I've written two files:
> - `tests/<name>-testSpec.yaml` — deploy with `sf agent test create --spec ...`
> - `tests/<name>-input.csv` — upload manually via Testing Center UI → Import from CSV"

---

## Phase 5 — Validate and report

After collecting responses, validate each one using the language validation logic from `EvalLocaleTestUtil`.

### Option A — In-context validation (Claude)

Evaluate responses directly without the Python script. Apply these rules:

**Critical check (run first):** If the target locale is NOT `en_US` and the response is entirely in English, that is a **CRITICAL FAILURE** — report it immediately with `overall_evaluation: POOR`.

**For each response, check:**
1. Language correctness — is it actually in the target language?
2. Cultural appropriateness and business tone
3. No untranslated fragments (mixed-language responses)
4. Grammar and formatting quality (lenient — flag only obvious issues)

### Option B — Python validator script (post-batch)

When the user has a batch results JSON file, run the script for fast automated analysis:

```bash
# Heuristic only (fast, no API cost)
python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/locale-test-results.json \
  --locales ja fr it de es es_MX pt_BR \
  --agent-name <AgentName> \
  --output /tmp/locale-validation-report.md

# With LLM-as-judge (mirrors EvalLocaleTestUtil.languagePrompt)
python3 skills/locale-validation/scripts/validate_locale_responses.py \
  --results /tmp/locale-test-results.json \
  --locales ja fr it de es es_MX pt_BR \
  --agent-name <AgentName> \
  --llm-validate \
  --llm-endpoint https://api.openai.com/v1/chat/completions \
  --llm-api-key "$OPENAI_API_KEY" \
  --llm-model gpt-4o \
  --output /tmp/locale-validation-report.md
```

**Input format:** The `--results` file must be a JSON object shaped as `{"result": {"testCases": [...]}}` where each test case has fields `locale`, `botResponse` (or `response`), and optionally `testCaseName`, `utterance`, `status`, `topic`. This is a custom intermediate format — not the raw `sf agent test results --result-format json` output.

**Exit codes:** `0` = all passed; `1` = one or more critical failures (English response in non-English locale) — suitable as a CI gate.

**LLM API key resolution order:** `--llm-api-key` flag → `OPENAI_API_KEY` env var → interactive prompt at runtime.

**If no API key is available:** Run the script with `--llm-validate` directly. If `OPENAI_API_KEY` is not set, the script will prompt for it interactively:

```
OPENAI_API_KEY is not set. Enter your OpenAI API key to continue:
```

The user types the key at the prompt — it is passed directly to the script and never written to disk or shell history. Do not pre-check for the key or ask the user to `export` it first; just run the script and let it prompt.

Do not silently skip LLM validation or fall back to heuristic-only when the user explicitly requested LLM-as-judge.

### Report format (both options)

```
## Locale Validation Report — <AgentName>
Date: <date>
Locales tested: ja, fr, it, de, es, es_MX, pt_BR

| Topic | Locale | Utterance (EN) | Result | Issues |
|-------|--------|----------------|--------|--------|
| OrderTopic | ja | "Check my order" | ✅ PASS | — |
| OrderTopic | fr | "Check my order" | ❌ FAIL | Response in English |

### Summary
- Total: N tests across M topics and K locales
- Passed: X  Failed: Y
- Critical failures (English response): Z

### Failures detail
<for each failure: locale, utterance, actual response excerpt, issue>
```

---

## Quick-start examples

**Run preview locale test on a named agent:**
```
User: "Run locale validation on MySDRAgent in preview mode"
→ Find MySDRAgent.agent, derive utterances, translate, run sf agent preview per locale
```

**Generate batch test spec with locale variants:**
```
User: "Create a batch locale test suite for MyAgent"
→ Introspect agent, derive utterances, translate all locales, write test-spec-locales.yaml
```

**fit-tests integration:**
```
User: "Generate multilingual eval test data for EngagementAgent"
→ Read references/fit-tests-mode.md for utterances.json + test-case.json generation
```
