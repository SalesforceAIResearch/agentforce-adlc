# MCP Management Reference

## Command Reference

### sf agent mcp create

**Purpose:** Register a new MCP server in the API Catalog

**Required Parameters:**
- `-n, --name <value>` — Unique server name
- `-o, --target-org <value>` — Target org alias/username
- `--server-url <value>` — MCP server endpoint URL

**Optional Parameters:**
- `--label <value>` — Human-readable display name
- `--description <value>` — Server description
- `--auth-type <OAUTH|NO_AUTH>` — Default: `NO_AUTH`
- `--identity-provider <value>` — OAuth IdP (required with `OAUTH`)
- `--client-id <value>` — OAuth client ID (required with `OAUTH`)
- `--client-secret <value>` — OAuth secret (use `-` for stdin)
- `--scope <value>` — OAuth scope (required with `OAUTH`)
- `--api-version <value>` — API version override
- `--json` — JSON output (ALWAYS use this)

**Response Structure:**
```json
{
  "status": 0,
  "result": {
    "id": "0XSxx0000000001",
    "name": "MyServer",
    "label": "My MCP Server",
    "description": "Test server",
    "type": "EXTERNAL",
    "status": "ACTIVE",
    "serverUrl": "https://mcp.example.com/mcp",
    "authType": "NO_AUTH",
    "createdDate": "2026-07-07T12:00:00.000Z",
    "lastModifiedDate": "2026-07-07T12:00:00.000Z"
  }
}
```

**Error Response:**
```json
{
  "status": 1,
  "name": "ServerCreationError",
  "message": "Failed to create MCP server: Connection refused",
  "exitCode": 1,
  "commandName": "Create"
}
```

### sf agent mcp list

**Purpose:** List all registered MCP servers

**Required Parameters:**
- `-o, --target-org <value>` — Target org

**Optional Parameters:**
- `--label <value>` — Filter by label
- `--type <EXTERNAL>` — Filter by type
- `--status <ACTIVE|DISCONNECTED>` — Filter by status
- `--json` — JSON output

**Response Structure:**
```json
{
  "status": 0,
  "result": [
    {
      "id": "0XSxx0000000001",
      "name": "Server1",
      "label": "Production Server",
      "status": "ACTIVE",
      "serverUrl": "https://prod.mcp.example.com/mcp",
      "type": "EXTERNAL"
    },
    {
      "id": "0XSxx0000000002",
      "name": "Server2",
      "label": "Test Server",
      "status": "DISCONNECTED",
      "serverUrl": "https://test.mcp.example.com/mcp",
      "type": "EXTERNAL"
    }
  ]
}
```

### sf agent mcp get

**Purpose:** Get details on a specific MCP server

**Required Parameters:**
- `-i, --mcp-server-id <value>` — Server ID
- `-o, --target-org <value>` — Target org

**Optional Parameters:**
- `--json` — JSON output

**Response Structure:**
```json
{
  "status": 0,
  "result": {
    "id": "0XSxx0000000001",
    "name": "MyServer",
    "label": "My MCP Server",
    "description": "Production MCP server for customer tools",
    "type": "EXTERNAL",
    "status": "ACTIVE",
    "serverUrl": "https://mcp.example.com/mcp",
    "authType": "OAUTH",
    "identityProvider": "MyIdp",
    "clientId": "abc123xyz",
    "scope": "read write execute",
    "createdDate": "2026-07-07T12:00:00.000Z",
    "createdBy": {
      "id": "005xx000000000001",
      "name": "John Doe"
    },
    "lastModifiedDate": "2026-07-07T14:30:00.000Z",
    "lastModifiedBy": {
      "id": "005xx000000000001",
      "name": "John Doe"
    }
  }
}
```

### sf agent mcp update

**Purpose:** Update an existing MCP server

**Required Parameters:**
- `-i, --mcp-server-id <value>` — Server ID
- `-o, --target-org <value>` — Target org
- At least one updatable field

**Optional Parameters:**
- `--label <value>` — New label
- `--description <value>` — New description
- `--server-url <value>` — New URL
- `--auth-type <OAUTH|NO_AUTH>` — New auth type
- `--identity-provider <value>` — OAuth IdP
- `--client-id <value>` — OAuth client ID
- `--client-secret <value>` — OAuth secret (use `-`)
- `--scope <value>` — OAuth scope
- `--json` — JSON output

**Response Structure:**
```json
{
  "status": 0,
  "result": {
    "id": "0XSxx0000000001",
    "name": "MyServer",
    "label": "Updated Label",
    "description": "Updated description",
    "status": "ACTIVE"
  }
}
```

### sf agent mcp delete

**Purpose:** Delete an MCP server

**Required Parameters:**
- `-i, --mcp-server-id <value>` — Server ID
- `-o, --target-org <value>` — Target org

**Optional Parameters:**
- `--no-prompt` — Skip confirmation
- `--json` — JSON output

**Response Structure:**
```json
{
  "status": 0,
  "result": {
    "id": "0XSxx0000000001",
    "name": "MyServer",
    "deleted": true
  }
}
```

### sf agent mcp fetch

**Purpose:** Fetch live assets from an MCP server

**Required Parameters:**
- `-i, --mcp-server-id <value>` — Server ID
- `-o, --target-org <value>` — Target org

**Optional Parameters:**
- `--json` — JSON output

**Response Structure:**
```json
{
  "status": 0,
  "result": {
    "serverId": "0XSxx0000000001",
    "serverName": "MyServer",
    "assets": [
      {
        "id": "0YSxx0000000001",
        "name": "McpTool__add",
        "kind": "MCP_TOOL",
        "active": false,
        "availableAsAgentAction": false,
        "description": "Add two numbers together",
        "inputSchema": {
          "type": "object",
          "properties": {
            "a": {
              "type": "number",
              "description": "First number"
            },
            "b": {
              "type": "number",
              "description": "Second number"
            }
          },
          "required": ["a", "b"]
        },
        "outputSchema": {
          "type": "object",
          "properties": {
            "result": {
              "type": "number",
              "description": "Sum of a and b"
            }
          }
        },
        "annotations": {
          "category": "math",
          "rateLimit": "100/minute"
        }
      },
      {
        "id": "0YSxx0000000002",
        "name": "McpTool__getWeather",
        "kind": "MCP_TOOL",
        "active": true,
        "availableAsAgentAction": true,
        "description": "Get current weather for a location",
        "inputSchema": {
          "type": "object",
          "properties": {
            "location": {
              "type": "string",
              "description": "City name or zip code"
            },
            "units": {
              "type": "string",
              "enum": ["celsius", "fahrenheit"],
              "default": "celsius"
            }
          },
          "required": ["location"]
        }
      },
      {
        "id": "0YSxx0000000003",
        "name": "McpPrompt__summarize",
        "kind": "MCP_PROMPT",
        "active": true,
        "description": "Summarize a long text document"
      },
      {
        "id": "0YSxx0000000004",
        "name": "McpResource__customerData",
        "kind": "MCP_RESOURCE",
        "active": false,
        "description": "Access to customer database"
      }
    ]
  }
}
```

### sf agent mcp asset list

**Purpose:** List the current asset allowlist for a server

**Required Parameters:**
- `-i, --mcp-server-id <value>` — Server ID
- `-o, --target-org <value>` — Target org

**Optional Parameters:**
- `--json` — JSON output

**Response Structure:**
```json
{
  "status": 0,
  "result": {
    "serverId": "0XSxx0000000001",
    "assets": [
      {
        "id": "0YSxx0000000001",
        "name": "McpTool__add",
        "kind": "MCP_TOOL",
        "active": true,
        "availableAsAgentAction": true
      },
      {
        "id": "0YSxx0000000002",
        "name": "McpTool__subtract",
        "kind": "MCP_TOOL",
        "active": false,
        "availableAsAgentAction": false
      }
    ]
  }
}
```

### sf agent mcp asset replace

**Purpose:** Replace the full asset allowlist for a server

**Required Parameters:**
- `-i, --mcp-server-id <value>` — Server ID
- `-o, --target-org <value>` — Target org
- Either `--assets <value>` OR `--assets-file <value>`

**Optional Parameters:**
- `--assets <value>` — JSON string or `-` for stdin
- `--assets-file <value>` — Path to JSON file
- `--json` — JSON output

**Asset Payload Format:**

Array format:
```json
[
  {
    "name": "McpTool__add",
    "active": true
  },
  {
    "name": "McpTool__subtract",
    "active": false
  }
]
```

Object format:
```json
{
  "assets": [
    {
      "name": "McpTool__add",
      "active": true
    }
  ]
}
```

**Response Structure:**
```json
{
  "status": 0,
  "result": {
    "serverId": "0XSxx0000000001",
    "assetsUpdated": 2,
    "assets": [
      {
        "name": "McpTool__add",
        "active": true
      },
      {
        "name": "McpTool__subtract",
        "active": false
      }
    ]
  }
}
```

## Asset Kinds

| Kind | Description | Use Case |
|------|-------------|----------|
| `MCP_TOOL` | Executable function/action | Agent can invoke tools to perform operations |
| `MCP_PROMPT` | Reusable prompt template | Agent can use prompts for structured generation |
| `MCP_RESOURCE` | Data source or endpoint | Agent can read resources for context |

## Authentication Types

### NO_AUTH

No authentication required. The MCP server is publicly accessible or uses a different auth mechanism (e.g., IP allowlisting, API gateway).

**Example:**
```bash
sf agent mcp create \
  -n PublicServer \
  --server-url https://public.mcp.example.com/mcp \
  --auth-type NO_AUTH \
  -o myOrg \
  --json
```

### OAUTH

OAuth 2.0 client credentials flow. Requires identity provider, client ID, client secret, and scope.

**Example:**
```bash
echo "my-secret" | sf agent mcp create \
  -n SecureServer \
  --server-url https://secure.mcp.example.com/mcp \
  --auth-type OAUTH \
  --identity-provider MyIdentityProvider \
  --client-id abc123xyz \
  --client-secret - \
  --scope "read write execute" \
  -o myOrg \
  --json
```

**OAuth Parameters:**
- `--identity-provider` — Named credential or external identity provider
- `--client-id` — OAuth client identifier
- `--client-secret` — OAuth client secret (use `-` to read from stdin)
- `--scope` — OAuth scopes (space-separated)

## Server Status

| Status | Meaning | Action |
|--------|---------|--------|
| `ACTIVE` | Server is reachable and responding | Normal operation |
| `DISCONNECTED` | Server is unreachable or not responding | Check URL, auth, network |

## Asset Activation States

| State | Meaning | Visibility |
|-------|---------|------------|
| `active: true` | Asset is whitelisted and available | Available to agents |
| `active: false` | Asset is fetched but not whitelisted | Not available to agents |
| Not in allowlist | Asset exists on server but not tracked | Not available to agents |

## Tool Metadata Fields

### Required Fields

- `name` — Tool identifier (e.g., `McpTool__add`)
- `kind` — Asset type (`MCP_TOOL`, `MCP_PROMPT`, `MCP_RESOURCE`)
- `description` — Human-readable description

### Optional Fields

- `inputSchema` — JSON Schema for tool inputs
- `outputSchema` — JSON Schema for tool outputs
- `annotations` — Additional metadata (custom fields)
  - Common annotations:
    - `category` — Tool category
    - `rateLimit` — Rate limiting info
    - `cost` — Cost per invocation
    - `latency` — Expected latency
    - `destructive` — Whether tool modifies data
    - `requiresAuth` — Additional auth requirements

## Interactive Whitelisting Flow

### Step-by-Step Process

1. **Fetch assets from server**
   ```bash
   sf agent mcp fetch -i <server-id> -o <org> --json
   ```

2. **For each asset, display:**
   ```
   ═══════════════════════════════════════════════════════════
   Tool: McpTool__add
   Kind: MCP_TOOL
   Description: Add two numbers together
   
   Input Schema:
   {
     "type": "object",
     "properties": {
       "a": {
         "type": "number",
         "description": "First number"
       },
       "b": {
         "type": "number",
         "description": "Second number"
       }
     },
     "required": ["a", "b"]
   }
   
   Output Schema:
   {
     "type": "object",
     "properties": {
       "result": {
         "type": "number",
         "description": "Sum of a and b"
       }
     }
   }
   
   Annotations:
   {
     "category": "math",
     "rateLimit": "100/minute"
   }
   
   Current Status: INACTIVE
   ═══════════════════════════════════════════════════════════
   
   Do you want to ACTIVATE this tool? (yes/no/skip)
   ```

3. **Collect user response:**
   - `yes` → Add to allowlist with `"active": true`
   - `no` → Add to allowlist with `"active": false` (explicit deactivation)
   - `skip` → Don't include in allowlist (keep current state)

4. **Build allowlist array:**
   ```json
   [
     {"name": "McpTool__add", "active": true},
     {"name": "McpTool__subtract", "active": false}
   ]
   ```

5. **Write to temp file:**
   ```bash
   # macOS/Linux
   echo '<json>' > /tmp/mcp-assets-<timestamp>.json
   
   # Windows PowerShell
   echo '<json>' > $env:TEMP\mcp-assets-<timestamp>.json
   ```

6. **Replace asset allowlist:**
   ```bash
   sf agent mcp asset replace \
     -i <server-id> \
     --assets-file /tmp/mcp-assets-<timestamp>.json \
     -o <org> \
     --json
   ```

7. **Display summary:**
   ```
   Asset Allowlist Updated:
   ✓ Activated: 3 tools
   ✗ Deactivated: 2 tools
   ─ Unchanged: 5 tools
   ```

8. **Clean up:**
   ```bash
   rm /tmp/mcp-assets-<timestamp>.json
   ```

## Security Considerations

### Client Secret Handling

**❌ NEVER do this (exposes secret in shell history):**
```bash
sf agent mcp create -n Server --server-url https://mcp.example.com --auth-type OAUTH --client-secret "my-secret" -o myOrg
```

**✅ DO THIS (stdin piping):**
```bash
echo "my-secret" | sf agent mcp create -n Server --server-url https://mcp.example.com --auth-type OAUTH --client-secret - -o myOrg
```

**✅ OR THIS (file piping):**
```bash
cat /secure/location/secret.txt | sf agent mcp create -n Server --server-url https://mcp.example.com --auth-type OAUTH --client-secret - -o myOrg
```

### Tool Review Checklist

Before activating a tool, review:

1. **Destructive operations**
   - Does it delete, update, or modify data?
   - Does it execute code or commands?
   - Does it have file system access?

2. **Data exposure**
   - Does it access sensitive data (PII, credentials)?
   - Does it query databases directly?
   - Does it have broad read permissions?

3. **Rate limits**
   - Are there rate limit annotations?
   - Could it cause DoS if overused?
   - Does it have cost implications?

4. **Authentication**
   - Does it require additional auth?
   - Does it impersonate users?
   - Does it have elevated privileges?

5. **Scope**
   - Is the tool's purpose clear?
   - Is it narrowly scoped or overly broad?
   - Does it align with agent use cases?

### Recommended Warnings

**Production org deployment:**
```
⚠️  WARNING: You are deploying to a PRODUCTION org.
    This will activate MCP tools in a live environment.
    Ensure all tools have been reviewed and tested.
    
    Continue? (yes/no)
```

**Destructive tool activation:**
```
⚠️  CAUTION: This tool has destructive capabilities.
    Tool: McpTool__deleteRecord
    Description: Delete records from the database
    
    Annotations: {"destructive": true, "scope": "all_records"}
    
    Are you sure you want to activate this tool? (yes/no)
```

**Broad permissions:**
```
⚠️  NOTICE: This tool has broad data access.
    Tool: McpResource__customerData
    Description: Access to all customer records
    
    Consider limiting scope or using field-level security.
    
    Activate anyway? (yes/no)
```

## Error Scenarios

### Server Creation Failures

**Connection refused:**
```json
{
  "status": 1,
  "name": "ConnectionError",
  "message": "Failed to connect to https://mcp.example.com/mcp: Connection refused"
}
```
**Resolution:** Verify server URL, check network connectivity, ensure server is running

**Invalid OAuth credentials:**
```json
{
  "status": 1,
  "name": "AuthenticationError",
  "message": "OAuth authentication failed: Invalid client credentials"
}
```
**Resolution:** Verify client ID, client secret, identity provider, and scope

**Duplicate name:**
```json
{
  "status": 1,
  "name": "DuplicateError",
  "message": "MCP server with name 'MyServer' already exists"
}
```
**Resolution:** Use a unique name or update the existing server

### Asset Replacement Failures

**Invalid JSON:**
```json
{
  "status": 1,
  "name": "ValidationError",
  "message": "Invalid asset payload: Expected array or object with 'assets' key"
}
```
**Resolution:** Verify JSON structure matches expected format

**Asset not found:**
```json
{
  "status": 1,
  "name": "NotFoundError",
  "message": "Asset 'McpTool__unknownTool' not found on server"
}
```
**Resolution:** Fetch fresh assets with `sf agent mcp fetch`

**Server disconnected:**
```json
{
  "status": 1,
  "name": "ServerError",
  "message": "Cannot update assets: Server is DISCONNECTED"
}
```
**Resolution:** Check server status, verify server URL and auth

## Edge Cases

### Empty Asset List

When a server has no assets:
```json
{
  "status": 0,
  "result": {
    "serverId": "0XSxx0000000001",
    "assets": []
  }
}
```

**Handling:**
```
No assets found on this MCP server.
This could mean:
- The server is not exposing any tools, prompts, or resources
- The server is newly registered and hasn't been indexed
- There was an error fetching assets

Would you like to:
1. Check server status
2. Try fetching again
3. Update server configuration
```

### All Tools Declined

If user declines/skips all tools during whitelisting:
```
All tools were declined or skipped.
No assets will be activated on this server.

Would you like to:
1. Review the tools again
2. Fetch fresh assets and retry
3. Cancel and keep current asset state
```

### Partial OAuth Configuration

If user provides some but not all OAuth parameters:
```
❌ ERROR: Incomplete OAuth configuration

Required for --auth-type OAUTH:
  --identity-provider <value>
  --client-id <value>
  --client-secret <value>
  --scope <value>

Missing:
  --client-secret

Please provide all required OAuth parameters.
```

### Server ID Ambiguity

If user refers to server by name instead of ID:
```
You specified server name "MyServer" but this command requires a server ID.

Found matching servers:
- ID: 0XSxx0000000001, Name: MyServer, Status: ACTIVE
- ID: 0XSxx0000000002, Name: MyServer_Dev, Status: ACTIVE

Which server do you want to use? (enter ID)
```

## Windows-Specific Examples

### PowerShell

**Create server with OAuth:**
```powershell
"my-secret" | sf agent mcp create `
  -n MyServer `
  --server-url https://mcp.example.com/mcp `
  --auth-type OAUTH `
  --identity-provider MyIdp `
  --client-id abc123 `
  --client-secret - `
  --scope "read write" `
  -o myOrg `
  --json
```

**Write assets to temp file:**
```powershell
$assets = @{
  assets = @(
    @{ name = "McpTool__add"; active = $true },
    @{ name = "McpTool__subtract"; active = $false }
  )
} | ConvertTo-Json -Depth 10

$assets | Out-File -FilePath "$env:TEMP\mcp-assets.json" -Encoding utf8

sf agent mcp asset replace `
  -i 0XSxx0000000001 `
  --assets-file "$env:TEMP\mcp-assets.json" `
  -o myOrg `
  --json

Remove-Item "$env:TEMP\mcp-assets.json"
```

### Command Prompt (cmd)

**Create server (no auth):**
```cmd
sf agent mcp create ^
  -n MyServer ^
  --server-url https://mcp.example.com/mcp ^
  -o myOrg ^
  --json
```

**Note:** For OAuth with client secret, use PowerShell or Git Bash for stdin piping.

## Complete Workflow Example

### Scenario: Register and whitelist a weather MCP server

```bash
# Step 1: Verify target org
$ sf config get target-org --json
{
  "result": [
    {
      "key": "target-org",
      "value": "myOrg"
    }
  ],
  "status": 0
}

# Step 2: Create the MCP server
$ sf agent mcp create \
    -n WeatherServer \
    --server-url https://weather.mcp.example.com/mcp \
    --label "Weather MCP Server" \
    --description "Provides current weather and forecasts" \
    -o myOrg \
    --json

{
  "status": 0,
  "result": {
    "id": "0XSxx0000000123",
    "name": "WeatherServer",
    "label": "Weather MCP Server",
    "status": "ACTIVE",
    "serverUrl": "https://weather.mcp.example.com/mcp"
  }
}

# Step 3: Fetch available tools
$ sf agent mcp fetch -i 0XSxx0000000123 -o myOrg --json

{
  "status": 0,
  "result": {
    "assets": [
      {
        "name": "McpTool__getCurrentWeather",
        "kind": "MCP_TOOL",
        "description": "Get current weather for a location",
        "inputSchema": {
          "type": "object",
          "properties": {
            "location": {"type": "string"}
          }
        },
        "active": false
      },
      {
        "name": "McpTool__getForecast",
        "kind": "MCP_TOOL",
        "description": "Get 7-day weather forecast",
        "inputSchema": {
          "type": "object",
          "properties": {
            "location": {"type": "string"},
            "days": {"type": "number", "default": 7}
          }
        },
        "active": false
      }
    ]
  }
}

# Step 4: Interactive review (user approves both tools)
# Tool 1: getCurrentWeather → yes (activate)
# Tool 2: getForecast → yes (activate)

# Step 5: Build allowlist
$ echo '{
  "assets": [
    {"name": "McpTool__getCurrentWeather", "active": true},
    {"name": "McpTool__getForecast", "active": true}
  ]
}' > /tmp/weather-assets.json

# Step 6: Replace asset allowlist
$ sf agent mcp asset replace \
    -i 0XSxx0000000123 \
    --assets-file /tmp/weather-assets.json \
    -o myOrg \
    --json

{
  "status": 0,
  "result": {
    "serverId": "0XSxx0000000123",
    "assetsUpdated": 2
  }
}

# Step 7: Verify activation
$ sf agent mcp asset list -i 0XSxx0000000123 -o myOrg --json

{
  "status": 0,
  "result": {
    "assets": [
      {
        "name": "McpTool__getCurrentWeather",
        "kind": "MCP_TOOL",
        "active": true,
        "availableAsAgentAction": true
      },
      {
        "name": "McpTool__getForecast",
        "kind": "MCP_TOOL",
        "active": true,
        "availableAsAgentAction": true
      }
    ]
  }
}

# Step 8: Clean up
$ rm /tmp/weather-assets.json

# SUCCESS: Weather tools are now available for Agentforce agents!
```
