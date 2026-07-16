# MCP Management Examples

Real-world examples of using the MCP management skill.

## Example 1: Register a Simple No-Auth Server

### User Request
```
Register an MCP server for me. The URL is https://af-mcp-server-242382b92d47.herokuapp.com/noauth/test/mcp, name it TestServer, and use my test1 org.
```

### Claude Workflow

1. **Verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **Create the server**
   ```bash
   sf agent mcp create \
     -n TestServer \
     --server-url https://af-mcp-server-242382b92d47.herokuapp.com/noauth/test/mcp \
     -o test1 \
     --json
   ```

3. **Extract server ID from response**
   ```json
   {
     "status": 0,
     "result": {
       "id": "0XSxx0000000001",
       "name": "TestServer",
       "status": "ACTIVE"
     }
   }
   ```

4. **Offer next steps**
   ```
   ✓ MCP server registered successfully!
   
   Server Details:
   - Name: TestServer
   - ID: 0XSxx0000000001
   - URL: https://af-mcp-server-242382b92d47.herokuapp.com/noauth/test/mcp
   - Status: ACTIVE
   - Auth Type: NO_AUTH
   
   Would you like to fetch and whitelist tools from this server now?
   ```

## Example 2: Fetch and Whitelist Tools Interactively

### User Request (continuing from Example 1)
```
Yes, let's whitelist the tools.
```

### Claude Workflow

1. **Fetch available tools**
   ```bash
   sf agent mcp fetch -i 0XSxx0000000001 -o test1 --json
   ```

2. **Display first tool**
   ```
   ═══════════════════════════════════════════════════════════
   Tool 1 of 5: McpTool__calculator_add
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
         "description": "The sum of a and b"
       }
     }
   }
   
   Annotations:
   {
     "category": "math",
     "rateLimit": "1000/minute",
     "cost": "low"
   }
   
   Current Status: INACTIVE
   ═══════════════════════════════════════════════════════════
   
   Do you want to ACTIVATE this tool? (yes/no/skip)
   ```

3. **User responds: yes**

4. **Display next tool**
   ```
   ═══════════════════════════════════════════════════════════
   Tool 2 of 5: McpTool__database_delete
   Kind: MCP_TOOL
   Description: Delete records from the database
   
   Input Schema:
   {
     "type": "object",
     "properties": {
       "table": {
         "type": "string",
         "description": "Table name"
       },
       "where": {
         "type": "string",
         "description": "SQL WHERE clause"
       }
     },
     "required": ["table"]
   }
   
   Output Schema:
   {
     "type": "object",
     "properties": {
       "rowsDeleted": {
         "type": "number"
       }
     }
   }
   
   Annotations:
   {
     "destructive": true,
     "requiresAuth": true,
     "category": "database"
   }
   
   Current Status: INACTIVE
   
   ⚠️  CAUTION: This tool has DESTRUCTIVE capabilities!
       It can delete database records.
   ═══════════════════════════════════════════════════════════
   
   Do you want to ACTIVATE this tool? (yes/no/skip)
   ```

5. **User responds: no**

6. **Continue through remaining tools...**

7. **Build and apply allowlist**
   ```bash
   # Create temp file with approved tools
   echo '{
     "assets": [
       {"name": "McpTool__calculator_add", "active": true},
       {"name": "McpTool__database_delete", "active": false},
       {"name": "McpTool__weather_get", "active": true},
       {"name": "McpTool__email_send", "active": true},
       {"name": "McpPrompt__summarize", "active": false}
     ]
   }' > /tmp/mcp-assets-1234567890.json
   
   # Apply allowlist
   sf agent mcp asset replace \
     -i 0XSxx0000000001 \
     --assets-file /tmp/mcp-assets-1234567890.json \
     -o test1 \
     --json
   
   # Clean up
   rm /tmp/mcp-assets-1234567890.json
   ```

8. **Display summary**
   ```
   ✓ Asset Allowlist Updated Successfully!
   
   Summary:
   ✓ Activated: 3 tools
     - McpTool__calculator_add
     - McpTool__weather_get
     - McpTool__email_send
   
   ✗ Deactivated: 2 tools
     - McpTool__database_delete
     - McpPrompt__summarize
   
   These tools are now available for use in Agentforce agents.
   ```

## Example 3: Register OAuth-Authenticated Server

### User Request
```
Register an MCP server with OAuth authentication.
Name: SecureAPI
URL: https://secure-api.example.com/mcp
Org: production
Identity Provider: ExternalIdP
Client ID: abc123xyz
Scope: read write execute
```

### Claude Workflow

1. **Verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **Prompt for client secret**
   ```
   I need the OAuth client secret to complete the registration.
   
   For security, I'll read it from stdin so it won't appear in your shell history.
   Please provide the client secret:
   ```

3. **User provides secret: `my-super-secret-token`**

4. **Create server with OAuth**
   ```bash
   echo "my-super-secret-token" | sf agent mcp create \
     -n SecureAPI \
     --server-url https://secure-api.example.com/mcp \
     --auth-type OAUTH \
     --identity-provider ExternalIdP \
     --client-id abc123xyz \
     --client-secret - \
     --scope "read write execute" \
     -o production \
     --json
   ```

5. **Display confirmation**
   ```
   ✓ MCP server registered successfully!
   
   Server Details:
   - Name: SecureAPI
   - ID: 0XSxx0000000456
   - URL: https://secure-api.example.com/mcp
   - Status: ACTIVE
   - Auth Type: OAUTH
   - Identity Provider: ExternalIdP
   - Client ID: abc123xyz
   - Scope: read write execute
   
   ⚠️  NOTE: You are deploying to a PRODUCTION org.
       Ensure this server has been tested in a sandbox first.
   
   Would you like to fetch and whitelist tools from this server now?
   ```

## Example 4: List All MCP Servers

### User Request
```
Show me all my MCP servers
```

### Claude Workflow

1. **Verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **List all servers**
   ```bash
   sf agent mcp list -o test1 --json
   ```

3. **Display results**
   ```
   MCP Servers (3 total):
   
   ┌─────────────────────┬─────────────┬────────────────────────────────────────┬──────────────┐
   │ Name                │ Status      │ URL                                    │ Server ID    │
   ├─────────────────────┼─────────────┼────────────────────────────────────────┼──────────────┤
   │ TestServer          │ ACTIVE      │ https://af-mcp-server.herokuapp.com/.. │ 0XSxx0000001 │
   │ SecureAPI           │ ACTIVE      │ https://secure-api.example.com/mcp     │ 0XSxx0000456 │
   │ OldServer           │ DISCONNECTED│ https://old.mcp.example.com/mcp        │ 0XSxx0000789 │
   └─────────────────────┴─────────────┴────────────────────────────────────────┴──────────────┘
   
   Actions:
   - View details: "Get details on [ServerName]"
   - Fetch tools: "Fetch tools from [ServerName]"
   - Update: "Update [ServerName]"
   - Delete: "Delete [ServerName]"
   ```

## Example 5: Update Server Configuration

### User Request
```
Update TestServer to use a new URL: https://new-domain.example.com/mcp
```

### Claude Workflow

1. **Verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **Get current server details**
   ```bash
   sf agent mcp list -o test1 --json
   ```
   *(Find server ID: 0XSxx0000000001)*

3. **Update server URL**
   ```bash
   sf agent mcp update \
     -i 0XSxx0000000001 \
     --server-url https://new-domain.example.com/mcp \
     -o test1 \
     --json
   ```

4. **Verify update**
   ```bash
   sf agent mcp get -i 0XSxx0000000001 -o test1 --json
   ```

5. **Display confirmation**
   ```
   ✓ MCP server updated successfully!
   
   Updated Server Details:
   - Name: TestServer
   - ID: 0XSxx0000000001
   - URL: https://new-domain.example.com/mcp (UPDATED)
   - Status: ACTIVE
   
   Note: You may need to re-fetch and re-whitelist tools if the server's
   capabilities have changed.
   
   Would you like to fetch fresh tools now?
   ```

## Example 6: Delete an MCP Server

### User Request
```
Delete the OldServer MCP server
```

### Claude Workflow

1. **Verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **Find server ID**
   ```bash
   sf agent mcp list -o test1 --json
   ```
   *(Match "OldServer" → ID: 0XSxx0000000789)*

3. **Get server details**
   ```bash
   sf agent mcp get -i 0XSxx0000000789 -o test1 --json
   ```

4. **Display confirmation prompt**
   ```
   ⚠️  WARNING: You are about to DELETE an MCP server.
   
   Server Details:
   - Name: OldServer
   - ID: 0XSxx0000000789
   - URL: https://old.mcp.example.com/mcp
   - Status: DISCONNECTED
   - Assets: 12 tools (5 active)
   
   This action is PERMANENT and cannot be undone.
   All whitelisted tools will be removed and unavailable to agents.
   
   Are you sure you want to delete this server? (yes/no)
   ```

5. **User confirms: yes**

6. **Delete server**
   ```bash
   sf agent mcp delete \
     -i 0XSxx0000000789 \
     -o test1 \
     --no-prompt \
     --json
   ```

7. **Display confirmation**
   ```
   ✓ MCP server deleted successfully.
   
   Deleted Server:
   - Name: OldServer
   - ID: 0XSxx0000000789
   
   All associated tools have been removed from the catalog.
   ```

## Example 7: View Asset Details

### User Request
```
Show me the whitelisted tools for TestServer
```

### Claude Workflow

1. **Verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **Find server ID**
   ```bash
   sf agent mcp list -o test1 --json
   ```
   *(Match "TestServer" → ID: 0XSxx0000000001)*

3. **List assets**
   ```bash
   sf agent mcp asset list -i 0XSxx0000000001 -o test1 --json
   ```

4. **Display results**
   ```
   Assets for TestServer (0XSxx0000000001):
   
   Active Tools (3):
   ✓ McpTool__calculator_add
     - Available as agent action
   
   ✓ McpTool__weather_get
     - Available as agent action
   
   ✓ McpTool__email_send
     - Available as agent action
   
   Inactive Assets (2):
   ✗ McpTool__database_delete (MCP_TOOL)
     - Not available to agents
   
   ✗ McpPrompt__summarize (MCP_PROMPT)
     - Not available to agents
   
   Actions:
   - Activate more tools: "Fetch tools from TestServer"
   - Deactivate tools: "Update TestServer allowlist"
   ```

## Example 8: Filter Servers by Status

### User Request
```
Show me only the disconnected MCP servers
```

### Claude Workflow

1. **Verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **List filtered servers**
   ```bash
   sf agent mcp list -o test1 --status DISCONNECTED --json
   ```

3. **Display results**
   ```
   Disconnected MCP Servers (1 total):
   
   ┌─────────────────────┬─────────────┬────────────────────────────────────────┬──────────────┐
   │ Name                │ Status      │ URL                                    │ Server ID    │
   ├─────────────────────┼─────────────┼────────────────────────────────────────┼──────────────┤
   │ OldServer           │ DISCONNECTED│ https://old.mcp.example.com/mcp        │ 0XSxx0000789 │
   └─────────────────────┴─────────────┴────────────────────────────────────────┴──────────────┘
   
   ⚠️  This server is not reachable. Common causes:
       - Server is down or offline
       - Network connectivity issues
       - Authentication failure
       - Invalid server URL
   
   Actions:
   - Check server status: "Get details on OldServer"
   - Update URL: "Update OldServer URL"
   - Remove server: "Delete OldServer"
   ```

## Example 9: Error Handling - No Target Org

### User Request
```
Register an MCP server called MyServer at https://mcp.example.com
```

### Claude Workflow

1. **Attempt to verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **Response indicates no target org**
   ```json
   {
     "status": 0,
     "result": []
   }
   ```

3. **Prompt user**
   ```
   ❌ No target org configured.
   
   Before I can register an MCP server, you need to set a target org:
   
   sf config set target-org <your-org-alias>
   
   Available orgs:
   ```
   
   ```bash
   sf org list --json
   ```
   
   ```
   Which org would you like to use?
   ```

## Example 10: Partial Approval During Whitelisting

### User Request
```
Fetch tools from TestServer but I want to skip reviewing most of them
```

### Claude Workflow

*(After displaying several tools and receiving mixed yes/no/skip responses)*

```
Tool Review Progress: 5 of 10 tools reviewed

Approved so far:
✓ McpTool__calculator_add
✓ McpTool__weather_get

Declined so far:
✗ McpTool__database_delete
✗ McpTool__file_write

Skipped so far:
─ McpTool__old_api_v1

Continuing with remaining tools...
```

*(After all tools reviewed)*

```
✓ Asset Review Complete!

Summary:
- Total tools: 10
- Reviewed: 10
- Approved: 4
- Declined: 3
- Skipped: 3 (keeping current status)

Would you like to apply these changes? (yes/no)
```

---

## Tips for Using the Skill

1. **Always have a target org set** — The skill will verify this before operations
2. **Review annotations carefully** — Look for destructive flags, auth requirements, rate limits
3. **Test in sandbox first** — Especially for OAuth servers or production deployments
4. **Keep credentials secure** — Always use stdin for client secrets
5. **Fetch before whitelisting** — Get fresh tool definitions before making allowlist changes
6. **Document your servers** — Use descriptive names and labels for easy identification
