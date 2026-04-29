---
name: adl-file-library
description: Create a File-type Agentforce Data Library (ADL), upload a file, trigger indexing, and verify it is ready for grounding. Use when the user asks to provision an ADL file library, upload a file to a data library, index a file for Agentforce grounding, or check ADL indexing status via REST.
---

# ADL File Library

End-to-end flow for creating a File-type Agentforce Data Library via the Einstein Data Libraries REST API, uploading a file, indexing it, and confirming it is ready for grounding.

## When to use

Use this skill when the user wants to:
- Provision a File (SFDRIVE) data library programmatically
- Upload a file to a data library and make it searchable by Agentforce
- Check indexing status or library readiness
- Build a script/tool/agent that does any of the above

Do NOT use for: Knowledge-type libraries, web crawl sources, or UI-driven library setup.

## Prerequisites

Before anything else, verify that `sf` (Salesforce CLI) and `jq` (JSON parser) are on PATH. Every later step calls them, and they fail in confusing ways (empty tokens, malformed URLs, 401s) when missing.

Run this check first and STOP if either is missing — do not proceed to Preflight or any `curl` step.

```bash
command -v sf >/dev/null 2>&1 || { echo "MISSING: sf (Salesforce CLI)"; }
command -v jq >/dev/null 2>&1 || { echo "MISSING: jq (JSON parser)"; }
```

If `sf` is missing, do NOT auto-install. Tell the user and offer these options (pick one):

- Homebrew (recommended on macOS): `brew install --cask sf`
- npm (requires Node 20+): `npm install -g @salesforce/cli`
- `.pkg` installer: https://developer.salesforce.com/docs/atlas.en-us.sfdx_setup.meta/sfdx_setup/sfdx_setup_install_cli.htm#sfdx_setup_install_cli_macos

Verify after install: `sf --version` should print `@salesforce/cli/<version>`.

If `jq` is missing, offer: `brew install jq` (macOS) or `sudo apt-get install jq` (Debian/Ubuntu).

Only continue to Preflight once both commands resolve.

## Verify against the live API spec (optional)

The ADL Connect API is still evolving — paths, methods, and request/response shapes can change between releases. The OpenAPI spec in the Core repo is the source of truth:

```
./assets/adl-api-spec.yaml
```

**Ask the user whether to run spec validation before proceeding.** It's time-consuming (finding the checkout, confirming the branch, diffing 8 endpoints against the spec) and unnecessary for routine runs. Skip it by default and only run it when:

- The user hit an unexpected 4xx/5xx on a prior run of this skill.
- The user explicitly says they're on a new release or suspects the API has drifted.
- The user asks for it by name.

If the user says skip, jump straight to Preflight. If they say run, follow the steps below and report the spec version you validated against.

How to use it:

1. Detect which Core branch the user is working on, since `main` and each release patch branch (`p4/<release>-patch`, e.g. `p4/260-patch`, `p4/262-patch`, `p4/264-patch`, …) can carry a different spec. Prefer the local checkout:
   ```bash
   # Find the user's Core checkout
   CORE_REPO=$(find ~ -maxdepth 4 -type d -name "core" -path "*/core-public/*" 2>/dev/null | head -1)
   # Read the branch the user is currently on
   BRANCH=$(git -C "$CORE_REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)
   echo "Detected: $CORE_REPO @ $BRANCH"
   ```
   Always **confirm the branch with the user before validating** — do not assume the checked-out branch is the one they want the spec verified against. They may be running the skill against a different release than the one checked out. Accept `main` or any `p4/<release>-patch` pattern; if the user's answer doesn't match either, ask again.

2. Locate the spec file:
   ```bash
   SPEC_PATH="$CORE_REPO/ai-data-library-connect-api/java/resources/adl-api-spec.yaml"
   ```
   If the file is absent on the confirmed branch, fall back to codesearch: look up `adl-api-spec.yaml` on the branch the user named and read the version there. Do not silently fall back to `main` or a different patch branch — ask the user first.

3. For each step below (Steps 1–8), match the endpoint against the spec and confirm:
   - The **path** still exists (e.g. `/einstein/data-libraries/{libraryId}/upload-readiness`, `/einstein/data-libraries/{libraryId}/files`)
   - The **HTTP method** matches
   - Required **request body fields** are unchanged (e.g. `masterLabel`, `developerName`, `groundingSource.sourceType`, `uploadedFiles[].filePath`, `uploadedFiles[].fileSize`)
   - **Response field names** still match what Steps 1–8 extract with `jq` (e.g. `libraryId`, `uploadUrls[].uploadUrl`, `indexingStatus.status`, `filesAccepted`, `groundingFileRefs`)
   - The **API version** in `servers.url` / `info.version` still matches the `v66.0` hardcoded below — if the spec has bumped, update the version in every `curl`.

4. If any mismatch is found, STOP and tell the user which step is out of date and what the spec now says. Do not silently adapt — the user needs to know the skill is drifting.

5. Record the branch, the spec file's last-modified date, and the commit hash you read it at in your preflight summary, so the user can see which version you validated against.

## Preflight

1. Confirm the target Salesforce org is authenticated with `sf`:
   ```bash
   sf org display --target-org <org-alias> --json
   ```
   If auth is missing, have the user run `sf org login web --alias <alias> --instance-url https://<your-org>.my.salesforce.com`. Do not guess the alias — ask if unspecified.

2. Confirm the file to upload exists and is a supported type (PDF, DOCX, TXT, etc.).

3. Ask the user for:
   - Target org alias
   - File path to upload
   - Library name (human-readable) — optional, default to a timestamped name

## Variables

Resolve these once at the start:

```bash
TARGET_ORG="<org-alias>"
FILE_NAME="<absolute-path-to-file>"
ADL_DevName="<snake_case_unique>"     # e.g. MyLib_0424_ab3
ADL_Name="<human readable label>"
ORG_URL=$(sf org display --target-org "$TARGET_ORG" --json | jq -r '.result.instanceUrl')
ACCESS_TOKEN=$(sf org display --target-org "$TARGET_ORG" --json | jq -r '.result.accessToken')
```

Note: `ACCESS_TOKEN` expires. If any later step returns `INVALID_SESSION_ID`, re-run the token line.

All endpoints below use `v66.0`. Adjust if the org requires a different API version.

## Step 1 — Create the library

```bash
curl -s -X POST "${ORG_URL}/services/data/v66.0/einstein/data-libraries" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"masterLabel\": \"${ADL_Name}\",
    \"developerName\": \"${ADL_DevName}\",
    \"groundingSource\": { \"sourceType\": \"SFDRIVE\" }
  }"
```

Capture `libraryId` from the response — every subsequent call needs it:
```bash
LIBRARY_ID=$(... | jq -r '.libraryId')
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

```bash
FILE_BASENAME=$(basename "$FILE_NAME")
curl -s -X POST \
  "${ORG_URL}/services/data/v66.0/einstein/data-libraries/$LIBRARY_ID/file-upload-urls" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{ \"files\": [ { \"fileName\": \"${FILE_BASENAME}\" } ] }"
```

From the response capture:
- `uploadUrls[0].uploadUrl` → `PRESIGNED_URL`
- `uploadUrls[0].filePath` → `FILE_PATH_S3`
- `uploadUrls[0].headers`   → header map to forward on the PUT

## Step 4 — Upload the file to S3

The presigned URL is on S3, not Salesforce. Forward every header from step 3 exactly.

```bash
UPLOAD_HEADERS=()
while IFS='=' read -r key value; do
  UPLOAD_HEADERS+=(-H "$key: $value")
done < <(echo "$STEP3_RESPONSE" | jq -r '.uploadUrls[0].headers | to_entries[] | "\(.key)=\(.value)"')

curl -X PUT "$PRESIGNED_URL" \
  "${UPLOAD_HEADERS[@]}" \
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

## Step 6 — Poll status until READY

```bash
curl -s \
  "${ORG_URL}/services/data/v66.0/einstein/data-libraries/$LIBRARY_ID/status" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.'
```

Response shape:
```json
{
  "indexingStatus": {
    "libraryId": "...",
    "lastUpdatedAt": 1776979814920,
    "stages": [
      { "completedAt": 1776979412000, "name": "DATA_LAKE_OBJECT",  "status": "SUCCESS" },
      { "completedAt": 1776979412000, "name": "DATA_MODEL_OBJECT", "status": "SUCCESS" },
      { "completedAt": 1776979412000, "name": "SEARCH_INDEX",      "status": "SUCCESS" },
      { "completedAt": 1776979412000, "name": "RETRIEVER",         "status": "SUCCESS" }
    ],
    "status": "IN_PROGRESS"
  }
}
```

Stages can all show `SUCCESS` while the top-level `status` still reports `IN_PROGRESS` — the overall status flips last. Poll every ~10s until `status: READY` or `status: FAILED`. Indexing typically completes in a few minutes depending on file size.

## Step 7 — Confirm the library is populated

```bash
curl -s \
  "${ORG_URL}/services/data/v66.0/einstein/data-libraries/$LIBRARY_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.'
```

Check `groundingFileRefs` — the uploaded file should appear with its path, size, and the retriever ID Agentforce uses at runtime.

## Step 8 — (Optional) Add files to an existing library

For day-2 incremental additions to an already-provisioned SFDRIVE library. This reuses Steps 3 and 4 to upload, then calls the dedicated `/files` endpoint (not `/indexing`) which triggers SearchIndex re-hydration.

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

Expected response shape:
```json
{
  "libraryId": "...",
  "filesAccepted": 1,
  "groundingFileRefs": [ { "filePath": "...", "fileSize": ..., "retrieverId": "..." } ]
}
```

3. Poll **Step 6** (`/status`) until it flips back to `READY` — re-hydration is async.

## Common pitfalls

- `INVALID_SESSION_ID` mid-flow → access token expired. Re-fetch with `sf org display`.
- `LightningDomain` login error → use the `*.my.salesforce.com` domain, not `*.lightning.force.com`.
- Step 4 returns 403 → a header from step 3 was dropped or reordered — forward them all exactly.
- `groundingFileRefs` empty right after Step 5 → indexing isn't done yet. Wait for Step 6 to show `READY`.
- Top-level `status` stuck on `IN_PROGRESS` with all stages `SUCCESS` → normal; the overall flip lags the last stage by up to a minute.

## Reference

- API version: `v66.0`
- Grounding source type: `SFDRIVE` (File)
- Base path: `/services/data/v66.0/einstein/data-libraries`