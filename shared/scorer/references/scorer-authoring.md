# Custom Scorer Authoring (mode-agnostic core)

Author, deploy, and iterate on a custom Agentforce scorer — an LLM-as-judge prompt
template that measures your own domain-specific criterion over agent sessions. This
reference is **validation-mode-agnostic**: it covers intake, prompt drafting, the YAML
spec, deploy, and the refine loop. Pair it with exactly one validation adapter:

- **Live Data Cloud sessions** → `scorer-validate-datacloud.md` (works today; used by `agentforce-observe`)
- **AI Testing Center / NGT test suite** → `scorer-validate-ngt.md` (blocked on NGT open-scorer support; used by `agentforce-test` later)

Everything rides on the vendored CLI at `shared/scorer/` (Python + a Flask companion UI).
**Do not reimplement any of it** — shell out to `python -m src.cli` and write YAML specs to
`shared/scorer/scorer_specs/`.

---

## Resolve the CLI directory and interpreter (run this first)

The CLI lives in the plugin's `shared/scorer/` tree, not inside a skill dir. Locate it and a
Python 3.10+ interpreter that has `click`, `jinja2`, `pyyaml`, `flask` importable. All CLI
commands run **from `$SCORER_DIR`** (the `parent.parent` path resolution and `python -m src.cli`
both assume cwd = that dir).

```bash
# 1. Locate the vendored CLI (plugin-dir, marketplace, or file-copy install).
SCORER_DIR="$(find "$PWD" "$HOME/.claude" "$HOME/.cursor" /Users 2>/dev/null \
  -path "*/shared/scorer/src/cli.py" -print -quit | xargs -r dirname | xargs -r dirname)"
if [ -z "$SCORER_DIR" ]; then
  echo "Could not locate shared/scorer/. Is the agentforce-adlc plugin installed?"; exit 1
fi

# 2. Resolve an interpreter with the CLI's deps (click/jinja2/yaml/flask).
PY=""
for cand in "$SCORER_DIR/.venv/bin/python" python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import click,jinja2,yaml,flask" 2>/dev/null; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  echo "No Python 3.10+ with click/jinja2/pyyaml/flask found. Install: pip install click jinja2 pyyaml flask"; exit 1
fi
echo "Scorer CLI: $SCORER_DIR (interpreter: $PY)"
```

Thereafter, invoke the CLI as: `(cd "$SCORER_DIR" && "$PY" -m src.cli <command> …)`.

---

## Behavioral rules (READ FIRST)

- **Ask each parameter as a free-text chat question, one at a time.** Wait for the reply before the next.
- **Multi-choice questions are always a vertical numbered list** (`1.` / `2.` / `3.` …). Accept either the number or the label.
- **When confirming a Claude-drafted artifact** (description, prompt body, YAML), paste it in a fenced code block and ask "Ship as-is (1) or tweak (2)?".
- **Never silently edit the prompt.** Show any change in full before saving to YAML.
- **Always pass `--json` to `score-and-fetch`** so you can build the results table.
- **Show, don't summarize, when iterating.** Display the old-vs-new diff before redeploying.
- **Keep the spec file in the repo.** Each scorer gets a permanent YAML in `$SCORER_DIR/scorer_specs/`. Don't scatter into `/tmp/`.
- **Don't commit or push the YAML** unless the user asks.
- **If a deploy or score fails**, show the `stderr` tail and ask before retrying. Common failures: `CANNOT_DELETE_ACTIVE_VERSION` (rare — the CLI handles it), `Scorer generation failed` (shown via `generationErrors`).
- **New scorers are always OpenEnded.** The authoring flow emits `data_type: OpenEnded` unconditionally; the 12 `lightning_type` subtypes cover every shape the old `Text`/`Number` types expressed, with predefined values now optional (constrained-plus-open). Legacy `data_type: Text`/`Number` YAMLs on disk still load and deploy.
- **Fallback is optional.** Ask for a fallback value only when the user supplies predefined values.
- **Name length cap: 35 characters.** Salesforce rejects `AiAgentScorerDefinition` fullNames longer than 35 chars at deploy. Abbreviate (`_with_`→`_w_`), drop redundant words, or pick a tighter name.
- **Don't say "sample" for the validation set.** "Sampling rate" is the live-traffic Observability feature. Use "number of sessions to run validations on" / "validation set" for the fixed set you score during authoring.

---

## Companion UI

A local single-page UI ships with the CLI (`python -m src.cli ui`). It renders the scorer
definition, targeted sessions (with full STDM JSON in a collapsible tree), per-session results,
and side-by-side diffs between iterations. It is **read-only** — the chat remains the source of
truth for every decision. It mirrors what's on disk; every successful `score` / `score-and-fetch`
auto-snapshots to `$SCORER_DIR/runs/<scorer>/<timestamp>-<hash>/`.

Launch it once, early (after Step 1 collects the org). Kill any stale server on 8765 first — the
UI loads `src/scorer_spec.py` at startup, so a long-lived process can reject newly-authored specs.

```bash
lsof -ti :8765 2>/dev/null | xargs -r kill 2>/dev/null
nohup "$PY" -m src.cli ui --org <org> --no-browser >/tmp/scorer-ui.log 2>&1 &
sleep 2
( cd "$SCORER_DIR" && curl -sf http://127.0.0.1:8765/healthz >/dev/null ) \
  && echo "UI up" || (echo "UI failed; tail:"; tail -20 /tmp/scorer-ui.log)
```

Run the `nohup` line **from `$SCORER_DIR`** (`cd "$SCORER_DIR" && nohup "$PY" -m src.cli ui …`).
Tell the user once: *"Companion UI at http://localhost:8765 — keep it open in a tab; it updates after each deploy/score."*

**Deep links** (paste in chat so the user can click):

- `http://localhost:8765/#scorer=<name>&tab=definition` — after writing YAML.
- `http://localhost:8765/#scorer=<name>&run=<run_id>&tab=results` — after a live-sessions run.
- `http://localhost:8765/#scorer=<name>&run=<run_id>&tab=sessions&session=<sid>` — one session's STDM.
- `http://localhost:8765/#scorer=<name>&compare=<run_a>,<run_b>&tab=compare` — the diff view.

Read `run_id` values from `ls -t "$SCORER_DIR/runs/<scorer>/" | head -n 1` (newest first).

---

## Step 1 — Intake: org, agent, model

**1a. Org alias.** Run `sf org list --skip-connection-status --json`, parse
`nonScratchOrgs`/`scratchOrgs`/`sandboxes`/`devHubs`/`other`, print distinct aliases as a numbered
list. The default is the **last alias in the printed list**. Ask "Which org? (default: `<last>`)".
Then launch the companion UI (above).

**1b. Agent.** Run `(cd "$SCORER_DIR" && "$PY" -m src.cli agents --org <org> --json)`, print the
agents as a numbered list, ask "Which agent does this scorer bind to?". Save the chosen
`agent_api_name` — used for the scorer's `agentAssociation` at deploy and for narrowing the
validation set.

**1c. Model.** Run `(cd "$SCORER_DIR" && "$PY" -m src.cli models)`, paste the table in a fenced
block, ask "Which model? (friendly name or identifier)". Match a friendly name to a catalog
`label`→`identifier`, or accept an exact `sfdc_ai__…` identifier verbatim. Save as `primary_model`.

Semantic type is **not** asked — it's auto-derived from the output shape in Step 2b (numeric → Measurement, else Dimension).

## Step 2 — Describe or paste the prompt

**2a. Unified intake.** Ask: *"Describe the scorer in a sentence or two, or paste a full prompt. (Or type `adapt` to start from a bundled scorer.)"* Then branch:

- Reply is exactly `adapt` → **Adapt subflow** (2e).
- Reply contains `{!$Input:Session}` **OR** is >800 chars with two-plus blank-line-separated paragraphs → **Paste branch** (2f). Skip 2b/2c/2d.
- Otherwise → **Describe branch**. Save the reply as `description`. Continue to 2b.

**2b. Output shape (Describe only).** Ask:
```
What shape should the output be?
1. text (default) — a summary, an answer, a label, or any free-form string
2. integer — whole numbers only
3. number — any decimal
4. boolean — true / false
5. date — YYYY-MM-DD
6. URL
```
Map to `lightning_type`: text→`lightning__multilineTextType`, integer→`lightning__integerType`,
number→`lightning__numberType`, boolean→`lightning__booleanType`, date→`lightning__dateType`,
URL→`lightning__urlType`. Accept a verbatim rarer subtype (`lightning__richTextType`,
`lightning__textType`, `lightning__dateTimeType`, `lightning__dateTimeStringType`,
`lightning__objectType`, `lightning__listType`). Then **auto-derive `semantic_type`** and print
one line: `Semantic type: {Dimension|Measurement} — say so if you want the other one instead.`
(integer/number → Measurement; everything else → Dimension).

**2c. Predefined values (Describe only).** Gate → propose.
- **2c.i Gate:** *"Do you want to define predefined values (a constrained-plus-open vocabulary that nudges the LLM toward known labels)? 1. Yes  2. No (fully open) (default)"*. If No, skip 2c.ii and 2d; don't set `values`/`fallback_value`.
- **2c.ii Propose:** draft **two distinct** rubrics (3–5 values each, one-line meaning per value; make them meaningfully differ — e.g. coarse vs. fine), plus option 3 "Provide your own". Save the chosen set as `values`.

**2d. Fallback (only if `values` set).** Gate → propose.
- **2d.i Gate:** *"Do you want to define a fallback value (used when the LLM can't decide)? 1. Yes  2. No (default)"*.
- **2d.ii Propose two:** Candidate 1 = a neutral/partial label **from** `values`; Candidate 2 = a **synthetic escape label outside** `values` (e.g. `NA`, `Uncertain`, `NOT_SET`) that the scorer XML materializes as its own `<outputEnumValue>` with `<isFallback>true</isFallback>`. Plus option 3 "Something else". Save as `fallback_value` (need not be in `values`).

**2e. Adapt subflow.** List the bundled OpenEnded specs — `scorer_specs/session_summary.yaml`
(multilineTextType), `scorer_specs/intent_sentiment.yaml` (numberType + Measurement),
`scorer_specs/session_deflected.yaml` (booleanType). Ask which to start from, paste its contents in
a ` ```yaml ` block, ask "What would you like to change?", apply edits. Skip 2b/2c/2d.

**2f. Paste branch.** Take the pasted prompt as-is. Ensure it contains
`{!$SalesforceDataAction:getSession.chatTranscript}` (or `{!$Input:Session}` if the user included
it); if neither is present, append a closing block referencing `getSession.chatTranscript`. Ask the
output shape (2b) to set `lightning_type`. Don't ask about predefined values. Skip Step 3; go to Step 4.

## Step 3 — Draft prompt (Describe branch only)

Draft an OpenEnded prompt from the description + `lightning_type` + any `values`. The prompt MUST
reference the session — **default to `{!$SalesforceDataAction:getSession.chatTranscript}`** (the Data
Action reference makes the platform's auto-sampling pipeline work). Use raw `{!$Input:Session}` only
if the user explicitly wants the full nested STDM payload.

**Free-form (no values):**
```
{{One-line evaluation instruction derived from the description.}}

Session:
{!$SalesforceDataAction:getSession.chatTranscript}

Return only the {{shape-noun}} — no preamble, no explanation.
```
`{{shape-noun}}`: "summary text" (multiline/richText), "integer", "number", "true or false", "date in YYYY-MM-DD", "URL".

**Constrained-plus-open (values set, no fallback):**
```
{{One-line evaluation instruction derived from the description.}}

Suggested values: {!$Input:AllowedLabels}
- {{value_1}}: {{one-line meaning}}
- {{value_2}}: {{one-line meaning}}

You may also return any other short value if none of the above fits.

Session:
{!$SalesforceDataAction:getSession.chatTranscript}

Return only the value, then on a new line provide a brief reason.
```

**Constrained-plus-open (values + fallback):** same, but insert before the Session block:
```
If the transcript is ambiguous, incomplete, or you genuinely cannot judge, fall back to: {!$Input:FallbackLabel}
Otherwise you may also return any other short value if none of the above fits.
```

**Drafter rule:** if `fallback_value` is set, the drafted prompt MUST contain the literal
`{!$Input:FallbackLabel}` — otherwise the runtime supplies the fallback token but the LLM never sees
it. When a 2c.ii proposal is picked, inline the per-value one-line meanings into the "Suggested
values" block. Paste the draft in a fenced block, ask "Ship as-is (1) or tweak (2)?", loop until accepted.

## Step 4 — Scorer name

Propose a snake_case name that renders the evaluation target and stays under 35 chars. Ask
*"Scorer name? (snake_case, max 35 chars; I suggest: `<name>`)"*. If the user types a too-long name, regenerate a shorter proposal.

## Step 5 — Write the YAML spec

Write to `$SCORER_DIR/scorer_specs/<name>.yaml`:

```yaml
name: {{name}}
description: "{{description}}"
data_type: OpenEnded
lightning_type: {{lightning_type}}
semantic_type: {{semantic_type}}   # optional; omit for platform default
primary_model: {{primary_model}}
# values / fallback_value only if supplied in 2c/2d:
values:
  - {{value1}}
  - {{value2}}
fallback_value: {{fallback_value}}
prompt: |
  {{prompt body, indented 2 spaces per line}}
```

`scorer_type` is derived from `data_type` — don't set it. After writing, tell the user the YAML is
the source of truth (re-rendered into XML on every deploy), rendered XMLs land at
`scorer_specs/rendered/{name}/` after deploy, and drop the Definition-tab deep link.

## Step 6 — Deployment config (validation mode)

Org and agent are known from Step 1 — don't re-ask. Ask:
```
Validation mode?
1. Last N live sessions
2. AI Testing Center test suite
```
Then hand off to the matching adapter reference:
- **Live sessions** → follow `scorer-validate-datacloud.md`.
- **Testing Center** → follow `scorer-validate-ngt.md`. **Caveat:** OpenEnded scorers (the default
  for new authoring) are not yet supported by the Testing Center server-side and FAIL there. If the
  user picks Testing Center for a fresh OpenEnded YAML, **silently steer to Live sessions**. Testing
  Center remains available for legacy Text/Number YAMLs.

Also ask: *"Activate live-traffic sampling? 1. Yes (default) — isActive=true, samples real traffic at samplingRate=1.0 from deploy.  2. No — deploy inactive; flip on later from Setup."*

## Step 9 — Iterate

After presenting results (see the adapter), ask:
```
Satisfied with the result, or another round?
1. Accept — end the loop; confirm the active template is final.
2. Tweak — collect specific changes, rewrite the prompt in the YAML, redeploy, revalidate on the SAME validation set (fair comparison), show the new table side-by-side with the previous one.
3. Change validation set — different --last N / --agent (live), or edit utterances/expected (test suite).
4. Change labels — rare; requires rewriting the YAML.
```
Loop until Accept. After the second (or later) iteration, drop the compare/deep link from the adapter.

## Step 10 — Final summary

> "Template `{{name}}` is deployed and active in `{{org}}`, judged by `{{primary_model}}`. Scorer
> definition is deployed, bound to `{{agent}}`, isActive=`{{true|false}}`, samplingRate=`{{rate}}`.
> Visible in Agentforce Studio → Scorers. Older template versions remain inactive; Salesforce serves
> only the active one."

---

## Provenance

Distilled from the standalone `scorer-create` skill (original SKILL.md preserved verbatim at
`shared/scorer/.claude/skills/scorer-create/ORIGINAL-SKILL.reference.md`). The CLI implementation is
documented in `shared/scorer/docs/implementation.md` and `shared/scorer/README.md`.
