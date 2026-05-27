# Data Library Reference (ADL)

How to provision a Files-based Agentforce Data Library (ADL) and wire it into an Agent Script `.agent` file so the agent can answer questions grounded on uploaded documents.

This reference is consumed by the **Create an Agent** and **Modify an Existing Agent** workflows in `SKILL.md`. The parent skill decides *whether* to provision an ADL (by asking the user); this file owns *how*.

## What this reference covers

- **Step 0** — Verify Data Cloud is provisioned. ADL has a hard dependency on Data Cloud.
- **Steps 1–7** — Create a SFDRIVE library, upload one file via presigned S3 URL, trigger indexing, poll until ready.
- **Step 8** — Day-2: add more files to an existing library.
- **Wiring the ADL into Agent Script** — the `knowledge:` block + `AnswerQuestionsWithKnowledge` action.

What this file deliberately does NOT cover:
- Knowledge-article (`Knowledge__kav`) libraries via the Setup UI wizard. This skill targets file grounding via the REST API only.
- Web-crawl sources or custom retrievers.

## Outputs the parent skill consumes

After Step 7 succeeds, hand the parent skill these values:
- `libraryId` — the raw library ID returned by the create call.
- `retrieverId` — populated once indexing completes.
- `rag_feature_config_id` — derived as `"ARFPC_" + libraryId`. This is the value that goes into the `.agent` file's `knowledge:` block. It is **not** the raw libraryId.

## Prerequisites

`sf` (Salesforce CLI) and `curl` must be on PATH. Both fail in confusing ways (empty tokens, malformed URLs, 401s) when missing. STOP if either is missing — do not proceed.

```bash
command -v sf >/dev/null 2>&1 || echo "MISSING: sf (Salesforce CLI)"
command -v curl >/dev/null 2>&1 || echo "MISSING: curl"
```

If `sf` is missing, do NOT auto-install. Offer:
- Homebrew (recommended on macOS): `brew install --cask sf`
- npm (Node 20+): `npm install -g @salesforce/cli`
- `.pkg` installer: https://developer.salesforce.com/docs/atlas.en-us.sfdx_setup.meta/sfdx_setup/sfdx_setup_install_cli.htm

`curl` ships with macOS and most Linux distros; if missing, `brew install curl` or use the system package manager.

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

### 0b. ADL service health check — `GET /einstein/data-libraries`

DC is provisioned. Confirm the ADL service itself is reachable on this org before doing any provisioning work.

First read the org's `instanceUrl` and `accessToken` from `sf org display`:

```bash
sf org display --target-org "$TARGET_ORG" --json
```

Read the JSON response, copy `result.instanceUrl` and `result.accessToken`, and use them as `ORG_URL` and `ACCESS_TOKEN` in the next command. Substitute the literal values directly — do not pipe the response through any filter:

```bash
curl -s -o /tmp/adl_health.json -w "%{http_code}\n" \
  "<ORG_URL>/services/data/v66.0/einstein/data-libraries" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

Then read `/tmp/adl_health.json` directly — it's the response body the LLM can parse natively:

```bash
cat /tmp/adl_health.json
```

- **`200`** → ✅ ADL service is healthy. The response includes `libraries[]` — useful for Step 5b reuse if a matching `developerName` is already provisioned. Continue to Step 1.
- **`400` with `errorCode: "INTERNAL_ERROR"`** or **`5xx`** → ⚠️ DC is provisioned but the ADL service is unhealthy on this org. Do not attempt to create a library — the create POST will return the same opaque error. Tell the user honestly:

  ```
  ⚠️ Data Cloud is provisioned, but the Agentforce Data Library service is
     returning an internal error on this org. ADL provisioning will fail
     until the service recovers. Options:

     A. Skip knowledge grounding for this run — author the agent without an ADL.
     B. Try a different org where ADL is healthy.
     C. Open a support case if this org should have ADL working.
  ```

  Default to option A — author without a `knowledge:` block — unless the user picks B or C.
- **`401` / `403`** → auth issue. Re-fetch the access token (`sf org display --target-org "$TARGET_ORG" --json`) and retry once. If still 401/403, the user's session lacks ADL permissions — surface that.
- **`404`** → ADL route not wired on this org. Treat the same as "DC not provisioned" — show the A/B prompt below.

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

Resolve these once after Step 0 passes (`TARGET_ORG` was already set in Prerequisites). For `ORG_URL` and `ACCESS_TOKEN`, run `sf org display --target-org "$TARGET_ORG" --json`, read the JSON response, and substitute the literal values for `<ORG_URL>` and `<ACCESS_TOKEN>` in every subsequent `curl` command.

```bash
FILE_NAME="<absolute-path-to-file>"
ADL_DevName="<snake_case_unique>"     # e.g. MyLib_0424_ab3
ADL_Name="<human readable label>"
# From sf org display --target-org "$TARGET_ORG" --json:
#   ORG_URL      = result.instanceUrl     (e.g. https://my-org.my.salesforce.com)
#   ACCESS_TOKEN = result.accessToken     (begins with 00D...)
```

If you prefer shell variables for readability, paste the literal values:

```bash
ORG_URL="<paste result.instanceUrl from sf org display --json>"
ACCESS_TOKEN="<paste result.accessToken from sf org display --json>"
```

`ACCESS_TOKEN` expires. If any later step returns `INVALID_SESSION_ID`, re-run `sf org display --json` and re-paste the new token.

All endpoints below use `v66.0`. Adjust if the org requires a different API version.

Confirm the file to upload exists and is a supported type (PDF, DOCX, TXT, etc.).

## Step 1 — Create the library

Write the response to a file so you can read it directly:

```bash
curl -s -o /tmp/adl_create.json -X POST \
  "${ORG_URL}/services/data/v66.0/einstein/data-libraries" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"masterLabel\": \"${ADL_Name}\",
    \"developerName\": \"${ADL_DevName}\",
    \"groundingSource\": { \"sourceType\": \"SFDRIVE\" }
  }"
cat /tmp/adl_create.json
```

Read the response and capture `libraryId` — every subsequent call needs it. Set it as a shell variable using the literal value:

```bash
LIBRARY_ID="<paste libraryId from the response>"
```

## Step 2 — Wait for upload readiness

Data Cloud provisions the Unified Data Lake Object (UDLO) and Unified Data Model Object (UDMO) that hold file metadata. Poll until `ready: true`:

```bash
curl -s --max-time 130 \
  "${ORG_URL}/services/data/v66.0/einstein/data-libraries/$LIBRARY_ID/upload-readiness?waitMaxTime=120000" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

The `waitMaxTime` query param lets the server long-poll — one call is usually enough. If `ready` is still `false`, call again.

## Step 3 — Get a presigned upload URL

Write the response to a file:

```bash
FILE_BASENAME=$(basename "$FILE_NAME")
curl -s -o /tmp/adl_presign.json -X POST \
  "${ORG_URL}/services/data/v66.0/einstein/data-libraries/$LIBRARY_ID/file-upload-urls" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{ \"files\": [ { \"fileName\": \"${FILE_BASENAME}\" } ] }"
cat /tmp/adl_presign.json
```

From the response read these fields and remember them — Step 4 needs all of them, written verbatim:

- `uploadUrls[0].uploadUrl` — the presigned S3 URL (will be the PUT target)
- `uploadUrls[0].filePath` — the S3 path (Step 5 needs this; capture it as a shell variable now)
- `uploadUrls[0].headers` — a JSON object of header name → header value pairs that S3 requires on the PUT

Capture the file path for later steps:

```bash
FILE_PATH_S3="<paste uploadUrls[0].filePath from the response>"
```

## Step 4 — Upload the file to S3

The presigned URL is on S3, not Salesforce. Forward every header from Step 3's `headers` object verbatim — drop or reorder one and S3 returns 403.

Construct the curl command by reading the headers object from Step 3's response and emitting one `-H "<name>: <value>"` flag per entry:

```bash
curl -X PUT "<paste uploadUrls[0].uploadUrl from Step 3>" \
  -H "<paste header 1 name>: <paste header 1 value>" \
  -H "<paste header 2 name>: <paste header 2 value>" \
  -H "<...one -H per header in the headers object...>" \
  --data-binary @"$FILE_NAME" \
  -w "\nHTTP Status: %{http_code}\n"
```

Expect `HTTP Status: 200`. The file is in S3 but not yet indexed.

## Step 5 — Trigger indexing

```bash
FILE_SIZE=$(stat -f%z "$FILE_NAME" 2>/dev/null || stat -c%s "$FILE_NAME")
curl -s -X POST \
  "${ORG_URL}/services/data/v66.0/einstein/data-libraries/$LIBRARY_ID/indexing" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"uploadedFiles\": [
      { \"filePath\": \"${FILE_PATH_S3}\", \"fileSize\": ${FILE_SIZE} }
    ]
  }"
```

Response returns `status: IN_PROGRESS`. The pipeline chunks, embeds, and builds a retriever in the background.

## Step 6 — Poll the detail endpoint until `retrieverId` populates

**The library is usable for grounding as soon as `retrieverId` is non-null.** Do not block on the top-level `indexingStatus.status` flag — it can lag behind the retriever by 10–30 minutes (sometimes longer for larger files), even after all sub-stages report `SUCCESS`. Poll the detail endpoint, not `/status`:

```bash
curl -s -o /tmp/adl_detail.json \
  "${ORG_URL}/services/data/v66.0/einstein/data-libraries/$LIBRARY_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
cat /tmp/adl_detail.json
```

Read the response and check `status`, `retrieverId`, `retrieverLabel`, and `groundingFileRefs`.

Response (excerpt):
```json
{
  "status": "IN_PROGRESS",
  "retrieverId": "0XRxx0000000123EAA",
  "retrieverLabel": "...",
  "groundingFileRefs": [ { "filePath": "...", "fileSize": 12345, "retrieverId": "..." } ]
}
```

- `retrieverId` non-null → ✅ ready for grounding. Continue to Step 7. The agent will return real results from this library now, even if the top-level `status` still reads `IN_PROGRESS`.
- `retrieverId` still null → poll every ~10 s. Typically populates within 1–2 minutes of triggering Step 5.
- `status: FAILED` → indexing failed; check `groundingFileRefs` and the `/status` endpoint for the failed sub-stage.

If you also want the granular sub-stage view for debugging:

```bash
curl -s -o /tmp/adl_status.json \
  "${ORG_URL}/services/data/v66.0/einstein/data-libraries/$LIBRARY_ID/status" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
cat /tmp/adl_status.json
```

Sub-stage shape (for reference):
```json
{
  "indexingStatus": {
    "stages": [
      { "name": "DATA_LAKE_OBJECT",  "status": "SUCCESS" },
      { "name": "DATA_MODEL_OBJECT", "status": "SUCCESS" },
      { "name": "SEARCH_INDEX",      "status": "SUCCESS" },
      { "name": "RETRIEVER",         "status": "SUCCESS" }
    ],
    "status": "IN_PROGRESS"
  }
}
```

All four sub-stages can read `SUCCESS` while the top-level `status` still says `IN_PROGRESS`. That's normal. Trust `retrieverId`.

## Step 7 — Confirm the library is populated

The Step 6 response already gave you `retrieverId` and `groundingFileRefs`. Sanity-check that the file you uploaded appears with the expected size by reading `/tmp/adl_detail.json` from Step 6 — focus on the `groundingFileRefs` array. If you want a fresh fetch:

```bash
curl -s -o /tmp/adl_detail.json \
  "${ORG_URL}/services/data/v66.0/einstein/data-libraries/$LIBRARY_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
cat /tmp/adl_detail.json
```

At this point the parent skill receives:
- `libraryId` — from Step 1
- `retrieverId` — from Step 6 (the readiness gate)
- `rag_feature_config_id` — computed as `"ARFPC_" + libraryId`

## Step 8 — (Optional) Add files to an existing library

For day-2 incremental additions to an already-provisioned SFDRIVE library. Reuses Steps 3 and 4 to upload, then calls the dedicated `/files` endpoint (not `/indexing`) which triggers SearchIndex re-hydration.

Constraints per the spec:
- At least one file required.
- No duplicate `fileName` values in the same batch.
- Total file count in the library must stay ≤ 1000.
- `filePath` must belong to the same `libraryId` — cross-library paths are rejected with 400.
- Only works on SFDRIVE libraries; Knowledge/Retriever libraries return 400.

Flow:

1. For each new file, repeat **Step 3** (presigned URL) and **Step 4** (S3 PUT) exactly as-is.
2. Call the add-files endpoint:

```bash
NEW_FILE_SIZE=$(stat -f%z "$NEW_FILE_NAME" 2>/dev/null || stat -c%s "$NEW_FILE_NAME")
curl -s -X POST \
  "${ORG_URL}/services/data/v66.0/einstein/data-libraries/$LIBRARY_ID/files" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"uploadedFiles\": [
      { \"filePath\": \"${NEW_FILE_PATH_S3}\", \"fileSize\": ${NEW_FILE_SIZE} }
    ]
  }"
```

Expected response:
```json
{
  "libraryId": "...",
  "filesAccepted": 1,
  "groundingFileRefs": [ { "filePath": "...", "fileSize": ..., "retrieverId": "..." } ]
}
```

3. Poll **Step 6** (`/status`) until it flips back to `READY` — re-hydration is async.

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

Inside whichever subagent should answer grounded questions — typically a `general_faq` subagent — declare the action invocation in the `actions:` block under `reasoning:`. **The first instruction must be the anti-hallucination guard** (see "Anti-hallucination guard" below):

```agentscript
subagent general_faq:
    description: "Answer customer questions by searching knowledge."

    reasoning:
        instructions: ->
            | If @outputs.AnswerQuestionsWithKnowledge.knowledgeSummary is empty or None,
              respond verbatim: "I don't have information about that in our knowledge base.
              Please contact support for help." Do NOT compose an answer from prior knowledge.
            | Otherwise, answer the user's question using ONLY the content in
              @outputs.AnswerQuestionsWithKnowledge.knowledgeSummary.
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

The four `with` lines bind the action's inputs. The trailing `...` tells the planner to fill them — `query` from the user's utterance, the other three from the top-level `knowledge:` block via the action definition's defaults.

#### Anti-hallucination guard

When retrieval misses (the user asks about something not in the corpus, or the library is still warming up after Step 5), `knowledgeSummary` comes back empty. Without an explicit refuse-rule, the LLM falls back to its training data and produces plausibly-wrong answers. For compliance-sensitive corpora — internal policy manuals, regulated content, medical/legal/financial guides — this is unacceptable: the agent will quote section numbers and dollar limits that don't exist.

The first instruction in the grounded subagent must therefore be a deterministic refuse-rule keyed on `@outputs.AnswerQuestionsWithKnowledge.knowledgeSummary` being empty/None. The rule must be the *first* line of the instructions block so it short-circuits the LLM's reasoning before it considers composing.

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

### 5. Permission prerequisite — Einstein Agent User Data Cloud access

Wiring the `knowledge:` block and `AnswerQuestionsWithKnowledge` action is only half the work. At runtime, the **Einstein Agent User must hold a Data Cloud permset/PSL** — without it, the action returns empty `knowledgeSummary` for every query, the anti-hallucination guard refuses, and the agent appears broken even though the ADL is fully indexed.

The permset name varies by org shape (`GenieDataPlatformStarterPsl` PSL, `GenieUserEnhancedSecurity` PS, or `DataCloudUser` PS). Don't hardcode a name — run the discovery-then-assign procedure documented at [Agent User Setup, Step 3b](agent-user-setup.md) when the agent has a `knowledge:` block.

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

- API version: `v66.0`
- Grounding source type: `SFDRIVE` (File)
- Base path: `/services/data/v66.0/einstein/data-libraries`
- OpenAPI spec (in this skill): `assets/adl-api-spec.yaml`

---

## Appendix: Validate against the live API spec (optional)

The ADL Connect API is still evolving — paths, methods, and response shapes can change between releases. The OpenAPI spec checked in at `assets/adl-api-spec.yaml` is the shipped reference. The source of truth lives in the Core repo.

**Skip by default.** Only run this when:
- The user hit an unexpected 4xx/5xx on a prior run.
- The user explicitly says they're on a new release or suspects the API has drifted.
- The user asks for it by name.

How to run:

1. Detect the user's Core branch. `main` and each release patch branch (`p4/<release>-patch`, e.g. `p4/260-patch`, `p4/262-patch`, `p4/264-patch`) can carry different specs. Prefer the local checkout:
   ```bash
   CORE_REPO=$(find ~ -maxdepth 4 -type d -name "core" -path "*/core-public/*" 2>/dev/null | head -1)
   BRANCH=$(git -C "$CORE_REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)
   echo "Detected: $CORE_REPO @ $BRANCH"
   ```
   Always confirm the branch with the user before validating — they may be running this skill against a different release than the one checked out. Accept `main` or any `p4/<release>-patch` pattern.

2. Locate the spec on that branch:
   ```bash
   SPEC_PATH="$CORE_REPO/ai-data-library-connect-api/java/resources/adl-api-spec.yaml"
   ```
   If the file is absent on the confirmed branch, fall back to codesearch against the branch the user named. Do not silently fall back to `main` or another patch branch.

3. For each REST step in this reference, confirm against the spec:
   - The **path** exists (e.g. `/einstein/data-libraries/{libraryId}/upload-readiness`, `/files`, `/indexing`).
   - The **HTTP method** matches.
   - Required **request body fields** are unchanged (`masterLabel`, `developerName`, `groundingSource.sourceType`, `uploadedFiles[].filePath`, `uploadedFiles[].fileSize`).
   - **Response field names** still match the fields this reference reads (`libraryId`, `uploadUrls[].uploadUrl`, `uploadUrls[].filePath`, `uploadUrls[].headers`, `indexingStatus.status`, `filesAccepted`, `groundingFileRefs`, `retrieverId`).
   - The **API version** in `servers.url` / `info.version` still matches the `v66.0` hardcoded above. If bumped, update the version in every `curl`.

4. If any mismatch is found, STOP and tell the user which step is out of date and what the spec now says. Do not silently adapt.

5. Record the branch, the spec file's last-modified date, and the commit hash you read it at, so the user can see which version you validated against.
