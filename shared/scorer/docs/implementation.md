# Implementation — How Each Step Works

This document explains how the `score-and-fetch` command is implemented under the hood, with file/line pointers.

```bash
# One command does everything:
scorer-cli score-and-fetch --org yuval-org1 --scorer ./my_fresh_scorer.yaml --last 3
```

Under the hood:

1. Fetches last 3 sessions via Data Cloud SQL.
2. Auto-deploys the scorer's prompt template if not present (3-step deploy-retrieve-activate).
3. Builds canonical STDM JSON for each session from 3 parallel Data Cloud queries + Python port of Core's `StdmBuilder`.
4. Invokes the scorer via `POST /einstein/prompt-templates/{name}/generations` Connect API.
5. Prints a concise label + reason per session.

---

## Step 1 — Fetch last 3 sessions via Data Cloud SQL

**Entry:** `src/cli.py` → `score_and_fetch()` command calls `session_stdm.list_sessions(org, agent_api_name=agent, limit=last)`.

**Orchestration:** `src/session_stdm.py:list_sessions()`

- Resolves the 18-char org id via `sf org display -o <alias> --json` (`discover_org_id()`).
- Builds a single SOQL string via `datacloud_query.build_session_list_sql(org_id, limit=3)` — a straightforward:
  ```sql
  SELECT sessionId, sessionStartTimestamp, sessionChannel
  FROM ssot__AiAgentSession__dlm
  WHERE ssot__ExternalSourceId__c = '<org>'
  ORDER BY sessionStartTimestamp DESC
  LIMIT 3
  ```
- Calls `datacloud_query.run_sql()`, which shells out to:
  ```
  sf api request rest /services/data/v62.0/ssot/query --method POST --body '{"sql":"..."}'
  ```

**Under the shell-out:** `src/sf_apex.py:api_request()`

- Writes the JSON body to a temp file (workaround: `sf api request rest --body` only accepts `@filepath` for JSON).
- Captures stdout; strips the warning banner; parses the response JSON.

**Response normalization:** `src/datacloud_query.py:_normalize_rows()`

- Data Cloud's `/ssot/query` returns:
  ```json
  {
    "data": [{"sessionId": "...", "sessionChannel": "..."}],
    "metadata": {},
    "rowCount": 3
  }
  ```
- `data` is already a list of column-name-keyed dicts — no reshaping needed. We just pass through.

**Result:** a list of `{"session_id", "start_time", "channel"}` dicts printed as a numbered table.

---

## Step 2 — Auto-deploy the scorer's prompt template if not present

**Entry:** `src/cli.py:score()` calls `scorer_deployer.ensure_prompt_template_deployed(org, spec)` before anything else.

**Existence check:** `src/scorer_deployer.py:template_exists()`

- `sf org list metadata --metadata-type GenAiPromptTemplate -o <org> --json`
- Scans returned names for the scorer's `developerName`.

`GenAiPromptTemplate` isn't SOQL-queryable (even via Tooling API returns `INVALID_TYPE`), so metadata listing is the reliable check.

**If missing — 3-step deploy** (`deploy_prompt_template()`):

### 1. Deploy (inactive)
- Render the scorer XML from YAML via Jinja (`xml_render.render()` using `templates/genAiPromptTemplate.xml.j2`) — omit `<activeVersionIdentifier>`.
- Write to a tempdir with a stub `sfdx-project.json`.
- `sf project deploy start --source-dir <path> -o <org>`
- Salesforce stores version `_1` but leaves the template inactive.

### 2. Retrieve
- `sf project retrieve start --source-dir <same path>`
- The retrieved XML now has `<versionIdentifier>xxx=_1</versionIdentifier>` filled in.

### 3. Activate
- `_inject_active_version()` edits the **retrieved** XML in place (critically, **not** a fresh Jinja render — whitespace differences make Salesforce treat it as a new version and trigger `CANNOT_DELETE_ACTIVE_VERSION`).
- Adds `<activeVersionIdentifier>` as a sibling of `<developerName>`, then redeploys.
- Now the template is active and invocable.

After all three steps succeed, the tempdir is deleted; on failure, kept for debugging (path printed).

**Fast path:** if `template_exists()` returns true, skip all of the above. Prints "Template is active; skipping deploy."

---

## Step 3 — Build canonical STDM JSON per session

**Orchestration:** `src/session_stdm.py:fetch_session_stdm()` runs three queries in parallel via `concurrent.futures.ThreadPoolExecutor(max_workers=3)`:

| Query (ports Core verbatim) | SQL builder | Result |
|---|---|---|
| Messages per interaction, LEFT JOINed to session | `build_message_sql()` | rows with `sessionId`, `interactionId`, `topicApiName`, `messageType`, `contentText`, `sessionParticipantId`, etc. |
| Tool action steps (ACTION_STEP + TURN only) | `build_step_sql()` | rows with `stepId`, `stepName`, `stepInput`, `stepOutput`, timestamps |
| Session state + participant/actor rows | `build_participant_sql()` | rows with `sessionChannel`, `participantId`, `participantObject`, `participantRole`, `aiAgentApiName`, etc. |

All three are direct ports of `core/agentforce-session-tracing-impl/java/src/.../{Message,Step,SessionParticipant}QueryBuilder.java` with `ssot__` prefix / `__c` / `__dlm` suffixes hardcoded for the default dataspace.

**Assembly:** `src/stdm_builder.py:assemble_stdm_detail_views()` — line-by-line Python port of Core's `StdmBuilder.assembleStdmDetailViews()`:

### 1. Validate + group
Groups all three row sets by `sessionId` using `group_rows_by_field()` (port of `EventProcessingUtils.groupRowsByField`).

### 2. Per session, assemble

- **`_build_session_state()`** — extracts `sessionId/startTimestamp/channel/...` from the first participant row (all rows for a session share these).
- **`_build_actors()` + `_build_actor()`** — iterates participant rows; drops any with null `sessionParticipantId`. For required `participantObject` that comes back null in DMOs, we infer from role (`USER` → `"User"`, `AGENT` → `"GenAiPlannerDefinition"`) — this was the last bug we hit on the WhatsApp sessions.
- **`_build_runs()`** — groups messages by `interactionId`, groups steps by `interactionId`, builds one `StdmRun` per interaction. Each message is linked to its actor via `sessionParticipantId → actor.id`.
- **`_build_metrics()`** — `durationMs` computed as session_start → latest_run_end, `turns` = count of TURN interactions.
- **Filter:** non-TURN runs are emitted in metrics but excluded from the output `runs[]` (matches Core's rule).
- **Deduplicate:** actors by `participantId`, keeping first occurrence.

### 3. Serialize
- `_non_null()` strips null fields (mirrors Jackson's `@JsonInclude(NON_NULL)`).
- Internal `_sessionParticipantId` and `_interactionType` fields are stripped (mirror `@JsonIgnore`).

### 4. Timestamps
- `_iso()` formats as `YYYY-MM-DDTHH:MM:SS.sss+0000` — matching Core's test fixture format.
- The `.sss+0000` suffix is important; Salesforce's validator rejected the plain `.sss` form.

**Output:** a canonical `SessionView` dict matching the schema at:
```
core/agentforce-session-tracing-impl/java/resources/experience/types/bundles/
  propertyType/agentforce_session_tracing/stdmDetailViewType/schema.json
```

Verified against Core's own `StdmBuilderTest.java` fixtures (16 parity tests).

---

## Step 4 — Invoke via Connect API prompt-template generations

**Entry:** `src/cli.py:score()` calls `prompt_template.run_scorer(org, spec, session_view)` for each fetched session.

**Request build:** `src/prompt_template.py:run_scorer()` constructs:

```python
body = {
    "isPreview": False,
    "inputParams": {
        "valueMap": {
            "Input:Session":       {"value": <STDM dict>},            # canonical schema
            "Input:AllowedLabels": {"value": "Label1,Label2,..."},    # from spec
            "Input:FallbackLabel": {"value": "Fallback"},             # from spec
        }
    },
    "additionalConfig": {"applicationName": "PromptTemplateGenerationsInvocable"},
}
```

POSTed to `/services/data/v64.0/einstein/prompt-templates/{scorer_name}/generations` via `sf_apex.api_request`.

Note the wire shape: each input is wrapped in `{"value": X}`, and the `Input:Session` value is a **nested JSON object** (not a stringified string). This is the Connect API's `Einstein Prompt Template Generations` resource.

> **⚠ Wrong endpoint trap:** `/services/data/vXX.0/actions/custom/generatePromptResponse/{name}` rejects `stdmDetailViewType` inputs with a misleading `$.sessionState missing` error. The Connect API endpoint (`/einstein/prompt-templates/...`) is the correct one.

Server hydrates the prompt (substitutes `{!$Input:Session}`, etc. into the template body), calls the LLM (GPT-4o-mini per the scorer spec), returns:

```json
{
  "generations": [{
    "text": "{\"output\":[\"Excellent\"],\"explanation\":\"...\"}",
    "structuredResponse": {"output": ["Excellent"], "explanation": "..."}
  }],
  "prompt": "<the hydrated prompt text sent to LLM>"
}
```

---

## Step 5 — Print concise label + reason per session

**Response parsing:** `prompt_template._extract_response_text()`

- Checks for `generationErrors[]` — raises if present (before this fix, errors were being swallowed as `(unparseable)` output).
- Reads `generations[0].text` preferentially; falls back to `structuredResponse.output[0]` + `structuredResponse.explanation` if `text` is empty.

**Label matching:** `_split_label_reason()`

- If the text starts with `{`, tries JSON-decoding; reads `output[0]` for the label, `explanation` for the reason. Matches the label case-insensitively against the allowed set.
- Falls back to plain-text: first line = label, rest = reason.

**Output:** `cli._print_scoring_results()` iterates results and prints:

```
Scorer:  <name>
Sessions scored: <N>
────────────────────────────────────────
  <session-id>
     label:  <Label>
     reason: <one-sentence reason>
  ...
```

---

## How the 5 steps flow together

```
cli.score_and_fetch()
  │
  ├─► session_stdm.list_sessions()                           [STEP 1]
  │     └─► datacloud_query.run_sql(build_session_list_sql())
  │
  └─► cli.score() for each session id:
        ├─► scorer_deployer.ensure_prompt_template_deployed() [STEP 2]
        │     ├─► template_exists (sf org list metadata)
        │     └─► if missing: render XML → deploy → retrieve → activate
        │
        ├─► session_stdm.fetch_session_stdm()                [STEP 3]
        │     ├─► 3 × datacloud_query.run_sql() in parallel
        │     └─► stdm_builder.assemble_stdm_detail_views()
        │           ├─► _build_session_state / _build_actors / _build_runs
        │           └─► _build_metrics / _non_null serialize
        │
        ├─► prompt_template.run_scorer()                     [STEP 4]
        │     ├─► build body with inputParams.valueMap shape
        │     └─► POST /einstein/prompt-templates/<name>/generations
        │
        └─► _print_scoring_results()                         [STEP 5]
              ├─► _extract_response_text (raises on generationErrors)
              └─► _split_label_reason (JSON or plain-text forms)
```

---

## Files touched per step

| Step | Files |
|---|---|
| 1 — List sessions | `cli.py`, `session_stdm.py`, `datacloud_query.py`, `sf_apex.py` |
| 2 — Auto-deploy | `cli.py`, `scorer_deployer.py`, `scorer_spec.py`, `xml_render.py`, `templates/genAiPromptTemplate.xml.j2`, `sf_apex.py` |
| 3 — Build STDM | `session_stdm.py`, `datacloud_query.py`, `stdm_builder.py`, `sf_apex.py` |
| 4 — Invoke scorer | `cli.py`, `prompt_template.py`, `sf_apex.py` |
| 5 — Print results | `cli.py`, `prompt_template.py` |

---

## Key gotchas documented during the spike

1. **`GenAiPromptTemplate` isn't SOQL-queryable.** Use `sf org list metadata` for existence checks.
2. **Re-rendering XML breaks activation.** Step 3 of deploy must edit the retrieved XML in place — a fresh Jinja render produces byte-different output and trips `CANNOT_DELETE_ACTIVE_VERSION`.
3. **Wrong endpoint rejects `stdmDetailViewType` inputs.** Use `/einstein/prompt-templates/{name}/generations` (Connect API), NOT `/actions/custom/generatePromptResponse/{name}` (invocable action).
4. **Timestamp format matters.** `YYYY-MM-DDTHH:MM:SS.sss+0000` — with both milliseconds AND `+0000` suffix. Other formats fail schema validation.
5. **Null `participantObject` in DMOs is common.** Infer from role (USER→"User", AGENT→"GenAiPlannerDefinition") to satisfy STDM schema's required-field check.
6. **`NOT_SET` sentinel is everywhere.** `get_field_as_string()` converts it to `None`, mirroring Core's `EventProcessingUtils.getFieldAsString`.
