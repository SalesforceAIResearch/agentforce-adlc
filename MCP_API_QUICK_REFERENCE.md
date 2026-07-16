# MCP Connect API Quick Reference - External Servers

## Base URL

```
/api-catalog/mcp-servers
```

All endpoints use the Salesforce REST API. Access via `sf api request rest`.

## Server Operations

### List Servers

```bash
# List all external servers
sf api request rest "/api-catalog/mcp-servers?type=EXTERNAL" --json -o OrgAlias

# Filter by label
sf api request rest "/api-catalog/mcp-servers?label=GitHub&type=EXTERNAL" --json -o OrgAlias
```

**Response:**
```json
{
  "servers": [
    {
      "id": "mcp_server_id",
      "name": "github_mcp",
      "label": "GitHub MCP Server",
      "type": "EXTERNAL",
      "status": "ACTIVE",
      "serverUrl": "https://mcp.github.example.com/sse",
      "assetCount": 8,
      "createdAt": "2026-06-01T10:00:00Z",
      "updatedAt": "2026-06-01T12:00:00Z"
    }
  ]
}
```

### Get Server Details

```bash
sf api request rest /api-catalog/mcp-servers/{id} --json -o OrgAlias
```

**Response:**
```json
{
  "id": "mcp_server_id",
  "name": "github_mcp",
  "label": "GitHub MCP Server",
  "description": "Access GitHub repositories and issues",
  "type": "EXTERNAL",
  "status": "ACTIVE",
  "serverUrl": "https://mcp.github.example.com/sse",
  "managed": false,
  "auth": {
    "authType": "OAUTH",
    "identityProvider": "GitHub_IDP",
    "clientId": "abc123",
    "scope": "read:org write:issues"
  },
  "assetCount": 8,
  "createdAt": "2026-06-01T10:00:00Z",
  "createdById": "005...",
  "updatedAt": "2026-06-01T12:00:00Z",
  "updatedById": "005..."
}
```

### Delete Server

```bash
sf api request rest /api-catalog/mcp-servers/{id} \
  --method DELETE \
  --json \
  -o OrgAlias
```

**Response:** 204 No Content

---

## External MCP Server Registration

### Register External Server

```bash
sf api request rest /api-catalog/mcp-servers \
  --method POST \
  --body @external-server-config.json \
  --json \
  -o OrgAlias
```

**Request Body (OAuth):**
```json
{
  "name": "github_mcp",
  "label": "GitHub MCP Server",
  "description": "Access GitHub repositories and issues",
  "type": "EXTERNAL",
  "serverUrl": "https://mcp.github.example.com/sse",
  "managed": false,
  "auth": {
    "authType": "OAUTH",
    "identityProvider": "GitHub_IDP",
    "clientId": "abc123xyz",
    "clientSecret": "secret_value_never_logged",
    "scope": "read:org write:issues"
  }
}
```

**Request Body (JWT):**
```json
{
  "name": "custom_mcp",
  "label": "Custom MCP Server",
  "type": "EXTERNAL",
  "serverUrl": "https://mcp.custom.example.com",
  "managed": true,
  "auth": {
    "authType": "JWT",
    "issuer": "https://auth.example.com",
    "subject": "service-account@example.com",
    "audience": "https://mcp.custom.example.com",
    "signingCertificate": "cert_name",
    "signingAlgorithm": "RS256"
  }
}
```

**Request Body (No Auth):**
```json
{
  "name": "public_mcp",
  "label": "Public MCP Server",
  "type": "EXTERNAL",
  "serverUrl": "https://mcp.public.example.com",
  "auth": {
    "authType": "NO_AUTH"
  }
}
```

**Response (McpServerCreateResult):**
```json
{
  "server": {
    "id": "mcp_server_id",
    "name": "github_mcp",
    "label": "GitHub MCP Server",
    "type": "EXTERNAL",
    "status": "ACTIVE",
    "serverUrl": "https://mcp.github.example.com/sse",
    "assetCount": 0,
    "createdAt": "2026-06-01T10:00:00Z"
  },
  "assets": [
    {
      "id": "create_issue",
      "name": "create_issue",
      "label": "Create Issue",
      "description": "Create a new GitHub issue",
      "kind": "MCP_TOOL",
      "storedInCore": false,
      "inputSchema": {
        "type": "object",
        "properties": {
          "repository": {"type": "string"},
          "title": {"type": "string"},
          "body": {"type": "string"}
        },
        "required": ["repository", "title"]
      },
      "outputSchema": {
        "type": "object",
        "properties": {
          "issueNumber": {"type": "integer"},
          "issueUrl": {"type": "string"}
        }
      },
      "annotations": {
        "permission_required": "write:issues",
        "rate_limit": "5000/hour"
      }
    }
  ]
}
```

**Key Behavior:** The API automatically fetches tools from the remote server and returns them in the `assets` array. No separate fetch call needed for initial registration.

### Fetch Tools from External Server (Re-Sync)

```bash
sf api request rest /api-catalog/mcp-servers/{id}/fetch \
  --method POST \
  --json \
  -o OrgAlias
```

**Response (FetchResult):**
```json
{
  "assets": [
    {
      "id": "create_issue",
      "name": "create_issue",
      "label": "Create Issue",
      "description": "Create a new GitHub issue",
      "kind": "MCP_TOOL",
      "storedInCore": true,
      "active": true,
      "serverAssetId": "asset_core_id",
      "inputSchema": {...},
      "outputSchema": {...},
      "annotations": {...}
    },
    {
      "id": "list_repos",
      "name": "list_repos",
      "label": "List Repositories",
      "kind": "MCP_TOOL",
      "storedInCore": false
    }
  ]
}
```

**Key Field:**
- `storedInCore: true` - Previously whitelisted (includes stored overrides)
- `storedInCore: false` - New tool, not yet whitelisted

**Note:** This is a stateless operation. It does not persist anything. Use `PUT /assets` to persist changes.

### Update External Server

```bash
sf api request rest /api-catalog/mcp-servers/{id} \
  --method PUT \
  --body @update-config.json \
  --json \
  -o OrgAlias
```

**Request Body:**
```json
{
  "label": "Updated Label",
  "description": "Updated description",
  "serverUrl": "https://new-url.example.com",
  "auth": {
    "authType": "OAUTH",
    "clientSecret": "new_secret"
  }
}
```

### List Connections

```bash
sf api request rest /api-catalog/mcp-servers/{id}/connections \
  --json \
  -o OrgAlias
```

**Response:**
```json
{
  "connections": [
    {
      "id": "connection_id",
      "label": "Primary Connection",
      "status": "ACTIVE",
      "slaTierId": "standard",
      "externalCredentialName": "GitHub_Cred",
      "namedCredentialId": "0XA..."
    }
  ]
}
```

### Update Connection

```bash
sf api request rest /api-catalog/mcp-servers/{id}/connections/{connectionId} \
  --method PUT \
  --body @connection-update.json \
  --json \
  -o OrgAlias
```

**Request Body:**
```json
{
  "label": "Updated Connection",
  "slaTierId": "premium",
  "externalCredentialName": "GitHub_Cred_V2"
}
```

---

## Asset Management

### List Server Assets

```bash
# List all assets
sf api request rest /api-catalog/mcp-servers/{id}/assets \
  --json \
  -o OrgAlias

# Filter by kind
sf api request rest "/api-catalog/mcp-servers/{id}/assets?kind=MCP_TOOL" \
  --json \
  -o OrgAlias

# Search by text
sf api request rest "/api-catalog/mcp-servers/{id}/assets?q=create" \
  --json \
  -o OrgAlias
```

**Response:**
```json
{
  "assets": [
    {
      "id": "asset_core_id",
      "operationId": "create_issue",
      "name": "create_github_issue",
      "label": "Create GitHub Issue",
      "description": "Creates a new issue in a GitHub repository",
      "kind": "MCP_TOOL",
      "active": true,
      "annotations": {
        "category": "github",
        "risk_level": "medium"
      },
      "createdAt": "2026-06-01T10:00:00Z",
      "updatedAt": "2026-06-01T12:00:00Z"
    }
  ]
}
```

### Replace Asset Whitelist (Atomic)

```bash
sf api request rest /api-catalog/mcp-servers/{id}/assets \
  --method PUT \
  --body @asset-whitelist.json \
  --json \
  -o OrgAlias
```

**Request Body (AssetReplaceInput):**
```json
{
  "assets": [
    {
      "operationId": "create_issue",
      "name": "create_github_issue",
      "label": "Create GitHub Issue",
      "description": "Custom description override",
      "active": true,
      "annotations": {
        "category": "github",
        "approved_by": "security_team"
      }
    },
    {
      "operationId": "list_repos",
      "name": "list_repositories",
      "active": true
    }
  ]
}
```

**Important:** This is a **replace** operation. Only assets in this array remain whitelisted. Assets not in the array are removed.

### Get Single Asset

```bash
sf api request rest /api-catalog/mcp-servers/{id}/assets/{assetId} \
  --json \
  -o OrgAlias
```

### Update Single Asset

```bash
sf api request rest /api-catalog/mcp-servers/{id}/assets/{assetId} \
  --method PUT \
  --body @asset-update.json \
  --json \
  -o OrgAlias
```

**Request Body:**
```json
{
  "name": "updated_name",
  "label": "Updated Label",
  "description": "Updated description",
  "active": false,
  "annotations": {
    "deprecated": true,
    "replacement": "new_tool_id"
  }
}
```

### Remove Single Asset

```bash
sf api request rest /api-catalog/mcp-servers/{id}/assets/{assetId} \
  --method DELETE \
  --json \
  -o OrgAlias
```

**Response:** 204 No Content

---

## Schemas

### OperationKind

```typescript
enum OperationKind {
  MCP_TOOL = "MCP_TOOL",
  MCP_RESOURCE = "MCP_RESOURCE",
  MCP_PROMPT = "MCP_PROMPT",
  SYNCHRONOUS = "SYNCHRONOUS",
  OTHER = "OTHER"
}
```

### ConnectionStatus

```typescript
enum ConnectionStatus {
  ACTIVE = "ACTIVE",
  INACTIVE = "INACTIVE",
  ERROR = "ERROR",
  PENDING = "PENDING"
}
```

### AuthType

```typescript
enum AuthType {
  OAUTH = "OAUTH",
  JWT = "JWT",
  NO_AUTH = "NO_AUTH"
}
```

### ServerAuthorization

OAuth authentication:
```typescript
{
  authType: "OAUTH",
  identityProvider: string,
  clientId: string,
  clientSecret: string,      // Write-only
  scope: string
}
```

JWT authentication:
```typescript
{
  authType: "JWT",
  issuer: string,
  subject: string,
  audience: string,
  signingCertificate: string,
  signingAlgorithm: string
}
```

No authentication:
```typescript
{
  authType: "NO_AUTH"
}
```

---

## Error Responses

### 400 Bad Request

```json
{
  "error": "VALIDATION_ERROR",
  "message": "serverUrl is required for EXTERNAL servers",
  "fields": ["serverUrl"]
}
```

### 401 Unauthorized

```json
{
  "error": "UNAUTHORIZED",
  "message": "Authentication required"
}
```

### 403 Forbidden

```json
{
  "error": "INSUFFICIENT_PERMISSIONS",
  "message": "Requires appropriate permissions per API documentation"
}
```

### 404 Not Found

```json
{
  "error": "NOT_FOUND",
  "message": "MCP server with id 'abc123' not found"
}
```

### 422 Unprocessable Entity

```json
{
  "error": "INVALID_OPERATION",
  "message": "Operation not supported for this server type"
}
```

### 502 Bad Gateway

```json
{
  "error": "UPSTREAM_ERROR",
  "message": "Failed to contact external MCP server at https://mcp.example.com",
  "details": "Connection timeout after 30s"
}
```

---

## Complete Workflows

### External Server Registration

```bash
# 1. Check for existing server (idempotency)
sf api request rest "/api-catalog/mcp-servers?label=GitHub&type=EXTERNAL" \
  --json -o MySandbox

# 2. Register server (auto-fetches tools)
sf api request rest /api-catalog/mcp-servers \
  --method POST \
  --body @github-server.json \
  --json \
  -o MySandbox

# Response includes server + discovered assets array

# 3. Review discovered tools (from step 2 response)
# ... user approves 8 out of 15 tools ...

# 4. Whitelist approved tools
sf api request rest /api-catalog/mcp-servers/abc123/assets \
  --method PUT \
  --body @approved-tools.json \
  --json \
  -o MySandbox

# 5. Verify connection status
sf api request rest /api-catalog/mcp-servers/abc123/connections \
  --json -o MySandbox
```

### Re-Sync External Server

```bash
# 1. Fetch current remote state
sf api request rest /api-catalog/mcp-servers/abc123/fetch \
  --method POST \
  --json \
  -o MySandbox

# Response shows storedInCore flag for each tool

# 2. Review changes (from step 1 response)
# - NEW: storedInCore = false
# - EXISTING: storedInCore = true  
# - REMOVED: in whitelist but not in fetch response

# 3. Update whitelist with approved changes
sf api request rest /api-catalog/mcp-servers/abc123/assets \
  --method PUT \
  --body @updated-whitelist.json \
  --json \
  -o MySandbox
```

### Update Server Credentials

```bash
# Update server auth configuration
sf api request rest /api-catalog/mcp-servers/abc123 \
  --method PUT \
  --body @new-credentials.json \
  --json \
  -o MySandbox
```

**new-credentials.json:**
```json
{
  "auth": {
    "authType": "OAUTH",
    "clientSecret": "new_secret_value"
  }
}
```

---

## Best Practices

1. **Always check for existing servers** before creating (idempotency)
2. **Never log credential fields** (`clientSecret`, tokens)
3. **Review all tool metadata** before whitelisting
4. **Use `managed: true`** for API Catalog-managed credentials when possible
5. **Test in sandbox** before production deployments
6. **Document approval decisions** in annotations
7. **Re-sync regularly** to catch new tools from external servers
8. **Verify connection status** after server updates
9. **Use atomic replace** (`PUT /assets`) for whitelist updates
10. **Audit trail** - track who approved which tools and when

---

## Authentication Examples

### OAuth with GitHub

```json
{
  "type": "EXTERNAL",
  "name": "github_mcp",
  "label": "GitHub MCP",
  "serverUrl": "https://mcp.github.example.com/sse",
  "auth": {
    "authType": "OAUTH",
    "identityProvider": "GitHub_IDP",
    "clientId": "Iv1.1234567890abcdef",
    "clientSecret": "secret_abc123",
    "scope": "read:org read:user write:issues"
  }
}
```

### JWT with Custom Service

```json
{
  "type": "EXTERNAL",
  "name": "internal_mcp",
  "label": "Internal MCP",
  "serverUrl": "https://mcp.internal.example.com",
  "managed": true,
  "auth": {
    "authType": "JWT",
    "issuer": "https://auth.internal.example.com",
    "subject": "mcp-service@example.com",
    "audience": "https://mcp.internal.example.com",
    "signingCertificate": "MCP_Cert",
    "signingAlgorithm": "RS256"
  }
}
```

### No Authentication (Public Server)

```json
{
  "type": "EXTERNAL",
  "name": "public_mcp",
  "label": "Public MCP",
  "serverUrl": "https://mcp.public.example.com",
  "auth": {
    "authType": "NO_AUTH"
  }
}
```

---

**Version**: 1.0 (External servers only)  
**Last Updated**: 2026-06-03  
**Based On**: API Catalog - MCP Servers Connect API Design Document
