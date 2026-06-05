# Data Library Reference (ADL)

How to provision an Agentforce Data Library (ADL) and wire it into an Agent Script `.agent` file so the agent can answer questions grounded on uploaded documents, Knowledge articles, or a custom retriever.

This reference is consumed by the **Create an Agent** and **Modify an Existing Agent** workflows in `SKILL.md`. The parent skill decides *whether* to provision an ADL (by asking the user); this file owns *how*.

## What this reference covers

- **Step 0** — Verify Data Cloud is provisioned. ADL has a hard dependency on Data Cloud.
- **Part A: SFDRIVE (File Library)** — Steps 1–7: Create library, upload file via presigned S3 URL, trigger indexing, poll until ready. Step 8: Day-2 add more files.
- **Part B: KNOWLEDGE (Knowledge Article Library)** — Create library with knowledgeConfig, trigger indexing, poll until ready. Day-2: update config fields.
- **Part C: RETRIEVER (Custom Retriever Library)** — Create library with active retrieverId, immediately ready.
- **Wiring the ADL into Agent Script** — the `knowledge:` block + `AnswerQuestionsWithKnowledge` action (same for all source types).

## Source type decision guide

Ask the user which grounding source they want:

| Source Type | Use When | Provisioning |
|-------------|----------|-------------|
| **SFDRIVE** | User has PDF/TXT/HTML docs to upload | Upload → Index → READY (2-10 min) |
| **KNOWLEDGE** | Org has Salesforce Knowledge articles | Create → Auto-index from KAV → READY (2-10 min) |
| **RETRIEVER** | User has an existing active Custom Retriever | Create → Immediately READY (no provisioning) |

If the user says "knowledge base" or "FAQ articles" → KNOWLEDGE. If they say "upload files" or "documents" → SFDRIVE. If they say "I have a retriever" or "custom search" → RETRIEVER.

## Outputs the parent skill consumes

After Step 7 succeeds, hand the parent skill these values:
- `libraryId` — the raw library ID returned by the create call.
- `retrieverId` — populated once indexing completes.
- `rag_feature_config_id` — derived as `"ARFPC_" + libraryId`. This is the value that goes into the `.agent` file's `knowledge:` block. It is **not** the raw libraryId.

## Prerequisites

`sf` (Salesforce CLI) must be on PATH. STOP if missing — do not proceed.

```bash
command -v sf >/dev/null 2>&1 || echo "MISSING: sf (Salesforce CLI)"
```

If `sf` is missing, do NOT auto-install. Offer:
- Homebrew (recommended on macOS): `brew install --cask sf`
- npm (Node 20+): `npm install -g @salesforce/cli`
- `.pkg` installer: https://developer.salesforce.com/docs/atlas.en-us.sfdx_setup.meta/sfdx_setup/sfdx_setup_install_cli.htm

Minimum version: `@salesforce/cli 2.138.6` (includes ADL commands). Check with `sf --version`.

Confirm the target org is authenticated:

```bash
sf org display --target-org <org-alias> --json
```

If auth is missing: `sf org login web --alias <alias> --instance-url https://<your-org>.my.salesforce.com`. Do not guess the alias — ask if unspecified.

Set the target-org alias as a shell variable now — every command from Step 0 onward references it:

```bash
TARGET_ORG="<org-alias>"
```

Substitute the user's real alias before continuing.

## Step 0 — Verify Data Cloud is provisioned and ADL is reachable

ADL requires both (a) Data Cloud provisioning to be complete and (b) the ADL service routes to be healthy. The two are independent in practice — orgs can have DC provisioned but a broken ADL service. Run both checks; do not collapse them.

### 0a. DC provisioning check — `DataKnowledgeSpace`

```bash
sf data query --target-org "$TARGET_ORG" --json -q "SELECT COUNT() FROM DataKnowledgeSpace"
```

- Returns without error (any `totalSize`, including 0) → ✅ Data Cloud is provisioned. Continue to 0b.
- `INVALID_TYPE` error → ❌ Data Cloud is NOT provisioned. Skip 0b and **STOP** with the A/B prompt below.

> **Why `DataKnowledgeSpace` and not `DataStream__dlm`:** `DataKnowledgeSpace` is the exact object the ADL pipeline depends on, and is queryable as soon as DC provisioning completes. `DataStream__dlm` only materializes after a user creates a data stream — querying it yields `INVALID_TYPE` even on fully-provisioned orgs that have never run a stream, so it produces a false-negative on healthy DC orgs. (Pattern adopted from `codey-cko2/.claude/skills/setting-up-help-agent/SKILL.md`.)

### 0b. ADL service health check — `sf agent adl list`

DC is provisioned. Confirm the ADL service itself is reachable on this org:

```bash
sf agent adl list --target-org "$TARGET_ORG" --json
```

- **`status: 0`** (success) → ✅ ADL service is healthy. The response includes `result.libraries[]` — useful for reuse if a matching `developerName` is already provisioned. Continue to Step 1.
- **Error with `"This feature is not currently enabled"`** → ⚠️ ADL not enabled on this org. Show the A/B prompt below.
- **Error with `"INTERNAL_ERROR"`** → ⚠️ DC is provisioned but the ADL service is unhealthy. Tell the user:

  ```
  ⚠️ Data Cloud is provisioned, but the Agentforce Data Library service is
     returning an internal error on this org. ADL provisioning will fail
     until the service recovers. Options:

     A. Skip knowledge grounding for this run — author the agent without an ADL.
     B. Try a different org where ADL is healthy.
     C. Open a support case if this org should have ADL working.
  ```

  Default to option A — author without a `knowledge:` block — unless the user picks B or C.
- **Auth error** → Re-authenticate: `sf org login web --alias "$TARGET_ORG"` and retry.

### A/B prompt — DC not provisioned

  ```
  ⚠️ Data Cloud is not provisioned in this org.

  An ADL requires Data Cloud, which provisions asynchronously (~30 min – 2 hr).
  Choose one:

  A. Trigger Data Cloud provisioning now — I'll deploy CustomerDataPlatformSettings
     and have you click "Get Started" on the Setup page. Provisioning runs in the
     background. We'll skip ADL on this pass and you can re-run /developing-agentforce
     to add grounding once it's live.
  B. Skip knowledge grounding — the agent will be authored without an ADL. You can
     add it later by re-running this workflow.
  ```

  - **If A — trigger DC and exit the ADL flow on this pass:**
    1. Create `force-app/main/default/settings/CustomerDataPlatform.settings-meta.xml`:
       ```xml
       <?xml version="1.0" encoding="UTF-8"?>
       <CustomerDataPlatformSettings xmlns="http://soap.sforce.com/2006/04/metadata">
           <enableCustomerDataPlatform>true</enableCustomerDataPlatform>
       </CustomerDataPlatformSettings>
       ```
    2. Deploy: `sf project deploy start --json --async --source-dir force-app/main/default/settings/CustomerDataPlatform.settings-meta.xml`
    3. Wait ~60s, re-run the `DataKnowledgeSpace` query from 0a. If it succeeds, re-run 0b. If both pass, continue to Step 1.
    4. Still `INVALID_TYPE` after ~2 min → open `sf org open --target-org "$TARGET_ORG" --path "/lightning/setup/CDPSetupHome/home"` and instruct the user:

       ```
       👤 I've opened the Data Cloud setup page. Click the "Get Started" button.
          Provisioning runs async (~30 min – 2 hr). When it's live, re-run
          /developing-agentforce to add knowledge grounding.
       ```
    5. **Exit the ADL flow.** Tell the parent skill to author the agent without a `knowledge:` block on this pass.

  - **If B — skip ADL:** Tell the parent skill the user opted out. Author the agent without a `knowledge:` block.

**Visual cross-check:** If you're uncertain about the verdict from 0a/0b, open `/lightning/setup/CDPSetupHome/home`. If the page reads *"Your Data Cloud instance is live and connected"*, DC is provisioned regardless of what the SOQL says. The page state is the ground truth the user sees in Setup.

## Variables

Resolve these once after Step 0 passes (`TARGET_ORG` was already set in Prerequisites):

```bash
FILE_NAME="<absolute-path-to-file>"       # e.g. ~/docs/product-manual.pdf
ADL_DevName="<snake_case_unique>"         # e.g. MyLib_0424_ab3
ADL_Name="<human readable label>"         # e.g. "Product Documentation"
```

All `sf agent adl` commands use `--target-org "$TARGET_ORG"` for authentication — no manual token management needed. If the session expires, re-authenticate with `sf org login web --alias "$TARGET_ORG"`.

Confirm the file to upload exists and is a supported type (PDF, TXT, HTML). Max file size: 100 MB.

**Important:** Read the file content before proceeding. Use the Read tool on the PDF to understand what it contains. Do NOT ask the user "what's in the file?" — inspect it yourself. The content determines:
- Agent description and instructions
- Test queries for preview validation
- Whether the file is suitable for grounding (empty or corrupt files will fail)

## Step 1 — Create the SFDRIVE library

```bash
sf agent adl create \
  --target-org "$TARGET_ORG" \
  --name "$ADL_Name" \
  --developer-name "$ADL_DevName" \
  --source-type sfdrive \
  --json
```

Read the JSON response and capture `result.libraryId`:

```bash
LIBRARY_ID="<paste result.libraryId from the response>"
```

## Step 2 — Upload file(s) and wait for READY

The `upload` command handles the entire flow: readiness check, presigned URL, S3 upload, indexing trigger, and polling.

For a single file:

```bash
sf agent adl upload \
  -i "$LIBRARY_ID" \
  --target-org "$TARGET_ORG" \
  --file "$FILE_NAME" \
  --wait 10 \
  --json
```

For multiple files (batch):

```bash
sf agent adl upload \
  -i "$LIBRARY_ID" \
  --target-org "$TARGET_ORG" \
  --file "$FILE_NAME_1" \
  --file "$FILE_NAME_2" \
  --wait 10 \
  --json
```

The `--wait 10` flag polls until the library reaches READY (up to 10 minutes). When it returns:

```json
{
  "status": "READY",
  "libraryId": "1JD...",
  "retrieverId": "1Cx...",
  "ragFeatureConfigId": "ARFPC_1JD..."
}
```

- `retrieverId` non-null → library is ready for grounding.
- `ragFeatureConfigId` — this is the value for the `.agent` file's `knowledge:` block.

If you omit `--wait`, the command returns immediately with `status: IN_PROGRESS`. Use `sf agent adl status` or `sf agent adl get` to check readiness later.

### Checking status manually

```bash
sf agent adl status -i "$LIBRARY_ID" --target-org "$TARGET_ORG"
```

Shows stage progression: `DATA_LAKE_OBJECT → DATA_MODEL_OBJECT → SEARCH_INDEX → INDEXING → RETRIEVER`

### Confirming readiness

```bash
sf agent adl get -i "$LIBRARY_ID" --target-org "$TARGET_ORG" --json
```

Check `result.retrieverId` — non-null means ready. The top-level `status` may lag behind; trust `retrieverId`.

At this point the parent skill receives:
- `libraryId` — from Step 1
- `retrieverId` — from Step 2 response
- `rag_feature_config_id` — from Step 2 response (or computed as `"ARFPC_" + libraryId`)

## Step 3 — (Optional) Add more files to an existing library

For day-2 incremental additions to an already-provisioned SFDRIVE library:

```bash
sf agent adl file add \
  -i "$LIBRARY_ID" \
  --path "$NEW_FILE_1" \
  --path "$NEW_FILE_2" \
  --target-org "$TARGET_ORG" \
  --json
```

Constraints:
- Library must already be READY (Day-0 provisioning complete).
- At least one file required per invocation.
- No duplicate file names in a batch.
- Total file count in the library must stay ≤ 1000.
- Only works on SFDRIVE libraries.

### List files in the library

```bash
sf agent adl file list -i "$LIBRARY_ID" --target-org "$TARGET_ORG"
```

### Delete a file

```bash
sf agent adl file delete -i "$LIBRARY_ID" --file-id "<fileId>" --target-org "$TARGET_ORG"
```

## Wiring the ADL into Agent Script

An indexed ADL does nothing until the `.agent` file declares the `knowledge:` block and at least one subagent invokes `AnswerQuestionsWithKnowledge`. This section gives the exact snippets — copy them verbatim, substituting `<libraryId>` with the value from Step 1.

### 1. Top-level `knowledge:` block

Place between `connection:` (if present) and `language:` per the block ordering in [Core Language](agent-script-core-language.md), Section 2:

```agentscript
knowledge:
    rag_feature_config_id: "ARFPC_<libraryId>"   # e.g. ARFPC_1JDg7000001hilBGAQ
    citations_enabled: True                       # True to render inline citations
    citations_url: ""                             # optional base URL prepended to citations
```

- `rag_feature_config_id` is **not** the raw `libraryId`. It is `ARFPC_` + `libraryId`.
- `citations_enabled: True` turns on inline citation rendering in the agent's response.
- `citations_url` is usually empty. Set it when citations should resolve to a public URL with a known prefix.
- Without the top-level `knowledge:` block, the `@knowledge.*` references inside the action's input defaults fail compilation.

### 2. Subagent that invokes the action

Inside whichever subagent should answer grounded questions — typically a `general_faq` subagent — declare the action invocation in the `actions:` block under `reasoning:`. **The first instruction must force the action to be called** — without this, the planner may skip the action and go directly to the refusal message:

```agentscript
subagent general_faq:
    description: "Answer customer questions by searching knowledge."

    reasoning:
        instructions: ->
            | ALWAYS call AnswerQuestionsWithKnowledge FIRST for every user question.
              Never respond without calling the action.
            | After the action returns: if @outputs.AnswerQuestionsWithKnowledge.knowledgeSummary
              is empty or None, respond verbatim: "I don't have information about that in our
              knowledge base. Please contact support for help." Do NOT compose an answer from
              prior knowledge.
            | If knowledgeSummary has content, answer ONLY using that content.
            | If the question is too vague, ask for clarification.
            | Always include sources in your response when available.
            | Do not use [text](url) syntax unless the URL is verbatim in the source.

        actions:
            AnswerQuestionsWithKnowledge: @actions.AnswerQuestionsWithKnowledge
                with query = ...
                with citationsUrl = ...
                with ragFeatureConfigId = ...
                with citationsEnabled = ...
```

**Why "ALWAYS call first" must be the first line:** Without it, the planner sees "if knowledgeSummary is empty → refuse" and short-circuits — it never calls the action because it interprets the empty check as a pre-condition rather than a post-condition. The explicit "call first" directive forces action execution before any response logic.

The four `with` lines bind the action's inputs. The trailing `...` tells the planner to fill them — `query` from the user's utterance, the other three from the top-level `knowledge:` block via the action definition's defaults.

#### Anti-hallucination guard

When retrieval misses (the user asks about something not in the corpus, or the library is still warming up), `knowledgeSummary` comes back empty. Without an explicit refuse-rule, the LLM falls back to its training data and produces plausibly-wrong answers.

The instruction ordering is critical:
1. **First line:** "ALWAYS call the action FIRST" — forces action execution
2. **Second line:** "After the action returns, if empty → refuse" — the post-condition check

Without the "call first" directive, the planner may skip the action entirely and go straight to the refusal (observed in testing — the planner interprets "if empty → refuse" as a reason to not call the action at all).

Tune the refuse message to the domain. A compliance agent should say something like *"I don't have that in the [Manual Name]. Please contact [the relevant team]."* rather than the generic line above.

### 3. Action definition

Add this `actions:` block at the same level as `reasoning:` (still inside `subagent general_faq:`). Copy verbatim — `target` and `source` are platform-fixed values:

```agentscript
    actions:
        AnswerQuestionsWithKnowledge:
            description: "Answers questions about company policies, procedures, troubleshooting, or product information by searching knowledge articles. For example: 'What is your return policy?' or 'How do I fix an issue?'"
            inputs:
                query: string
                    description: "Required. A string created by generative AI to be used in the knowledge article search."
                    label: "Query"
                    is_required: True
                    is_user_input: True
                citationsUrl: string = @knowledge.citations_url
                    description: "The URL to use for citations for custom Agents."
                    label: "Citations Url"
                    is_required: False
                    is_user_input: True
                ragFeatureConfigId: string = @knowledge.rag_feature_config_id
                    description: "The RAG Feature ID to use for grounding this copilot action invocation."
                    label: "RAG Feature Configuration Id"
                    is_required: False
                    is_user_input: True
                citationsEnabled: boolean = @knowledge.citations_enabled
                    description: "Whether or not citations are enabled."
                    label: "Citations Enabled"
                    is_required: False
                    is_user_input: True
            outputs:
                knowledgeSummary: object
                    description: "A string formatted as rich text that includes a summary of the information retrieved from the knowledge articles and citations to those articles."
                    label: "Knowledge Summary"
                    complex_data_type_name: "lightning__richTextType"
                    filter_from_agent: False
                    is_displayable: True
                citationSources: object
                    description: "Source links for the chunks in the hydrated prompt that's used by the planner service."
                    label: "Citation Sources"
                    complex_data_type_name: "@apexClassType/AiCopilot__GenAiCitationInput"
                    filter_from_agent: False
                    is_displayable: False
            target: "standardInvocableAction://streamKnowledgeSearch"
            label: "Answer Questions with Knowledge"
            require_user_confirmation: False
            include_in_progress_indicator: True
            progress_indicator_message: "Getting answers"
            source: "EmployeeCopilot__AnswerQuestionsWithKnowledge"
```

### 4. Reuse an existing library

When modifying an existing agent: if the `.agent` already has a `knowledge:` block with a populated `rag_feature_config_id`, skip provisioning and reuse. Confirm the underlying library is still indexed by querying its detail endpoint (`GET /einstein/data-libraries/<libraryId>`) and checking `retrieverId` is present.

A complete minimal template lives at `assets/agents/knowledge-grounded.agent`.

### 5. Permission prerequisite — Einstein Agent User access

Wiring the `knowledge:` block and `AnswerQuestionsWithKnowledge` action is only half the work. At runtime, the Einstein Agent User needs **three layers of access** — missing any one causes silent empty results:

#### 5a. Data Cloud permset

The agent user must hold a Data Cloud permset/PSL. Without it, `knowledgeSummary` returns empty for every query.

The permset name varies by org shape (`GenieDataPlatformStarterPsl` PSL, `GenieUserEnhancedSecurity` PS, or `DataCloudUser` PS). Don't hardcode a name — run the discovery-then-assign procedure documented at [Agent User Setup, Step 3b](agent-user-setup.md).

#### 5b. Knowledge object + field-level security (KNOWLEDGE source type only)

For KNOWLEDGE libraries, the agent user must also have:
- **Object-level Read** on `Knowledge__kav`
- **Field-level Read** on ALL fields configured in the library (`primaryIndexField1`, `primaryIndexField2`, and all `contentFields`)

Without these, the runtime returns: `"Looks like you don't have access to one or more fields used by the assigned data library."` — but the error is only visible in server logs, not surfaced to the user.

Deploy a permset with the required access:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>Knowledge FLS for Agent</label>
    <objectPermissions>
        <allowRead>true</allowRead>
        <object>Knowledge__kav</object>
    </objectPermissions>
    <fieldPermissions>
        <editable>false</editable>
        <field>Knowledge__kav.Answer__c</field>
        <readable>true</readable>
    </fieldPermissions>
    <!-- Add all contentFields configured in the library -->
</PermissionSet>
```

Note: Standard fields like `Title` and `ArticleNumber` cannot be set via permset deploy (they're always-readable). Only custom fields (e.g. `Answer__c`, `Summary`) need explicit FLS grants.

#### 5c. Language alignment (KNOWLEDGE source type only)

The retriever filters chunks by language at query time. If the article language doesn't match the user's language context, results are silently excluded. Even subtle mismatches like `en_US` vs `en_GB` cause empty results (confirmed by W-21956266).

Before declaring a KNOWLEDGE library ready:
```bash
# Check article languages in the org
sf data query --target-org "$TARGET_ORG" -q \
  "SELECT Language, COUNT(Id) ct FROM Knowledge__kav WHERE PublishStatus='Online' GROUP BY Language"
```

If the agent user's locale doesn't match the article language:
- Publish articles in the agent user's language variant, OR
- Use a RETRIEVER source type with a custom retriever that disables language filtering

Reference: https://www.salesforce.com/blog/multi-language-guide/

#### 5d. Data Space scope

If the assignment lands but grounded queries still return empty results, also check the **Data Space scope** on the assigned permset (UI-only, no API) — see [Agent User Setup, Step 3b.4](agent-user-setup.md).

## Common pitfalls

- `INVALID_SESSION_ID` mid-flow → access token expired. Re-fetch with `sf org display`.
- `LightningDomain` login error → use the `*.my.salesforce.com` domain, not `*.lightning.force.com`.
- Step 4 returns 403 → a header from step 3 was dropped or reordered — forward them all exactly.
- `groundingFileRefs` empty right after Step 5 → indexing isn't done yet. Wait for Step 6 to populate `retrieverId`.
- Top-level `status` stuck on `IN_PROGRESS` with all sub-stages `SUCCESS` → normal. Top-level lag of 10–30 minutes is common (longer for large files). **Do not block on it.** Use `retrieverId is not null` as the readiness gate.
- Step 5 returns `INVALID_REQUEST_STATE: "One or more files have not been uploaded..."` despite a successful S3 200 → the org's `bypass-s3-file-exist` gate hasn't rolled out. Skip ADL on this pass; the user can upload via the Setup UI later.
- `.agent` validation fails with `unresolved reference @knowledge.rag_feature_config_id` → the top-level `knowledge:` block is missing or misordered. It must precede `language:` per Core Language Section 2.
- Agent published, ADL indexed (`retrieverId` populated), but every grounded query returns empty `knowledgeSummary` and the agent refuses → Einstein Agent User lacks Data Cloud access. See "Wiring → Permission prerequisite" above and [Agent User Setup, Step 3b](agent-user-setup.md).

## Reference

- Grounding source type: `SFDRIVE` (File)
- All operations use `sf agent adl` CLI commands which auto-negotiate API version

---

## Part B: KNOWLEDGE — Knowledge Article Library

Use this when the org has Salesforce Knowledge articles (KAV) and the user wants to ground the agent on article content. No file upload needed — the library indexes directly from Knowledge articles.

### Prerequisites (Knowledge-specific)

- "Knowledge User" enabled for the user
- Knowledge articles exist in the org (at least one published article)
- The `isAsyncKnowledgeAdlEnabled` gate must be open on the org

### Step K1 — Create the Knowledge library

Ask the user which Knowledge fields to index. Required: two primary index fields (immutable after creation). Optional: contentFields for additional searchable content.

Common field choices:
- `ArticleNumber` — unique article identifier
- `Title` — article title
- `UrlName` — URL-friendly name
- `Summary` — article summary
- Custom fields like `Answer__c`, `Detail__c`

```bash
sf agent adl create \
  --target-org "$TARGET_ORG" \
  --name "$ADL_Name" \
  --developer-name "$ADL_DevName" \
  --source-type knowledge \
  --primary-index-field1 ArticleNumber \
  --primary-index-field2 Title \
  --json
```

Capture `result.libraryId` from the response. Indexing is auto-triggered on creation.

```bash
LIBRARY_ID="<paste result.libraryId>"
```

### Step K2 — Poll status until READY

Knowledge libraries provision through stages: `DATA_STREAM → DATA_LAKE_OBJECT → DATA_MODEL_OBJECT → SEARCH_INDEX → RETRIEVER`

```bash
sf agent adl status -i "$LIBRARY_ID" --target-org "$TARGET_ORG"
```

Check readiness via the detail endpoint:

```bash
sf agent adl get -i "$LIBRARY_ID" --target-org "$TARGET_ORG" --json
```

Once `result.retrieverId` is non-null, the library is ready: `rag_feature_config_id = "ARFPC_" + LIBRARY_ID`

### Step K3 (Day-2) — Update Knowledge config

Update which fields are indexed. This triggers full server-side re-indexing.

```bash
sf agent adl update \
  -i "$LIBRARY_ID" \
  --target-org "$TARGET_ORG" \
  --content-fields "Answer__c,Summary__c" \
  --restrict-to-public-articles
```

Important constraints:
- `primaryIndexField1` and `primaryIndexField2` are **immutable** after creation
- Updates are **blocked while provisioning is in progress** (server returns `INVALID_REQUEST_STATE`)
- Knowledge articles re-index automatically when articles are updated in the org
- Metadata-only updates (masterLabel, description) do NOT trigger re-indexing

### Knowledge validation errors

| Error | Cause |
|-------|-------|
| `MISSING_REQUIRED_FIELD` | primaryIndexField1 or primaryIndexField2 missing |
| `DUPLICATE_PRIMARY_FIELDS` | Same field for both primary fields |
| `OVERLAPPING_CONTENT_FIELD` | A contentField matches a primary field |
| `DUPLICATE_CONTENT_FIELDS` | Same field appears twice in contentFields |
| `DATA_CATEGORY_NOT_SUPPORTED` | isDataCategoryRuleEnabled=true (not yet supported) |
| `PRIMARY_FIELDS_IMMUTABLE` | Attempt to change primary fields after creation |
| `ADL_UNSUPPORTED_SOURCE_TYPE` | Knowledge gate not enabled on org |

---

## Part C: RETRIEVER — Custom Retriever Library

Use this when the user has an existing active Custom Retriever and wants to wrap it in an ADL library. No file upload or indexing needed — the library is immediately ready.

### Prerequisites (Retriever-specific)

- An active Custom Retriever exists in the org (18-char ID with prefix `1Cx` or `0pm`)
- The retriever must be in active state (inactive retrievers are rejected)

### Finding an active retriever ID

If the user doesn't know their retriever ID, find one from existing READY libraries:

```bash
sf agent adl list --target-org "$TARGET_ORG" --json
```

Then get the retrieverId from a READY library:

```bash
sf agent adl get -i <READY_LIBRARY_ID> --target-org "$TARGET_ORG" --json
```

Look for `result.retrieverId` in the response.

### Step R1 — Create the Retriever library

```bash
sf agent adl create \
  --target-org "$TARGET_ORG" \
  --name "$ADL_Name" \
  --developer-name "$ADL_DevName" \
  --source-type retriever \
  --retriever-id "<active-retriever-id>" \
  --json
```

Expected: JSON with `libraryId`, `sourceType: "RETRIEVER"`, `groundingSource.retrieverId` populated. The library is **immediately usable** — no indexing or polling needed.

### Step R2 — Verify READY status

```bash
sf agent adl get -i "$LIBRARY_ID" --target-org "$TARGET_ORG" --json
```

Expected: `status: "READY"`, `retrieverId` matches input.

The `rag_feature_config_id = "ARFPC_" + LIBRARY_ID` — wire this into the agent immediately.

### Step R3 (Day-2) — Update metadata or swap retriever

```bash
# Update metadata
sf agent adl update -i "$LIBRARY_ID" --target-org "$TARGET_ORG" \
  --name "Updated Retriever Library" --description "Updated description"

# Swap to a different retriever
sf agent adl update -i "$LIBRARY_ID" --target-org "$TARGET_ORG" \
  --retriever-id "<new-active-retriever-id>"
```

### Retriever validation errors

| Error | Cause |
|-------|-------|
| `INVALID_REQUEST_STATE: retriever not active` | retrieverId points to an inactive retriever |
| `retriever not found` | retrieverId doesn't exist |
| `retrieverId is required` | sourceType RETRIEVER without retrieverId |
| `ADL_UNSUPPORTED_SOURCE_TYPE` | File operations (upload, add, indexing) on RETRIEVER library |

### Unsupported operations for RETRIEVER

These endpoints return `400: ADL_UNSUPPORTED_SOURCE_TYPE`:
- `POST /file-upload-urls`
- `POST /files`
- `POST /indexing`
- `GET /upload-readiness`
- `DELETE /files/{fileId}`

